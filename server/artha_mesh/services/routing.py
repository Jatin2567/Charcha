from collections.abc import Iterable

from ..models import Participant


def recipients_for(
    participants: Iterable[Participant], speaker_id: str, target_language: str
) -> list[str]:
    return [
        p.id for p in participants
        if p.id != speaker_id and not p.is_agent and p.language == target_language
    ]


def target_languages(participants: Iterable[Participant], speaker_id: str) -> set[str]:
    return {p.language for p in participants if p.id != speaker_id and not p.is_agent}
