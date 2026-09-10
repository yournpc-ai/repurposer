"""Incremental prose extraction from a streaming JSON verdict (chat SSE).

The intent agents answer with one structured JSON verdict whose user-facing
prose lives in a string field (``answer`` for the book path's InferredIntent,
``text`` / ``summary`` for the chat loop's IntentResult, ``prose`` for the
ask verdict's framing speech — nested inside the ``ask`` object, still at
extractable depth). When the LLM call
streams, the raw JSON arrives character by character; this extractor watches
the accumulating stream and yields the prose field's *decoded* content as it
grows, so the chat surface can typewriter the answer while the verdict is
still generating. The fully-assembled JSON is validated afterwards exactly as
before — the deltas are a preview channel only, never the source of truth.

Design rules (pressure-tested 2026-08-04):
- **Depth-gated keys**: a target key is accepted only at object depth 1–2
  (bare proposal shape or the ``{"proposal": {...}}`` wrapper). This rejects
  deeply nested lookalikes like ``ops[i].params.text`` (depth ≥ 3).
- **Provider dialects never reach this layer** (2026-09-11 用户拍板): a
  ``<think>`` reasoning preamble is stripped at the Model seam
  (``providers/llm/minimax._ThinkStripper``) before any fragment arrives —
  feeding raw provider text here is a caller bug.
- **A `null` value skips the pair, never kills the stream**: several prose
  keys are watched at once (``answer`` / ``text`` / ``summary`` / ``prose``),
  and every ask verdict carries ``"answer": null`` — one key's null must not
  latch the extractor off while another key's prose is still coming
  (打字机律 2026-09-08: dying on the null popped the whole framing prose in
  as one blob at the envelope). Any OTHER non-string value (number / bool /
  object / array) still goes dead — a surprise never produces a wrong preview.
- **Any surprise goes dead**: malformed escapes, control characters, or
  structural confusion disable the extractor silently. Worst case is no
  preview — never wrong preview.
"""

from __future__ import annotations

import json

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
_EXPECT_NULL = "expect_null"  # consuming a target key's `null` literal
_CAPTURING = "capturing"  # inside the prose string, decoding
_DONE = "done"  # prose string closed; never emit again


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

        # Capture state.
        self._escape_buf = ""  # incomplete escape sequence across chunks
        self._high_surrogate: int | None = None  # \uD800-\uDBFF awaiting its low
        self._null_buf = ""  # `null` literal in progress (a skipped pair)
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
        if self._state == _CAPTURING:
            self._step_capture(char)
            return
        self._step_structural(char)

    def _step_structural(self, char: str) -> None:
        """Brace/string tracking + target-key detection (non-capture states)."""
        if self._state == _EXPECT_VALUE:
            # Dedicated sub-state: no structural tracking — the next non-ws
            # char either opens the prose string, starts a `null` literal
            # (skipped, the scan resumes), or latches the extractor off.
            if char in " \t\r\n":
                return
            if char == '"':
                self._state = _CAPTURING
                self._escape_buf = ""
                return
            if char == "n":
                # A null value on THIS key: the pair carries no prose — skip
                # it and keep scanning. Several prose keys are watched at
                # once and every ask verdict carries "answer": null; one
                # key's null must never kill another key's prose.
                self._state = _EXPECT_NULL
                self._null_buf = "n"
                return
            # number / bool / object / array — not prose.
            self._dead = True
            return
        if self._state == _EXPECT_NULL:
            self._null_buf += char
            if self._null_buf == "null":
                self._state = _SCANNING
                self._null_buf = ""
                return
            if not "null".startswith(self._null_buf):
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


# AskObjectWatcher states.
_ASK_SCANNING = "scanning"  # structural scan, looking for the top-level "ask" key
_ASK_AFTER_TOKEN = "after_token"  # a string token completed; expect ':' or not
_ASK_EXPECT_VALUE = "expect_value"  # the "ask" key's colon seen; expect its value
_ASK_IN_OBJECT = "in_object"  # buffering the ask object's raw chars
_ASK_DONE = "done"  # fired (or resolved this verdict has no ask) — never again


class AskObjectWatcher:
    """Feed raw verdict fragments; fires once when the top-level ``ask``
    object CLOSES, with its parsed payload (book-path ask previews).

    Object-level trust boundary (2026-09-09 用户拍板——「选项该和这句话一
    起来」): the ask object's internal key order puts ``prose`` first, so by
    the time the echo's last character streams, ``question`` / ``options`` /
    ``default_path`` have ALREADY closed inside the same object — the pill's
    whole payload exists while the verdict's brief-ledger tail is still
    generating. Parsing the closed subtree (a real ``json.loads`` of the
    complete object — never a partial guess) lets the SSE pump preview-dock
    the question pill seconds earlier; the terminal envelope stays
    authoritative, exactly like the prose preview (envelope always wins, a
    flipped or failed turn rolls the preview back client-side).

    Same discipline as the extractor: any surprise goes dead SILENTLY —
    ``"ask": null`` (a non-ask verdict), a structural hiccup, or a parse
    failure means no preview, never a wrong preview. The chat loop's flat
    shape C carries no top-level ``ask`` key (its ``"ask"`` is a *value* of
    ``type``, which never matches the key scan), so the watcher is inert
    there by construction.
    """

    def __init__(self, on_ask) -> None:
        self._on_ask = on_ask
        self._state = _ASK_SCANNING
        self._dead = False
        self._depth = 0
        self._close_depth = 0  # the depth the ask object must return to
        self._in_string = False
        self._escaped = False
        self._key_buf = ""
        self._key_depth = 0
        self._buf: list[str] = []

    @property
    def dead(self) -> bool:
        return self._dead or self._state == _ASK_DONE

    def feed(self, chunk: str) -> None:
        if self.dead:
            return
        for char in chunk:
            self._step(char)
            if self.dead:
                return

    def _step(self, char: str) -> None:
        if self._state == _ASK_IN_OBJECT:
            self._step_object(char)
            return
        self._step_structural(char)

    def _step_structural(self, char: str) -> None:
        if self._state == _ASK_EXPECT_VALUE:
            if char in " \t\r\n":
                return
            if char == "{":
                self._buf = ["{"]
                self._close_depth = self._depth
                self._depth += 1
                self._state = _ASK_IN_OBJECT
                return
            # "ask": null / anything-not-an-object — no ask this verdict.
            self._dead = True
            return

        if self._in_string:
            if self._escaped:
                self._escaped = False
                if self._state == _ASK_SCANNING:
                    self._key_buf += char
            elif char == "\\":
                self._escaped = True
            elif char == '"':
                self._in_string = False
                if self._state == _ASK_SCANNING:
                    self._state = _ASK_AFTER_TOKEN
            else:
                if self._state == _ASK_SCANNING:
                    self._key_buf += char
            return

        if char == '"':
            self._in_string = True
            if self._state == _ASK_SCANNING:
                self._key_buf = ""
                self._key_depth = self._depth
            return
        if char in "{[":
            self._depth += 1
            if self._state == _ASK_AFTER_TOKEN:
                self._state = _ASK_SCANNING
            return
        if char in "}]":
            self._depth -= 1
            if self._depth < 0:
                self._dead = True
                return
            if self._state == _ASK_AFTER_TOKEN:
                self._state = _ASK_SCANNING
            return

        if self._state == _ASK_AFTER_TOKEN:
            if char in " \t\r\n":
                return
            if char == ":":
                self._state = (
                    _ASK_EXPECT_VALUE
                    if self._key_buf == "ask" and 1 <= self._key_depth <= 2
                    else _ASK_SCANNING
                )
                return
            self._state = _ASK_SCANNING

    def _step_object(self, char: str) -> None:
        self._buf.append(char)
        if self._in_string:
            if self._escaped:
                self._escaped = False
            elif char == "\\":
                self._escaped = True
            elif char == '"':
                self._in_string = False
            return
        if char == '"':
            self._in_string = True
            return
        if char in "{[":
            self._depth += 1
            return
        if char in "}]":
            self._depth -= 1
            if self._depth == self._close_depth:
                # The ask object's matching close — the subtree is complete.
                self._state = _ASK_DONE
                try:
                    payload = json.loads("".join(self._buf))
                except Exception:  # noqa: BLE001 — no preview, never wrong
                    self._dead = True
                    return
                if isinstance(payload, dict):
                    self._on_ask(payload)
            elif self._depth < self._close_depth:
                self._dead = True
