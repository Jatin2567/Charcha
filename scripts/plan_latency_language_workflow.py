"""Offline ten-language workflow and physical speech-end latency acceptance gates.

This planner never runs, approves or renews a provider flow. Passing a gate only
makes the next bounded test eligible for human review; it grants no API usage.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation/language_latency_cases.json"
_spec = importlib.util.spec_from_file_location("latency_plan_stock_catalog", ROOT / "server/charcha/voice_catalog.py")
_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_catalog)
VOICES = dict(_catalog.TIMBRE_V25_STOCK_VOICES)
NAMES = {"hi": "Hindi", "ta": "Tamil", "bn": "Bengali", "en": "English", "te": "Telugu",
         "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi"}
MIN_WARM_ATTEMPTS = 10
LATENCY_GOAL_MS = 2000
MAX_OBSERVATIONS = 1000
PHYSICAL_CAPTURE_KINDS = {"acoustic_single_channel", "acoustic_two_channel", "electrical_loopback_two_channel"}
POLICY = {
    "minimum_warm_attempts": MIN_WARM_ATTEMPTS, "all_warm_attempts_complete": True,
    "maximum_warm_failure_rate": 0, "p50_strictly_under_ms": LATENCY_GOAL_MS,
    "p95_strictly_under_ms": LATENCY_GOAL_MS, "percentile_method": "nearest_rank",
    "clock": "single_recording_sample_index", "boundary": "source_speech_end_to_listener_output",
    "provider_kind": "live", "capture_kinds": sorted(PHYSICAL_CAPTURE_KINDS),
    "capture_attestation_required": True, "meaning_review_required": True,
    "annotations_review_required": True, "voice_mode": "standard",
    "negative_latency_policy": "preserve_signed_value_and_mark_overlap_requires_review",
    "duplicate_policy": "reject_repeated_observation_id_or_recording_and_source_end_within_direction",
    "first_route_policy": "report_separately_never_substitute_for_warm_attempts",
    "provenance_limit": "Provider and capture provenance are operator-attested, not cryptographic proof of live providers or physical hardware.",
}


def content_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _finite(value) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _sha(value) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{64}", value))


def nearest_rank(values: list[float], quantile: float):
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)] if values else None


def observation_reasons(row: dict) -> list[str]:
    reasons = []
    if (type(row.get("schema_version")) is not int or row.get("schema_version") != 1
            or row.get("record_type") != "speech_end_playback_observation"):
        reasons.append("measurement_contract_not_eligible")
    if row.get("clock") != POLICY["clock"] or row.get("boundary") != POLICY["boundary"]:
        reasons.append("shared_recording_boundary_required")
    if row.get("provider_kind") != "live": reasons.append("live_provider_required")
    if not isinstance(row.get("capture_kind"), str) or row["capture_kind"] not in PHYSICAL_CAPTURE_KINDS:
        reasons.append("physical_or_electrical_capture_required")
    if row.get("capture_attested") is not True: reasons.append("capture_attestation_required")
    if row.get("meaning_reviewed") is not True: reasons.append("meaning_review_pending")
    if row.get("annotations_reviewed") is not True: reasons.append("annotation_review_pending")
    if (row.get("voice_mode") != "standard" or row.get("voice_cloning") is not False
            or row.get("screening_mode") != "off"):
        reasons.append("standard_voice_stage_required")
    if not _sha(row.get("observation_id")) or not _sha(row.get("recording_sha256")):
        reasons.append("observation_identity_required")
    end, start, rate = (row.get(key) for key in ("source_speech_end_sample", "listener_audio_start_sample", "sample_rate_hz"))
    valid_indices = (type(end) is int and 0 <= end <= 2 ** 53 and type(start) is int and 0 <= start <= 2 ** 53
                     and type(rate) is int and 8000 <= rate <= 192000)
    latency = row.get("latency_ms")
    if not valid_indices or not _finite(latency):
        reasons.append("invalid_sample_clock_measurement")
    elif abs(latency - (start - end) * 1000 / rate) > .001:
        reasons.append("latency_sample_indices_disagree")
    if _finite(latency) and latency < 0: reasons.append("overlap_requires_review")
    if row.get("status") != "complete": reasons.append("attempt_not_complete")
    return reasons


def evaluate_gate(observations: list[dict], source: str, target: str) -> dict:
    if source not in VOICES or target not in VOICES or source == target:
        raise ValueError("Use a directed pair from the current stock-voice catalog")
    if not isinstance(observations, list) or len(observations) > MAX_OBSERVATIONS or any(not isinstance(row, dict) for row in observations):
        raise ValueError("Use at most 1000 local observation objects")
    relevant = [row for row in observations if row.get("source_language") == source and row.get("target_language") == target]
    warm = [row for row in relevant if row.get("condition") == "warm_route"]
    first = [row for row in relevant if row.get("condition") == "first_route"]
    ids = Counter(row.get("observation_id") for row in relevant if _sha(row.get("observation_id")))
    identities = Counter((row["recording_sha256"], row["source_speech_end_sample"]) for row in relevant
                         if _sha(row.get("recording_sha256")) and type(row.get("source_speech_end_sample")) is int)
    duplicate_rows = sum(1 for row in relevant if
        (_sha(row.get("observation_id")) and ids[row["observation_id"]] > 1)
        or (_sha(row.get("recording_sha256")) and type(row.get("source_speech_end_sample")) is int
            and identities[(row["recording_sha256"], row["source_speech_end_sample"])] > 1))
    reasons = set()
    qualifying = []
    for row in warm:
        problems = observation_reasons(row)
        reasons.update(problems)
        if not problems: qualifying.append(row["latency_ms"])
    if any(row.get("condition") not in ("warm_route", "first_route") for row in relevant):
        reasons.add("unknown_observation_condition")
    if duplicate_rows: reasons.add("duplicate_observation")
    if len(warm) < MIN_WARM_ATTEMPTS: reasons.add("minimum_warm_attempts_not_met")
    complete = sum(row.get("status") == "complete" for row in warm)
    if complete != len(warm): reasons.add("all_warm_attempts_must_complete")
    if len(qualifying) != len(warm): reasons.add("all_warm_attempts_must_qualify")
    p50, p95 = nearest_rank(qualifying, .5), nearest_rank(qualifying, .95)
    if p50 is None or p50 >= LATENCY_GOAL_MS: reasons.add("p50_not_strictly_under_goal")
    if p95 is None or p95 >= LATENCY_GOAL_MS: reasons.add("p95_not_strictly_under_goal")
    first_valid = [row["latency_ms"] for row in first if not observation_reasons(row)]
    return {"source_language": source, "target_language": target, "passed": not reasons,
        "status": "passed_for_next_test_review" if not reasons else "blocked",
        "reason_codes": sorted(reasons),
        "counts": {"warm_attempts": len(warm), "warm_complete": complete, "warm_qualifying": len(qualifying),
                   "warm_failures": len(warm) - complete, "first_route_attempts": len(first),
                   "duplicate_observations": duplicate_rows,
                   "overlap_observations": sum(_finite(row.get("latency_ms")) and row["latency_ms"] < 0 for row in warm)},
        "metrics": {"p50_ms": p50, "p95_ms": p95, "warm_failure_rate": (len(warm) - complete) / len(warm) if warm else None,
                    "basis": "qualifying_warm_attempts_only", "first_route_ms": first_valid[0] if len(first_valid) == 1 else None},
        "observed_warm_latency_ms": [row["latency_ms"] for row in warm if _finite(row.get("latency_ms"))],
        "approval_granted": False, "physical_provenance": "operator_attested_not_cryptographic_proof"}


def load_drafts(path: Path = FIXTURES) -> list[dict]:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    if (set(VOICES) != set(NAMES) or corpus.get("record_type") != "ten_language_latency_draft_cases"
            or corpus.get("source_reference_status") != "draft_pending_fluent_review"
            or set(corpus.get("languages", {})) != set(VOICES)
            or set(corpus.get("categories", {})) != {"ordinary", "negation", "names", "numbers"}):
        raise ValueError("Draft fixtures must match the exact current stock-voice catalog")
    drafts = []
    for code in VOICES:
        for category, reference in corpus["categories"].items():
            text = corpus["languages"][code].get(category)
            if not isinstance(text, str) or not 0 < len(text) <= 300:
                raise ValueError("Draft source text must contain 1–300 characters")
            drafts.append({"case_id": f"{code}-{category}", "source_language": code, "category": category,
                "source_text": text, "source_characters": len(text),
                "expected_meaning": corpus["languages"][code].get("negation_meaning", reference["expected_meaning"])
                    if category == "negation" else reference["expected_meaning"],
                "review_focus": reference["review_focus"], "source_reference_status": "draft_pending_fluent_review",
                "target_reference": None, "meaning_acceptance": "pending"})
    return drafts


def build_plan(observations: list[dict] | None = None) -> dict:
    observations = [] if observations is None else observations
    drafts = load_drafts()
    forward, reverse = evaluate_gate(observations, "hi", "ta"), evaluate_gate(observations, "ta", "hi")
    both_passed = forward["passed"] and reverse["passed"]
    languages = [{"code": code, "name": NAMES[code], "locale": f"{code}-IN", "standard_voice": voice,
        "providers": {
            "stt": {"requested_model": "prisma-v3.0", "catalog_status": "documented", "account_access": "not_verified", "live_language_acceptance": "not_assessed_by_this_plan"},
            "mt": {"model": "gnani/gnani-evon-v3.3-30B-A3B", "catalog_status": "documented", "live_language_acceptance": "not_assessed_by_this_plan"},
            "tts": {"model": "timbre-v2.5", "voice": voice, "catalog_status": "documented", "account_access": "not_verified", "live_language_acceptance": "not_assessed_by_this_plan"}},
        "source_review": "pending", "meaning_review": "pending", "physical_device_acceptance": "pending"}
        for code, voice in VOICES.items()]
    routes = []
    for source in VOICES:
        for target in VOICES:
            if source == target: continue
            phase = "optimize_hindi_tamil" if (source, target) == ("hi", "ta") else "reverse_after_forward" if (source, target) == ("ta", "hi") else "expanded_test_purpose_only"
            eligible = True if phase == "optimize_hindi_tamil" else forward["passed"] if phase == "reverse_after_forward" else both_passed
            routes.append({"route_id": f"{source}-{target}", "source_language": source, "target_language": target,
                "phase": phase, "purpose": "bounded_acceptance_test", "eligible_for_test_review": eligible,
                "approval_granted": False, "automatic_execution": False,
                "case_options": [row["case_id"] for row in drafts if row["source_language"] == source],
                "voice": {"mode": "standard", "model": "timbre-v2.5", "name": VOICES[target]},
                "semantic_acceptance": "pending", "physical_latency_acceptance": "pending"})
    plan = {"schema_version": 1, "record_type": "latency_language_workflow_plan", "plan_id": "physical-gated-common-ten-v1",
        "plan_only": True, "provider_calls_made": 0, "approval_granted": False, "automatic_matrix_runner": False,
        "full_matrix_authorized": False, "full_matrix_eligible_for_test_review": both_passed,
        "catalog_checked_on": "2026-10-30", "catalog_source": "server/charcha/voice_catalog.py:TIMBRE_V25_STOCK_VOICES",
        "language_count": len(languages), "languages": languages, "planned_directed_pairs": len(routes),
        "optional_same_language_routes": len(VOICES), "draft_case_count": len(drafts), "draft_cases": drafts,
        "gate_policy": deepcopy(POLICY), "gates": {"hi_to_ta": forward, "ta_to_hi": reverse},
        "sequence": [
            {"id": "hi_to_ta", "title": "Optimize Hindi to Tamil first", "eligible_for_test_review": True, "requires": "fresh_explicit_bounded_operator_approval"},
            {"id": "ta_to_hi", "title": "Review the reverse direction", "eligible_for_test_review": forward["passed"], "requires": "forward_physical_gate_and_fresh_explicit_bounded_operator_approval"},
            {"id": "remaining_88", "title": "Other language pairs for test purposes", "eligible_for_test_review": both_passed, "requires": "both_physical_gates_and_new_individual_test_approvals"}],
        "routes": routes,
        "same_language_routes": [{"route_id": f"{code}-{code}", "source_language": code, "target_language": code,
            "microphone_path": "forward_original_without_stt_mt_tts", "self_output": False,
            "optional_test": True, "automatic_execution": False} for code in VOICES],
        "excluded": [{"code": "or", "reason": "Not in the current stock-voice speech catalog; Evon text support alone does not establish a full speech path."}],
        "evidence_note": "Existing paid protocol reports remain separate and immutable. STT-start/first-PCM, decoded RTC, synthetic tones and browser render estimates cannot satisfy this physical playback gate.",
        "approval_note": "No passing result grants API permission, creates a server or runs any matrix. Each next test needs fresh bounded human approval.",
        "sources": ["https://docs.gnani.ai/api/STT/stt-websocket", "https://docs.gnani.ai/api/TTS/available-voices",
                    "https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B"]}
    plan["plan_sha256"] = content_hash(plan)
    return plan


def load_observations(paths: list[Path]) -> list[dict]:
    result = []
    for path in paths:
        with path.open("rb") as file: data = file.read(1_048_577)
        if len(data) > 1_048_576: raise ValueError("Local evidence file exceeds the size limit")
        def unique(pairs):
            row = {}
            for key, value in pairs:
                if key in row: raise ValueError("Duplicate evidence keys are not accepted")
                row[key] = value
            return row
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite evidence is not accepted")))
        result.extend(value if isinstance(value, list) else [value])
        if len(result) > MAX_OBSERVATIONS or any(not isinstance(row, dict) for row in result):
            raise ValueError("Use at most 1000 local observation objects")
    return result


def main(argv=None) -> int:
    # A small fixed CLI avoids even argparse/gettext's locale environment reads.
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        print("Usage: plan_latency_language_workflow.py [--plan] [--evidence LOCAL.json ...]\nOffline assessment only; no run, approval or renewal action exists.")
        return 0
    paths, index, requested_plan = [], 0, False
    while index < len(arguments):
        if arguments[index] == "--plan" and not requested_plan:
            requested_plan = True
            index += 1
        elif arguments[index] == "--evidence" and index + 1 < len(arguments) and not arguments[index + 1].startswith("--"):
            paths.append(Path(arguments[index + 1]))
            index += 2
        else:
            print("Offline plan only: no run, approval or renewal action exists.", file=sys.stderr)
            return 2
    try:
        plan = build_plan(load_observations(paths))
        print(json.dumps(plan, ensure_ascii=True, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print("Offline workflow plan rejected invalid local evidence or fixtures; no provider request was made.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
