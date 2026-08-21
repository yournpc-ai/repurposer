"""Filler-word and repeated-take detection over ASR word timestamps.

Deterministic mechanics (the filler tool package's private module): no
LLM, pure functions on the
word stream (``Asset.meta["words"]`` = [{start, end, word}]). Conservative
lexicons on purpose — a false positive cuts real speech.
"""

import re
from dataclasses import dataclass, field

# Conservative: hesitation sounds only, no content words.
FILLER_LEXICON: dict[str, set[str]] = {
    "en": {"um", "uh", "er", "ah", "mm", "hmm"},
    "zh": {"呃", "嗯", "啊", "那个"},
}

# Adjacent repeated n-grams of this size range count as repeated takes; the
# FIRST occurrence is the failed take (marked for removal).
_REPEAT_NGRAM_MIN = 2
_REPEAT_NGRAM_MAX = 6


@dataclass
class FillerReport:
    filler_ranges: list[tuple[float, float]] = field(default_factory=list)
    repeat_ranges: list[tuple[float, float]] = field(default_factory=list)

    @property
    def ranges(self) -> list[tuple[float, float]]:
        return sorted(self.filler_ranges + self.repeat_ranges)

    @property
    def filler_count(self) -> int:
        return len(self.filler_ranges)

    @property
    def repeat_count(self) -> int:
        return len(self.repeat_ranges)


def _normalize(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def detect(words: list[dict], language: str) -> FillerReport:
    """Find filler words and repeated takes in a word stream.

    ``words`` items carry start/end seconds + the surface word; ``language``
    picks the lexicon (unknown languages fall back to English + Chinese
    combined — the lexicons are disjoint).
    """
    report = FillerReport()
    lexicon = FILLER_LEXICON.get(language) or (
        FILLER_LEXICON["en"] | FILLER_LEXICON["zh"]
    )

    normalized = [_normalize(str(w.get("word", ""))) for w in words]

    for w, norm in zip(words, normalized):
        if norm and norm in lexicon:
            start, end = float(w["start"]), float(w["end"])
            if end > start:
                report.filler_ranges.append((start, end))

    # Repeated takes: the speaker restarts a phrase ("I think we — I think we
    # should"). The first occurrence is the failed take → mark it for removal.
    i = 0
    n = len(words)
    while i < n:
        marked = False
        for size in range(min(_REPEAT_NGRAM_MAX, (n - i) // 2), _REPEAT_NGRAM_MIN - 1, -1):
            first = normalized[i : i + size]
            second = normalized[i + size : i + 2 * size]
            if any(first) and first == second:
                start = float(words[i]["start"])
                end = float(words[i + size - 1]["end"])
                if end > start:
                    report.repeat_ranges.append((start, end))
                i += size  # keep the second (better) take; continue after it
                marked = True
                break
        if not marked:
            i += 1

    return report
