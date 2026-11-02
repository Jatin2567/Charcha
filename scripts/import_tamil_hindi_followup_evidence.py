"""Strictly validate/redact one separate approved Tamil-to-Hindi follow-up report.

Offline only: no settings, credentials, ledger, cloud or provider calls. The
original two-case evidence is never replaced by this importer's --replace flag.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _module("followup_import_pure_validation", "import_hindi_tamil_evidence.py")
CONTRACT = _module("followup_import_runner_contract", "check_tamil_hindi_followup.py")
Rejected, require, number, decode = BASE.Rejected, BASE.require, BASE.number, BASE.decode
TYPE = "controlled_tamil_hindi_followup_evidence"
COMPLETE = "provider_chain_complete_meaning_review_pending"
STATUSES = {COMPLETE, "stopped_no_retry", "cancelled"}
STAGES = {None, "approval", "configuration", "stt", "mt", "target_tts", "cancelled"}
ERROR_CLASSES = {None, "cancelled", "timeout", "validation_error", "provider_error", "io_error",
                 "unexpected_error", "cleanup_error", "flow_close_error"}
CLEANUP = BASE.CLEANUP | {"stt_stream_cleanup_incomplete"}
TIMINGS = ("stt_final_ms", "mt_complete_ms", "stt_start_to_target_first_pcm_ms", "stt_start_to_target_complete_ms")


def _enum(value, allowed) -> bool:
    return (value is None or type(value) is str) and value in allowed


def curate(report: object, *, source_sha256: str) -> dict:
    require(isinstance(report, dict) and type(report.get("schema_version")) is int
            and report["schema_version"] == 1 and report.get("record_type") == "tamil_hindi_followup_result",
            "Use a saved separate Tamil-to-Hindi follow-up result.")
    require(isinstance(source_sha256, str) and bool(re.fullmatch(r"[a-f0-9]{64}", source_sha256)), "Source report hash is invalid.")
    plan = report.get("plan")
    require(isinstance(plan, dict), "The exact bound follow-up plan is required.")
    expected = CONTRACT.build_plan()
    if plan.get("prompt_version") == "evon-explicit-target-v2":
        expected["prompt_version"] = "evon-explicit-target-v2"
    for field in ("endpoint_sha256", "flow_id_sha256"):
        require(isinstance(plan.get(field), str) and bool(re.fullmatch(r"[a-f0-9]{64}", plan[field])), "Bound plan provenance hashes are required.")
        expected[field] = plan[field]
    expected["plan_sha256"] = CONTRACT.shared.digest({key: value for key, value in expected.items() if key != "plan_sha256"})
    require(plan == expected and CONTRACT.shared.digest({key: value for key, value in plan.items() if key != "plan_sha256"}) == plan.get("plan_sha256"),
            "The saved plan differs from the reviewed follow-up contract or hash.")
    require(_enum(report.get("status"), STATUSES) and _enum(report.get("error_stage"), STAGES)
            and _enum(report.get("error_class"), ERROR_CLASSES), "Unknown follow-up status, stage or safe error class.")
    require(report.get("rtc_tested") is False and report.get("physical_microphone_tested") is False
            and report.get("voice_cloning") is False and report.get("screening_mode") == "off"
            and type(report.get("automatic_retries")) is int and report["automatic_retries"] == 0
            and type(report.get("source_tts_requests")) is int and report["source_tts_requests"] == 0
            and report.get("listener_latency_ms") is None and report.get("meaning_review") == "pending_human_bilingual_review",
            "Only the approved fixed-input standard-voice follow-up is accepted.")
    require(report.get("actual_provider_charge_inr") is None and report.get("actual_modal_charge_usd") is None,
            "Actual billing reconciliation is outside this evidence contract.")
    require(report.get("stt") == {"requested_model": "prisma-v3.0", "provider_model": None},
            "Retain the explicit requested STT model and unknown provider acknowledgement.")
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
        require(isinstance(used, dict) and set(used) == set(CONTRACT.BUDGETS), "Usage must contain exactly the approved resource units.")
        for field, cap in CONTRACT.BUDGETS.items():
            require(type(used[field]) is int and 0 <= used[field] <= cap, "Usage exceeds the follow-up caps or has invalid units.")
        used = dict(used)
    require(report.get("flow_status") in (None, "closed") and (report.get("flow_status") == "closed") == (used is not None),
            "Flow closure and recorded usage must agree.")
    timings = {field: number(report.get(field), maximum=wall * 1000 + 1, nullable=True) for field in TIMINGS}
    synthesis = report.get("target_synthesis")
    if synthesis is not None:
        require(isinstance(synthesis, dict), "Target synthesis timing must be an object.")
        first = number(synthesis.get("first_pcm_ms"), maximum=wall * 1000 + 1)
        complete = number(synthesis.get("complete_ms"), maximum=wall * 1000 + 1)
        duration = number(synthesis.get("audio_seconds"), maximum=15)
        require(first <= complete and duration > 0, "Target synthesis timing or audio duration is invalid.")
        timings.update(target_tts_first_pcm_ms=first, target_tts_complete_ms=complete)
    else:
        timings.update(target_tts_first_pcm_ms=None, target_tts_complete_ms=None)
    if timings["stt_start_to_target_first_pcm_ms"] is not None and timings["stt_start_to_target_complete_ms"] is not None:
        require(timings["stt_start_to_target_first_pcm_ms"] <= timings["stt_start_to_target_complete_ms"], "Chain timing order is invalid.")
    if report["status"] == COMPLETE:
        require(report.get("error_stage") is None and report.get("error_class") is None and not cleanup
                and used is not None and all(value is not None for value in timings.values()),
                "Protocol completion requires all timings, usage and clean closure.")
        recognized, translated = report.get("recognized_text"), report.get("translated_text")
        require(isinstance(recognized, str) and 0 < len(recognized.strip()) <= 500
                and isinstance(translated, str) and 0 < len(translated.strip()) <= 300,
                "A complete flow lacks bounded provider-text provenance.")
        require(used["stt_connections"] == used["mt_requests"] == used["tts_requests"] == 1
                and used["stt_seconds"] >= 1 and used["mt_characters"] == len(recognized)
                and used["tts_characters"] == len(translated), "Complete usage does not match the fixed follow-up flow.")
    elif report["status"] == "cancelled":
        require(report.get("error_class") == "cancelled" and report.get("error_stage") == "cancelled", "Cancellation diagnostics must agree.")
    else:
        require(report.get("error_class") is not None, "A stopped flow requires a safe error class.")
    reference = None if used is None else round(used["stt_seconds"] * 27 / 3600 + used["tts_characters"] * 27 / 10000, 6)
    return {"schema_version": 1, "record_type": TYPE, "recorded_on": created.date().isoformat(),
        "source_report_sha256": source_sha256, "plan_sha256": plan["plan_sha256"],
        "input_sha256": CONTRACT.INPUT_SHA256, "source_audio_seconds": 3.2,
        "source_provenance": "existing_standard_voice_clip", "source_language": "ta", "target_language": "hi",
        "translation_model": CONTRACT.MODEL, "prompt_version": plan["prompt_version"],
        "voice_mode": "standard", "status": report["status"], "error_stage": report.get("error_stage"),
        "error_class": report.get("error_class"), "stt": {"requested_model": "prisma-v3.0", "provider_model": None},
        "timings": timings, "used": used, "caps": dict(CONTRACT.BUDGETS), "wall_seconds": wall,
        "cleanup_complete": not cleanup, "flow_closed": report.get("flow_status") == "closed",
        "meaning_review": "pending", "rtc_tested": False, "physical_microphone_tested": False,
        "listener_latency_ms": None, "voice_cloning": False, "screening_mode": "off", "automatic_retries": 0,
        "source_tts_requests": 0, "cost_reference": {"currency": "INR", "stt_per_hour": 27,
            "tts_per_10000_characters": 27, "local_usage_reference_inr": reference,
            "approved_maximum_reference_inr": .9975, "actual_provider_charge_inr": None,
            "actual_modal_charge_usd": None, "programme_credits_used": None}}


def import_file(input_path: Path, output_path: Path, *, replace: bool = False) -> dict:
    require(input_path.resolve() != output_path.resolve(), "Input and output must be different files.")
    require(output_path.suffix == ".json" and not output_path.is_symlink()
            and not bool(getattr(output_path, "is_junction", lambda: False)()), "Choose an ordinary JSON output file.")
    with input_path.open("rb") as handle:
        raw = handle.read(1_048_577)
    public = curate(decode(raw), source_sha256=hashlib.sha256(raw).hexdigest())
    if output_path.exists():
        existing = decode(output_path.read_bytes())
        if existing == public:
            return public
        require(existing is None or replace and isinstance(existing, dict) and existing.get("record_type") == TYPE,
                "Existing evidence belongs to another result or requires explicit replacement.")
    require(output_path.parent.is_dir(), "Output parent must already exist.")
    temporary = output_path.with_suffix(".json.importing")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(public, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temporary.replace(output_path)
    finally:
        if temporary.exists(): temporary.unlink()
    return public


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = import_file(args.input, args.output, replace=args.replace)
        print(json.dumps({"imported": True, "status": result["status"], "provider_calls_made_by_importer": 0}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print("Follow-up evidence import rejected. Review the exact saved report and output; no provider request was made.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
