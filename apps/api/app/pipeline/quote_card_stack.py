"""Stacked quote card compositor (RECIPES §4.6.2 stacked variant, 2026-08-25).

Builds a 9:16 PNG by extracting frames from the source video at the
surrounding context sentences and stacking them as a cascade (newest on
top, oldest on bottom) — the visual reference is the 小红书 Charlie-Munger
gold-quote card genre where 3 cards sit on top of each other and the
upper ones progressively reveal only the lower card's caption strip.

The composite is one image — captions are baked into the PNG (no
``caption_track``), so the renderer just holds it for the configured
duration with a subtle Ken-Burns (zoom_in 1.05). Single-language first;
multi-language text on each caption strip is a future variation (not in
this slice — bilingual captures ride the standard quote-card path with
``caption_mode="bilingual"``, this variant owns the cascade VISUAL).

Pipeline:
1. ``find_context_spans(words, quote_start_idx, quote_end_idx, before=1,
   after=1)`` — locate N sentences before + the quote + N sentences after
   in the ASR word stream (sentence boundaries = pause gaps > 0.6s).
2. ``extract_video_frames(video_bytes, timecodes)`` — PyAV grabs one JPEG
   per timecode at the source's native resolution.
3. ``composite_stacked_quote_card(frames, captions)`` — PIL composites the
   3 frame cards onto a 9:16 canvas (cascading reveal), caption baked
   onto each card with a soft dark gradient at the bottom.

Caller (``_materialize_quote_card_outputs``) uploads the PNG to TOS and
   hands the URL to ``build_stacked_quote_card_spec``.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFont


# ----- Layout constants -----------------------------------------------------

CANVAS_W = 1080
CANVAS_H = 1920
FRAME_W = 1080
FRAME_H = 900  # 6:5 — slight 16:9 crop for cascade density
FRAME_OFFSET = 480  # vertical offset between adjacent frames
CAPTION_H = 180  # caption strip height (baked into each card)

# ASR word-gap threshold — gaps longer than this are treated as sentence
# boundaries. Whisper pauses ≥ ~0.5s typically mark sentence ends; 0.6s
# is a slightly conservative read so we don't split mid-phrase.
_SENTENCE_BREAK_S = 0.6

# Frame extraction: take the frame nearest the sentence MIDPOINT (not the
# start) — the start often lands on a pause just before the next word,
# producing a stiller of an empty mouth. Mid-frame is consistently more
# expressive (mouth mid-shaping).
_FONT_REGULAR_CANDIDATES = (
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


@dataclass(frozen=True)
class ContextSpan:
    """One sentence around the picked quote — the runtime input to a
    single cascade card. ``label`` is ``"before"|"quote"|"after"`` (drives
    visual emphasis — quote is the visual focus)."""

    label: str
    text: str
    start_s: float  # sentence start (seconds, source clock)
    end_s: float  # sentence end (seconds, source clock)
    mid_s: float  # mid timestamp — where to grab the frame

    @property
    def caption(self) -> str:
        """Caption text (whitespace-collapsed)."""
        return _collapse(self.text)


def _collapse(text: str) -> str:
    """Collapse ASR whitespace runs to a single space."""
    return re.sub(r"\s+", " ", text or "").strip()


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Best-effort system font load — fall back to PIL's default bitmap
    font if no TTF candidate is reachable (the caption still renders, just
    without CJK / accent fidelity."""
    for p in _FONT_REGULAR_CANDIDATES:
        try:
            return ImageFont.truetype(p, size=size)
        except (OSError, FileNotFoundError):
            continue
    return ImageFont.load_default()


def find_context_spans(
    words: list[dict[str, Any]],
    quote_start_s: float,
    quote_end_s: float,
    *,
    before: int = 1,
    after: int = 1,
) -> list[ContextSpan]:
    """Group ASR words into sentence spans around the picked quote.

    A sentence = a maximal run of consecutive words with inter-word gap
    < ``_SENTENCE_BREAK_S``. Returns:
    - ``before`` sentences ending before ``quote_start_s``
    - the QUOTE sentence (spans ``quote_start_s`` to ``quote_end_s``)
    - ``after`` sentences starting after ``quote_end_s``

    Each span's mid-point = ``(start + end) / 2`` (the frame-grab anchor).
    No matches → ``[]`` — caller drops the card and the recipe still
    renders without a stacked variant (graceful degrade).
    """
    if not words or quote_end_s <= quote_start_s:
        return []
    sentences = _split_sentences(words)
    quote_sentence_idx: int | None = None
    for i, (s_start, s_end, s_words) in enumerate(sentences):
        if s_start <= quote_start_s and quote_end_s <= s_end:
            quote_sentence_idx = i
            break
    if quote_sentence_idx is None:
        # Quote span straddles a sentence boundary (rare but possible when
        # the LLM picks a line that falls between two natural pauses).
        # Pick the sentence whose center is closest to the quote's center.
        qc = (quote_start_s + quote_end_s) / 2
        quote_sentence_idx = min(
            range(len(sentences)),
            key=lambda i: abs((sentences[i][0] + sentences[i][1]) / 2 - qc),
        )

    out: list[ContextSpan] = []
    # BEFORE
    j = quote_sentence_idx - 1
    picked = 0
    while j >= 0 and picked < before:
        s_start, s_end, s_words = sentences[j]
        out.insert(
            0,
            ContextSpan(
                label="before",
                text=" ".join(str(w.get("word", "")) for w in s_words),
                start_s=s_start,
                end_s=s_end,
                mid_s=(s_start + s_end) / 2,
            ),
        )
        picked += 1
        j -= 1
    # QUOTE
    s_start, s_end, s_words = sentences[quote_sentence_idx]
    out.append(
        ContextSpan(
            label="quote",
            text=" ".join(str(w.get("word", "")) for w in s_words),
            start_s=s_start,
            end_s=s_end,
            mid_s=(s_start + s_end) / 2,
        )
    )
    # AFTER
    j = quote_sentence_idx + 1
    picked = 0
    while j < len(sentences) and picked < after:
        s_start, s_end, s_words = sentences[j]
        out.append(
            ContextSpan(
                label="after",
                text=" ".join(str(w.get("word", "")) for w in s_words),
                start_s=s_start,
                end_s=s_end,
                mid_s=(s_start + s_end) / 2,
            )
        )
        picked += 1
        j += 1
    return out


def _split_sentences(words: list[dict[str, Any]]) -> list[tuple[float, float, list[dict]]]:
    """ASR word stream → sentence spans via inter-word pause threshold.

    A run of consecutive words with gap < ``_SENTENCE_BREAK_S`` is one
    sentence. Returns ``[(start_s, end_s, [w...])]``. Empty list when
    no words.
    """
    if not words:
        return []
    out: list[tuple[float, float, list[dict]]] = []
    cur: list[dict] = [words[0]]
    for w in words[1:]:
        prev_end = float(cur[-1].get("end", 0))
        cur_start = float(w.get("start", 0))
        if cur_start - prev_end >= _SENTENCE_BREAK_S:
            out.append((float(cur[0]["start"]), float(cur[-1]["end"]), cur))
            cur = []
        cur.append(w)
    if cur:
        out.append((float(cur[0]["start"]), float(cur[-1]["end"]), cur))
    return out


def extract_video_frames(
    video_bytes: bytes, timecodes_s: list[float]
) -> list[Image.Image]:
    """PyAV-based still-frame grabber.

    Decodes the source video once, seeks to each timecode, returns one
    PIL Image per entry in the same order. Output images are at the
    source's native resolution — the compositor resizes/crops. ``bytes``
    is expected to be a real video stream (not a 404 HTML body); invalid
    input raises (caller decides whether to drop or 5xx).
    """
    import av  # type: ignore  # PyAV — direct dep, see pyproject.toml

    container = av.open(io.BytesIO(video_bytes))
    try:
        stream = container.streams.video[0]
        # Pre-decode all frames into a list so we can do timestamp lookups
        # without seeking-thrashing the demuxer (PyAV's seek on small clips
        # is fine but inconsistent across keyframe layouts).
        frames: list[Any] = []
        for f in container.decode(stream):
            frames.append(f)
        if not frames:
            raise ValueError("video: no frames decoded")
        out: list[Image.Image] = []
        for t in timecodes_s:
            idx = _nearest_frame_index(frames, t)
            out.append(frames[idx].to_image())
        return out
    finally:
        container.close()


def _nearest_frame_index(frames: list[Any], t_s: float) -> int:
    """Index of the frame whose timestamp is closest to ``t_s`` (seconds).
    Binary search by frame time — frames are PTS-ordered post-decode."""
    lo, hi = 0, len(frames) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if float(frames[mid].time) < t_s:
            lo = mid + 1
        else:
            hi = mid
    # lo is the first frame with time >= t_s; compare to lo-1 for closer.
    if lo > 0 and abs(float(frames[lo - 1].time) - t_s) <= abs(float(frames[lo].time) - t_s):
        return lo - 1
    return lo


# ----- Composite ------------------------------------------------------------


def _crop_to_card(img: Image.Image, *, w: int, h: int) -> Image.Image:
    """Fit (preserve aspect) an arbitrary-resolution image into the card
    slot, letterboxing with CHAIN_BG when the source aspect differs.

    v9 fix (2026-08-26, user feedback on image #43): the previous
    version center-CROPPED horizontally when the source was wider than
    the card — for a 16:9 source in a 9:16 card, that meant losing
    ~70% of the horizontal width (only the center 6:5 strip of the
    frame survived). User: "左右两边明显被截断了呀，原视频很宽的".

    Now we FIT instead of crop: the source is resized to fill the
    card's shorter dimension and CHAIN_BG fills the rest. For a
    16:9 source in a 9:16 card slot, the video shows full-width at
    the center with CHAIN_BG letterbox bars top and bottom — the
    source's left/right edges are preserved (not cropped away).
    """
    src_w, src_h = img.size
    target_ratio = w / h
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        # Source is wider — fit WIDTH, letterbox top/bottom
        new_w = w
        new_h = int(round(w / src_ratio))
        x0 = 0
        y0 = (h - new_h) // 2
    elif src_ratio < target_ratio:
        # Source is taller — fit HEIGHT, letterbox left/right
        new_w = int(round(h * src_ratio))
        new_h = h
        x0 = (w - new_w) // 2
        y0 = 0
    else:
        new_w, new_h = w, h
        x0, y0 = 0, 0
    img = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), CHAIN_BG)
    canvas.paste(img, (x0, y0))
    return canvas


def _draw_caption_card(
    base: Image.Image, text: str, *, top_y: int, w: int, h: int, focus: bool
) -> None:
    """Draw the caption strip onto ``base`` covering ``[top_y, top_y + h]``
    within the card. ``focus=True`` = the QUOTE card (larger font,
    slightly different gradient). The strip's bottom 30% is a soft dark
    gradient (caption readability on bright video frames); text is
    white, centered, with subtle stroke for legibility."""
    # Soft gradient (alpha gradient from 0 → ~70% black over the bottom).
    grad = Image.new("L", (w, h), 0)
    for y in range(h):
        # Bottom 30% ramps from alpha 0 to 200; rest stays clear so the
        # frame image dominates.
        alpha = max(0, min(200, int((y - h * 0.7) * 1000 / (h * 0.3)))) if y > h * 0.7 else 0
        # Cheap fill: draw a 1-row-alpha rect across the full width.
        ImageDraw.Draw(grad).rectangle([0, y, w, y + 1], fill=alpha)
    # Composite the gradient as a black-tinted mask
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    overlay.putalpha(grad)
    base.paste(overlay, (0, top_y), overlay)

    # Text
    font_size = 56 if focus else 44
    line_max = 2 if focus else 2  # both cards get 2-line captions max
    font = _load_font(font_size)
    draw = ImageDraw.Draw(base)
    text = _collapse(text)
    if text:
        # Wrap into ≤ line_max lines by simple greedy char budget (font-
        # width-aware: 1 em ≈ font_size, so ~font_size*0.55 per char).
        char_budget = max(8, int(w / max(1, font_size * 0.55)))
        lines = _wrap_text(text, char_budget, max_lines=line_max)
        # Vertical anchor: center in caption strip (text doesn't always
        # fill the strip — the gradient is the floor).
        line_h = font_size + 8
        total_h = line_h * len(lines)
        y_text = top_y + (h - total_h) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x_text = (w - text_w) // 2
            # Stroke first (subtle dark outline for legibility on light frames)
            for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((x_text + offset[0], y_text), line, font=font, fill=(0, 0, 0, 180))
            draw.text((x_text, y_text), line, font=font, fill=(255, 255, 255, 255))
            y_text += line_h


def _wrap_text(text: str, char_budget: int, *, max_lines: int) -> list[str]:
    """Greedy word-wrap into at most ``max_lines`` lines (overflow lines
    are concatenated with a leading "…", capped at one)."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for w in words:
        wlen = len(w) + (1 if cur else 0)
        if cur and cur_len + wlen > char_budget:
            lines.append(" ".join(cur))
            cur = [w]
            cur_len = len(w)
        else:
            cur.append(w)
            cur_len += wlen
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    elif cur:
        # Last line overflows — replace with a "…" truncation.
        lines[-1] = lines[-1] + " …"
    return lines


def composite_stacked_quote_card(
    frames: list[Image.Image],
    captions: list[str],
) -> bytes:
    """Compose a 9:16 PNG cascade from N (frame, caption) cards.

    Returns the PNG bytes (caller uploads to TOS). Caller passes the
    frames in CHRONOLOGICAL order (oldest first, newest last) — the
    compositor inverts the Y placement so the NEWEST card sits at the
    TOP of the canvas (fully visible) and the OLDEST at the BOTTOM
    (only its bottom strip / caption peeks out). Matches the "倒叙从下
    往上堆叠" visual: reverse-chronological top-to-bottom on the canvas.

    Two-phase paint (the first-pass bug fix): frames are pasted in
    bottom-up z-order (oldest first, newest last), THEN all captions are
    drawn on top of the painted canvas. If captions were drawn inside
    the per-frame loop, the upper frame's body would cover the lower
    frame's caption strip — only the bottom-most card's caption would
    render. Splitting the phases keeps every caption visible.
    """
    if not frames or len(frames) != len(captions):
        raise ValueError("frames and captions must be parallel lists")
    n = len(frames)
    # Quote focus = the middle card (len==3 → idx 1). Larger caption font
    # + slightly stronger gradient on the QUOTE card to mark it as the
    # visual anchor.
    quote_idx = n // 2

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (10, 10, 14))
    # Phase 1 — paste frames. Mapping: input i=0 (oldest) → canvas y at
    # the BOTTOM; i=n-1 (newest) → canvas y=0 (top). This gives the
    # "newest-on-top" cascade the user asked for.
    for i, frame in enumerate(frames):
        card = _crop_to_card(frame, w=FRAME_W, h=FRAME_H)
        y_canvas = (n - 1 - i) * FRAME_OFFSET
        canvas.paste(card, (0, y_canvas))

    # Phase 2 — draw captions on top of the painted canvas, at each
    # card's true bottom (inside its visible region so the lower cards'
    # captions are never covered by an upper card's body).
    for i, caption in enumerate(captions):
        y_canvas = (n - 1 - i) * FRAME_OFFSET
        focus = i == quote_idx
        _draw_caption_card(
            canvas,
            caption,
            top_y=y_canvas + FRAME_H - CAPTION_H,
            w=FRAME_W,
            h=CAPTION_H,
            focus=focus,
        )

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Chain variant (RECIPES §4.6.2, 2026-08-25)
#
# The single-frame cascade above was the v1 cascade. v2 (chain) replaces
# it: the writer picks a core idea + N sentence chain (N=3..7), each
# sentence rendered as a CAPTION STRIP (just text on dark, no frame body)
# — with an optional speaker face on top (image #35 Charlie Munger style)
# or pure text-only stack (image #34 学术椅 style). This is the
# 小红书 stacked-card genre: tight, text-first, minimal empty space.
# ---------------------------------------------------------------------------

# Layout constants for the chain variant.
CHAIN_CANVAS_W = 1080
CHAIN_CANVAS_H = 1920
CHAIN_SPEAKER_H = 960  # 50% of canvas when needs_speaker_frame
CHAIN_BG = (10, 10, 14)
CHAIN_PADDING_X = 60
CHAIN_STRIP_OVERLAP_PX = 1260  # very tight stacking (RECIPES §4.6.2
                                # chain variant, v6 — 2026-08-26).
                                # User feedback chain: 200 → 600 (half
                                # the y-distance, image #42) → 1260
                                # (halve again, image #43). With
                                # overlap=1260, for N=3:
                                #   vh = (1920 + 2*1260)/3 = 1480
                                #   peek = vh - overlap = 220
                                # which is half of v4's 440 peek. For
                                # N=7: vh = 1354, peek = 94 (very
                                # tight — cards nearly fully stacked).
                                # The cards now read as a dense cascade
                                # with just a sliver of each lower
                                # card peeking out below.
CHAIN_PRIMARY_FONT_MAX = 32  # English font cap (was 44 — user
                              # asked to shrink again on image #43,
                              # 2026-08-26; bilingual captions should
                              # keep English as the secondary visual
                              # layer after the speaker label)
CHAIN_SECONDARY_FONT_MAX = 36  # Alt-translation font (unchanged — at
                                # this point the Chinese carries the
                                # heavier visual weight)
CHAIN_PRIMARY_FONT_MIN = 22
CHAIN_SECONDARY_FONT_MIN = 22
CHAIN_PRIMARY_RATIO = 0.07  # font size = strip_h * ratio (was 0.10;
                             # English now sized at 7% of vh, capped
                             # at MAX 32 — visually quiet, lets the
                             # video frames + alt translation carry)
CHAIN_SECONDARY_RATIO = 0.10  # secondary at 10%, larger than primary
                                # now — alt translation is the dominant
                                # caption layer
CHAIN_PRIMARY_LINE_GAP = 22  # was +28 — line gap follows font down
CHAIN_SECONDARY_LINE_GAP = 10

# Speaker label (poster-style text). Drawn ONCE on the canvas at
# the top-left corner — NO chip, NO background, NO rounded box.
# Just white text with a subtle dark stroke so it reads against
# any underlying card body. Sized like a movie-poster credit
# (40px — small for the canvas but prominent as attribution). The
# v5 chip was rejected (user: "不需要chip，而是一个海报那样文字")
# — chips read as UI badges, poster text reads as a title.
SPEAKER_LABEL_FONT_SIZE = 40  # px — poster-credit size
SPEAKER_LABEL_MARGIN_X = 44   # px from canvas left edge
SPEAKER_LABEL_MARGIN_Y = 48   # px from canvas top edge

# v3 pyramid narrowing (2026-08-26 — user feedback on image #40:
# v2 stack y-overlap was correct but the cards were all the same
# full canvas width, so the cascade read as "flat tiles with thin
# peeks" instead of "stacked cards". The classic sticky-note /
# index-card cascade (image #37 reference) gets its "stacked"
# reading from each lower card being NARROWER and CENTERED, so the
# upper card leaves visible strips of the lower card peeking out on
# BOTH SIDES, not just below. CHAIN_CARD_WIDTH_FACTOR = 0.92: each
# next card down is 92% of the previous card's width, so by N=3 the
# bottom card is 85% (0.92^2) wide with 7.5% margin on each side.
# By N=7: 0.92^6 ≈ 61% wide — still readable as a card, never a sliver.
# The y-overlap stack (CHAIN_STRIP_OVERLAP_PX) and the x-narrowing
# combine to give the cascade BOTH vertical depth (peek below) AND
# lateral depth (peek on sides) — the "stacked cards" reading.
CHAIN_CARD_WIDTH_FACTOR = 0.92


@dataclass(frozen=True)
class ChainCaption:
    """One caption strip entry (RECIPES §4.6.2 chain variant).

    ``primary`` is the verbatim source-language sentence (the LLM's
    pick from ``quotable_lines``). ``secondary`` is the alt translation
    when ``caption_mode == "bilingual"`` — None for source_only /
    target_only runs.
    """

    primary: str
    secondary: str | None = None


def composite_chain_quote_card(
    *,
    speaker_frame: Image.Image | None,
    chain: list[ChainCaption],
    chain_frames: list[Image.Image] | None = None,
    speaker_label: str | None = None,
) -> bytes:
    """Chain-variant composite (RECIPES §4.6.2, 2026-08-25).

    Layout (overlap variant, 2026-08-25 — image #37 reference):

    - Canvas 1080×1920 (9:16), dark base.
    - If ``speaker_frame`` is provided: it occupies the top half
      (1080×960), centered / cropped to fill. Below it, N caption
      strips occupy the bottom 960px (each visible region = 960/N).
    - If ``speaker_frame`` is None: N caption strips fill the full
      1920px (each visible region = 1920/N).
    - **Each strip = one VIDEO FRAME as the card body** (PyAV-grabbed
      at the chain entry's ``frame_at`` midpoint, supplied via
      ``chain_frames[i]``) — the source speaker footage is the visual
      anchor, the caption is baked on. When ``chain_frames`` is None
      or shorter than the chain, the strip falls back to dark fill
      with caption-only (graceful degrade for the no-video path).
    - **Strips overlap**: each strip is ``vh + overlap`` tall but only
      ``vh`` is visible — the upper strip paints over the lower
      strip's top ``overlap`` pixels. The visible regions stack exactly
      to fill the strip area; drawing order is top-first so each new
      strip covers the previous one's overlap zone.

    Returns PNG bytes for the caller to upload to TOS.

    Empty chain returns a single-color 1080×1920 PNG (the canvas
    background) — graceful degradation for the no-material path.
    """
    canvas = Image.new("RGB", (CHAIN_CANVAS_W, CHAIN_CANVAS_H), CHAIN_BG)
    n = len(chain)
    if n == 0:
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    # Speaker frame slot (top half, when provided).
    if speaker_frame is not None:
        slot = _crop_to_card(speaker_frame, w=CHAIN_CANVAS_W, h=CHAIN_SPEAKER_H)
        canvas.paste(slot, (0, 0))
        strips_visible_total = CHAIN_CANVAS_H - CHAIN_SPEAKER_H
    else:
        strips_visible_total = CHAIN_CANVAS_H

    # v2 stack geometry (2026-08-26 — see CHAIN_STRIP_OVERLAP_PX
    # comment for the v1 bug). Each card's body occupies exactly
    # `vh` vertical pixels. Cards are stacked with y_top offset of
    # `(vh - overlap_px)` so consecutive cards' bodies genuinely
    # OVERLAP by `overlap_px` at their boundary (v1 had them just
    # touching, which read as flat tiles).
    #
    # Total content height = (n-1)*(vh - overlap) + vh
    #                      = n*vh - (n-1)*overlap
    # Solving for vh given total = strips_visible_total:
    #     vh = (strips_visible_total + (n-1)*overlap) / n
    #
    # Drawing order (reversed iteration): chain[N-1] (back, smallest
    # z) drawn FIRST at canvas BOTTOM, chain[0] (front, largest z)
    # drawn LAST at canvas TOP. The later draw paints over the
    # previous card's overlap zone, so the upper card visually sits
    # ON TOP of the lower card (smaller y = larger z = front of the
    # z-stack). The lower card PEEKS OUT below the upper card's
    # body for (vh - overlap_px) pixels — that's the "stacked
    # cascade" the user wants.
    vh = max(
        80,
        (strips_visible_total + (n - 1) * CHAIN_STRIP_OVERLAP_PX) // n,
    )
    overlap_px = CHAIN_STRIP_OVERLAP_PX
    strip_h = vh  # body height = visible region height (v2 stack geometry)

    # Font sizing scales with vh (the per-card body height). Capped
    # at MAX so tall cards (low N) don't blow up the type size.
    font_size_primary = max(
        CHAIN_PRIMARY_FONT_MIN,
        min(CHAIN_PRIMARY_FONT_MAX, int(vh * CHAIN_PRIMARY_RATIO)),
    )
    font_size_secondary = max(
        CHAIN_SECONDARY_FONT_MIN,
        min(CHAIN_SECONDARY_FONT_MAX, int(vh * CHAIN_SECONDARY_RATIO)),
    )
    font_primary = _load_font(font_size_primary)
    font_secondary = _load_font(font_size_secondary)

    draw = ImageDraw.Draw(canvas)
    # v2 stack geometry (2026-08-26 — see CHAIN_STRIP_OVERLAP_PX
    # comment for the v1 bug). y_top[i] = i*(vh - overlap_px): cards
    # are offset by less than vh, so consecutive cards' bodies
    # GENUINELY OVERLAP by overlap_px at their boundary. The
    # strip's visible region (the part not covered by the next
    # card) is [y_top + overlap_px, y_top + vh] for i > 0; for
    # i = 0 there's no card above so the full body [y_top, y_top +
    # vh] is visible.
    #
    # When a speaker frame is on top, the speaker occupies [0,
    # CHAIN_SPEAKER_H] and strips fill [CHAIN_SPEAKER_H,
    # CHAIN_CANVAS_H]. strip_h = vh (no extension), so the first
    # strip's body sits at [CHAIN_SPEAKER_H, CHAIN_SPEAKER_H + vh]
    # and the second at [CHAIN_SPEAKER_H + vh - overlap_px, ...] —
    # the speaker frame stays intact at the top, cards cascade
    # below it.
    #
    # Each strip = one VIDEO FRAME as the card body (RECIPES §4.6.2:
    # "这几句话的帧截图下来做字幕" — the chain is a frame-anchored
    # cascade, not a text-only deck). ``chain_frames[i]`` is the
    # PyAV-grabbed frame at the i-th chain entry's ``frame_at``
    # midpoint; the runner provides it from the source video. When
    # the chain has more entries than frames (or frames is None),
    # the missing strip falls back to dark fill with caption only —
    # the cascade still reads, just without the speaker footage for
    # the back-of-stack entries.
    speaker_offset = CHAIN_SPEAKER_H if speaker_frame is not None else 0
    frames_supplied = chain_frames or []
    # Drawing order: BACK first (smaller z, drawn at canvas BOTTOM),
    # FRONT last (largest z, drawn at canvas TOP). The chain index is
    # the inverse of z — chain[0] is the FRONT quote (drawn last at
    # canvas top), chain[N-1] is the BACK quote (drawn first at
    # canvas bottom). Iterating reversed() lets the LAST paste land
    # on top of the canvas, painting over earlier draws so the front
    # of the stack visually sits at the top.
    for i in reversed(range(n)):
        cap = chain[i]
        z_index = i  # 0 = front (top), N-1 = back (bottom)
        # v2: offset by (vh - overlap_px) so consecutive cards overlap.
        y_top = speaker_offset + z_index * (vh - overlap_px)
        # v4 (2026-08-26): all cards same width (CHAIN_CANVAS_W).
        # Undoes the v3 pyramid narrowing (CHAIN_CARD_WIDTH_FACTOR)
        # per user feedback — "所有图片同宽度". The "stack" reads
        # purely from the y-overlap (CHAIN_STRIP_OVERLAP_PX=600
        # tightening). card_w / x_offset kept as parameters to
        # _draw_caption_strip for forward compat — when a future
        # iteration wants lateral variation again, flip back on.
        card_w = CHAIN_CANVAS_W
        x_offset = 0
        # Paste the strip's card body at its full draw height
        # (strip_h = vh in v2 geometry). Always paste SOMETHING so
        # the strip's top overlap_px rows actually cover the
        # previous strip's body (when the chain has more entries
        # than frames, missing strips fall back to a dark fill —
        # otherwise the previous strip's frame would bleed through
        # the overlap zone and the cascade would read as a single
        # tall card).
        card_body = (
            frames_supplied[i]
            if i < len(frames_supplied) and frames_supplied[i] is not None
            else None
        )
        if card_body is not None:
            # Crop the source frame to the per-card slot (card_w wide,
            # strip_h tall) so the body fills exactly the card slot —
            # no letterboxing, the cascade reads as a true frame stack.
            body = _crop_to_card(card_body, w=card_w, h=strip_h)
            canvas.paste(body, (x_offset, y_top))
        else:
            canvas.paste(
                Image.new("RGB", (card_w, strip_h), CHAIN_BG),
                (x_offset, y_top),
            )
        # Caption overlay drawn on top of the card body (or on dark
        # fill when no frame supplied for this entry). Anchored at
        # the BOTTOM of the card body (per-card width) so the body
        # extends ABOVE the caption — the "card" reading.
        _draw_caption_strip(
            draw,
            y_top,
            vh,
            card_w,
            x_offset,
            cap.primary,
            cap.secondary,
            font_primary,
            font_secondary,
        )

    # Speaker label badge — drawn ONCE at the top-left corner of
    # the canvas, on top of whatever cards are there. The label
    # anchors the speaker's identity across the cascade without
    # competing with the per-card captions. Drawn last so it sits
    # above every card body and caption strip (RECIPES §4.6.2 v4
    # layout, 2026-08-26 — user feedback on image #42: "Yu Xiong
    # 的标签打在整个视频的左上角").
    if speaker_label:
        _draw_speaker_label(canvas, draw, speaker_label)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_speaker_label(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    label: str,
) -> None:
    """Top-left speaker attribution — poster-style text.

    v6 (2026-08-26): no chip, no rounded box, no background fill —
    just white text with a subtle dark stroke so it reads against
    any underlying card body (video frame, speaker face, or dark
    fill). Like a movie-poster credit line: small font, top-left,
    white-on-whatever's-there. Drawn last so it sits ON TOP of every
    card body and caption strip — a stable watermark that anchors
    the speaker's identity across the whole composition without
    competing with the cascade.
    """
    font = _load_font(SPEAKER_LABEL_FONT_SIZE)
    # Optical alignment: the textbbox top is the glyph ascender, not
    # the visual top — add a small fudge so the text sits visually
    # centered on the margin line.
    text_x = SPEAKER_LABEL_MARGIN_X
    text_y = SPEAKER_LABEL_MARGIN_Y
    # Subtle dark stroke for legibility against bright video frames
    # (matches the per-card caption stroke pattern).
    for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text(
            (text_x + offset[0], text_y + offset[1]),
            label,
            font=font,
            fill=(0, 0, 0, 220),
        )
    draw.text((text_x, text_y), label, font=font, fill=(255, 255, 255, 255))


def _draw_caption_strip(
    draw: ImageDraw.ImageDraw,
    y_top: int,
    vh: int,
    card_w: int,
    x_offset: int,
    primary: str,
    secondary: str | None,
    font_primary: ImageFont.FreeFont,
    font_secondary: ImageFont.FreeFont,
) -> None:
    """One chain caption strip (text only — no frame imagery).

    v3 stack geometry (2026-08-26): the strip's body occupies
    ``[y_top, y_top + vh]`` with width ``card_w`` (varying per card
    — pyramid narrowing via ``CHAIN_CARD_WIDTH_FACTOR``) and is
    horizontally centered at ``x_offset``. The caption is anchored
    near the BOTTOM of the body so the body extends ABOVE the
    caption — each card reads as a "card" with body on top and
    caption on the lower edge. The combined effect with the y-stack
    + x-narrowing: cards cascade both vertically (peek below) and
    laterally (peek on sides in the overlap zone) — the "stacked
    cards" sticky-note reading.

    Primary line wraps to fit the per-card width, secondary line
    below it. Text is centered within the card's bounding box.
    """
    if not primary:
        return

    # Wrap primary to fit the per-card width (not the full canvas).
    inner_w = card_w - 2 * CHAIN_PADDING_X
    char_budget = max(4, int(inner_w / max(1, font_primary.size * 0.55)))
    primary_lines = _wrap_text(primary, char_budget, max_lines=3)

    # Secondary (alt) wraps tighter, sits below primary with a small gap.
    secondary_lines: list[str] = []
    if secondary:
        char_budget_2 = max(4, int(inner_w / max(1, font_secondary.size * 0.55)))
        secondary_lines = _wrap_text(secondary, char_budget_2, max_lines=2)

    # Vertical layout — caption near the BOTTOM of the card body so
    # the body extends ABOVE the caption (the "card" reading).
    primary_lh = font_primary.size + CHAIN_PRIMARY_LINE_GAP
    secondary_lh = font_secondary.size + CHAIN_SECONDARY_LINE_GAP if secondary_lines else 0
    primary_total = primary_lh * len(primary_lines)
    secondary_total = secondary_lh * len(secondary_lines) if secondary_lines else 0
    gap = 18 if secondary_lines else 0
    block_total = primary_total + gap + secondary_total
    # Anchor: caption block ends ~16px above the bottom of the card body.
    # Anchor: caption block ends ~80px above the bottom of the card body
    # (was 16 — bumped after user feedback on image #43, 2026-08-26:
    # "我们这个好像没显示完" — the Examples overlay's "Quote cards example"
    # pill at bottom-2 was covering the very last row of the bottom
    # card's caption. 80px breathing room keeps the bottom caption
    # fully above the overlay pill on the recipe inspect page).
    y_text = y_top + vh - block_total - 80

    # Primary
    for line in primary_lines:
        bbox = draw.textbbox((0, 0), line, font=font_primary)
        text_w = bbox[2] - bbox[0]
        # Center within the per-card bounding box, not the full canvas.
        x_text = x_offset + (card_w - text_w) // 2
        # Subtle dark stroke for legibility on the dark canvas
        for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text(
                (x_text + offset[0], y_text),
                line,
                font=font_primary,
                fill=(0, 0, 0, 200),
            )
        draw.text((x_text, y_text), line, font=font_primary, fill=(255, 255, 255, 255))
        y_text += primary_lh

    y_text += gap

    # Secondary (alt translation)
    for line in secondary_lines:
        bbox = draw.textbbox((0, 0), line, font=font_secondary)
        text_w = bbox[2] - bbox[0]
        x_text = x_offset + (card_w - text_w) // 2
        draw.text(
            (x_text, y_text),
            line,
            font=font_secondary,
            fill=(220, 220, 220, 230),
        )
        y_text += secondary_lh

    # No hairline separator — the gap between strips is the separator.
    # Earlier hairlines cut through the secondary line when strips
    # were tight; the gap alone reads cleaner (image #34 / #35
    # references use spacing, not strokes).