"""Follow-up uses fabricated fixed-length PCM and provider doubles only."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
from types import SimpleNamespace
import wave

import pytest

from artha_mesh.config import Settings
from artha_mesh.services.usage import UsageGuard

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ta_hi_followup_test", ROOT / "scripts/check_tamil_hindi_followup.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
ENDPOINT = "https://owned-followup.modal.run/v1"
SECRET = "NEVER-EXPORT-FOLLOWUP-TEST-CREDENTIAL"


def wav_bytes(*, rate=16000, channels=1, width=2, frames=51200, nonzero=True):
    data = io.BytesIO()
    with wave.open(data, "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(width)
        file.setframerate(rate)
        file.writeframes((b"\x01" if nonzero else b"\x00") * frames * channels * width)
    return data.getvalue()


class SpeechDouble:
    def __init__(self, settings, guard, failure=None):
        self.settings, self.guard, self.failure = settings, guard, failure
        self.calls, self.closed = [], False

    async def transcribe(self, audio, language):
        self.calls.append(("stt", language))
        assert language == "ta"
        async with self.guard.operation({"stt_connections": 1, "stt_seconds": 1}, stt=True):
            assert len(await anext(audio)) == 102400
            assert await anext(audio) == bytes(1024)
            if self.failure == "over_budget":
                self.guard.reserve({"stt_seconds": 24})
                self.guard.reserve({"stt_seconds": 1})
            else:
                self.guard.reserve({"stt_seconds": 2})
            if self.failure == "stt":
                raise RuntimeError(SECRET)
            if self.failure == "timeout":
                raise TimeoutError(SECRET)
            if self.failure == "cancelled":
                raise asyncio.CancelledError
            if self.failure == "hang":
                await asyncio.Event().wait()
            if self.failure == "empty":
                return
            text = check.SOURCE_TEXT
            if self.failure == "long_stt": text = "த" * 501
            if self.failure == "reflected_stt": text = SECRET
            yield SimpleNamespace(text=text)

    async def synthesize(self, text, language, embedding=None):
        self.calls.append(("tts", language, embedding))
        assert language == "hi" and embedding is None
        async with self.guard.operation({"tts_requests": 1, "tts_characters": len(text)}):
            if self.failure == "tts": raise RuntimeError(SECRET)
            yield b"\x00\x08" * 1600

    async def aclose(self):
        self.closed = True
        if self.failure == "cleanup": raise RuntimeError(SECRET)


class TranslatorDouble:
    def __init__(self, settings, guard, failure=None):
        self.settings, self.guard, self.failure = settings, guard, failure
        self.calls, self.closed = [], False

    async def translate(self, text, source, target):
        self.calls.append((text, source, target))
        assert (source, target) == ("ta", "hi")
        async with self.guard.operation({"mt_requests": 1, "mt_characters": len(text)}):
            if self.failure == "mt": raise RuntimeError(SECRET)
            if self.failure == "long_mt": return "अ" * 301
            if self.failure == "wrong_script": return "எனக்கு நீலப் புத்தகம் வேண்டும்"
            if self.failure == "reflected_mt": return SECRET
            return "मुझे नीली किताब चाहिए, लाल नहीं।"

    async def aclose(self):
        self.closed = True


def harness(tmp_path, monkeypatch, *, failure=None, now=None):
    work = tmp_path / "work"
    work.mkdir()
    input_path = work / "source.wav"
    data = wav_bytes()
    input_path.write_bytes(data)
    monkeypatch.setattr(check, "INPUT_SHA256", hashlib.sha256(data).hexdigest())
    settings = Settings(_env_file=None, mode="demo", gnani_api_key=SECRET,
        evon_api_key="test-vllm-auth-never-export", evon_modal_key="test-proxy-key-never-export",
        evon_modal_secret="test-proxy-secret-never-export", evon_base_url=ENDPOINT, evon_model=check.MODEL,
        usage_db_path=work / "usage.sqlite3", usage_require_flow_approval=True)
    guard = UsageGuard(settings.model_copy(update={"mode": "live"}), now=now)
    flow = guard.approve_flow(purpose="live_interpretation", seconds=180, budgets=dict(check.BUDGETS))
    speech = SpeechDouble(settings, None, failure)
    translator = TranslatorDouble(settings, guard, failure)
    factories = []
    def speech_factory(configured, budget):
        factories.append("speech")
        speech.settings, speech.guard = configured, budget
        return speech
    def translator_factory(configured, budget):
        factories.append("translator")
        translator.settings, translator.guard = configured, budget
        return translator
    return SimpleNamespace(settings=settings, guard=guard, flow=flow, speech=speech, translator=translator,
        input_path=input_path, factories=factories, speech_factory=speech_factory, translator_factory=translator_factory)


async def run(tmp_path, h, **overrides):
    values = {"endpoint": ENDPOINT, "flow_id": h.flow["id"],
        "approved_plan": check.build_plan(endpoint=ENDPOINT, flow_id=h.flow["id"])["plan_sha256"],
        "input_path": h.input_path, "output_dir": Path("work/followup-01"), "root": tmp_path,
        "guard": h.guard, "speech_factory": h.speech_factory, "translator_factory": h.translator_factory}
    values.update(overrides)
    return await check.run_check(h.settings, **values)


def test_plan_never_opens_source_or_environment_or_ledger_or_network(monkeypatch, capsys):
    def forbidden(*_a, **_k): pytest.fail("Planning performed runtime work")
    monkeypatch.setattr(check.shared, "_runtime", forbidden)
    monkeypatch.setattr(check, "read_input", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    assert check.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["input"]["sha256"] == "0c3b3c5a5e78fa824bc633cf21c12fac74f88cde0f708b98f46924dc9b987c39"
    assert plan["input"]["audio_seconds"] == 3.2
    assert plan["budgets"] == {"stt_seconds": 25, "stt_connections": 1, "mt_requests": 1,
        "mt_characters": 500, "tts_requests": 1, "tts_characters": 300, "voice_enrollments": 0}
    assert plan["grant_seconds"] == 180 and plan["limits"]["stt_recognition_deadline_seconds"] == 18
    assert plan["stt"]["requested_model"] == "prisma-v3.0" and plan["stt"]["provider_model"] is None
    assert plan["limits"]["cleanup_seconds_per_client"] == 3 and plan["limits"]["mt_output_tokens"] == 1024
    assert plan["limits"]["source_tts_requests"] == 0
    assert plan["cost_reference"]["combined_reference"] == .9975


def test_plan_hash_binds_endpoint_input_and_exact_flow(monkeypatch):
    identifier = "00000000-0000-0000-0000-000000000001"
    plan = check.build_plan(endpoint=ENDPOINT, flow_id=identifier)
    assert plan["plan_sha256"] != check.build_plan(endpoint="https://other.modal.run/v1", flow_id=identifier)["plan_sha256"]
    assert plan["plan_sha256"] != check.build_plan(endpoint=ENDPOINT, flow_id="00000000-0000-0000-0000-000000000002")["plan_sha256"]
    monkeypatch.setattr(check, "INPUT_SHA256", "f" * 64)
    assert plan["plan_sha256"] != check.build_plan(endpoint=ENDPOINT, flow_id=identifier)["plan_sha256"]


async def test_one_tamil_hindi_chain_reuses_source_and_never_runs_source_tts(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    original = h.input_path.read_bytes()
    report = await run(tmp_path, h)
    assert report["status"] == "provider_chain_complete_meaning_review_pending" and report["error_class"] is None
    assert h.speech.calls == [("stt", "ta"), ("tts", "hi", None)] and len(h.translator.calls) == 1
    assert h.speech.settings.audio_sample_rate == 16000 and h.speech.settings.audio_screening_mode == "off"
    assert h.speech.settings.usage_stt_max_retries == h.speech.settings.usage_voice_enrollments_per_day == 0
    assert h.speech.settings.timbre_voice_hi == "Nalini" and h.speech.guard.max_seconds == 25
    assert h.speech.settings.gnani_stt_model == "prisma-v3.0" and h.settings.gnani_stt_model is None
    assert report["stt"] == {"requested_model": "prisma-v3.0", "provider_model": None}
    assert h.settings.mode == "demo" and h.speech.closed and h.translator.closed
    assert report["flow_status"] == "closed" and report["used"]["stt_connections"] == 1
    assert report["used"]["mt_requests"] == report["used"]["tts_requests"] == 1
    assert report["used"]["voice_enrollments"] == report["source_tts_requests"] == 0
    assert report["listener_latency_ms"] is None and report["rtc_tested"] is False
    assert report["stt_start_to_target_first_pcm_ms"] <= report["stt_start_to_target_complete_ms"]
    assert h.input_path.read_bytes() == original
    folder = tmp_path / "work/followup-01"
    assert [path.name for path in folder.glob("*.wav")] == ["target.wav"]
    assert json.loads((folder / "report.json").read_text()) == report
    encoded = json.dumps(report)
    assert SECRET not in encoded and h.flow["id"] not in encoded and str(tmp_path) not in encoded


@pytest.mark.parametrize("failure,stage,error_class", [("stt", "stt", "unexpected_error"),
    ("timeout", "stt", "timeout"), ("empty", "stt", "validation_error"),
    ("mt", "mt", "unexpected_error"), ("tts", "target_tts", "unexpected_error"),
    ("long_stt", "stt", "validation_error"), ("long_mt", "mt", "validation_error"),
    ("wrong_script", "mt", "validation_error"), ("reflected_stt", "stt", "validation_error"),
    ("reflected_mt", "mt", "validation_error"), ("over_budget", "stt", "validation_error")])
async def test_failure_stops_exactly_once_and_closes_the_flow_without_exception_text(tmp_path, monkeypatch, failure, stage, error_class):
    h = harness(tmp_path, monkeypatch, failure=failure)
    report = await run(tmp_path, h)
    assert report["status"] == "stopped_no_retry" and report["error_stage"] == stage
    assert report["error_class"] == error_class and report["flow_status"] == "closed"
    assert len([call for call in h.speech.calls if call[0] == "stt"]) == 1
    assert len([call for call in h.speech.calls if call[0] == "tts"]) <= 1 and len(h.translator.calls) <= 1
    assert SECRET not in json.dumps(report)
    assert h.speech.closed and h.translator.closed
    if failure == "over_budget": assert report["used"]["stt_seconds"] == 25


async def test_stt_deadline_cancels_stuck_provider_and_records_safe_timeout(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch, failure="hang")
    monkeypatch.setattr(check, "STT_SECONDS", .01)
    report = await run(tmp_path, h)
    assert report["error_class"] == "timeout" and report["wall_seconds"] < 1
    assert report["flow_status"] == "closed" and h.speech.closed and h.translator.closed


async def test_final_transcript_gets_separate_bounded_close_slack(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    original = h.speech.transcribe
    closed = []
    async def closes_after_recognition_deadline(audio, language):
        try:
            async for row in original(audio, language):
                yield row
        finally:
            await asyncio.sleep(.03)
            closed.append(True)
    h.speech.transcribe = closes_after_recognition_deadline
    monkeypatch.setattr(check, "STT_SECONDS", .01)
    monkeypatch.setattr(check, "CLOSE_SECONDS", .2)
    report = await run(tmp_path, h)
    assert closed == [True] and report["status"] == "provider_chain_complete_meaning_review_pending"
    assert report["cleanup_errors"] == []


async def test_stt_final_receipt_timing_excludes_close_but_chain_waits_for_close(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    original_stream, original_translate = h.speech.transcribe, h.translator.translate
    clock = [0.0]
    monkeypatch.setattr(check.time, "perf_counter", lambda: clock[0])
    async def delayed_close(audio, language):
        try:
            async for row in original_stream(audio, language):
                yield row
        finally:
            # Simulate exactly two seconds spent closing, without a real sleep.
            clock[0] += 2
    async def after_close(*args):
        assert clock[0] == 2
        return await original_translate(*args)
    h.speech.transcribe, h.translator.translate = delayed_close, after_close
    report = await run(tmp_path, h)
    assert report["status"] == "provider_chain_complete_meaning_review_pending"
    assert report["stt_final_ms"] == 0
    assert report["stt_start_to_target_first_pcm_ms"] == 2000
    assert report["stt_start_to_target_complete_ms"] == 2000


async def test_cancellation_preserves_report_and_closes_clients_and_own_flow(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch, failure="cancelled")
    with pytest.raises(asyncio.CancelledError):
        await run(tmp_path, h)
    report = json.loads((tmp_path / "work/followup-01/report.json").read_text())
    assert report["status"] == report["error_class"] == "cancelled" and report["flow_status"] == "closed"
    assert h.speech.closed and h.translator.closed


async def test_cleanup_error_never_becomes_protocol_success(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch, failure="cleanup")
    report = await run(tmp_path, h)
    assert report["status"] == "stopped_no_retry" and report["error_class"] == "cleanup_error"
    assert report["cleanup_errors"] == ["speech_cleanup_incomplete"] and report["flow_status"] == "closed"


@pytest.mark.parametrize("change", ["purpose", "lifetime", "budget", "used", "expired"])
async def test_wrong_or_expired_or_used_grant_does_no_provider_work_or_close_other_flow(tmp_path, monkeypatch, change):
    now = [datetime.now(timezone.utc)]
    h = harness(tmp_path, monkeypatch, now=lambda: now[0])
    if change in {"purpose", "lifetime", "budget"}:
        flow = dict(h.flow)
        if change == "purpose": flow["purpose"] = "gnani_speech_check"
        if change == "lifetime": flow["expires_at"] = (now[0] + timedelta(seconds=179)).isoformat()
        if change == "budget": flow["budgets"] = {**flow["budgets"], "tts_requests": 2}
        h.guard.inspect_flow = lambda *_a: flow
    elif change == "used":
        with h.guard.bind_flow(h.flow["id"]): h.guard.reserve({"tts_requests": 1, "tts_characters": 1})
    else:
        now[0] += timedelta(seconds=181)
    closed = []
    h.guard.close_flow = lambda *_a: closed.append(True)
    with pytest.raises(check.Rejected): await run(tmp_path, h)
    assert h.factories == [] and closed == [] and not (tmp_path / "work/followup-01").exists()


@pytest.mark.parametrize("format", [{"rate": 8000}, {"channels": 2}, {"width": 1},
    {"frames": 51199}, {"nonzero": False}])
def test_even_hash_matching_audio_with_wrong_format_or_duration_is_rejected(tmp_path, monkeypatch, format):
    work = tmp_path / "work"
    work.mkdir()
    path = work / "source.wav"
    data = wav_bytes(**format)
    path.write_bytes(data)
    monkeypatch.setattr(check, "INPUT_SHA256", hashlib.sha256(data).hexdigest())
    with pytest.raises(check.Rejected): check.read_input(path, root=tmp_path)


async def test_changed_input_or_existing_output_or_wrong_hash_never_creates_clients(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    with pytest.raises(check.Rejected): await run(tmp_path, h, approved_plan="wrong")
    original = h.input_path.read_bytes()
    h.input_path.write_bytes(original[:-1] + b"\xff")
    with pytest.raises(check.Rejected): await run(tmp_path, h)
    h.input_path.write_bytes(original)
    folder = tmp_path / "work/followup-01"
    folder.mkdir()
    (folder / "keep.txt").write_text("keep")
    with pytest.raises(check.Rejected): await run(tmp_path, h)
    assert h.factories == [] and (folder / "keep.txt").read_text() == "keep"
    assert h.guard.inspect_flow(h.flow["id"])["status"] == "approved"


def test_run_with_missing_requirements_never_loads_environment(monkeypatch, capsys):
    monkeypatch.setattr(check.shared, "_runtime", lambda: pytest.fail("Environment loaded"))
    assert check.main(["--run"]) == 2
    assert "No automatic retry" in capsys.readouterr().err
