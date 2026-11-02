"""Offline matrix/gate tests use fabricated observations, never physical claims."""
from copy import deepcopy
from array import array
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import wave

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("latency_language_workflow_test", ROOT / "scripts/plan_latency_language_workflow.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def observation(index=0, *, source="hi", target="ta", delay_ms=1500, **changes):
    # Test-only operator assertions. This deliberately does not prove real audio.
    end = 16000 * (index + 10)
    start = end + round(delay_ms * 16)
    row = {"schema_version": 1, "record_type": "speech_end_playback_observation",
        "observation_id": hashlib.sha256(f"fixture-{source}-{target}-{index}".encode()).hexdigest(),
        "recording_sha256": hashlib.sha256(b"FABRICATED-TEST-ONLY-NOT-A-RECORDING").hexdigest(),
        "source_speech_end_sample": end, "listener_audio_start_sample": start, "sample_rate_hz": 16000,
        "clock": "single_recording_sample_index", "boundary": "source_speech_end_to_listener_output",
        "provider_kind": "live", "capture_kind": "acoustic_two_channel", "capture_attested": True,
        "source_language": source, "target_language": target, "condition": "warm_route", "status": "complete",
        "latency_ms": (start - end) * 1000 / 16000, "meaning_reviewed": True, "annotations_reviewed": True,
        "voice_mode": "standard", "voice_cloning": False, "screening_mode": "off"}
    row.update(changes)
    return row


def observations(**changes):
    return [observation(index, **changes) for index in range(10)]


def test_exact_current_catalog_ninety_pairs_ten_optional_routes_and_forty_drafts():
    plan = check.build_plan()
    from artha_mesh.voice_catalog import TIMBRE_V25_STOCK_VOICES
    assert {row["code"]: row["standard_voice"] for row in plan["languages"]} == TIMBRE_V25_STOCK_VOICES
    assert plan["language_count"] == 10 and plan["planned_directed_pairs"] == 90
    pairs = {(row["source_language"], row["target_language"]) for row in plan["routes"]}
    assert len(pairs) == 90 and pairs == {(s, t) for s in TIMBRE_V25_STOCK_VOICES for t in TIMBRE_V25_STOCK_VOICES if s != t}
    assert plan["optional_same_language_routes"] == len(plan["same_language_routes"]) == 10
    assert all(row["source_language"] == row["target_language"] and not row["self_output"] for row in plan["same_language_routes"])
    assert plan["draft_case_count"] == len(plan["draft_cases"]) == 40
    for code in TIMBRE_V25_STOCK_VOICES:
        drafts = [row for row in plan["draft_cases"] if row["source_language"] == code]
        assert {row["category"] for row in drafts} == {"ordinary", "negation", "names", "numbers"}
        assert all(row["source_reference_status"] == "draft_pending_fluent_review" for row in drafts)
        assert all(row["meaning_acceptance"] == "pending" and row["target_reference"] is None for row in drafts)
        assert all(row["source_characters"] == len(row["source_text"]) for row in drafts)
    assert "or" not in {row["code"] for row in plan["languages"]}


def test_initial_gate_keeps_first_optimization_available_for_review_but_no_approval_or_matrix():
    plan = check.build_plan()
    assert plan["plan_only"] and plan["provider_calls_made"] == 0
    assert not plan["approval_granted"] and not plan["automatic_matrix_runner"] and not plan["full_matrix_authorized"]
    assert not plan["full_matrix_eligible_for_test_review"]
    eligible = [row["route_id"] for row in plan["routes"] if row["eligible_for_test_review"]]
    assert eligible == ["hi-ta"]
    assert all(not row["passed"] for row in plan["gates"].values())
    assert all(row["metrics"]["p50_ms"] is None for row in plan["gates"].values())
    assert all(not row["approval_granted"] and not row["automatic_execution"] for row in plan["routes"])


def test_gate_accepts_ten_distinct_reviewed_live_physical_attempts_only_for_next_review():
    gate = check.evaluate_gate(observations(), "hi", "ta")
    assert gate["passed"] and gate["reason_codes"] == []
    assert gate["counts"]["warm_attempts"] == gate["counts"]["warm_complete"] == gate["counts"]["warm_qualifying"] == 10
    assert gate["metrics"]["p50_ms"] == gate["metrics"]["p95_ms"] == 1500
    assert gate["metrics"]["warm_failure_rate"] == 0 and not gate["approval_granted"]
    plan = check.build_plan(observations())
    assert plan["sequence"][1]["eligible_for_test_review"] and not plan["sequence"][2]["eligible_for_test_review"]
    assert not plan["full_matrix_eligible_for_test_review"] and not plan["full_matrix_authorized"]
    both = check.build_plan(observations() + observations(source="ta", target="hi"))
    assert both["full_matrix_eligible_for_test_review"] and not both["full_matrix_authorized"]
    assert all(row["eligible_for_test_review"] and not row["approval_granted"] for row in both["routes"])


@pytest.mark.parametrize("capture", ["acoustic_single_channel", "acoustic_two_channel", "electrical_loopback_two_channel"])
def test_only_physical_or_electrical_shared_recording_capture_can_qualify(capture):
    assert check.evaluate_gate(observations(capture_kind=capture), "hi", "ta")["passed"]


@pytest.mark.parametrize("change,reason", [({"capture_attested": False}, "capture_attestation_required"),
    ({"annotations_reviewed": False}, "annotation_review_pending"),
    ({"meaning_reviewed": False}, "meaning_review_pending"),
    ({"provider_kind": "double"}, "live_provider_required")])
def test_one_phone_capture_preserves_live_provider_attestation_and_review_gates(change, reason):
    rows = observations(capture_kind="acoustic_single_channel", recording_channels=1,
                        source_channel_index=0, listener_channel_index=0)
    rows[-1].update(change)
    gate = check.evaluate_gate(rows, "hi", "ta")
    assert not gate["passed"] and reason in gate["reason_codes"]


def test_one_phone_negative_overlap_is_preserved_and_cannot_pass():
    rows = observations(capture_kind="acoustic_single_channel")
    rows[-1] = observation(9, capture_kind="acoustic_single_channel", delay_ms=-100)
    gate = check.evaluate_gate(rows, "hi", "ta")
    assert not gate["passed"] and gate["observed_warm_latency_ms"][-1] == -100
    assert "overlap_requires_review" in gate["reason_codes"]


def test_mono_analyzer_schema_keeps_free_hardware_rehearsal_outside_live_acceptance(tmp_path):
    spec = importlib.util.spec_from_file_location("mono_gate_analyzer_integration", ROOT / "scripts/measure_speech_end_playback.py")
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    rate = 16000
    pcm = array("h", [0]) * (rate * 21)
    for index in range(10):
        end = (index * 2 + 1) * rate
        start = end + rate // 2
        pcm[end-rate//50:end] = array("h", [4000]) * (rate // 50)
        pcm[start:start+rate//50] = array("h", [-5000]) * (rate // 50)
    if sys.byteorder != "little": pcm.byteswap()
    path = tmp_path / "FABRICATED-mono-not-human-or-provider.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(pcm.tobytes())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = []
    for index in range(10):
        end = (index * 2 + 1) * rate
        rows.append(analyzer.analyze(path, {"recording_sha256": digest,
            "trial_id": f"synthetic-rehearsal-{index}", "source_language": "hi", "target_language": "ta",
            "condition": "warm_route", "provider_kind": "double", "capture_kind": "acoustic_single_channel",
            "voice_mode": "standard", "status": "complete", "source_speech_end_sample": end,
            "listener_audio_start_sample": end + rate // 2, "capture_attested": True,
            "annotations_reviewed": True, "meaning_reviewed": True}))
    assert len({row["observation_id"] for row in rows}) == 10
    assert all(row["latency_ms"] == 500 and row["recording_channels"] == 1 for row in rows)
    assert all(row["source_channel_index"] == row["listener_channel_index"] == 0 for row in rows)
    gate = check.evaluate_gate(rows, "hi", "ta")
    assert not gate["passed"] and "live_provider_required" in gate["reason_codes"]
    assert gate["counts"]["warm_attempts"] == 10 and gate["counts"]["duplicate_observations"] == 0
    assert gate["observed_warm_latency_ms"] == [500] * 10


@pytest.mark.parametrize("change,reason", [
    ({"record_type": "speech_end_latency_evidence"}, "measurement_contract_not_eligible"),
    ({"clock": "single_process_monotonic"}, "shared_recording_boundary_required"),
    ({"boundary": "source_end_to_first_decoded_rtc"}, "shared_recording_boundary_required"),
    ({"provider_kind": "double"}, "live_provider_required"),
    ({"capture_kind": "browser_render_dual_channel"}, "physical_or_electrical_capture_required"),
    ({"capture_kind": "decoded_rtc"}, "physical_or_electrical_capture_required"),
    ({"capture_kind": []}, "physical_or_electrical_capture_required"),
    ({"capture_attested": False}, "capture_attestation_required"),
    ({"meaning_reviewed": False}, "meaning_review_pending"),
    ({"annotations_reviewed": False}, "annotation_review_pending"),
    ({"meaning_reviewed": 1}, "meaning_review_pending"),
    ({"voice_mode": "cloned"}, "standard_voice_stage_required"),
    ({"voice_cloning": True}, "standard_voice_stage_required"),
    ({"screening_mode": "monitor"}, "standard_voice_stage_required"),
    ({"observation_id": "not-an-id"}, "observation_identity_required"),
    ({"recording_sha256": "not-a-hash"}, "observation_identity_required"),
    ({"source_speech_end_sample": True}, "invalid_sample_clock_measurement"),
    ({"listener_audio_start_sample": None}, "invalid_sample_clock_measurement"),
    ({"sample_rate_hz": 0}, "invalid_sample_clock_measurement"),
    ({"latency_ms": float("nan")}, "invalid_sample_clock_measurement"),
    ({"latency_ms": 1}, "latency_sample_indices_disagree"),
])
def test_single_unqualified_warm_attempt_blocks_even_nine_good_attempts(change, reason):
    rows = observations()
    rows[-1].update(change)
    result = check.evaluate_gate(rows, "hi", "ta")
    assert not result["passed"] and reason in result["reason_codes"]


def test_cold_result_cannot_replace_tenth_warm_attempt_and_is_kept_separate():
    rows = observations()[:9] + [observation(20, condition="first_route", delay_ms=1900)]
    gate = check.evaluate_gate(rows, "hi", "ta")
    assert not gate["passed"] and gate["counts"]["warm_attempts"] == 9
    assert gate["counts"]["first_route_attempts"] == 1 and gate["metrics"]["first_route_ms"] == 1900


@pytest.mark.parametrize("status", ["error", "timeout", "cancelled"])
def test_failed_attempts_cannot_disappear_from_success_only_latency_stats(status):
    rows = observations() + [observation(20, status=status)]
    gate = check.evaluate_gate(rows, "hi", "ta")
    assert not gate["passed"] and gate["counts"]["warm_attempts"] == 11
    assert gate["counts"]["warm_complete"] == 10 and gate["counts"]["warm_failures"] == 1
    assert gate["metrics"]["warm_failure_rate"] == 1 / 11


def test_under_two_seconds_is_strict_and_p95_catches_one_slow_attempt_in_ten():
    rows = observations()
    rows[-1] = observation(9, delay_ms=2000)
    gate = check.evaluate_gate(rows, "hi", "ta")
    assert not gate["passed"] and gate["metrics"]["p50_ms"] == 1500 and gate["metrics"]["p95_ms"] == 2000
    assert "p95_not_strictly_under_goal" in gate["reason_codes"]
    assert not check.evaluate_gate(observations(delay_ms=2000), "hi", "ta")["passed"]


def test_negative_latency_is_preserved_signed_and_ineligible_for_final_turn_gate():
    rows = observations()
    rows[-1] = observation(9, delay_ms=-100)
    gate = check.evaluate_gate(rows, "hi", "ta")
    assert not gate["passed"] and gate["observed_warm_latency_ms"][-1] == -100
    assert gate["counts"]["overlap_observations"] == 1 and "overlap_requires_review" in gate["reason_codes"]


def test_duplicate_id_or_recording_end_cannot_multiply_one_attempt_into_ten():
    copied = [deepcopy(observation()) for _ in range(10)]
    assert "duplicate_observation" in check.evaluate_gate(copied, "hi", "ta")["reason_codes"]
    disguised = observations()
    disguised[-1]["source_speech_end_sample"] = disguised[0]["source_speech_end_sample"]
    disguised[-1]["listener_audio_start_sample"] = disguised[0]["listener_audio_start_sample"]
    gate = check.evaluate_gate(disguised, "hi", "ta")
    assert not gate["passed"] and gate["counts"]["duplicate_observations"] == 2


def test_several_utterances_in_one_recording_are_distinct_when_end_indices_differ():
    rows = observations()
    assert len({row["recording_sha256"] for row in rows}) == 1
    assert check.evaluate_gate(rows, "hi", "ta")["passed"]


def test_fresh_plans_have_independent_policy_and_stable_hashes():
    original = check.build_plan()
    assert original["plan_sha256"] == check.content_hash({key: value for key, value in original.items() if key != "plan_sha256"})
    changed = check.build_plan()
    changed["gate_policy"]["capture_kinds"].append("unreviewed")
    changed["draft_cases"][0]["expected_meaning"].append("private change")
    assert check.build_plan() == original


def test_default_plan_never_reads_environment_or_ledger_or_constructs_network(monkeypatch, capsys):
    def forbidden(*_a, **_k): pytest.fail("Offline workflow attempted runtime work")
    class NoEnvironment(dict):
        __getitem__ = get = __iter__ = forbidden
    with monkeypatch.context() as context:
        context.setattr(os, "environ", NoEnvironment())
        context.setattr(socket, "socket", forbidden)
        context.setattr(sqlite3, "connect", forbidden)
        assert check.main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["provider_calls_made"] == 0 and not output["full_matrix_authorized"]


def test_evidence_loader_reads_one_or_many_observations_without_exporting_paths(tmp_path):
    one, rest = tmp_path / "one.json", tmp_path / "rest.json"
    rows = observations()
    one.write_text(json.dumps(rows[0]))
    rest.write_text(json.dumps(rows[1:]))
    assert check.load_observations([one, rest]) == rows
    assert str(tmp_path) not in json.dumps(check.build_plan(rows))


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]' + b'x' * 1_048_576],
                         ids=["duplicate", "nonfinite", "oversized"])
def test_evidence_loader_rejects_ambiguous_nonfinite_or_oversized_input(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError): check.load_observations([path])


@pytest.mark.parametrize("flag", ["--run", "--approve", "--renew"])
def test_cli_offers_no_execution_or_approval_action(flag, capsys):
    assert check.main([flag]) == 2
    assert "no run, approval or renewal" in capsys.readouterr().err
