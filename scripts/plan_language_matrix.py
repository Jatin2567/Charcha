"""Print a standard-voice language test matrix. Never run or approve a test.

Standard library only: no settings, environment, provider, ledger, network or
audio access. The phrases are draft review prompts, not trusted translations.
"""
from __future__ import annotations

import hashlib
import json
import sys

PLAN_ID = "common-ten-standard-language-matrix-v1"
BASELINE_CODES = ("hi", "ta", "bn", "en")
LANGUAGES = (
    ("hi", "Hindi", "hi-IN", "Nalini"),
    ("ta", "Tamil", "ta-IN", "Trisha"),
    ("bn", "Bengali", "bn-IN", "Kirra"),
    ("en", "English", "en-IN", "Pranav"),
    ("te", "Telugu", "te-IN", "Suhana"),
    ("kn", "Kannada", "kn-IN", "Saanvi"),
    ("ml", "Malayalam", "ml-IN", "Reshma"),
    ("mr", "Marathi", "mr-IN", "Zahira"),
    ("gu", "Gujarati", "gu-IN", "Falak"),
    ("pa", "Punjabi", "pa-IN", "Mehuli"),
)
CASES = {
    "hi": ("meeting-time", "हम 10 बजे मिलेंगे, 11 बजे नहीं।",
           ("Meet at 10", "11 is rejected", "Do not invent a date or time zone")),
    "ta": ("book-colour", "எனக்கு நீலப் புத்தகம் வேண்டும், சிவப்பு வேண்டாம்.",
           ("The speaker wants the blue book", "Red is rejected")),
    "bn": ("relative-day", "আগামীকাল সকাল 9টায় লাইব্রেরিতে দেখা করব, আজ নয়।",
           ("Meet tomorrow morning at 9", "Meet at the library", "Today is rejected")),
    "en": ("polite-condition", "Could you close the window after I call, not before?",
           ("A polite request to close the window", "Only after I call", "Not before the call")),
    "te": ("decimal-unit", "ఈ సీసాలో 1.5 లీటర్ల నీరు ఉంది, 150 మిల్లీలీటర్లు కాదు.",
           ("The bottle contains 1.5 litres of water", "150 millilitres is rejected")),
    "kn": ("directions", "ಮೊದಲು ಎಡಕ್ಕೆ ತಿರುಗಿ, ನಂತರ 200 ಮೀಟರ್ ನೇರವಾಗಿ ಹೋಗಿ.",
           ("Turn left first", "Then go straight for 200 metres", "Preserve the order and unit")),
    "ml": ("name-association", "ചുവന്ന പുസ്തകം മീനയ്ക്കും പച്ച പുസ്തകം രവിക്കും കൊടുക്കൂ.",
           ("Give the red book to Meena", "Give the green book to Ravi", "Do not swap the associations")),
    "mr": ("past-tense", "काल संध्याकाळी आम्ही उद्यानात भेटलो होतो.",
           ("We met at the park yesterday evening", "The meeting already happened")),
    "gu": ("conditional-plan", "જો વરસાદ પડે તો આપણે ઘરની અંદર રમીશું, નહીં તો બગીચામાં જઈશું.",
           ("If it rains, play indoors", "Otherwise go to the park", "This is a conditional plan, not a weather prediction")),
    "pa": ("mixed-identifiers", "ਅਸੀਂ Room AM-204 ਵਿੱਚ ਮਿਲਾਂਗੇ। Wi-Fi ਦਾ ਨਾਮ Lotus Guest ਹੈ।",
           ("Meet in Room AM-204", "The Wi-Fi network name is Lotus Guest", "Preserve both identifiers")),
}


def content_hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def speaker_flow(source: str, listener_languages: list[str]) -> dict:
    """Describe one microphone speaker's fan-out, without constructing a client."""
    known = {entry[0] for entry in LANGUAGES}
    if source not in known or any(language not in known for language in listener_languages):
        raise ValueError("Use only a documented common language code from this plan")
    translated = sorted(set(listener_languages) - {source})
    return {
        "source_language": source,
        "different_target_languages": translated,
        "stt_connections_while_unmuted": int(bool(translated)),
        "mt_jobs_per_utterance": len(translated),
        "tts_jobs_per_utterance": len(translated),
        "same_language_original_forwarding": source in listener_languages,
        "self_output": False,
        "voice_mode": "standard",
    }


def build_plan() -> dict:
    languages = [
        {"code": code, "name": name, "bcp47": locale, "standard_voice": voice,
         "provider_contract": "documented_common_stt_evon_tts", "live_acceptance": "not_verified"}
        for code, name, locale, voice in LANGUAGES
    ]
    voices = {entry["code"]: entry["standard_voice"] for entry in languages}
    routes = []
    for source, *_rest in LANGUAGES:
        focus, text, meaning = CASES[source]
        for target, *_rest in LANGUAGES:
            if source == target:
                continue
            route = {
                "route_id": f"{source}-{target}-{focus}",
                "source_language": source,
                "target_language": target,
                "source_text": text,
                "source_characters": len(text),
                "review_focus": focus,
                "expected_meaning": list(meaning),
                "source_reference_status": "unreviewed_draft",
                "target_reference": None,
                "semantic_result": "not_tested",
                "voice": {"mode": "standard", "model": "timbre-v2.5", "name": voices[target]},
                "first_phase": "baseline_four" if source in BASELINE_CODES and target in BASELINE_CODES else "expanded_ten",
                "proposed_individual_typed_flow": {
                    "approval_granted": False,
                    "purpose": "live_interpretation",
                    "expiry_seconds": 120,
                    "budgets": {
                        "stt_seconds": 0, "stt_connections": 0,
                        "mt_requests": 1, "mt_characters": len(text),
                        "tts_requests": 1, "tts_characters": 200, "voice_enrollments": 0,
                    },
                    "automatic_retries": 0,
                    "evon_charge": None,
                    "actual_billed_total": None,
                },
            }
            route["route_sha256"] = content_hash(route)
            routes.append(route)
    plan = {
        "schema_version": 1,
        "plan_id": PLAN_ID,
        "plan_only": True,
        "provider_calls_made": 0,
        "approval_granted": False,
        "full_matrix_authorized": False,
        "automatic_matrix_runner": False,
        "baseline_language_codes": list(BASELINE_CODES),
        "baseline_directed_pairs": len(BASELINE_CODES) * (len(BASELINE_CODES) - 1),
        "common_language_count": len(LANGUAGES),
        "planned_directed_pairs": len(routes),
        "simultaneous_user_count_required": 2,
        "capability_note": "Provider documentation describes the common language set. Account access, application enablement and translation quality each need separate verification.",
        "languages": languages,
        "excluded": [
            {"code": "or", "reason": "Odia is listed for Evon but absent from the documented live STT/TTS common set; full spoken interpretation is not claimed."},
            {"code": "dedicated_code_mix_modes", "reason": "Hinglish/Tanglish/Benglish codes and automatic language detection are outside this matrix. Mixed words/identifiers in a chosen language remain experimental review cases."},
        ],
        "sequence": [
            "Obtain the official Evon endpoint/model/authentication contract; retain the existing account key.",
            "Approve and review the existing two-turn Hindi/Tamil typed smoke plan first; this matrix does not approve it.",
            "Review the other baseline-four typed routes one individually approved flow at a time.",
            "Add microphone STT only after typed MT/TTS passes, with a separate bounded approval.",
            "Repeat the accepted two-person cases on the second device and hosted interface.",
            "Extend pairwise acceptance to the other six common languages; review every directed route separately.",
            "Test three-party fan-out, duplicate target languages, overlap, mute, leave and recovery as later gates.",
            "Keep voice cloning deferred until standard voices and earlier gates pass.",
        ],
        "branch_examples": [speaker_flow("hi", ["ta", "ta", "bn", "hi"]), speaker_flow("hi", ["hi"])],
        "required_evidence_per_route": [
            "Human confirmation that the draft source phrase and English meaning agree",
            "Actual source transcript for microphone input, assessed separately from MT",
            "Bilingual review of target meaning, numbers, negation, units, names and intent",
            "Audible target-language speech, route identity, no self output or original double playback",
            "Performance stage timings, sample count, completion/failure and Usage reservations",
            "Listener delay only from a described shared-timebase method; otherwise unknown",
        ],
        "limitations": [
            "One draft prompt per direction is smoke coverage, not a comprehensive translation benchmark.",
            "Offline matrix consistency and mock routing tests do not prove model access, meaning preservation or speech quality.",
            "A shared target-language track's first subscriber readiness does not prove every listener is ready; later multi-party listening acceptance is required.",
            "Same-language microphone audio forwards without MT/TTS. Typed same-language fallback can synthesize and is outside these cross-language pairs.",
        ],
        "routes": routes,
    }
    plan["plan_sha256"] = content_hash(plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        print("Usage: plan_language_matrix.py [--plan]\nPrint an offline matrix; no run or approval action exists.")
        return 0
    if arguments not in ([], ["--plan"]):
        print("Plan only: this script cannot run, approve or renew provider flows.", file=sys.stderr)
        return 2
    print(json.dumps(build_plan(), ensure_ascii=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
