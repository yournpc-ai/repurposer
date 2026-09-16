"""align_stills' private procedure: estimated speaking timeline (RECIPES §2
third time source — reading pace).

No recording -> no ASR words. Caption timing for a photo-slideshow clip is
derived from the transcript text itself at reading pace; the resulting word
dicts are the SAME shape as ASR output ({"word","start","end"}), so the
stills branch / anchored transcript / locate_span consume them untouched.

Reading-pace constants: zh counts CJK characters, latin scripts count
whitespace-ish tokens. Deliberately mid-tempo — captions that linger a beat
too long read better than captions that rush.
"""

import re
from typing import Any

_CHARS_PER_SECOND_ZH = 4.5
_TOKENS_PER_SECOND_LATIN = 2.6
_SENTENCE_GAP_S = 0.35
_CLAUSE_GAP_S = 0.1

_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")
_TOKEN_RE = re.compile(r"[A-Za-z0-9’'\-]+|[一-鿿぀-ヿ가-힯]")
_SENTENCE_RE = re.compile(r"[^.!?。！？;；\n]+[.!?。！？;；]?")
_SENTENCE_END = frozenset(".!?。！？;；")


def estimate_words_timeline(text: str) -> list[dict[str, Any]]:
    """Transcript text -> estimated word-level timeline at reading pace.

    Sentences advance by their own estimated duration plus a small gap; zh is
    chunked into 2-char "words" so caption lines read like ASR zh output
    (cue spans are joined with spaces downstream, same as whisper tokens).
    """
    words: list[dict[str, Any]] = []
    t = 0.0
    for sentence in _SENTENCE_RE.findall(text):
        raw = _TOKEN_RE.findall(sentence)
        if not raw:
            continue
        # Group consecutive single CJK chars into 2-char chunks; latin tokens
        # stay whole. Trailing sentence punctuation rides the last token.
        tokens: list[str] = []
        cjk_buf = ""
        for tok in raw:
            if _CJK_RE.match(tok):
                cjk_buf += tok
                if len(cjk_buf) == 2:
                    tokens.append(cjk_buf)
                    cjk_buf = ""
            else:
                if cjk_buf:
                    tokens.append(cjk_buf)
                    cjk_buf = ""
                tokens.append(tok)
        if cjk_buf:
            tokens.append(cjk_buf)
        tail = sentence.rstrip()[-1:] if sentence.rstrip() else ""
        if tail in ".!?。！？;；,，、:：" and tokens:
            tokens[-1] += tail

        for tok in tokens:
            cjk_chars = len(_CJK_RE.findall(tok))
            has_latin = bool(re.search(r"[A-Za-z0-9]", tok))
            dur = cjk_chars / _CHARS_PER_SECOND_ZH + (
                1 / _TOKENS_PER_SECOND_LATIN if has_latin else 0
            )
            dur = max(dur, 0.12)
            words.append({"word": tok, "start": round(t, 3), "end": round(t + dur, 3)})
            t += dur
        t += _SENTENCE_GAP_S if tail in _SENTENCE_END else _CLAUSE_GAP_S
    return words


def cjk_ratio(text: str) -> float:
    """CJK character share of ``text`` (language heuristic for the estimate)."""
    return len(_CJK_RE.findall(text)) / max(1, len(text))
