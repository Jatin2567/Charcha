"""Print a bounded five-language speech plan or blank review CSV; never execute it.

Standard library only. No environment, application settings, providers, network,
audio, approval ledger or cloud access. Prompts reuse the draft language matrix.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import sys
from decimal import Decimal

from plan_language_matrix import CASES, LANGUAGES, content_hash


PLAN_ID = "five-language-latency-before-screening-v1"
LANGUAGE_CODES = ("hi", "ta", "bn", "te", "mr")
REPEATS = ("planned_cold_route", "planned_warm_repeat_1", "planned_warm_repeat_2")
LIMITS = {
    "stt_seconds": 15, "stt_connections": 1,
    "mt_requests": 1, "mt_characters": 500,
    "tts_requests": 1, "tts_characters": 300, "voice_enrollments": 0,
}
RESULT_FIELDS = (
    "observed_at", "room_code", "usage_flow_id", "performance_sample_id",
    "status", "error_stage", "failure_detail", "observed_setup_state",
    "source_draft_reviewer", "source_draft_agrees_with_meaning",
    "actual_transcript", "transcript_review", "actual_target_text",
    "target_bilingual_reviewer", "meaning_preserved", "number_negation_unit_review",
    "listener_heard_target_voice", "wrong_target_or_self_audio", "original_double_playback",
    "queue_ms", "stt_processing_to_transcript_ms", "mt_ms", "tts_first_pcm_ms",
    "server_queue_to_first_pcm_plus_stt_ms", "stt_marker_present",
    "listener_common_clock_method", "listener_common_clock_evidence_id",
    "source_phrase_end_on_common_clock_ms", "listener_audio_onset_on_common_clock_ms",
    "listener_phrase_end_to_audio_onset_ms", "gcp_runtime_seconds", "gcp_spend_inr",
    "stt_reserved_seconds", "tts_reserved_characters", "gnani_reference_inr",
    "actual_gnani_billed_inr", "next_action",
)
CSV_FIELDS = (
    "plan_id", "plan_sha256", "trial_id", "trial_sha256", "route_id", "route_sha256",
    "source_language", "target_language", "planned_setup", "source_draft",
    "source_reference_status", "draft_expected_meaning", "target_standard_voice",
    "review_status", "approval_granted",
) + RESULT_FIELDS


def build_plan() -> dict:
    catalog = {entry[0]: entry for entry in LANGUAGES}
    languages = [
        {"code": code, "name": catalog[code][1], "bcp47": catalog[code][2],
         "standard_voice": catalog[code][3], "live_acceptance": "not_verified"}
        for code in LANGUAGE_CODES
    ]
    routes, trials = [], []
    for source in LANGUAGE_CODES:
        focus, prompt, meaning = CASES[source]
        for target in LANGUAGE_CODES:
            if source == target:
                continue
            route = {
                "route_id": f"{source}-{target}-{focus}",
                "source_language": source, "target_language": target,
                "source_text": prompt, "source_characters": len(prompt),
                "review_focus": focus, "expected_meaning": list(meaning),
                "source_reference_status": "unreviewed_draft", "target_reference": None,
                "semantic_result": "not_tested",
                "voice": {"mode": "standard", "model": "timbre-v2.5", "name": catalog[target][3]},
            }
            route["route_sha256"] = content_hash(route)
            routes.append(route)
            for index, setup in enumerate(REPEATS, 1):
                trial = {
                    "trial_id": f"{source}-{target}-r{index}", "route_id": route["route_id"],
                    "route_sha256": route["route_sha256"], "planned_setup": setup,
                    "observed_setup_state": None, "stage": "latency", "input_kind": "audio",
                    "screening_mode": "off", "voice_mode": "standard",
                    "participants": 2, "microphone_speakers_at_once": 1,
                    "listener_microphone": "muted", "review_status": "pending",
                    "proposed_flow": {
                        "approval_granted": False, "purpose": "live_interpretation",
                        "expiry_seconds": 120, "budgets": copy.deepcopy(LIMITS),
                        "stt_budget_includes_handshake_and_idle": True,
                        "automatic_retries": 0, "renewal_requires_new_approval": True,
                    },
                    "measurements": {key: None for key in RESULT_FIELDS},
                }
                trial["trial_sha256"] = content_hash(trial)
                trials.append(trial)
    count = len(trials)
    stt_seconds = count * LIMITS["stt_seconds"]
    tts_characters = count * LIMITS["tts_characters"]
    stt_inr = Decimal(stt_seconds) * Decimal("27") / Decimal("3600")
    tts_inr = Decimal(tts_characters) * Decimal("27") / Decimal("10000")
    plan = {
        "schema_version": 1, "plan_id": PLAN_ID, "plan_only": True,
        "provider_calls_made": 0, "gpu_resources_started": 0,
        "approval_granted": False, "full_matrix_authorized": False,
        "automatic_matrix_runner": False, "voice_cloning_deferred": True,
        "language_codes": list(LANGUAGE_CODES), "languages": languages,
        "planned_directed_pairs": len(routes), "planned_observations": count,
        "observations_per_pair": len(REPEATS), "simultaneous_user_count_required": 2,
        "completed_observations": 0, "results_status": "not_run",
        "budget": {
            "gcp_project_ceiling_inr": 5000, "gcp_latency_stage_ceiling_inr": 2500,
            "gcp_reserved_for_later_inr": 2500,
            "scope": "GCP resource charges; Gnani speech reference is separate",
            "gcp_price_and_runtime_estimate": None, "actual_gcp_spend_inr": None,
            "gcp_budget_is_not_a_provider_flow_grant": True,
            "gnani_each_flow_requires_approval": True,
            "reference_rates_source": "user-supplied Gnani pricing table",
            "stt_inr_per_hour": "27.00", "tts_inr_per_10000_characters": "27.00",
            "max_stt_seconds": stt_seconds, "max_tts_characters": tts_characters,
            "max_mt_requests": count, "max_mt_source_characters": count * LIMITS["mt_characters"],
            "max_stt_connections": count, "max_tts_requests": count,
            "stt_reference_inr": str(stt_inr.quantize(Decimal("0.01"))),
            "tts_reference_inr": str(tts_inr.quantize(Decimal("0.01"))),
            "speech_reference_inr": str((stt_inr + tts_inr).quantize(Decimal("0.01"))),
            "actual_gnani_billed_inr": None, "programme_credit_conversion": None,
            "reference_is_invoice_or_grant": False,
            "reference_excludes": ["provider billing rounding", "tax", "GPU and other GCP charges", "additional or replacement trials"],
            "stop_rule": "Stop before the next flow if conservative remaining GCP cost would exceed the stage or project ceiling; quota, billing and a bounded runtime must be checked first.",
        },
        "sequence": [
            "Review the draft phrases with a speaker of each source language; correct and re-hash before any approval.",
            "Verify GPU quota, model access, selected image/model revisions, serving readiness, explicit auto-stop and remaining GCP stage budget.",
            "Verify all five selected languages and standard voices in the current account without assuming documented support proves live access.",
            "Join two participants with screening off, standard voices and the listener microphone muted.",
            "Approve only the next identified bounded trial, speak its one prompt once, then mute/close the source flow by its 15-second STT cap.",
            "Record latency, failures and manual meaning/listener review for each route's planned cold and two repeat trials. Do not automatically retry failures.",
            "Export actual evidence and review latency results before the separate deepfake-screening protocol.",
            "Repeat selected accepted routes on two physical devices with explicit HTTPS trust before claiming device-to-device acceptance. Voice cloning stays deferred.",
        ],
        "setup_notes": [
            "Cold means a newly joined route/output path with an already loaded GPU model, not GPU boot or model-download time.",
            "Repeat labels are planned conditions. Recreated tracks/rooms or unknown cache state must be recorded; do not claim a warm transport merely from trial order.",
            "Every trial is a separate bounded approval, including repeats; keep the model loaded only within the bounded GCP session.",
            "One prompt is spoken once. Additional finalized STT segments may exhaust the one-MT/one-TTS limits; retain that as a failed trial instead of increasing limits.",
            "Text longer than either character cap must fail closed and be reviewed, not silently truncated or funded by a new grant.",
        ],
        "metric_boundaries": {
            "queue_ms": "Application work queue wait on the server clock.",
            "stt_processing_to_transcript_ms": "Gnani processing event to final transcript; null when no processing marker is received. Not source acoustic phrase-end delay.",
            "mt_ms": "Application translation request timing on the server clock.",
            "tts_first_pcm_ms": "Application synthesis/output-path start to first server PCM; inspect output/subscriber readiness effects.",
            "server_queue_to_first_pcm_plus_stt_ms": "Queue entry to first server PCM plus available STT marker duration; partial when STT marker is absent. Not listener or microphone-to-speaker latency.",
            "listener_phrase_end_to_audio_onset_ms": "Listener output onset minus source phrase end measured in one consented shared-clock recording. Otherwise leave blank; never subtract independent device clocks.",
        },
        "reporting_rules": [
            "All pending measurement fields remain null/blank. An offline consistency test is not a live E2E result.",
            "Retain every scheduled trial including errors, cancellations and missing markers; show attempted/completed counts per direction.",
            "Show individual observations and descriptive medians. Three trials per pair, with only two planned warm repeats, do not establish a reliable p95 or a latency SLA.",
            "Keep cold/repeat, partial/complete and server/listener measurements separate. Do not average stage percentiles into an end-to-end percentile.",
            "One source prompt per language is smoke coverage; bilingual semantic review is required and does not establish general translation accuracy.",
            "Screening accuracy and latency require the separate genuine/spoof protocol after this latency pass. No detector or voice-cloning claim follows from this plan.",
        ],
        "routes": routes, "trials": trials,
    }
    plan["plan_sha256"] = content_hash(plan)
    return plan


def csv_safe(value: object) -> str:
    """Keep spreadsheet imports from interpreting draft/user text as a formula."""
    text = str(value)
    return "'" + text if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def review_csv(plan: dict | None = None) -> str:
    plan = build_plan() if plan is None else plan
    routes = {route["route_id"]: route for route in plan["routes"]}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for trial in plan["trials"]:
        route = routes[trial["route_id"]]
        row = dict.fromkeys(CSV_FIELDS, "")
        row.update({
            "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"],
            "trial_id": trial["trial_id"], "trial_sha256": trial["trial_sha256"],
            "route_id": route["route_id"], "route_sha256": route["route_sha256"],
            "source_language": route["source_language"], "target_language": route["target_language"],
            "planned_setup": trial["planned_setup"], "source_draft": route["source_text"],
            "source_reference_status": route["source_reference_status"],
            "draft_expected_meaning": " | ".join(route["expected_meaning"]),
            "target_standard_voice": route["voice"]["name"],
            "review_status": "pending", "approval_granted": "false",
        })
        writer.writerow({key: csv_safe(value) for key, value in row.items()})
    return output.getvalue()


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        print("Usage: plan_five_language_test.py [--plan | --review-csv]\nPrint an offline plan or blank CSV. No execute, approve or renew action exists.")
        return 0
    if arguments == ["--review-csv"]:
        # Explicit UTF-8 stdout for native Windows consoles; no files are opened.
        output = review_csv()
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(output.encode("utf-8"))
        else:
            print(output, end="")
        return 0
    if arguments not in ([], ["--plan"]):
        print("Plan only: this script cannot run, approve or renew provider flows.", file=sys.stderr)
        return 2
    print(json.dumps(build_plan(), ensure_ascii=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
