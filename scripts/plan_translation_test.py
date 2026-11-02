"""Print the fixed Hindi/Tamil standard-voice test plan, without running it.

This script imports no application configuration or provider code, reads no
environment file, opens no ledger, and performs no network or audio operation.
"""
from __future__ import annotations

import hashlib
import json
import sys

PLAN_ID = "hi-ta-standard-typed-v1"
CASES = (
    (
        "hi-ta-meeting-time",
        "hi",
        "ta",
        "हम 10 बजे मिलेंगे, 11 बजे नहीं।",
        ("Meet at 10", "11 is explicitly rejected", "No invented date or time zone"),
    ),
    (
        "ta-hi-book-colour",
        "ta",
        "hi",
        "எனக்கு நீலப் புத்தகம் வேண்டும், சிவப்பு வேண்டாம்.",
        ("The speaker wants the blue book", "Red is explicitly rejected", "Keep the request's meaning"),
    ),
)


def content_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_plan() -> dict:
    cases = []
    for case_id, source, target, text, expected in CASES:
        case = {
            "case_id": case_id,
            "source_language": source,
            "target_language": target,
            "source_text": text,
            "source_characters": len(text),
            "expected_meaning": list(expected),
            "review_status": "human_bilingual_review_required",
        }
        case["case_sha256"] = content_hash(case)
        cases.append(case)
    plan = {
        "schema_version": 1,
        "plan_id": PLAN_ID,
        "plan_only": True,
        "provider_calls_made": 0,
        "approval_granted": False,
        "input_kind": "text",
        "microphones": "off_for_both_participants",
        "voice": {
            "mode": "standard",
            "model": "timbre-v2.5",
            "by_target_language": {"hi": "Nalini", "ta": "Trisha"},
            "account_language_availability": "not_verified",
        },
        "flow": {
            "purpose": "live_interpretation",
            "expiry_seconds": 120,
            "budgets": {
                "stt_seconds": 0,
                "stt_connections": 0,
                "mt_requests": 2,
                "mt_characters": sum(case["source_characters"] for case in cases),
                "tts_requests": 2,
                "tts_characters": 400,
                "voice_enrollments": 0,
            },
            "automatic_retries": 0,
            "on_failure": "Stop; do not resubmit or renew without a separate human approval.",
        },
        "cases": cases,
        "cost_reference": {
            "standard_tts_inr_per_10000_characters": 27,
            "standard_tts_inr_at_full_character_budget": 1.08,
            "evon_charge": None,
            "actual_billed_total": None,
            "programme_credit_conversion": None,
            "note": "User-supplied TTS rate only; billing rounding and Evon pricing are unverified.",
        },
        "required_before_approval": [
            "Official Evon endpoint, served model ID and authentication contract",
            "Configure the documented Evon authentication header using the existing Gnani key",
            "Disclose Evon pricing if supplied, or explicitly keep its bounded-flow charge unknown",
            "Two joined Hindi/Tamil members with working audio and standard voices",
            "Human approval of this exact two-turn plan before any provider call",
        ],
        "record": [
            "Case ID and source/translated text reviewed",
            "Bilingual meaning and audible target-language result",
            "MT, first-PCM, completion/failure and Usage reservations",
            "Listener delay only when measured by a described shared-timebase method",
        ],
        "next_stage": {
            "input_kind": "microphone_audio",
            "approval_granted": False,
            "status": "Separate plan and approval after the typed pair passes",
            "voice_cloning": "deferred",
        },
    }
    plan["plan_sha256"] = content_hash(plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        print("Usage: plan_translation_test.py [--plan]\nPrint a fixed offline plan. No run or approval action is supported.")
        return 0
    if arguments not in ([], ["--plan"]):
        print("Plan only: use no arguments or --plan. This script cannot run or approve a provider flow.", file=sys.stderr)
        return 2
    # ASCII console output works with Windows legacy encodings; JSON retains
    # the exact Unicode source phrases through its standard escape sequences.
    print(json.dumps(build_plan(), indent=2, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
