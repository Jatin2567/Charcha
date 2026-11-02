"""Bounded provider-chain checks use fabricated PCM and provider doubles only."""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import socket
from types import SimpleNamespace
import wave

import pytest

from artha_mesh.config import Settings
from artha_mesh.services.usage import UsageGuard

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hindi_tamil_e2e_runner", ROOT / "scripts/check_hindi_tamil_e2e.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
ENDPOINT = "https://owned-artha-test.modal.run/v1"
SECRET = "NEVER-EXPORT-TEST-ONLY-GNANI-CREDENTIAL"


def configured(tmp_path):
    return Settings(_env_file=None, mode="demo", gnani_api_key=SECRET,
                    evon_api_key="NEVER-EXPORT-TEST-ONLY-VLLM-CREDENTIAL",
                    evon_modal_key="NEVER-EXPORT-TEST-ONLY-PROXY-KEY",
                    evon_modal_secret="NEVER-EXPORT-TEST-ONLY-PROXY-SECRET",
                    evon_base_url=ENDPOINT, evon_model=check.MODEL,
                    usage_db_path=tmp_path / "usage.sqlite3", usage_require_flow_approval=True)


class SpeechDouble:
    def __init__(self, settings, guard, failure=None):
        self.settings, self.guard, self.failure = settings, guard, failure
        self.calls, self.closed, self.input = [], False, None

    async def synthesize(self, text, language, embedding=None):
        self.calls.append(("tts", text, language, embedding))
        async with self.guard.operation({"tts_requests": 1, "tts_characters": len(text)}):
            ordinal = len([call for call in self.calls if call[0] == "tts"])
            if self.failure == "source_tts" and ordinal == 1 or self.failure == "target_tts" and ordinal == 2:
                raise RuntimeError("PRIVATE PROVIDER BODY " + SECRET)
            if self.failure == "cancelled":
                raise asyncio.CancelledError
            if self.failure == "hang":
                await asyncio.Event().wait()
            if self.failure == "empty":
                return
            if self.failure == "odd":
                yield b"x"
            elif self.failure == "zero":
                yield bytes(3200)
            elif self.failure == "oversized":
                yield b"\x01\x00" * (check.SAMPLE_RATE * 9)
            else:
                yield b"\x00\x08" * 1600

    async def transcribe(self, audio, language):
        self.calls.append(("stt", language))
        async with self.guard.operation({"stt_connections": 1, "stt_seconds": 1}, stt=True):
            self.input = await anext(audio)
            assert await anext(audio) == bytes(1024)
            if self.failure == "connection_budget":
                self.guard.reserve({"stt_seconds": 14})
                self.guard.reserve({"stt_seconds": 1})
            else:
                self.guard.reserve({"stt_seconds": 2})
            if self.failure == "stt":
                raise RuntimeError("PRIVATE STT " + SECRET)
            text = next(case[3] for case in check.CASES if case[1] == language)
            if self.failure == "long_recognition":
                text = "अ" * 501
            if self.failure == "reflected_recognition":
                text = SECRET
            yield SimpleNamespace(text=text)

    async def aclose(self):
        self.closed = True
        if self.failure == "cleanup":
            raise RuntimeError("PRIVATE CLEANUP " + SECRET)


class TranslatorDouble:
    def __init__(self, settings, guard, failure=None):
        self.settings, self.guard, self.failure = settings, guard, failure
        self.calls, self.closed = [], False

    async def translate(self, text, source, target):
        self.calls.append((text, source, target))
        async with self.guard.operation({"mt_requests": 1, "mt_characters": len(text)}):
            if self.failure == "mt":
                raise RuntimeError("PRIVATE MT " + SECRET)
            if self.failure == "long_translation":
                return "अ" * 301
            if self.failure == "reflected_translation":
                return SECRET
            return {"hi": "मुझे नीली किताब चाहिए, लाल नहीं।", "ta": "நாம் 10 மணிக்கு சந்திப்போம், 11 மணிக்கு இல்லை."}[target]

    async def aclose(self):
        self.closed = True
        if self.failure == "cleanup":
            raise RuntimeError("PRIVATE CLEANUP " + SECRET)


def harness(tmp_path, *, failure=None, approval=None, now=None):
    settings = configured(tmp_path)
    guard = UsageGuard(settings.model_copy(update={"mode": "live"}), now=now)
    flow = guard.approve_flow(purpose="live_interpretation", seconds=300,
                              budgets=dict(check.BUDGETS), **(approval or {}))
    speech = SpeechDouble(settings, check.SpeechBudget(guard), failure)
    translator = TranslatorDouble(settings, guard, failure)
    factories = []
    def speech_factory(run_settings, budget):
        factories.append("speech")
        speech.settings, speech.guard = run_settings, budget
        return speech
    def translator_factory(run_settings, budget):
        factories.append("translator")
        translator.settings, translator.guard = run_settings, budget
        return translator
    values = {"settings": settings, "guard": guard, "speech": speech, "translator": translator,
              "flow": flow, "factories": factories, "speech_factory": speech_factory,
              "translator_factory": translator_factory}
    return SimpleNamespace(**values)


async def run(tmp_path, h, **overrides):
    values = dict(endpoint=ENDPOINT, flow_id=h.flow["id"],
                  approved_plan=check.build_plan(endpoint=ENDPOINT, flow_id=h.flow["id"])["plan_sha256"],
                  output_dir=Path("work/run-01"), root=tmp_path, guard=h.guard,
                  speech_factory=h.speech_factory, translator_factory=h.translator_factory)
    values.update(overrides)
    return await check.run_check(h.settings, **values)


def test_plan_and_default_cli_never_construct_clients_or_touch_network_environment_or_ledger(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("A plan must not construct settings, clients or a network connection")
    monkeypatch.setattr(check, "_runtime", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    assert check.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["provider_calls_made"] == 0 and plan["flow_id_sha256"] is None
    assert plan["budgets"] == check.BUDGETS
    assert plan["cost_reference"]["combined_reference"] == 2.385
    assert plan["screening_mode"] == "off" and plan["voice_cloning"] is False
    assert plan["limits"]["provider_work_deadline_seconds"] < plan["limits"]["wall_seconds"] <= 240


def test_cases_match_the_existing_reviewed_standard_voice_plan():
    other_spec = importlib.util.spec_from_file_location("existing_typed_plan", ROOT / "scripts/plan_translation_test.py")
    other = importlib.util.module_from_spec(other_spec)
    other_spec.loader.exec_module(other)
    assert check.CASES == tuple(case[:4] for case in other.CASES)
    assert check.EXPECTED == {case[0]: list(case[4]) for case in other.CASES}


def test_hash_changes_with_exact_flow_endpoint_or_case_content():
    first = check.build_plan(endpoint=ENDPOINT, flow_id="00000000-0000-0000-0000-000000000001")
    assert first["plan_sha256"] != check.build_plan(endpoint="https://other.modal.run/v1", flow_id="00000000-0000-0000-0000-000000000001")["plan_sha256"]
    assert first["plan_sha256"] != check.build_plan(endpoint=ENDPOINT, flow_id="00000000-0000-0000-0000-000000000002")["plan_sha256"]
    first["cases"][0]["source_text"] = "changed"
    with pytest.raises(check.Rejected, match="exact"):
        check.authorize(first, first["plan_sha256"], {})


@pytest.mark.parametrize("endpoint", ["http://owned.modal.run/v1", "https://owned.modal.run:8443/v1",
    "https://other.example/v1", "https://key@owned.modal.run/v1", "https://owned.modal.run/v1?key=private",
    "https://owned.modal.run/v1#private", "https://owned.modal.run/", "https://modal.run/v1"])
def test_unapproved_authentication_destinations_are_rejected(endpoint):
    with pytest.raises((check.Rejected, ValueError)):
        check.build_plan(endpoint=endpoint)


async def test_two_complete_chains_use_exact_grant_standard_voices_and_private_wavs(tmp_path):
    h = harness(tmp_path)
    report = await run(tmp_path, h)
    assert report["status"] == "provider_chain_complete_meaning_review_pending"
    assert len(h.speech.calls) == 6 and len(h.translator.calls) == 2
    assert [row[0] for row in h.speech.calls] == ["tts", "stt", "tts", "tts", "stt", "tts"]
    assert all(call[3] is None for call in h.speech.calls if call[0] == "tts")
    assert h.speech.settings.audio_screening_mode == "off"
    assert h.speech.settings.usage_stt_max_retries == 0 and h.speech.settings.usage_voice_enrollments_per_day == 0
    assert h.speech.settings.timbre_voice_hi == "Nalini" and h.speech.settings.timbre_voice_ta == "Trisha"
    assert h.settings.mode == "demo" and h.settings.audio_sample_rate == 24000
    assert report["used"]["tts_requests"] == 4 and report["used"]["stt_connections"] == 2
    assert report["used"]["stt_seconds"] == 6 and report["used"]["mt_requests"] == 2
    assert report["used"]["voice_enrollments"] == 0 and report["flow_status"] == "closed"
    assert h.speech.closed and h.translator.closed
    serialized = json.dumps(report)
    assert SECRET not in serialized and str(tmp_path) not in serialized and h.flow["id"] not in serialized
    assert report["listener_latency_ms"] is None and report["rtc_tested"] is False
    assert all(row["meaning_review"] == "pending" and row["exact_source_text_match"] for row in report["cases"])
    assert all(row["stt_start_to_target_first_pcm_ms"] <= row["stt_start_to_target_complete_ms"] for row in report["cases"])
    folder = tmp_path / "work/run-01"
    assert len(list(folder.glob("*.wav"))) == 4
    for path in folder.glob("*.wav"):
        with wave.open(str(path)) as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) == (16000, 1, 2, 1600)
    assert json.loads((folder / "report.json").read_text()) == report


@pytest.mark.parametrize("failure,stage", [
    ("source_tts", "source_tts"), ("stt", "stt"), ("mt", "mt"), ("target_tts", "target_tts"),
    ("empty", "source_tts"), ("odd", "source_tts"), ("zero", "source_tts"), ("oversized", "source_tts"),
    ("long_recognition", "stt"), ("long_translation", "mt"),
    ("reflected_recognition", "stt"), ("reflected_translation", "mt"),
])
async def test_first_failure_stops_without_retries_or_following_case_and_keeps_conservative_units(tmp_path, failure, stage):
    h = harness(tmp_path, failure=failure)
    report = await run(tmp_path, h)
    assert report["status"] == "stopped_no_retry" and report["error_stage"] == stage
    assert [row["status"] for row in report["cases"]] == ["error", "unattempted"]
    assert report["used"]["tts_requests"] >= 1
    assert len(h.speech.calls) <= 3 and len(h.translator.calls) <= 1
    assert h.speech.closed and h.translator.closed and report["flow_status"] == "closed"
    saved = (tmp_path / "work/run-01/report.json").read_text()
    assert SECRET not in saved and "PRIVATE PROVIDER" not in saved


async def test_per_connection_stt_budget_blocks_sixteenth_reserved_second(tmp_path):
    h = harness(tmp_path, failure="connection_budget")
    report = await run(tmp_path, h)
    assert report["error_stage"] == "stt" and report["used"]["stt_seconds"] == 15
    assert report["used"]["stt_connections"] == 1 and report["used"]["mt_requests"] == 0


async def test_cancellation_closes_bound_flow_and_clients_and_preserves_report(tmp_path):
    h = harness(tmp_path, failure="cancelled")
    with pytest.raises(asyncio.CancelledError):
        await run(tmp_path, h)
    report = json.loads((tmp_path / "work/run-01/report.json").read_text())
    assert report["status"] == "cancelled" and report["error_stage"] == "cancelled"
    assert report["used"]["tts_requests"] == 1 and report["flow_status"] == "closed"
    assert h.speech.closed and h.translator.closed


async def test_admission_deadline_cancels_hanging_provider_and_closes_the_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "PROVIDER_WORK_SECONDS", .01)
    h = harness(tmp_path, failure="hang")
    report = await run(tmp_path, h)
    assert report["status"] == "stopped_no_retry" and report["used"]["tts_requests"] == 1
    assert report["flow_status"] == "closed" and report["wall_seconds"] < 1


async def test_cleanup_failures_cannot_become_protocol_success(tmp_path):
    h = harness(tmp_path, failure="cleanup")
    report = await run(tmp_path, h)
    assert report["status"] == "stopped_no_retry"
    assert report["cleanup_errors"] == ["speech_cleanup_incomplete", "translator_cleanup_incomplete"]
    assert report["flow_status"] == "closed"


async def test_replaced_flow_is_not_consumed_or_closed_by_the_running_old_flow(tmp_path):
    h = harness(tmp_path)
    replacement = []
    async def changed_flow(audio, language):
        h.guard.close_flow(h.flow["id"])
        replacement.append(h.guard.approve_flow(purpose="live_interpretation", seconds=300, budgets=check.BUDGETS))
        async with h.speech.guard.operation({"stt_connections": 1, "stt_seconds": 1}, stt=True):
            yield SimpleNamespace(text=check.CASES[0][3])
    h.speech.transcribe = changed_flow
    report = await run(tmp_path, h)
    assert report["status"] == "stopped_no_retry" and report["error_stage"] == "stt"
    assert report["used"]["tts_requests"] == 1 and report["used"]["stt_connections"] == 0
    new = h.guard.inspect_flow(replacement[0]["id"])
    assert new["status"] == "approved" and all(value == 0 for value in new["used"].values())


async def test_flow_close_failure_is_redacted_and_never_becomes_success(tmp_path):
    h = harness(tmp_path)
    def failed_close(*args):
        raise RuntimeError(SECRET)
    h.guard.close_flow = failed_close
    report = await run(tmp_path, h)
    assert report["status"] == "stopped_no_retry" and report["used"] is None
    assert report["cleanup_errors"] == ["flow_close_failed"] and SECRET not in json.dumps(report)


async def test_stuck_client_close_has_a_deadline_and_does_not_skip_flow_closure(tmp_path, monkeypatch):
    h = harness(tmp_path)
    monkeypatch.setattr(check, "CLOSE_SECONDS", .01)
    async def stuck():
        await asyncio.Event().wait()
    h.speech.aclose = stuck
    report = await run(tmp_path, h)
    # Allow loaded Windows CI/SQLite scheduling overhead; the close deadline is
    # 10ms and the assertions below still require closure of the exact flow.
    assert report["status"] == "stopped_no_retry" and report["wall_seconds"] < 3
    assert report["cleanup_errors"] == ["speech_cleanup_incomplete"] and report["flow_status"] == "closed"


async def test_cancellation_during_client_cleanup_is_preserved_and_propagated(tmp_path):
    h = harness(tmp_path)
    async def cancelled_close():
        raise asyncio.CancelledError
    h.speech.aclose = cancelled_close
    with pytest.raises(asyncio.CancelledError):
        await run(tmp_path, h)
    report = json.loads((tmp_path / "work/run-01/report.json").read_text())
    assert report["status"] == "cancelled" and report["error_stage"] == "cancelled"
    assert report["cleanup_errors"] == ["speech_cleanup_cancelled"] and report["flow_status"] == "closed"
    assert h.translator.closed


@pytest.mark.parametrize("change", ["purpose", "lifetime", "budget", "used", "expired"])
async def test_wrong_or_used_or_expired_grant_does_not_create_clients_output_or_close_another_flow(tmp_path, change):
    now = [datetime.now(timezone.utc)]
    h = harness(tmp_path, now=lambda: now[0])
    if change in {"purpose", "lifetime", "budget"}:
        flow = dict(h.flow)
        if change == "purpose": flow["purpose"] = "gnani_speech_check"
        if change == "lifetime": flow["expires_at"] = (now[0] + timedelta(seconds=299)).isoformat()
        if change == "budget": flow["budgets"] = {**flow["budgets"], "mt_requests": 3}
        h.guard.inspect_flow = lambda *_: flow
    elif change == "used":
        with h.guard.bind_flow(h.flow["id"]):
            h.guard.reserve({"tts_requests": 1, "tts_characters": 1})
    else:
        now[0] += timedelta(seconds=301)
    closed = []
    h.guard.close_flow = lambda *_: closed.append(True)
    with pytest.raises(check.Rejected):
        await run(tmp_path, h)
    assert h.factories == [] and closed == [] and not (tmp_path / "work/run-01").exists()


@pytest.mark.parametrize("change", ["endpoint", "model", "missing_key", "gnani_url"])
async def test_configuration_mismatch_fails_before_clients_or_grant_close(tmp_path, change):
    h = harness(tmp_path)
    updates = {"endpoint": {"evon_base_url": "https://different.modal.run/v1"}, "model": {"evon_model": "other-model"},
               "missing_key": {"evon_modal_secret": ""}, "gnani_url": {"gnani_stt_url": "wss://different.example/stream"}}[change]
    h.settings = h.settings.model_copy(update=updates)
    if change == "missing_key":
        from pydantic import SecretStr
        h.settings = h.settings.model_copy(update={"evon_modal_secret": SecretStr("")})
    with pytest.raises(check.Rejected):
        await run(tmp_path, h)
    assert h.factories == [] and h.guard.inspect_flow(h.flow["id"])["status"] == "approved"


async def test_wrong_plan_hash_and_existing_output_refuse_before_runtime_or_secret_access(tmp_path):
    h = harness(tmp_path)
    with pytest.raises(check.Rejected, match="hash"):
        await run(tmp_path, h, approved_plan="bad")
    folder = tmp_path / "work/run-01"
    folder.mkdir(parents=True)
    (folder / "keep.txt").write_text("keep")
    with pytest.raises(check.Rejected, match="new"):
        await run(tmp_path, h)
    assert h.factories == [] and (folder / "keep.txt").read_text() == "keep"
    assert h.guard.inspect_flow(h.flow["id"])["status"] == "approved"


async def test_an_injected_guard_cannot_disable_the_required_flow_budget(tmp_path):
    h = harness(tmp_path)
    h.guard.settings = h.guard.settings.model_copy(update={"usage_require_flow_approval": False})
    with pytest.raises(check.Rejected, match="guard"):
        await run(tmp_path, h)
    assert h.factories == [] and not (tmp_path / "work/run-01").exists()


@pytest.mark.parametrize("path", ["work", "outside/run", "work/../elsewhere"])
def test_output_must_stay_inside_ignored_work(tmp_path, path):
    with pytest.raises(check.Rejected):
        check.output_destination(Path(path), root=tmp_path)


def test_run_cli_missing_requirements_or_wrong_hash_does_not_load_environment(monkeypatch, capsys):
    monkeypatch.setattr(check, "_runtime", lambda: pytest.fail("No environment before complete reviewed arguments"))
    assert check.main(["--run"]) == 2
    assert check.main(["--run", "--flow-id", "00000000-0000-0000-0000-000000000001",
                       "--approve-plan", "wrong", "--output-dir", "work/never-created-by-test"]) == 2
    assert "no automatic retry" in capsys.readouterr().err


@pytest.mark.parametrize("error,expected", [(TimeoutError(SECRET), "timeout"),
    (RuntimeError(SECRET), "unexpected_error"), (ValueError(SECRET), "validation_error"),
    (OSError(SECRET), "io_error"), (asyncio.CancelledError(), "cancelled")])
def test_error_diagnostics_are_fixed_enums_not_upstream_messages_or_class_names(error, expected):
    result = check.safe_error_class(error)
    assert result == expected and SECRET not in result
