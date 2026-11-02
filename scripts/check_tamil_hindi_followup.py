"""Offline-first, single Tamil-to-Hindi follow-up using one fixed existing WAV.

This script never approves a flow. Execution needs an unused exact 180-second
operator grant and endpoint/input/flow-bound plan hash. No source TTS, cloning,
screening or automatic retries. Default planning reads no settings or ledger.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
from uuid import UUID
import wave

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("followup_pure_speech_helpers", ROOT / "scripts/check_hindi_tamil_e2e.py")
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)
Rejected = shared.Rejected
MODEL = shared.MODEL
BUDGETS = dict(zip(shared.RESOURCE_KEYS, (25, 1, 1, 500, 1, 300, 0), strict=True))
GRANT_SECONDS = 180
STT_SECONDS = 18
PROVIDER_WORK_SECONDS = 110
WALL_SECONDS = 120
CLOSE_SECONDS = 3
INPUT_SHA256 = "0c3b3c5a5e78fa824bc633cf21c12fac74f88cde0f708b98f46924dc9b987c39"
INPUT_FRAMES = 51200
DEFAULT_INPUT = ROOT / "work/modal-stage-01/hindi-tamil-speech/source-2.wav"
SOURCE_TEXT = shared.CASES[1][3]
STT_MODEL = "prisma-v3.0"


def build_plan(*, endpoint: str = "https://replace-with-approved-host.modal.run/v1", flow_id: str | None = None) -> dict:
    endpoint = shared.endpoint_url(endpoint)
    if flow_id is not None and str(UUID(flow_id)) != flow_id:
        raise Rejected("Use the exact operator flow UUID.")
    plan = {"schema_version": 1, "record_type": "tamil_hindi_followup_plan", "plan_only": True,
            "provider_calls_made": 0, "purpose": "live_interpretation", "grant_seconds": GRANT_SECONDS,
            "budgets": dict(BUDGETS), "model": MODEL, "prompt_version": shared._prompt.PROMPT_VERSION,
            "stt": {"requested_model": STT_MODEL, "provider_model": None,
                    "selection": "WebSocket upgrade model header", "language": "ta-IN"},
            "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(),
            "flow_id_sha256": hashlib.sha256(flow_id.encode()).hexdigest() if flow_id else None,
            "input": {"sha256": INPUT_SHA256, "sample_rate": 16000, "channels": 1,
                      "sample_width_bytes": 2, "frames": INPUT_FRAMES, "audio_seconds": 3.2,
                      "provenance": "Existing standard-voice Trisha source-2.wav; no new source TTS."},
            "case": {"case_id": "ta-hi-book-colour-followup", "source_language": "ta", "target_language": "hi",
                     "source_text": SOURCE_TEXT, "expected_meaning": shared.EXPECTED["ta-hi-book-colour"]},
            "voice_model": "timbre-v2.5", "target_voice": "Nalini", "voice_mode": "standard",
            "voice_cloning": False, "screening_mode": "off", "automatic_retries": 0,
            "limits": {"wall_seconds": WALL_SECONDS, "provider_work_deadline_seconds": PROVIDER_WORK_SECONDS,
                       "stt_recognition_deadline_seconds": STT_SECONDS, "stt_reserved_seconds_per_connection": 25,
                       "cleanup_seconds_per_client": CLOSE_SECONDS, "recognized_characters": 500,
                       "mt_requests": 1, "mt_output_tokens": 1024, "mt_stage_seconds": 30,
                       "target_tts_requests": 1, "target_tts_characters": 300,
                       "target_audio_max_seconds": 15, "tts_stage_seconds": 30, "source_tts_requests": 0},
            "cost_reference": {"currency": "INR", "stt_per_hour": 27, "tts_per_10000_characters": 27,
                               "maximum_stt_reference": .1875, "maximum_tts_reference": .81,
                               "combined_reference": .9975, "actual_charge": None,
                               "programme_credit_conversion": None,
                               "note": "Reference units only; provider rounding/taxes unverified. Modal compute is separate."},
            "measurement": "STT start to first/complete target PCM; no RTC or physical listener playback.",
            "meaning_acceptance": "Human bilingual review remains required; protocol completion is not accuracy.",
            "deadline_policy": "110-second cooperative provider-work deadline, then up to three seconds cleanup per client; no OS-level hard termination."}
    plan["plan_sha256"] = shared.digest(plan)
    return plan


def read_input(path: Path, *, root: Path = ROOT) -> bytes:
    work = root.resolve() / "work"
    candidate = path if path.is_absolute() else root.resolve() / path
    if (".." in path.parts or not candidate.is_relative_to(work) or candidate.suffix.lower() != ".wav"
            or not candidate.resolve().is_relative_to(work.resolve())):
        raise Rejected("Use the fixed source WAV inside ignored work.")
    for part in (candidate, *candidate.parents):
        if part.is_relative_to(work) and (part.is_symlink() or bool(getattr(part, "is_junction", lambda: False)())):
            raise Rejected("Linked input files are not supported.")
    if not candidate.is_file() or candidate.stat().st_size > INPUT_FRAMES * 2 + 4096:
        raise Rejected("The fixed source WAV is missing or invalid.")
    data = candidate.read_bytes()
    if hashlib.sha256(data).hexdigest() != INPUT_SHA256:
        raise Rejected("The source WAV differs from the reviewed input hash.")
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes(), audio.getcomptype()) != (1, 2, 16000, INPUT_FRAMES, "NONE"):
                raise Rejected("Use the reviewed 3.2-second mono PCM16 WAV at 16 kHz.")
            pcm = audio.readframes(INPUT_FRAMES + 1)
    except (wave.Error, EOFError):
        raise Rejected("The fixed source WAV is invalid.") from None
    if len(pcm) != INPUT_FRAMES * 2 or not any(pcm):
        raise Rejected("The source WAV must contain all reviewed nonempty PCM frames.")
    return pcm


def authorize(plan: dict, approved_hash: str | None, flow: dict) -> None:
    if (shared.digest({key: value for key, value in plan.items() if key != "plan_sha256"}) != plan.get("plan_sha256")
            or approved_hash != plan["plan_sha256"]):
        raise Rejected("Review the exact endpoint, input and flow-bound plan hash.")
    try:
        lifetime = (datetime.fromisoformat(flow["expires_at"]) - datetime.fromisoformat(flow["started_at"])).total_seconds()
        valid = (flow["status"] == "approved" and flow["purpose"] == plan["purpose"]
                 and flow["budgets"] == BUDGETS and lifetime == GRANT_SECONDS
                 and hashlib.sha256(flow["id"].encode()).hexdigest() == plan["flow_id_sha256"]
                 and set(flow["used"]) == set(shared.RESOURCE_KEYS)
                 and all(type(value) is int and value == 0 for value in flow["used"].values()))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise Rejected("The exact unused active 180-second live_interpretation grant is required.")


async def run_check(settings, *, endpoint: str, flow_id: str, approved_plan: str,
                    input_path: Path, output_dir: Path, guard=None, speech_factory=None,
                    translator_factory=None, root: Path = ROOT) -> dict:
    plan = build_plan(endpoint=endpoint, flow_id=flow_id)
    folder = shared.output_destination(output_dir, root=root)
    if approved_plan != plan["plan_sha256"]:
        raise Rejected("Review the exact endpoint, input and flow-bound plan hash.")
    pcm = read_input(input_path, root=root)
    secrets = [getattr(settings, key).get_secret_value() for key in ("gnani_api_key", "evon_api_key", "evon_modal_key", "evon_modal_secret")]
    endpoint = shared.endpoint_url(endpoint)
    if (not all(secrets) or "replace" in endpoint.lower()
            or settings.gnani_stt_url != shared.OFFICIAL_STT or settings.gnani_tts_url != shared.OFFICIAL_TTS
            or shared.endpoint_url(settings.evon_base_url) != endpoint or settings.evon_model != MODEL):
        raise Rejected("Configure the reviewed Modal model, both authentication layers and official speech endpoints.")
    configured = settings.model_copy(update={"mode": "live", "usage_require_flow_approval": True,
        "audio_sample_rate": 16000, "audio_screening_mode": "off", "local_audio_lab_enabled": False,
        "gnani_stt_model": STT_MODEL,
        "usage_stt_max_retries": 0, "usage_voice_enrollments_per_day": 0, "provider_timeout_seconds": 30,
        "timbre_model": "timbre-v2.5", "timbre_voice": "Nalini", "timbre_voice_hi": "Nalini"})
    owned_guard = guard is None
    if guard is None or speech_factory is None or translator_factory is None:
        _, guard_class, speech_class, translator_class = shared._runtime()
        guard = guard or guard_class(configured)
        speech_factory = speech_factory or speech_class
        translator_factory = translator_factory or translator_class
    if guard.settings.mode != "live" or guard.settings.usage_require_flow_approval is not True:
        raise Rejected("The guard must enforce live operator-flow approval.")
    report = {"schema_version": 1, "record_type": "tamil_hindi_followup_result", "plan": plan,
        "created_at": datetime.now(timezone.utc).isoformat(), "status": "not_started",
        "error_stage": None, "error_class": None, "used": None, "flow_status": None,
        "programme_credits_used": None, "actual_provider_charge_inr": None, "actual_modal_charge_usd": None,
        "meaning_review": "pending_human_bilingual_review", "listener_latency_ms": None,
        "rtc_tested": False, "physical_microphone_tested": False, "voice_cloning": False,
        "screening_mode": "off", "automatic_retries": 0, "cleanup_errors": [], "source_tts_requests": 0}
    report["stt"] = {"requested_model": STT_MODEL, "provider_model": None}
    speech = translator = None
    cancelled, stage = False, "approval"
    started = time.perf_counter()
    try:
        authorize(plan, approved_plan, guard.inspect_flow(flow_id))
        with guard.bind_flow(flow_id):
            try:
                stage = "configuration"
                folder.mkdir(parents=True, mode=0o700)
                speech = speech_factory(configured, shared.SpeechBudget(guard, max_seconds=25))
                translator = translator_factory(configured, guard)
                async with asyncio.timeout(PROVIDER_WORK_SECONDS):
                    stage, recognized, recognized_at = "stt", None, None
                    chain_started = time.perf_counter()
                    stream = speech.transcribe(shared.audio_with_silence(pcm), "ta")
                    recognition_error = None
                    try:
                        async with asyncio.timeout(STT_SECONDS):
                            async for row in stream:
                                recognized = shared.safe_text(row.text, secrets, maximum=500)
                                if recognized:
                                    recognized_at = time.perf_counter()
                                    break
                    except BaseException as error:
                        recognition_error = error
                        raise
                    finally:
                        try:
                            await asyncio.wait_for(stream.aclose(), CLOSE_SECONDS)
                        except BaseException:
                            report["cleanup_errors"].append("stt_stream_cleanup_incomplete")
                            if recognition_error is None:
                                raise
                    if not recognized:
                        raise Rejected("Recognition returned no final transcript.")
                    report.update(recognized_text=recognized, stt_final_ms=round((recognized_at - chain_started) * 1000, 3),
                                  exact_source_text_match=recognized == SOURCE_TEXT)
                    stage, mt_started = "mt", time.perf_counter()
                    async with asyncio.timeout(30):
                        translated = shared.safe_text(await translator.translate(recognized, "ta", "hi"), secrets, maximum=300)
                    shared._prompt.check_target_script(translated, "hi")
                    report.update(translated_text=translated, mt_complete_ms=round((time.perf_counter() - mt_started) * 1000, 3))
                    stage, target_started = "target_tts", time.perf_counter()
                    target_pcm, synthesis = await shared.synthesize(speech, translated, "hi", maximum_seconds=15)
                    report.update(target_synthesis=synthesis,
                        stt_start_to_target_first_pcm_ms=round((target_started - chain_started) * 1000 + synthesis["first_pcm_ms"], 3),
                        stt_start_to_target_complete_ms=round((time.perf_counter() - chain_started) * 1000, 3))
                    shared.save_wav(folder / "target.wav", target_pcm)
                report["status"], stage = "provider_chain_complete_meaning_review_pending", None
            except asyncio.CancelledError:
                cancelled = True
                report["status"], stage, report["error_class"] = "cancelled", "cancelled", "cancelled"
            except Exception as error:
                report["status"], report["error_class"] = "stopped_no_retry", shared.safe_error_class(error)
            finally:
                report["error_stage"] = stage
                for label, client in (("speech", speech), ("translator", translator)):
                    if client is not None:
                        try:
                            await asyncio.wait_for(client.aclose(), CLOSE_SECONDS)
                        except asyncio.CancelledError:
                            cancelled = True
                            report["error_class"], report["error_stage"] = "cancelled", "cancelled"
                            report["cleanup_errors"].append(label + "_cleanup_cancelled")
                        except BaseException:
                            report["error_class"] = report["error_class"] or "cleanup_error"
                            report["cleanup_errors"].append(label + "_cleanup_incomplete")
                try:
                    flow = guard.close_flow(flow_id)
                    report.update(used=flow["used"], flow_status=flow["status"], programme_credits_used=flow.get("credits_used"))
                except Exception:
                    report["error_class"] = report["error_class"] or "flow_close_error"
                    report["cleanup_errors"].append("flow_close_failed")
        report["wall_seconds"] = round(time.perf_counter() - started, 3)
        if cancelled:
            report["status"] = "cancelled"
        elif report["cleanup_errors"]:
            report["status"] = "stopped_no_retry"
        if folder.is_dir():
            shared.write_private(folder / "report.json", json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False).encode())
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
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--flow-id")
    parser.add_argument("--approve-plan")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        plan = build_plan(endpoint=args.endpoint, flow_id=args.flow_id)
        if not args.run:
            print(json.dumps(plan, ensure_ascii=True, indent=2, allow_nan=False))
            return 0
        if not args.flow_id or not args.approve_plan or not args.output_dir:
            raise Rejected("Run requires an exact existing grant, plan hash and new work output.")
        shared.output_destination(args.output_dir)
        if args.approve_plan != plan["plan_sha256"]:
            raise Rejected("Review the endpoint, input and flow-bound plan hash.")
        read_input(args.input)
        settings_class, *_ = shared._runtime()
        report = asyncio.run(run_check(settings_class(), endpoint=args.endpoint, flow_id=args.flow_id,
            approved_plan=args.approve_plan, input_path=args.input, output_dir=args.output_dir))
        print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
        return 0 if report["status"] == "provider_chain_complete_meaning_review_pending" else 1
    except (Exception, KeyboardInterrupt):
        print("The follow-up did not run or stopped; review the exact local plan, source input and existing grant. No automatic retry was made.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
