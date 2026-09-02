"""Incremental prose extraction from a streaming JSON verdict (chat SSE).

The intent agents answer with one structured JSON verdict whose user-facing
prose lives in a string field (``answer`` for the book path's InferredIntent,
``text`` / ``summary`` for the chat loop's IntentResult). When the LLM call
streams, the raw JSON arrives character by character; this extractor watches
the accumulating stream and yields the prose field's *decoded* content as it
grows, so the chat surface can typewriter the answer while the verdict is
still generating. The fully-assembled JSON is validated afterwards exactly as
before — the deltas are a preview channel only, never the source of truth.

Design rules (pressure-tested 2026-08-04):
- **Depth-gated keys**: a target key is accepted only at object depth 1–2
  (bare proposal shape or the ``{"proposal": {...}}`` wrapper). This rejects
  ``<think>`` preambles (depth 0) and deeply nested lookalikes like
  ``ops[i].params.text`` (depth ≥ 3).
- **Think-block skip**: an optional leading ``<think>…</think>`` preamble is
  discarded before structural scanning, so example JSON inside the model's
  reasoning can never trigger capture.
- **Non-string values go dead**: ``"answer": null`` (generate/start verdicts)
  latches the extractor off — zero deltas, the final envelope lands as one
  piece exactly like the non-streaming path.
- **Any surprise goes dead**: malformed escapes, control characters, or
  structural confusion disable the extractor silently. Worst case is no
  preview — never wrong preview.
"""

from __future__ import annotations

_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

# Extractor states.
_SCANNING = "scanning"  # structural scan, looking for a target key
_AFTER_KEY = "after_key"  # a string token completed; expect ':' (key) or not
_EXPECT_VALUE = "expect_value"  # target key confirmed; expect its value
_CAPTURING = "capturing"  # inside the prose string, decoding
_DONE = "done"  # prose string closed; never emit again

# A think preamble is only skipped at the very start of the stream (matches
# _clean_json's assumption in the MiniMax client).
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


class ProseDeltaExtractor:
    """Feed raw JSON fragments, get back decoded prose deltas."""

    def __init__(self, target_keys: tuple[str, ...]) -> None:
        self._targets = target_keys
        self._state = _SCANNING
        self._dead = False

        # Structural scan state.
        self._depth = 0
        self._in_string = False
        self._escaped = False

        # Candidate-key tracking.
        self._key_buf = ""
        self._key_depth = 0

        # Think-preamble skip (start-of-stream only).
        self._prelude = ""  # accumulates until think/payload decision
        self._prelude_done = False
        self._think_skip = False

        # Capture state.
        self._escape_buf = ""  # incomplete escape sequence across chunks
        self._high_surrogate: int | None = None  # \uD800-\uDBFF awaiting its low
        self._out: list[str] = []  # decoded chars ready to emit

    @property
    def dead(self) -> bool:
        """True once the extractor has permanently given up (or finished)."""
        return self._dead or self._state == _DONE

    def feed(self, chunk: str) -> str:
        """Consume a raw JSON fragment; return newly decoded prose (maybe '')."""
        if self.dead:
            return ""
        for char in chunk:
            self._step(char)
            if self.dead:
                break
        out = "".join(self._out)
        self._out.clear()
        return out

    # ------------------------------------------------------------------
    # State machine

    def _step(self, char: str) -> None:
        if not self._prelude_done:
            self._step_prelude(char)
            return
        if self._state == _CAPTURING:
            self._step_capture(char)
            return
        self._step_structural(char)

    def _step_prelude(self, char: str) -> None:
        """Skip an optional leading ``<think>…</think>`` block."""
        self._prelude += char
        if self._think_skip:
            if self._prelude.endswith(_THINK_CLOSE):
                self._prelude = ""
                self._prelude_done = True
                self._think_skip = False
            return
        # Not (or no longer) a think preamble: decide from what's buffered.
        stripped = self._prelude.lstrip()
        if stripped == "" or _THINK_OPEN.startswith(stripped):
            return  # still could become a think block — keep buffering
        if stripped.startswith(_THINK_OPEN):
            self._think_skip = True
            return
        # Real payload (JSON or a markdown fence) — replay buffered chars.
        self._prelude_done = True
        buffered, self._prelude = self._prelude, ""
        for buffered_char in buffered:
            self._step_structural(buffered_char)

    def _step_structural(self, char: str) -> None:
        """Brace/string tracking + target-key detection (non-capture states)."""
        if self._state == _EXPECT_VALUE:
            # Dedicated sub-state: no structural tracking — the next non-ws
            # char either opens the prose string or latches the extractor off.
            if char in " \t\r\n":
                return
            if char == '"':
                self._state = _CAPTURING
                self._escape_buf = ""
                return
            # null / number / bool / object / array — not prose.
            self._dead = True
            return

        if self._in_string:
            if self._escaped:
                self._escaped = False
                if self._state == _SCANNING:
                    self._key_buf += char
            elif char == "\\":
                self._escaped = True
            elif char == '"':
                self._in_string = False
                if self._state == _SCANNING:
                    # A string token completed — maybe a key. Depth was read
                    # when the token opened (its content can't change depth).
                    self._state = _AFTER_KEY
            else:
                if self._state == _SCANNING:
                    self._key_buf += char
            return

        if char == '"':
            self._in_string = True
            if self._state == _SCANNING:
                self._key_buf = ""
                self._key_depth = self._depth
            return
        if char in "{[":
            self._depth += 1
            if self._state in (_AFTER_KEY, _EXPECT_VALUE):
                self._reject_position()
            return
        if char in "}]":
            self._depth -= 1
            if self._depth < 0:
                self._dead = True
                return
            if self._state in (_AFTER_KEY, _EXPECT_VALUE):
                self._reject_position()
            return

        if self._state == _AFTER_KEY:
            if char in " \t\r\n":
                return
            if char == ":":
                if (
                    self._key_buf in self._targets
                    and 1 <= self._key_depth <= 2
                ):
                    self._state = _EXPECT_VALUE
                else:
                    self._state = _SCANNING
                return
            # Not a key — the token was a value; this char needs structural
            # handling (it can't be a quote/brace here — those returned above).
            self._state = _SCANNING
            return

    def _reject_position(self) -> None:
        """A structural char where a key colon / value was expected."""
        if self._state == _EXPECT_VALUE:
            # Value is an object/array — not prose.
            self._dead = True
        else:
            self._state = _SCANNING

    # ------------------------------------------------------------------
    # Capture + escape decoding

    def _step_capture(self, char: str) -> None:
        if self._escape_buf:
            self._escape_buf += char
            if len(self._escape_buf) == 2 and self._escape_buf[1] != "u":
                decoded = _SIMPLE_ESCAPES.get(self._escape_buf[1])
                if decoded is None:
                    self._dead = True
                    return
                self._emit(decoded)
                self._escape_buf = ""
            elif len(self._escape_buf) == 6:
                self._emit_code_unit(self._escape_buf)
                self._escape_buf = ""
            elif len(self._escape_buf) > 2 and self._escape_buf[1] != "u":
                self._dead = True
            elif len(self._escape_buf) > 6:
                self._dead = True
            elif len(self._escape_buf) >= 3 and self._escape_buf[1] == "u":
                # \u escape in progress — validate hex digits as they arrive.
                if any(c not in "0123456789abcdefABCDEF" for c in self._escape_buf[2:]):
                    self._dead = True
            return
        if char == "\\":
            self._escape_buf = "\\"
            return
        if char == '"':
            self._flush_surrogate()
            self._state = _DONE
            return
        if ord(char) < 0x20:
            self._dead = True  # raw control char in a JSON string — malformed
            return
        self._emit(char)

    def _emit(self, text: str) -> None:
        if self._high_surrogate is not None:
            # A lone high surrogate followed by anything but a \uDC00-\uDFFF
            # escape — replace and move on.
            self._out.append("�")
            self._high_surrogate = None
        self._out.append(text)

    def _emit_code_unit(self, escape: str) -> None:
        code = int(escape[2:], 16)
        if 0xD800 <= code <= 0xDBFF:
            self._flush_surrogate()
            self._high_surrogate = code
            return
        if 0xDC00 <= code <= 0xDFFF and self._high_surrogate is not None:
            combined = (
                0x10000
                + ((self._high_surrogate - 0xD800) << 10)
                + (code - 0xDC00)
            )
            self._high_surrogate = None
            self._out.append(chr(combined))
            return
        self._flush_surrogate()
        self._out.append(chr(code))

    def _flush_surrogate(self) -> None:
        if self._high_surrogate is not None:
            self._out.append("�")
            self._high_surrogate = None
