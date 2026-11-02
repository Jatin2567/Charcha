"""Documented stock-voice preferences, not claims of tested synthesis quality.

Source: https://docs.gnani.ai/api/TTS/available-voices
Catalogs are model-specific; v2.5 voices must not be applied to v3.0.
"""
from collections.abc import Mapping

LEGACY_DEFAULT_TIMBRE_VOICE = "Nalini"
TIMBRE_V25_STOCK_VOICES = {
    "hi": "Nalini", "ta": "Trisha", "bn": "Kirra", "en": "Pranav",
    "te": "Suhana", "kn": "Saanvi", "ml": "Reshma", "mr": "Zahira",
    "gu": "Falak", "pa": "Mehuli",
}


def select_stock_voice(
    language: str, *, model: str, global_voice: str, overrides: Mapping[str, str],
) -> str:
    """Explicit language override, legacy custom global, then model defaults.

    Existing custom TIMBRE_VOICE configurations retain their global behavior.
    The old default Nalini becomes the v2.5 Hindi preference, rather than being
    silently used for every newly supported language. Other models keep their
    configured global voice and never inherit this v2.5-only catalog.
    """
    override = overrides.get(language, "").strip()
    if override:
        return override
    if model == "timbre-v2.5" and global_voice == LEGACY_DEFAULT_TIMBRE_VOICE:
        return TIMBRE_V25_STOCK_VOICES.get(language, global_voice)
    return global_voice
