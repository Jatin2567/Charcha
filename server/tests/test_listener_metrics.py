import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from charcha.config import Settings
from charcha.models import Participant
from charcha.services.listener_metrics import ListenerMetrics, MAX_PROBE_SAMPLES, ProbeReport
from charcha.store import Store


class Clock:
    value = 100.0

    def __call__(self):
        return self.value


@pytest.fixture
def probes(monkeypatch):
    clock = Clock()
    monkeypatch.setattr("charcha.services.listener_metrics.time.monotonic", clock)
    store = Store(Settings(mode="transport", _env_file=None))
    state = store.create_room("Local audio timing")
    listener = Participant(name="Private listener name", language="hi")
    second = Participant(name="Second person", language="ta")
    state.room.participants.extend([listener, second])
    token = store.issue_session(state, listener.id)
    second_token = store.issue_session(state, second.id)
    return ListenerMetrics(store), state, token, second_token, clock


def test_probe_has_exact_listener_track_and_single_monotonic_measurement(probes):
    metrics, state, token, _, clock = probes
    challenge = metrics.issue(token, state.room.code)
    assert challenge["track_name"] == f"probe:{challenge['probe_id']}:{state.room.participants[0].id}"
    assert challenge["expires_in_ms"] == 30000
    metrics.start(token, state.room.code, challenge["probe_id"])
    clock.value += 0.5
    row = metrics.record(token, state.room.code, ProbeReport(
        probe_id=challenge["probe_id"], elapsed_ms=350.2,
    ))
    assert row["elapsed_ms"] == 350.2
    assert row["server_start_to_report_ms"] == 500
    # Server interval is separate; it must not be subtracted from browser time.
    snapshot = metrics.snapshot(state.room.code)
    assert snapshot["summary"]["p50_ms"] == 350.2
    assert snapshot["measurement"]["translation_end_to_end_measured"] is False
    assert snapshot["measurement"]["physical_speaker_output_measured"] is False
    assert snapshot["measurement"]["client_reported"] is True
    encoded = json.dumps(snapshot)
    assert "Private listener name" not in encoded
    assert token not in encoded


def test_membership_and_exact_probe_owner_are_required(probes):
    metrics, state, token, other_token, _ = probes
    challenge = metrics.issue(token, state.room.code)
    with pytest.raises(HTTPException) as error:
        metrics.start(other_token, state.room.code, challenge["probe_id"])
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        metrics.start(token, "another-room", challenge["probe_id"])
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        metrics.issue("invalid", state.room.code)
    assert error.value.status_code == 401
    metrics.start(token, state.room.code, challenge["probe_id"])
    with pytest.raises(HTTPException) as error:
        metrics.record(other_token, state.room.code, ProbeReport(
            probe_id=challenge["probe_id"], elapsed_ms=100,
        ))
    assert error.value.status_code == 403


def test_unstarted_repeated_start_and_replayed_report_are_rejected(probes):
    metrics, state, token, _, _ = probes
    challenge = metrics.issue(token, state.room.code)
    report = ProbeReport(probe_id=challenge["probe_id"], elapsed_ms=100)
    with pytest.raises(HTTPException) as error:
        metrics.record(token, state.room.code, report)
    assert error.value.status_code == 409
    metrics.start(token, state.room.code, challenge["probe_id"])
    with pytest.raises(HTTPException) as error:
        metrics.start(token, state.room.code, challenge["probe_id"])
    assert error.value.status_code == 409
    metrics.record(token, state.room.code, report)
    with pytest.raises(HTTPException) as error:
        metrics.record(token, state.room.code, report)
    assert error.value.status_code == 404
    assert metrics.snapshot(state.room.code)["summary"]["sample_count"] == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0, 30001, True, "123"])
def test_invalid_client_intervals_do_not_enter_report(value):
    with pytest.raises(ValidationError):
        ProbeReport(probe_id="a" * 24, elapsed_ms=value)


@pytest.mark.parametrize("changes", [
    {"output_enabled": False},
    {"elapsed_ms": None},
    {"status": "cancelled", "elapsed_ms": 100},
    {"poll_interval_ms": float("nan")},
    {"poll_interval_ms": 0},
    {"listener_id": "forged-listener"},
])
def test_inconsistent_detection_or_extra_identity_fields_are_rejected(changes):
    payload = {"probe_id": "a" * 24, "elapsed_ms": 100}
    payload.update(changes)
    with pytest.raises(ValidationError):
        ProbeReport(**payload)


def test_expired_pending_and_inactive_members_cannot_report(probes):
    metrics, state, token, second_token, clock = probes
    expired = metrics.issue(token, state.room.code)
    metrics.start(token, state.room.code, expired["probe_id"])
    clock.value += 31
    with pytest.raises(HTTPException) as error:
        metrics.record(token, state.room.code, ProbeReport(probe_id=expired["probe_id"], elapsed_ms=50))
    assert error.value.status_code == 404
    snapshot = metrics.snapshot(state.room.code)
    assert snapshot["summary"]["failed_count"] == 1
    assert snapshot["summary"]["p95_ms"] is None
    challenge = metrics.issue(second_token, state.room.code)
    metrics.start(second_token, state.room.code, challenge["probe_id"])
    metrics.store.forget_session(second_token)
    with pytest.raises(HTTPException) as error:
        metrics.record(second_token, state.room.code, ProbeReport(probe_id=challenge["probe_id"], elapsed_ms=50))
    assert error.value.status_code == 401
    metrics.snapshot(state.room.code)
    assert challenge["probe_id"] not in metrics.pending


def test_active_limit_and_rate_limit_bound_probe_creation(probes):
    metrics, state, token, _, _ = probes
    metrics.issue(token, state.room.code)
    metrics.issue(token, state.room.code)
    with pytest.raises(HTTPException) as error:
        metrics.issue(token, state.room.code)
    assert error.value.status_code == 429
    assert len(metrics.pending) == 2


def test_retention_and_percentiles_exclude_timeout_and_cancellation(probes):
    metrics, state, token, _, clock = probes
    for index in range(MAX_PROBE_SAMPLES + 3):
        clock.value += 61  # Independent permitted test, not a real sleep.
        challenge = metrics.issue(token, state.room.code)
        metrics.start(token, state.room.code, challenge["probe_id"])
        metrics.record(token, state.room.code, ProbeReport(
            probe_id=challenge["probe_id"], elapsed_ms=100 + index,
        ))
    snapshot = metrics.snapshot(state.room.code)
    assert len(snapshot["samples"]) == MAX_PROBE_SAMPLES
    assert snapshot["samples"][0]["elapsed_ms"] == 103
    for status in ["timeout", "cancelled"]:
        clock.value += 61
        challenge = metrics.issue(token, state.room.code)
        metrics.start(token, state.room.code, challenge["probe_id"])
        metrics.record(token, state.room.code, ProbeReport(probe_id=challenge["probe_id"], status=status))
    snapshot = metrics.snapshot(state.room.code)
    assert snapshot["summary"]["detected_count"] == MAX_PROBE_SAMPLES - 2
    assert snapshot["summary"]["failed_count"] == snapshot["summary"]["cancelled_count"] == 1
    assert snapshot["summary"]["p95_ms"] is not None
    metrics.close_room(state.room.code)
    assert not metrics.samples and not metrics.pending


def test_demo_probes_are_not_reported_as_real_audio(probes):
    metrics, state, token, _, _ = probes
    state.room.mode = "demo"
    with pytest.raises(HTTPException) as error:
        metrics.issue(token, state.room.code)
    assert error.value.status_code == 409


def test_room_expiry_cleans_all_retained_probe_data(probes):
    metrics, state, token, _, _ = probes
    challenge = metrics.issue(token, state.room.code)
    metrics.start(token, state.room.code, challenge["probe_id"])
    metrics.record(token, state.room.code, ProbeReport(probe_id=challenge["probe_id"], elapsed_ms=100))
    metrics.issue(token, state.room.code)
    state.expires_at = 0
    metrics._prune()
    assert not metrics.pending and not metrics.samples


def test_server_delivery_error_is_recorded_without_overwriting_a_completed_detection(probes):
    metrics, state, token, _, _ = probes
    failed = metrics.issue(token, state.room.code)
    metrics.start(token, state.room.code, failed["probe_id"])
    metrics.fail("wrong-room", failed["probe_id"])
    assert failed["probe_id"] in metrics.pending
    metrics.fail(state.room.code, failed["probe_id"])
    snapshot = metrics.snapshot(state.room.code)
    assert snapshot["samples"][0]["status"] == "delivery_error"
    assert snapshot["summary"]["failed_count"] == 1
    assert snapshot["summary"]["p50_ms"] is None
    complete = metrics.issue(token, state.room.code)
    metrics.start(token, state.room.code, complete["probe_id"])
    metrics.record(token, state.room.code, ProbeReport(probe_id=complete["probe_id"], elapsed_ms=150))
    metrics.fail(state.room.code, complete["probe_id"])
    snapshot = metrics.snapshot(state.room.code)
    assert len(snapshot["samples"]) == 2
    assert snapshot["samples"][-1]["status"] == "detected"
