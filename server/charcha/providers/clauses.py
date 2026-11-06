"""Split a streamed translation into speakable clauses.

The split runs on the *translated* output, after the whole source sentence was
sent to the model, so meaning still comes from the full source context. Clauses
only decide when speech synthesis may start; they never change the text.
"""

from __future__ import annotations

# Sentence ends: Latin, Devanagari danda/double danda, Urdu-style full stop.
STRONG = frozenset(".!?।॥۔")
# Soft pauses: comma (Latin, Arabic/Urdu), semicolon, colon.
SOFT = frozenset(",;:،")


class ClauseSplitter:
    """Accumulate model deltas and release complete clauses.

    * A strong terminator followed by whitespace releases a clause of at least
      ``min_strong`` characters.
    * A soft pause followed by whitespace releases a clause of at least
      ``min_chars`` characters, so tiny fragments ("हाँ,") are not spoken alone.
    * A clause that reaches ``max_chars`` without punctuation is cut at the
      last space, so a long unpunctuated answer still starts speaking.

    Released pieces keep their original whitespace; ``"".join(pieces)`` equals
    the full streamed text. Callers strip each piece before synthesis.
    A punctuation mark is only a boundary once the next character is
    whitespace, so decimals ("3.5") and abbreviations without spaces stay whole.
    """

    def __init__(self, min_chars: int = 24, max_chars: int = 180, min_strong: int = 8):
        if not 1 <= min_strong <= min_chars < max_chars:
            raise ValueError("Invalid clause bounds")
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.min_strong = min_strong
        self.buffer = ""

    def feed(self, delta: str) -> list[str]:
        out: list[str] = []
        for char in delta:
            self.buffer += char
            piece = self._boundary()
            if piece:
                out.append(piece)
        return out

    def flush(self) -> list[str]:
        piece, self.buffer = self.buffer, ""
        return [piece] if piece else []

    def _boundary(self) -> str | None:
        buf = self.buffer
        if len(buf) >= 2 and buf[-1].isspace():
            mark = buf[-2]
            size = len(buf[:-1].strip())
            if (mark in STRONG and size >= self.min_strong) or (mark in SOFT and size >= self.min_chars):
                self.buffer = ""
                return buf
        if len(buf) >= self.max_chars:
            cut = buf.rfind(" ", 0, len(buf) - 1)
            if cut <= 0:
                cut = len(buf) - 1
            piece, self.buffer = buf[: cut + 1], buf[cut + 1:]
            return piece
        return None
