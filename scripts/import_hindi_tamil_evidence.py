"""Validate and redact one saved Hindi–Tamil provider report; performs no API calls.

Usage: python scripts/import_hindi_tamil_evidence.py --input work/TEST/report.json
       --output web/src/data/hindiTamilProviderResults.json
An existing null placeholder may be replaced. Replacing prior evidence needs --replace.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("charcha_hindi_tamil_evidence_contract", ROOT / "scripts/check_hindi_tamil_e2e.py")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)
TYPE = "controlled_hindi_tamil_provider_evidence"
COMPLETE = "provider_chain_complete_meaning_review_pending"
STATUSES = {COMPLETE, "stopped_no_retry", "cancelled"}
CASE_STATUSES = {COMPLETE, "unattempted", "error", "cancelled"}
STAGES = {None, "approval", "configuration", "source_tts", "stt", "mt", "target_tts", "cancelled"}
CLEANUP = {"speech_cleanup_cancelled", "speech_cleanup_incomplete", "translator_cleanup_cancelled",
           "translator_cleanup_incomplete", "flow_close_failed"}
TIMINGS = ("stt_final_ms", "mt_complete_ms", "stt_start_to_target_first_pcm_ms", "stt_start_to_target_complete_ms")


class Rejected(ValueError):
    """Fixed local validation messages; never interpolate source data."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Rejected(message)


def number(value: object, *, maximum: float, nullable: bool = False):
    if value is None and nullable:
        return None
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum,
            "Report contains an invalid or out-of-bound measurement.")
    return value


def duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON keys are not accepted.")
        result[key] = value
    return result


def decode(raw: bytes):
    require(len(raw) <= 1_048_576, "Report exceeds the local import size limit.")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(Rejected("Non-finite JSON is not accepted.")))
    except (UnicodeError, json.JSONDecodeError):
        raise Rejected("Report is not valid UTF-8 JSON.") from None


def curate(report: object, *, source_sha256: str) -> dict:
    require(isinstance(report, dict) and report.get("schema_version") == 1
            and report.get("record_type") == "hindi_tamil_provider_chain_result", "Use a saved provider-chain result, not a plan or room report.")
    require(bool(re.fullmatch(r"[a-f0-9]{64}", source_sha256)), "Source report hash is invalid.")
    plan = report.get("plan")
    require(isinstance(plan, dict), "The runner's bound plan is required.")
    expected = CONTRACT.build_plan()
    if plan.get("prompt_version") == "evon-explicit-target-v2":
        expected["prompt_version"] = "evon-explicit-target-v2"
    for field in ("endpoint_sha256", "flow_id_sha256"):
        require(isinstance(plan.get(field), str) and bool(re.fullmatch(r"[a-f0-9]{64}", plan[field])), "The bound plan lacks provenance hashes.")
        expected[field] = plan[field]
    expected["plan_sha256"] = CONTRACT.digest({key: value for key, value in expected.items() if key != "plan_sha256"})
    require(plan == expected, "The saved plan differs from the reviewed runner contract or hash.")
    require(report.get("status") in STATUSES and report.get("error_stage") in STAGES, "Unknown result status or stage.")
    require(report.get("rtc_tested") is False and report.get("physical_microphone_tested") is False
            and report.get("voice_cloning") is False and report.get("screening_mode") == "off"
            and type(report.get("automatic_retries")) is int and report["automatic_retries"] == 0
            and report.get("listener_latency_ms") is None
            and report.get("meaning_review") == "pending_human_bilingual_review", "This importer accepts only the controlled standard-voice, no-RTC flow.")
    require(report.get("actual_provider_charge_inr") is None and report.get("actual_modal_charge_usd") is None,
            "Billing reconciliation is outside this controlled evidence contract.")
    cleanup = report.get("cleanup_errors")
    require(isinstance(cleanup, list) and all(isinstance(row, str) and row in CLEANUP for row in cleanup), "Unknown cleanup state.")
    wall = number(report.get("wall_seconds"), maximum=3600)
    try:
        created = datetime.fromisoformat(report.get("created_at", "").replace("Z", "+00:00"))
        require(created.tzinfo is not None and created.utcoffset().total_seconds() == 0, "Use the runner's UTC recording time.")
    except (ValueError, TypeError, AttributeError):
        raise Rejected("Use the runner's UTC recording time.") from None
    used = report.get("used")
    if used is not None:
        require(isinstance(used, dict) and set(used) == set(CONTRACT.BUDGETS), "Usage must include exactly the reviewed resource units.")
        for key, cap in CONTRACT.BUDGETS.items():
            require(type(used[key]) is int and 0 <= used[key] <= cap, "Usage exceeds the reviewed caps or has invalid units.")
        used = dict(used)
    raw_cases = report.get("cases")
    require(isinstance(raw_cases, list) and len(raw_cases) == 2, "Both fixed test cases must remain visible.")
    cases = []
    for raw, (identifier, source, target, text) in zip(raw_cases, CONTRACT.CASES, strict=True):
        require(isinstance(raw, dict) and (raw.get("case_id"), raw.get("source_language"), raw.get("target_language"), raw.get("source_text"))
                == (identifier, source, target, text), "Test case identity or stock-source provenance differs.")
        require(raw.get("status") in CASE_STATUSES and raw.get("meaning_review") == "pending", "Unknown case status or meaning review.")
        timings = {field: number(raw.get(field), maximum=wall * 1000 + 1, nullable=True) for field in TIMINGS}
        synthesis = {}
        for name, max_audio in (("source_preparation", 8), ("target_synthesis", 15)):
            value = raw.get(name)
            if value is None:
                synthesis[name] = None
            else:
                require(isinstance(value, dict), "Synthesis timing must be an object.")
                first = number(value.get("first_pcm_ms"), maximum=wall * 1000 + 1)
                complete = number(value.get("complete_ms"), maximum=wall * 1000 + 1)
                number(value.get("audio_seconds"), maximum=max_audio)
                require(first <= complete, "Synthesis timing order is invalid.")
                synthesis[name] = {"first_pcm_ms": first, "complete_ms": complete}
        if raw["status"] == COMPLETE:
            require(all(value is not None for value in timings.values()) and all(synthesis.values()), "A complete case must retain every stage timing.")
            require(isinstance(raw.get("recognized_text"), str) and 0 < len(raw["recognized_text"]) <= 500
                    and isinstance(raw.get("translated_text"), str) and 0 < len(raw["translated_text"]) <= 300,
                    "A complete case lacks bounded provider text provenance.")
            require(timings["stt_start_to_target_first_pcm_ms"] <= timings["stt_start_to_target_complete_ms"], "Chain timing order is invalid.")
        cases.append({"case_id": identifier, "source_language": source, "target_language": target,
                      "status": raw["status"], "meaning_review": "pending",
                      "source_preparation": synthesis["source_preparation"],
                      "stt_final_ms": timings["stt_final_ms"], "mt_complete_ms": timings["mt_complete_ms"],
                      "target_synthesis": synthesis["target_synthesis"],
                      "stt_start_to_target_first_pcm_ms": timings["stt_start_to_target_first_pcm_ms"],
                      "stt_start_to_target_complete_ms": timings["stt_start_to_target_complete_ms"]})
    if report["status"] == COMPLETE:
        require(all(row["status"] == COMPLETE for row in cases) and not cleanup and used is not None
                and report.get("error_stage") is None and report.get("flow_status") == "closed", "Overall completion requires both cases, usage and clean shutdown.")
        require(used["tts_requests"] == 4 and used["stt_connections"] == 2 and used["mt_requests"] == 2 and used["stt_seconds"] >= 2,
                "Complete usage does not account for the fixed request flow.")
        require(used["mt_characters"] == sum(len(row["recognized_text"]) for row in raw_cases)
                and used["tts_characters"] == sum(len(row["source_text"]) + len(row["translated_text"]) for row in raw_cases),
                "Complete text units do not match the local request ledger.")
    reference = None if used is None else round(used["stt_seconds"] * 27 / 3600 + used["tts_characters"] * 27 / 10000, 6)
    return {"schema_version": 1, "record_type": TYPE, "recorded_on": created.date().isoformat(),
            "source_report_sha256": source_sha256, "plan_sha256": plan["plan_sha256"],
            "source_provenance": "deliberately_generated_stock_voice_utterances", "voice_mode": "standard",
            "status": report["status"], "error_stage": report.get("error_stage"), "cases": cases,
            "used": used, "caps": dict(CONTRACT.BUDGETS), "wall_seconds": wall,
            "wall_target_seconds": 240, "wall_target_exceeded": wall > 240, "cleanup_complete": not cleanup,
            "meaning_review": "pending", "rtc_tested": False, "physical_microphone_tested": False,
            "listener_latency_ms": None, "voice_cloning": False, "screening_mode": "off", "automatic_retries": 0,
            "cost_reference": {"currency": "INR", "stt_per_hour": 27, "tts_per_10000_characters": 27,
                               "local_usage_reference_inr": reference, "approved_maximum_reference_inr": 2.385,
                               "actual_provider_charge_inr": None, "actual_modal_charge_usd": None,
                               "programme_credits_used": None},
            "boundary": "Stock-source TTS preparation is separate. STT-start to first target PCM includes connection setup and real-time source-audio transmission; it is not speech-end delay. RTC, physical capture and listener playback are excluded.",
            "usage_boundary": "Exact local request/character reservations. STT seconds are reserved connection units, not verified provider-billed audio time. Reference pricing excludes Modal compute, rounding and taxes."}


def import_file(input_path: Path, output_path: Path, *, replace: bool = False) -> dict:
    require(input_path.resolve() != output_path.resolve(), "Input and output must be different files.")
    require(output_path.suffix == ".json" and not output_path.is_symlink()
            and not bool(getattr(output_path, "is_junction", lambda: False)()), "Choose an explicit ordinary JSON output file.")
    with input_path.open("rb") as handle:
        raw = handle.read(1_048_577)
    public = curate(decode(raw), source_sha256=hashlib.sha256(raw).hexdigest())
    if output_path.exists():
        existing = decode(output_path.read_bytes())
        if existing == public:
            return public
        require(existing is None or replace and isinstance(existing, dict) and existing.get("record_type") == TYPE,
                "Prior evidence exists; preserve it or explicitly replace that evidence file.")
    require(output_path.parent.is_dir(), "Output parent must already exist.")
    temporary = output_path.with_suffix(".json.importing")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(public, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        temporary.replace(output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return public


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = import_file(args.input, args.output, replace=args.replace)
        print(json.dumps({"imported": True, "case_count": len(result["cases"]), "status": result["status"], "provider_calls_made_by_importer": 0}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print("Evidence import rejected. Review the saved runner report, bounds and explicit output; no provider request was made.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
