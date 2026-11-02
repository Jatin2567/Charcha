"""Plan/run one explicitly approved Hindi–Tamil standard-voice provider chain.

Default planning imports no application settings, environment, client or ledger.
Execution is controlled source TTS -> STT -> Evon -> target TTS, not RTC or
physical microphone/listener testing. This tool never grants itself permission.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import aclosing, asynccontextmanager
from datetime import datetime, timezone
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID
import wave

ROOT = Path(__file__).resolve().parents[1]
_prompt_spec = importlib.util.spec_from_file_location("hi_ta_pure_prompt", ROOT / "server/artha_mesh/providers/translation_prompt.py")
_prompt = importlib.util.module_from_spec(_prompt_spec)
_prompt_spec.loader.exec_module(_prompt)
MODEL = "gnani/gnani-evon-v3.3-30B-A3B"
RESOURCE_KEYS = ("stt_seconds", "stt_connections", "mt_requests", "mt_characters",
                 "tts_requests", "tts_characters", "voice_enrollments")
BUDGETS = dict(zip(RESOURCE_KEYS, (30, 2, 2, 1000, 4, 800, 0), strict=True))
CASES = (
    ("hi-ta-meeting-time", "hi", "ta", "हम 10 बजे मिलेंगे, 11 बजे नहीं।"),
    ("ta-hi-book-colour", "ta", "hi", "எனக்கு நீலப் புத்தகம் வேண்டும், சிவப்பு வேண்டாம்."),
)
OFFICIAL_STT = "wss://api.vachana.ai/stt/v3/stream"
OFFICIAL_TTS = "wss://api.vachana.ai/api/v1/tts"
VOICES = {"hi": "Nalini", "ta": "Trisha"}
EXPECTED = {
    "hi-ta-meeting-time": ["Meet at 10", "11 is explicitly rejected", "No invented date or time zone"],
    "ta-hi-book-colour": ["The speaker wants the blue book", "Red is explicitly rejected", "Keep the request's meaning"],
}
SAMPLE_RATE = 16000
GRANT_SECONDS = 300
WALL_SECONDS = 240
PROVIDER_WORK_SECONDS = 230
TTS_SECONDS = 30
MT_SECONDS = 30
STT_SECONDS = 12  # Leaves up to three seconds of close-handshake slack.
CLOSE_SECONDS = 3
SOURCE_AUDIO_SECONDS = 8
TARGET_AUDIO_SECONDS = 15


class Rejected(Exception):
    """Fixed safe local validation failures; provider exceptions are not exported."""


def safe_error_class(error: BaseException) -> str:
    """Return a fixed enum, never an upstream message or arbitrary class name."""
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (Rejected, ValueError)):
        return "validation_error"
    if type(error).__name__ == "ProviderError":
        return "provider_error"
    if isinstance(error, OSError):
        return "io_error"
    return "unexpected_error"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def endpoint_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".modal.run")
            or not parsed.hostname.removesuffix(".modal.run") or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") != "/v1"):
        raise Rejected("Use the exact approved HTTPS Modal /v1 endpoint without credentials or query values.")
    return value.rstrip("/")


def build_plan(*, endpoint: str = "https://replace-with-approved-host.modal.run/v1",
               flow_id: str | None = None) -> dict:
    endpoint = endpoint_url(endpoint)
    if flow_id is not None and str(UUID(flow_id)) != flow_id:
        raise Rejected("Use the exact operator flow UUID.")
    plan = {
        "schema_version": 1, "record_type": "hindi_tamil_provider_chain_plan", "plan_only": True,
        "provider_calls_made": 0, "purpose": "live_interpretation", "grant_seconds": GRANT_SECONDS,
        "budgets": dict(BUDGETS), "model": MODEL,
        "prompt_version": _prompt.PROMPT_VERSION,
        "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(),
        "flow_id_sha256": hashlib.sha256(flow_id.encode()).hexdigest() if flow_id else None,
        "cases": [{"case_id": identifier, "source_language": source, "target_language": target,
                   "source_text": text, "expected_meaning": EXPECTED[identifier],
                   "source_voice": VOICES[source], "target_voice": VOICES[target]}
                  for identifier, source, target, text in CASES],
        "voice_model": "timbre-v2.5", "voice_mode": "standard", "voice_cloning": False,
        "screening_mode": "off", "automatic_retries": 0,
        "limits": {"wall_seconds": WALL_SECONDS, "provider_work_deadline_seconds": PROVIDER_WORK_SECONDS,
                   "tts_stage_seconds": TTS_SECONDS,
                   "mt_stage_seconds": MT_SECONDS, "stt_recognition_deadline_seconds": STT_SECONDS,
                   "mt_output_tokens_per_request": 1024,
                   "stt_reserved_seconds_per_connection": 15, "cleanup_seconds": CLOSE_SECONDS,
                   "source_audio_max_seconds": SOURCE_AUDIO_SECONDS, "target_audio_max_seconds": TARGET_AUDIO_SECONDS,
                   "recognized_characters_per_case": 500, "target_characters_per_case": 300},
        "cost_reference": {"currency": "INR", "stt_per_hour": 27, "tts_per_10000_characters": 27,
                           "maximum_stt_reference": .225, "maximum_tts_reference": 2.16,
                           "combined_reference": 2.385, "actual_charge": None,
                           "programme_credit_conversion": None,
                           "note": "Owner-supplied rates. Reservations/deadlines are not a provider invoice; rounding, taxes and cancellation/close timing remain unverified. Modal GPU compute is separate."},
        "measurement": "Controlled-source preparation is separate from STT-final, MT-complete and target-TTS-first-PCM timings; no RTC or physical-listener measurement.",
        "deadline_policy": "Provider work has a 230-second admission deadline, followed by at most three seconds of asynchronous cleanup per client. Cancellation is cooperative; synchronous local file/ledger work is not a hard operating-system timeout.",
        "source_provenance": "Two deliberately generated stock-voice utterances, not human microphone samples or cloned references.",
        "meaning_review": "Human bilingual review is required even after the protocol completes.",
    }
    plan["plan_sha256"] = digest(plan)
    return plan


def authorize(plan: dict, approved_hash: str | None, flow: dict) -> None:
    if digest({key: value for key, value in plan.items() if key != "plan_sha256"}) != plan.get("plan_sha256") or approved_hash != plan["plan_sha256"]:
        raise Rejected("Review and approve the exact endpoint-and-flow-bound plan before execution.")
    try:
        lifetime = (datetime.fromisoformat(flow["expires_at"]) - datetime.fromisoformat(flow["started_at"])).total_seconds()
        valid = (flow["status"] == "approved" and flow["purpose"] == plan["purpose"]
                 and flow["budgets"] == BUDGETS and lifetime == GRANT_SECONDS
                 and hashlib.sha256(flow["id"].encode()).hexdigest() == plan["flow_id_sha256"]
                 and set(flow["used"]) == set(RESOURCE_KEYS)
                 and all(type(value) is int and value == 0 for value in flow["used"].values()))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise Rejected("The exact active, unused 300-second live_interpretation grant is required.")


def output_destination(path: Path, *, root: Path = ROOT) -> Path:
    root, work = root.resolve(), root.resolve() / "work"
    candidate = path if path.is_absolute() else root / path
    if ".." in path.parts or not candidate.is_relative_to(work) or candidate == work or candidate.exists():
        raise Rejected("Choose a new output directory strictly inside work/.")
    for part in (candidate, *candidate.parents):
        if part.is_relative_to(work) and (part.is_symlink() or bool(getattr(part, "is_junction", lambda: False)())):
            raise Rejected("Linked output directories are not supported.")
    if not candidate.resolve().is_relative_to(work.resolve()):
        raise Rejected("Output escapes the local work directory.")
    return candidate


def write_private(path: Path, data: bytes):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)


def save_wav(path: Path, pcm: bytes):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    write_private(path, output.getvalue())


def _runtime():
    sys.path.insert(0, str(ROOT / "server"))
    from artha_mesh.config import Settings
    from artha_mesh.services.usage import UsageGuard
    from artha_mesh.providers.gnani import GnaniSpeech
    from artha_mesh.providers.evon import EvonTranslator
    return Settings, UsageGuard, GnaniSpeech, EvonTranslator


class SpeechBudget:
    """Default 15-second connection cap; reviewed single-flow callers may use up to 25."""
    def __init__(self, guard, *, max_seconds: int = 15):
        if type(max_seconds) is not int or not 1 <= max_seconds <= 25:
            raise Rejected("Use a reviewed per-connection STT cap of at most 25 seconds.")
        self.guard, self.seconds, self.active = guard, 0, False
        self.max_seconds = max_seconds

    @asynccontextmanager
    async def operation(self, units, *, stt=False):
        if stt:
            if units.get("stt_seconds", 0) > self.max_seconds:
                raise Rejected("Per-connection STT reservation limit reached.")
            self.seconds, self.active = units.get("stt_seconds", 0), True
        try:
            async with self.guard.operation(units, stt=stt):
                yield
        finally:
            if stt:
                self.active = False

    def reserve(self, units):
        seconds = units.get("stt_seconds", 0)
        if seconds and (not self.active or self.seconds + seconds > self.max_seconds):
            raise Rejected("Per-connection STT reservation limit reached.")
        result = self.guard.reserve(units)
        self.seconds += seconds
        return result


async def audio_with_silence(pcm):
    yield pcm
    while True:
        yield bytes(1024)


async def synthesize(speech, text, language, *, maximum_seconds: int):
    if not isinstance(text, str) or not text.strip() or len(text) > 300:
        raise Rejected("Synthesis text exceeds the reviewed per-case cap.")
    started, first, chunks, size = time.perf_counter(), None, [], 0
    async with asyncio.timeout(TTS_SECONDS), aclosing(speech.synthesize(text, language, None)) as stream:
        async for chunk in stream:
            if not isinstance(chunk, bytes) or len(chunk) % 2:
                raise Rejected("Synthesis did not return bounded PCM16 audio.")
            if chunk:
                first = first if first is not None else (time.perf_counter() - started) * 1000
                size += len(chunk)
                if size > maximum_seconds * SAMPLE_RATE * 2:
                    raise Rejected("Synthesis audio exceeded the reviewed duration.")
                chunks.append(chunk)
    if not size:
        raise Rejected("Synthesis returned no audio.")
    pcm = b"".join(chunks)
    if not any(pcm):
        raise Rejected("Synthesis returned only zero-valued audio.")
    return pcm, {"first_pcm_ms": round(first, 3), "complete_ms": round((time.perf_counter() - started) * 1000, 3), "audio_seconds": size / (SAMPLE_RATE * 2)}


def safe_text(value: object, secrets: list[str], *, maximum: int) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(secret and secret in value for secret in secrets)):
        raise Rejected("Provider text did not satisfy the reviewed output contract.")
    return value.strip()


async def run_check(settings, *, endpoint: str, flow_id: str, approved_plan: str,
                    output_dir: Path, guard=None, speech_factory=None, translator_factory=None,
                    root: Path = ROOT) -> dict:
    plan = build_plan(endpoint=endpoint, flow_id=flow_id)
    folder = output_destination(output_dir, root=root)
    if approved_plan != plan["plan_sha256"]:
        raise Rejected("Review the exact endpoint-and-flow-bound plan hash.")
    endpoint = endpoint_url(endpoint)
    secrets = [getattr(settings, key).get_secret_value() for key in ("gnani_api_key", "evon_api_key", "evon_modal_key", "evon_modal_secret")]
    if (not all(secrets) or "replace" in endpoint.lower()
            or settings.gnani_stt_url != OFFICIAL_STT or settings.gnani_tts_url != OFFICIAL_TTS
            or endpoint_url(settings.evon_base_url) != endpoint or settings.evon_model != MODEL):
        raise Rejected("Configure the approved Modal endpoint/model, both authentication layers and official Gnani speech endpoints.")
    configured = settings.model_copy(update={"mode": "live", "usage_require_flow_approval": True,
        "audio_sample_rate": SAMPLE_RATE, "audio_screening_mode": "off", "local_audio_lab_enabled": False,
        "usage_stt_max_retries": 0, "usage_voice_enrollments_per_day": 0,
        "provider_timeout_seconds": 30, "timbre_model": "timbre-v2.5", "timbre_voice": "Nalini",
        "timbre_voice_hi": "Nalini", "timbre_voice_ta": "Trisha"})
    owned_guard = guard is None
    if guard is None or speech_factory is None or translator_factory is None:
        _, guard_class, speech_class, translator_class = _runtime()
        guard = guard or guard_class(configured)
        speech_factory, translator_factory = speech_factory or speech_class, translator_factory or translator_class
    if guard.settings.mode != "live" or guard.settings.usage_require_flow_approval is not True:
        raise Rejected("The supplied guard must enforce live operator-flow approval.")
    report = {"schema_version": 1, "record_type": "hindi_tamil_provider_chain_result", "plan": plan,
              "created_at": datetime.now(timezone.utc).isoformat(), "status": "not_started",
              "cases": [{"case_id": identifier, "source_language": source, "target_language": target,
                         "source_text": text, "status": "unattempted", "meaning_review": "pending"}
                        for identifier, source, target, text in CASES],
              "error_stage": None, "error_class": None, "used": None, "programme_credits_used": None,
              "actual_provider_charge_inr": None, "actual_modal_charge_usd": None,
              "meaning_review": "pending_human_bilingual_review", "listener_latency_ms": None,
              "rtc_tested": False, "physical_microphone_tested": False, "voice_cloning": False,
              "screening_mode": "off", "automatic_retries": 0, "cleanup_errors": [],
              "latency_boundary": "Source stock-TTS preparation reported separately. Timed provider chain starts immediately before STT and ends at first/complete target PCM, without RTC or physical playback."}
    speech = translator = None
    cancelled, stage = False, "approval"
    started = time.perf_counter()
    try:
        authorize(plan, approved_plan, guard.inspect_flow(flow_id))
        with guard.bind_flow(flow_id):
            try:
                stage = "configuration"
                folder.mkdir(parents=True, mode=0o700)
                speech = speech_factory(configured, SpeechBudget(guard))
                translator = translator_factory(configured, guard)
                async with asyncio.timeout(PROVIDER_WORK_SECONDS):
                    for index, (identifier, source, target, text) in enumerate(CASES, 1):
                        case = report["cases"][index - 1]
                        case["status"] = "incomplete"
                        stage = "source_tts"
                        pcm, case["source_preparation"] = await synthesize(speech, text, source, maximum_seconds=SOURCE_AUDIO_SECONDS)
                        save_wav(folder / f"source-{index}.wav", pcm)
                        chain_started = time.perf_counter()
                        stage, recognized = "stt", None
                        async with asyncio.timeout(STT_SECONDS), aclosing(speech.transcribe(audio_with_silence(pcm), source)) as stream:
                            async for result in stream:
                                recognized = safe_text(result.text, secrets, maximum=500)
                                if recognized:
                                    break
                        if not recognized:
                            raise Rejected("Recognition returned no final transcript.")
                        case.update(recognized_text=recognized, stt_final_ms=round((time.perf_counter() - chain_started) * 1000, 3),
                                    exact_source_text_match=recognized == text)
                        stage, mt_started = "mt", time.perf_counter()
                        async with asyncio.timeout(MT_SECONDS):
                            translated = safe_text(await translator.translate(recognized, source, target), secrets, maximum=300)
                        case.update(translated_text=translated, mt_complete_ms=round((time.perf_counter() - mt_started) * 1000, 3))
                        stage, target_started = "target_tts", time.perf_counter()
                        target_pcm, synthesis = await synthesize(speech, translated, target, maximum_seconds=TARGET_AUDIO_SECONDS)
                        case.update(target_synthesis=synthesis,
                                    stt_start_to_target_first_pcm_ms=round((target_started - chain_started) * 1000 + synthesis["first_pcm_ms"], 3),
                                    stt_start_to_target_complete_ms=round((time.perf_counter() - chain_started) * 1000, 3))
                        save_wav(folder / f"target-{index}.wav", target_pcm)
                        case["status"] = "provider_chain_complete_meaning_review_pending"
                report["status"] = "provider_chain_complete_meaning_review_pending"
                stage = None
            except asyncio.CancelledError:
                cancelled = True
                report["error_class"] = "cancelled"
                report["status"], stage = "cancelled", "cancelled"
            except Exception as error:
                report["error_class"] = safe_error_class(error)
                report["status"] = "stopped_no_retry"
            finally:
                report["error_stage"] = stage
                for case in report["cases"]:
                    if case["status"] == "incomplete":
                        case["status"] = "cancelled" if cancelled else "error"
                        case["error_class"] = report["error_class"]
                for label, client in (("speech", speech), ("translator", translator)):
                    if client is not None:
                        try:
                            await asyncio.wait_for(client.aclose(), CLOSE_SECONDS)
                        except asyncio.CancelledError:
                            cancelled = True
                            report["error_class"] = "cancelled"
                            report["error_stage"] = "cancelled"
                            report["cleanup_errors"].append(label + "_cleanup_cancelled")
                        except BaseException:
                            report["error_class"] = report["error_class"] or "cleanup_error"
                            report["cleanup_errors"].append(label + "_cleanup_incomplete")
                try:
                    flow = guard.close_flow(flow_id)
                    report["used"], report["flow_status"] = flow["used"], flow["status"]
                    report["programme_credits_used"] = flow.get("credits_used")
                except Exception:
                    report["error_class"] = report["error_class"] or "flow_close_error"
                    report["cleanup_errors"].append("flow_close_failed")
                    report["status"] = "stopped_no_retry"
        report["wall_seconds"] = round(time.perf_counter() - started, 3)
        if cancelled:
            report["status"] = "cancelled"
        elif report["cleanup_errors"]:
            report["status"] = "stopped_no_retry"
        if folder.is_dir():
            write_private(folder / "report.json", json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False).encode())
        if cancelled:
            raise asyncio.CancelledError
        return report
    finally:
        if owned_guard:
            guard.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--plan", action="store_true")
    actions.add_argument("--run", action="store_true")
    parser.add_argument("--endpoint", default="https://replace-with-approved-host.modal.run/v1")
    parser.add_argument("--flow-id")
    parser.add_argument("--approve-plan")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        plan = build_plan(endpoint=args.endpoint, flow_id=args.flow_id)
        if not args.run:
            print(json.dumps(plan, ensure_ascii=True, indent=2))
            return 0
        if not args.flow_id or not args.approve_plan or not args.output_dir:
            raise Rejected("Run requires an existing exact flow ID, approved plan hash and new work output directory.")
        output_destination(args.output_dir)
        if args.approve_plan != plan["plan_sha256"]:
            raise Rejected("Review the exact endpoint-and-flow-bound plan hash.")
        settings_class, *_ = _runtime()
        result = asyncio.run(run_check(settings_class(), endpoint=args.endpoint, flow_id=args.flow_id,
                                       approved_plan=args.approve_plan, output_dir=args.output_dir))
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return 0 if result["status"] == "provider_chain_complete_meaning_review_pending" else 1
    except (Exception, KeyboardInterrupt):
        print("The bounded test could not run or stopped. Review configuration, the exact existing grant and local report; no automatic retry was made.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
