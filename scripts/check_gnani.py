"""Plan one bounded Gnani speech check; paid calls require an existing operator grant.

The default/--plan path loads no environment, constructs no provider and writes no
ledger. --run never grants permission itself. Voice cloning additionally requires
a local recording and explicit own-voice consent; no reference is manufactured.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
import wave
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from artha_mesh.config import Settings  # noqa: E402
from artha_mesh.services.approvals import RESOURCE_KEYS  # noqa: E402
from artha_mesh.services.usage import UsageGuard  # noqa: E402
from artha_mesh.services.voice import MAX_REFERENCE_BYTES, validate_reference  # noqa: E402

PHRASE = "नमस्ते भारत।"
PURPOSES = ("gnani_speech_check", "voice_clone_check")
FLOW_SECONDS = 60
SAMPLE_RATE = 16000
TTS_TIMEOUT_SECONDS = 15
STT_TIMEOUT_SECONDS = 8
MAX_AUDIO_SECONDS = 10
OUTPUT_ROOT = ROOT / "server" / "data" / "gnani-checks"
OFFICIAL_URLS = {
    "gnani_stt_url": "wss://api.vachana.ai/stt/v3/stream",
    "gnani_tts_url": "wss://api.vachana.ai/api/v1/tts",
    "gnani_embedding_url": "https://api.vachana.ai/api/v1/tts/voice-clone/embeddings",
}


class CheckRejected(Exception):
    """A local, intentionally generic failure safe to show without provider text."""


def build_plan(purpose: str = "gnani_speech_check") -> dict:
    if purpose not in PURPOSES:
        raise CheckRejected("Choose a supported speech check purpose.")
    budgets = dict.fromkeys(RESOURCE_KEYS, 0)
    budgets.update(tts_requests=1, tts_characters=len(PHRASE))
    if purpose == "gnani_speech_check":
        budgets.update(stt_connections=1, stt_seconds=9)
    else:
        budgets["voice_enrollments"] = 1
    # Human-supplied pricing is reference arithmetic only. It is never a ledger
    # deduction or a conversion to the separate programme-credit balance.
    is_standard = purpose == "gnani_speech_check"
    tts_reference = len(PHRASE) * 27 / 10000 if is_standard else None
    stt_reference = 9 * 27 / 3600 if is_standard else None
    return {
        "purpose": purpose, "approval_expiry_seconds": FLOW_SECONDS,
        "phrase": PHRASE, "language": "hi", "budgets": budgets,
        "audio_sample_rate": SAMPLE_RATE, "tts_timeout_seconds": TTS_TIMEOUT_SECONDS,
        "stt_timeout_seconds": STT_TIMEOUT_SECONDS if purpose == "gnani_speech_check" else None,
        "maximum_generated_audio_seconds": MAX_AUDIO_SECONDS,
        "requires_own_voice_reference": purpose == "voice_clone_check",
        "programme_credits_used": None,
        "reference_pricing": {
            "currency": "INR", "source": "user_provided_pricing_table",
            "stt_per_hour": 27, "tts_per_10000_characters": 27,
            "tts_reference_amount": round(tts_reference, 8) if is_standard else None,
            "stt_budget_reference_amount": round(stt_reference, 8) if is_standard else None,
            "known_component_reference_total": round(tts_reference + stt_reference, 8) if is_standard else None,
            "voice_enrollment_price": None, "billing_rounding": "unconfirmed",
            "complete_estimate": is_standard,
            "detail": "Reference arithmetic only; not a guaranteed charge or a programme-credit conversion. Both clone enrollment and cloned synthesis tariffs are unknown.",
        },
        "detail": "Plan only costs zero. Run needs fresh human permission and the exact active, unused 60-second grant. No translation or retries are included.",
    }


def load_reference(path: Path | None, consent: bool) -> tuple[bytes, float]:
    if not consent or path is None:
        raise CheckRejected("Cloning needs a local own-voice recording and explicit consent.")
    try:
        if not path.is_file() or path.stat().st_size > MAX_REFERENCE_BYTES:
            raise CheckRejected("Reference must be a local 5–30 second 16-bit PCM WAV.")
        clip = path.read_bytes()
        duration = validate_reference(clip, "audio/wav")
    except CheckRejected:
        raise
    except Exception:
        raise CheckRejected("Reference must be an audible local 5–30 second 16-bit PCM WAV.") from None
    return clip, duration


def validate_grant(flow: dict, plan: dict) -> None:
    try:
        lifetime = (datetime.fromisoformat(flow["expires_at"]) -
                    datetime.fromisoformat(flow["started_at"])).total_seconds()
        valid = (flow["status"] == "approved" and flow["purpose"] == plan["purpose"]
                 and flow["budgets"] == plan["budgets"] and lifetime == FLOW_SECONDS
                 and set(flow["used"]) == set(RESOURCE_KEYS)
                 and all(type(value) is int and value == 0 for value in flow["used"].values()))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise CheckRejected("The exact active, unused 60-second approval for this plan is required.")


def create_speech(settings: Settings, guard: UsageGuard):
    # Lazy import keeps both plan and preflight rejection paths free of clients.
    from artha_mesh.providers.gnani import GnaniSpeech
    return GnaniSpeech(settings, guard)


def write_private(path: Path, data: bytes) -> None:
    # O_EXCL avoids replacing user files; POSIX permissions are restricted at
    # creation. Windows inherits the account-owned server/data folder ACL.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as destination:
        destination.write(data)


def write_report(folder: Path, report: dict, pcm: bytes | None) -> None:
    if pcm:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm)
        write_private(folder / "speech.wav", output.getvalue())
    write_private(folder / "report.json", json.dumps(
        report, ensure_ascii=False, indent=2, allow_nan=False,
    ).encode("utf-8"))


async def audio_with_silence(pcm: bytes):
    yield pcm
    # Keep the stream alive so Gnani's VAD can emit a final segment. The adapter
    # paces 1,024-byte frames; the enclosing eight-second deadline bounds silence.
    while True:
        yield bytes(1024)


async def run_check(
    settings: Settings, *, flow_id: str | None, purpose: str = "gnani_speech_check",
    reference: Path | None = None, consent_own_voice: bool = False,
    guard: UsageGuard | None = None, speech_factory=None, output_root: Path = OUTPUT_ROOT,
) -> dict:
    plan = build_plan(purpose)
    clip = None
    metrics: dict = {"error_stage": "none"}
    if purpose == "voice_clone_check":
        clip, metrics["reference_seconds"] = load_reference(reference, consent_own_voice)
    elif reference is not None or consent_own_voice:
        raise CheckRejected("Reference recordings are accepted only by the separate voice-clone check.")
    if not flow_id:
        raise CheckRejected("Supply an existing explicitly approved flow ID; this tool never approves a flow.")
    # Only this in-memory check becomes live. The saved .env and application mode
    # remain unchanged; no LiveKit/Evon configuration is needed for speech checks.
    run_settings = settings.model_copy(update={
        "mode": "live", "usage_require_flow_approval": True,
        "audio_sample_rate": SAMPLE_RATE, "provider_timeout_seconds": TTS_TIMEOUT_SECONDS,
    })
    if not run_settings.gnani_api_key.get_secret_value() or any(
        getattr(run_settings, key) != value for key, value in OFFICIAL_URLS.items()
    ):
        raise CheckRejected("A configured Gnani key and the documented Gnani speech endpoints are required.")
    own_guard = guard is None
    guard = guard or UsageGuard(run_settings)
    speech = None
    bound = False
    cancelled = False
    pcm = b""
    transcript = None
    folder = None
    report = {"success": False, "flow_id": flow_id, "purpose": purpose,
              "plan": plan, "metrics": metrics, "programme_credits_used": None,
              "programme_credit_source": "unknown", "used": None,
              "created_at": datetime.now(UTC).isoformat()}
    try:
        # Inspection and all reference/configuration validation precede provider
        # construction. A wrong or expired grant is never closed by this runner.
        try:
            validate_grant(guard.inspect_flow(flow_id), plan)
        except Exception:
            raise CheckRejected("The exact active, unused 60-second approval for this plan is required.") from None
        with guard.bind_flow(flow_id):
            bound = True
            try:
                metrics["error_stage"] = "configuration"
                output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                folder = output_root / str(uuid4())
                folder.mkdir(mode=0o700)
                speech = (speech_factory or create_speech)(run_settings, guard)
                embedding = None
                if clip is not None:
                    metrics["error_stage"] = "enrollment"
                    async with asyncio.timeout(TTS_TIMEOUT_SECONDS):
                        embedding = await speech.enroll(clip)
                    # Reference bytes need not survive the enrollment request.
                    clip = None
                metrics["error_stage"] = "tts"
                started = time.perf_counter()
                chunks = []
                byte_count = 0
                async with asyncio.timeout(TTS_TIMEOUT_SECONDS), aclosing(
                    speech.synthesize(PHRASE, "hi", embedding)
                ) as generated:
                    async for chunk in generated:
                        if not isinstance(chunk, bytes) or len(chunk) % 2:
                            raise CheckRejected("Speech output did not match the requested PCM format.")
                        if not chunk:
                            continue
                        if "tts_first_pcm_ms" not in metrics:
                            metrics["tts_first_pcm_ms"] = round((time.perf_counter() - started) * 1000, 2)
                        byte_count += len(chunk)
                        if byte_count > SAMPLE_RATE * 2 * MAX_AUDIO_SECONDS:
                            raise CheckRejected("Speech output exceeded the bounded check duration.")
                        chunks.append(chunk)
                embedding = None
                if not chunks:
                    raise CheckRejected("Speech synthesis returned no PCM audio.")
                pcm = b"".join(chunks)
                metrics["tts_total_ms"] = round((time.perf_counter() - started) * 1000, 2)
                metrics["tts_audio_seconds"] = round(len(pcm) / (SAMPLE_RATE * 2), 4)
                if purpose == "gnani_speech_check":
                    metrics["error_stage"] = "stt"
                    started = time.perf_counter()
                    async with asyncio.timeout(STT_TIMEOUT_SECONDS), aclosing(
                        speech.transcribe(audio_with_silence(pcm), "hi")
                    ) as recognized:
                        async for result in recognized:
                            transcript = str(result.text)[:2000]
                            if transcript.strip():
                                metrics["stt_final_ms"] = round((time.perf_counter() - started) * 1000, 2)
                                break
                    if not transcript or not transcript.strip():
                        raise CheckRejected("Speech recognition returned no final transcript.")
                metrics["error_stage"] = "none"
                report["success"] = True
            except asyncio.CancelledError:
                metrics["error_stage"] = "cancelled"
                cancelled = True
            except Exception:
                # Provider exception messages, URLs, request bodies and headers
                # never enter the report, terminal or local flow metadata.
                report["success"] = False
            finally:
                try:
                    if speech is not None:
                        await speech.aclose()
                except asyncio.CancelledError:
                    metrics["error_stage"] = "cancelled"
                    report["success"] = False
                    cancelled = True
                except BaseException:
                    # Resource cleanup failure never permits another provider call.
                    pass
                if bound:
                    try:
                        guard.record_flow_metrics(flow_id, metrics)
                    finally:
                        flow = guard.close_flow(flow_id)
                        report["used"] = flow["used"]
                        report["programme_credits_used"] = flow.get("credits_used")
                        report["programme_credit_source"] = flow.get("credits_source", "unknown")
                        report["flow_status"] = flow["status"]
        if transcript is not None and report["success"]:
            # This isolated check recognizes only its own fixed synthetic phrase.
            report["synthetic_transcript"] = transcript
        report["message"] = ("Bounded protocol check completed; transcript presence does not certify word accuracy or voice similarity. Reconcile programme credits against dashboard evidence."
                             if report["success"] else "Bounded check stopped; no retry was attempted. Review the recorded error stage.")
        if folder is not None:
            write_report(folder, report, pcm or None)
            report["report_directory"] = str(folder)
        if cancelled:
            raise asyncio.CancelledError
        return report
    finally:
        if own_guard:
            guard.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    action = result.add_mutually_exclusive_group()
    action.add_argument("--plan", action="store_true", help="Default: print the bounded plan without clients or environment access")
    action.add_argument("--run", action="store_true", help="Perform only the separately approved flow; may use provider credits")
    result.add_argument("--purpose", choices=PURPOSES, default="gnani_speech_check")
    result.add_argument("--flow-id", help="Exact existing operator-approved flow UUID; never auto-generated")
    result.add_argument("--reference", type=Path, help="Own-voice local 5–30 second PCM WAV for the separate clone check")
    result.add_argument("--consent-own-voice", action="store_true", help="Confirm the supplied reference is your own voice and you consent to cloning it")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.run:
        # Windows terminals may use cp1252. ASCII JSON escapes preserve every
        # Hindi code point while keeping CLI output portable; saved reports are UTF-8.
        print(json.dumps(build_plan(args.purpose), ensure_ascii=True, indent=2))
        return 0
    try:
        if not args.flow_id:
            raise CheckRejected("Supply an existing explicitly approved flow ID; this tool never approves a flow.")
        report = asyncio.run(run_check(
            Settings(), flow_id=args.flow_id, purpose=args.purpose,
            reference=args.reference, consent_own_voice=args.consent_own_voice,
        ))
        print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
        return 0 if report["success"] else 1
    except CheckRejected as exc:
        print(str(exc), file=sys.stderr)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Check cancelled; the bound flow was closed. No retry was attempted.", file=sys.stderr)
    except Exception:
        print("Check could not complete. Values are redacted; no retry was attempted.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
