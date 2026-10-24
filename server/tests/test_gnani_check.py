"""The operator check is verified with doubles; these tests make no provider calls."""
import asyncio
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import make_wav
from pydantic import SecretStr

from artha_mesh.config import Settings
from artha_mesh.services.usage import UsageGuard

spec = importlib.util.spec_from_file_location(
    "artha_check_gnani", Path(__file__).resolve().parents[2] / "scripts" / "check_gnani.py",
)
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)


def settings(tmp_path):
    return Settings(_env_file=None, mode="demo", gnani_api_key=SecretStr("test-double-only"),
                    usage_db_path=tmp_path / "usage.sqlite3", usage_require_flow_approval=True)


def live_guard(tmp_path, now=None):
    return UsageGuard(settings(tmp_path).model_copy(update={"mode": "live"}), now=now)


def approve(guard, purpose="gnani_speech_check", **overrides):
    values = {"purpose": purpose, "seconds": 60, "budgets": check.build_plan(purpose)["budgets"]}
    values.update(overrides)
    return guard.approve_flow(**values)


class StubSpeech:
    def __init__(self, configured, guard, *, failure=None):
        self.configured = configured
        self.guard = guard
        self.failure = failure
        self.calls = []
        self.closed = False
        self.output = b"\x01\x00" * 1600
        self.input = None

    async def synthesize(self, text, language, embedding=None):
        self.calls.append("tts")
        assert text == check.PHRASE and language == "hi"
        async with self.guard.operation({"tts_requests": 1, "tts_characters": len(text)}):
            if self.failure == "tts":
                raise RuntimeError("Do not leak: api-key private-address provider-body")
            if self.failure == "cancelled":
                raise asyncio.CancelledError
            if self.failure == "too-long":
                yield b"\x01\x00" * (check.SAMPLE_RATE * 11)
            elif self.failure == "odd-pcm":
                yield b"\x01"
            else:
                yield self.output

    async def transcribe(self, audio, language):
        self.calls.append("stt")
        async with self.guard.operation({"stt_connections": 1, "stt_seconds": 1}, stt=True):
            self.input = await anext(audio)
            assert await anext(audio) == bytes(1024)
            self.guard.reserve({"stt_seconds": 2})
            if self.failure == "stt":
                raise RuntimeError("Do not leak: authorization and provider body")
            yield SimpleNamespace(text=check.PHRASE)

    async def enroll(self, clip):
        self.calls.append("enrollment")
        async with self.guard.operation({"voice_enrollments": 1}):
            if self.failure == "enrollment":
                raise RuntimeError("Do not leak private-reference and response")
            return {"embedding": "private-fake-embedding", "shape": [1, 768], "dtype": "test"}

    async def aclose(self):
        self.closed = True


def factory_capture(*, failure=None):
    instances = []

    def factory(configured, guard):
        result = StubSpeech(configured, guard, failure=failure)
        instances.append(result)
        return result

    return factory, instances


def test_default_plan_never_reads_settings_constructs_client_or_writes_ledger(monkeypatch, capsys, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Plan must not load settings, create a provider, or open a ledger")

    monkeypatch.setattr(check, "Settings", forbidden)
    monkeypatch.setattr(check, "create_speech", forbidden)
    monkeypatch.setattr(check, "UsageGuard", forbidden)
    assert check.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["budgets"] == {
        "stt_seconds": 9, "stt_connections": 1, "mt_requests": 0, "mt_characters": 0,
        "tts_requests": 1, "tts_characters": 12, "voice_enrollments": 0,
    }
    assert plan["reference_pricing"]["known_component_reference_total"] == pytest.approx(0.0999)
    assert plan["programme_credits_used"] is None
    assert plan["approval_expiry_seconds"] == 60
    assert not (tmp_path / "usage.sqlite3").exists()


def test_clone_plan_has_no_stt_and_unknown_enrollment_price():
    plan = check.build_plan("voice_clone_check")
    assert plan["budgets"] == {
        "stt_seconds": 0, "stt_connections": 0, "mt_requests": 0, "mt_characters": 0,
        "tts_requests": 1, "tts_characters": 12, "voice_enrollments": 1,
    }
    assert plan["requires_own_voice_reference"]
    assert plan["reference_pricing"]["voice_enrollment_price"] is None
    assert plan["reference_pricing"]["tts_reference_amount"] is None
    assert plan["reference_pricing"]["stt_budget_reference_amount"] is None
    assert plan["reference_pricing"]["known_component_reference_total"] is None
    assert not plan["reference_pricing"]["complete_estimate"]


def test_plan_prints_portable_ascii_json_without_settings_clients_or_ledger(monkeypatch):
    class AsciiTerminal:
        def __init__(self):
            self.parts = []

        def write(self, value):
            value.encode("ascii", errors="strict")
            self.parts.append(value)
            return len(value)

        def flush(self):
            pass

    def forbidden(*args, **kwargs):
        pytest.fail("Plan must never load settings or create a provider/ledger")

    terminal = AsciiTerminal()
    monkeypatch.setattr(check.sys, "stdout", terminal)
    monkeypatch.setattr(check, "Settings", forbidden)
    monkeypatch.setattr(check, "create_speech", forbidden)
    monkeypatch.setattr(check, "UsageGuard", forbidden)
    assert check.main(["--plan"]) == 0
    output = "".join(terminal.parts)
    assert "\\u0928" in output
    assert json.loads(output)["phrase"] == check.PHRASE


@pytest.mark.parametrize("mismatch", ["missing", "expired", "purpose", "budgets", "lifetime", "used"])
async def test_missing_expired_or_wrong_approval_never_constructs_provider_or_closes_grant(tmp_path, mismatch):
    current = [datetime(2026, 10, 24, tzinfo=UTC)]
    guard = live_guard(tmp_path, now=lambda: current[0])
    kwargs = {}
    if mismatch == "purpose":
        kwargs["purpose"] = "voice_clone_check"
    elif mismatch == "budgets":
        kwargs["budgets"] = check.build_plan()["budgets"] | {"tts_requests": 2}
    elif mismatch == "lifetime":
        kwargs["seconds"] = 120
    flow = approve(guard, **kwargs)
    if mismatch == "expired":
        current[0] += timedelta(seconds=61)
    elif mismatch == "used":
        with guard.bind_flow(flow["id"]):
            guard.reserve({"tts_requests": 1})
    factory, instances = factory_capture()
    with pytest.raises(check.CheckRejected):
        await check.run_check(settings(tmp_path), guard=guard,
                              flow_id=None if mismatch == "missing" else flow["id"],
                              speech_factory=factory, output_root=tmp_path / "checks")
    assert not instances
    assert guard.inspect_flow(flow["id"])["closed_at"] is None
    assert not (tmp_path / "checks").exists()
    guard.close()


async def test_success_reuses_fixed_tts_audio_records_actual_units_metrics_and_closes_grant(tmp_path):
    guard = live_guard(tmp_path)
    flow = approve(guard)
    factory, instances = factory_capture()
    original = settings(tmp_path)
    report = await check.run_check(original, guard=guard, flow_id=flow["id"],
                                   speech_factory=factory, output_root=tmp_path / "checks")
    assert report["success"] and report["flow_status"] == "closed"
    assert original.mode == "demo"
    speech = instances[0]
    assert speech.configured.mode == "live" and speech.configured.usage_require_flow_approval
    assert speech.configured.audio_sample_rate == 16000
    assert speech.input == speech.output and speech.calls == ["tts", "stt"] and speech.closed
    assert report["used"] == check.build_plan()["budgets"] | {"stt_seconds": 3}
    assert report["metrics"]["error_stage"] == "none"
    assert report["metrics"]["tts_audio_seconds"] == pytest.approx(0.1)
    for key in ("tts_first_pcm_ms", "tts_total_ms", "stt_final_ms"):
        assert report["metrics"][key] >= 0
    saved = json.loads((Path(report["report_directory"]) / "report.json").read_text("utf-8"))
    assert saved["synthetic_transcript"] == check.PHRASE
    assert saved["programme_credits_used"] is None
    assert "test-double-only" not in json.dumps(saved)
    assert (Path(report["report_directory"]) / "speech.wav").is_file()
    stored = guard.inspect_flow(flow["id"])
    assert stored["status"] == "closed" and stored["metrics"] == report["metrics"]
    guard.close()


@pytest.mark.parametrize("failure,stage,calls", [
    ("tts", "tts", ["tts"]), ("stt", "stt", ["tts", "stt"]),
    ("too-long", "tts", ["tts"]), ("odd-pcm", "tts", ["tts"]),
])
async def test_failed_attempt_stays_counted_closes_without_retry_or_sensitive_messages(tmp_path, failure, stage, calls):
    guard = live_guard(tmp_path)
    flow = approve(guard)
    factory, instances = factory_capture(failure=failure)
    report = await check.run_check(settings(tmp_path), guard=guard, flow_id=flow["id"],
                                   speech_factory=factory, output_root=tmp_path / "checks")
    assert not report["success"] and report["metrics"]["error_stage"] == stage
    assert instances[0].calls == calls and instances[0].closed
    assert report["used"]["tts_requests"] == 1
    assert report["used"]["tts_characters"] == 12
    assert guard.inspect_flow(flow["id"])["status"] == "closed"
    serialized = (Path(report["report_directory"]) / "report.json").read_text("utf-8")
    assert "Do not leak" not in serialized and "provider-body" not in serialized
    assert "test-double-only" not in serialized
    guard.close()


async def test_cancellation_closes_bound_flow_records_cancelled_and_never_retries(tmp_path):
    guard = live_guard(tmp_path)
    flow = approve(guard)
    factory, instances = factory_capture(failure="cancelled")
    with pytest.raises(asyncio.CancelledError):
        await check.run_check(settings(tmp_path), guard=guard, flow_id=flow["id"],
                              speech_factory=factory, output_root=tmp_path / "checks")
    stored = guard.inspect_flow(flow["id"])
    assert stored["status"] == "closed" and stored["metrics"]["error_stage"] == "cancelled"
    assert instances[0].calls == ["tts"] and instances[0].closed
    guard.close()


@pytest.mark.parametrize("reference,consent", [(None, False), ("valid", False), ("missing", True), ("invalid", True)])
async def test_clone_consent_and_file_validation_precede_provider_and_grant_binding(tmp_path, reference, consent):
    guard = live_guard(tmp_path)
    flow = approve(guard, "voice_clone_check")
    path = None
    if reference:
        path = tmp_path / "reference.wav"
        if reference == "valid":
            path.write_bytes(make_wav())
        elif reference == "invalid":
            path.write_bytes(b"bad file")
    factory, instances = factory_capture()
    with pytest.raises(check.CheckRejected):
        await check.run_check(settings(tmp_path), guard=guard, flow_id=flow["id"], purpose="voice_clone_check",
                              reference=path, consent_own_voice=consent,
                              speech_factory=factory, output_root=tmp_path / "checks")
    assert not instances and guard.inspect_flow(flow["id"])["closed_at"] is None
    guard.close()


async def test_consented_clone_uses_one_embedding_and_one_tts_without_stt_or_saved_embedding(tmp_path):
    guard = live_guard(tmp_path)
    flow = approve(guard, "voice_clone_check")
    path = tmp_path / "own-reference.wav"
    # A synthetic WAV is only a local format fixture consumed by StubSpeech.
    # The real runner never creates or sends synthetic enrollment references.
    path.write_bytes(make_wav())
    factory, instances = factory_capture()
    report = await check.run_check(settings(tmp_path), guard=guard, flow_id=flow["id"], purpose="voice_clone_check",
                                   reference=path, consent_own_voice=True,
                                   speech_factory=factory, output_root=tmp_path / "checks")
    assert report["success"] and instances[0].calls == ["enrollment", "tts"]
    assert report["used"] == check.build_plan("voice_clone_check")["budgets"]
    assert report["metrics"]["reference_seconds"] == pytest.approx(5.1)
    serialized = (Path(report["report_directory"]) / "report.json").read_text("utf-8")
    assert "private-fake-embedding" not in serialized and "speaker_embedding" not in serialized
    assert "own-reference.wav" not in serialized and "synthetic_transcript" not in report
    guard.close()


async def test_clone_enrollment_failure_stops_before_tts_and_closes_flow(tmp_path):
    guard = live_guard(tmp_path)
    flow = approve(guard, "voice_clone_check")
    path = tmp_path / "own-reference.wav"
    path.write_bytes(make_wav())
    factory, instances = factory_capture(failure="enrollment")
    report = await check.run_check(settings(tmp_path), guard=guard, flow_id=flow["id"], purpose="voice_clone_check",
                                   reference=path, consent_own_voice=True,
                                   speech_factory=factory, output_root=tmp_path / "checks")
    assert not report["success"] and report["metrics"]["error_stage"] == "enrollment"
    assert instances[0].calls == ["enrollment"]
    assert report["used"]["voice_enrollments"] == 1 and report["used"]["tts_requests"] == 0
    assert guard.inspect_flow(flow["id"])["status"] == "closed"
    guard.close()


async def test_constructor_failure_closes_bound_grant_without_upstream_error_text(tmp_path):
    guard = live_guard(tmp_path)
    flow = approve(guard)

    def broken_factory(*args):
        raise RuntimeError("secret constructor configuration")

    report = await check.run_check(settings(tmp_path), guard=guard, flow_id=flow["id"],
                                   speech_factory=broken_factory, output_root=tmp_path / "checks")
    assert not report["success"] and report["metrics"]["error_stage"] == "configuration"
    assert not any(report["used"].values())
    assert guard.inspect_flow(flow["id"])["status"] == "closed"
    assert "secret constructor" not in json.dumps(report)
    guard.close()


async def test_untrusted_endpoint_rejected_before_provider_construction_or_binding(tmp_path):
    guard = live_guard(tmp_path)
    flow = approve(guard)
    altered = settings(tmp_path).model_copy(update={"gnani_tts_url": "wss://example.invalid/tts"})
    factory, instances = factory_capture()
    with pytest.raises(check.CheckRejected):
        await check.run_check(altered, guard=guard, flow_id=flow["id"],
                              speech_factory=factory, output_root=tmp_path / "checks")
    assert not instances and guard.inspect_flow(flow["id"])["closed_at"] is None
    guard.close()


@pytest.mark.parametrize("stage", ["tts", "stt"])
async def test_deadline_stops_a_stalled_stage_without_retry_and_closes_grant(tmp_path, monkeypatch, stage):
    guard = live_guard(tmp_path)
    flow = approve(guard)
    instances = []

    class StalledSpeech(StubSpeech):
        async def synthesize(self, text, language, embedding=None):
            if stage != "tts":
                async for chunk in super().synthesize(text, language, embedding):
                    yield chunk
                return
            self.calls.append("tts")
            async with self.guard.operation({"tts_requests": 1, "tts_characters": len(text)}):
                await asyncio.Event().wait()
                yield b"unreachable"

        async def transcribe(self, audio, language):
            self.calls.append("stt")
            async with self.guard.operation({"stt_connections": 1, "stt_seconds": 1}, stt=True):
                await asyncio.Event().wait()
                yield SimpleNamespace(text="unreachable")

    def factory(configured, usage):
        speech = StalledSpeech(configured, usage)
        instances.append(speech)
        return speech

    monkeypatch.setattr(check, "TTS_TIMEOUT_SECONDS" if stage == "tts" else "STT_TIMEOUT_SECONDS", 0.01)
    report = await check.run_check(settings(tmp_path), guard=guard, flow_id=flow["id"],
                                   speech_factory=factory, output_root=tmp_path / "checks")
    assert not report["success"] and report["metrics"]["error_stage"] == stage
    assert instances[0].calls == (["tts"] if stage == "tts" else ["tts", "stt"])
    assert instances[0].closed and guard.inspect_flow(flow["id"])["status"] == "closed"
    guard.close()
