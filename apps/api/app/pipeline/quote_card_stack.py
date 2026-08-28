"""Chain quote card compositor (RECIPES §4.6.2, stacked = 卡本体).

Builds the 9:16 stacked quote card: N caption strips (N=3..7, the writer's
core-idea chain, setup → payoff) cascading down the canvas, each strip
backed by a video frame grabbed at the entry's ``frame_at`` midpoint,
with an optional speaker frame on top (``needs_speaker_frame``). The
composite is one PNG — captions are baked in (no ``caption_track``), so
the renderer just holds it for the configured duration with a subtle
Ken-Burns (zoom_in 1.05).

Pipeline:
1. ``extract_video_frames(video_bytes, timecodes)`` — streaming PyAV
   grabber: seek to the keyframe before each target, decode until the
   target is reached, stop. Never a full-decode residency.
2. ``composite_chain_quote_card(...)`` — PIL composite: strips overlap
   (each upper strip covers the lower strip's top rows), captions drawn
   with per-script sizing (CJK lines big / Latin lines small) and
   per-script wrapping (CJK wraps per character, Latin on spaces).

Caller (``_materialize_quote_card_outputs``) uploads the PNG to project
storage and hands the URL to ``build_stacked_quote_card_spec``.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ----- Fonts -----------------------------------------------------------------

# Vendored CJK-capable font (D12, 2026-08-27): production containers ship no
# desktop fonts, so the vendored Noto Sans SC (SIL OFL, apps/api/assets/fonts/)
# is the ONLY guaranteed CJK path. System paths stay as local-dev fallback.
_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FONT_REGULAR_CANDIDATES = (
    str(_FONT_DIR / "NotoSansSC-Regular.otf"),
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Best-effort font load — vendored CJK font first, system paths as
    local-dev fallback, PIL's default bitmap font last (the caption still
    renders, just without CJK / accent fidelity)."""
    for p in _FONT_REGULAR_CANDIDATES:
        try:
            return ImageFont.truetype(p, size=size)
        except (OSError, FileNotFoundError):
            continue
    return ImageFont.load_default()


# ----- Frame extraction -------------------------------------------------------


def extract_video_frames(
    video_bytes: bytes, timecodes_s: list[float]
) -> list[Image.Image | None]:
    """Streaming PyAV still-frame grabber — memory-flat (D11, 2026-08-27).

    The previous implementation decoded EVERY frame of the source into a
    resident list before picking — a lecture-length video OOMed / hit the
    download timeout. This version walks the timecodes in ascending order,
    seeks to the keyframe before each target, and decodes only until the
    target is reached (a target ≤3s ahead of the cursor just keeps decoding
    forward — cheaper than a seek). Memory residency = the grabbed frames,
    never the whole video.

    Returns a list PARALLEL to ``timecodes_s`` — entries are None where no
    frame could be grabbed (the caller's per-strip dark-fill fallback
    absorbs the holes without index drift). Raises only when the video
    yields no frames at all (caller decides whether to drop or 5xx).
    """
    import av  # type: ignore  # PyAV — direct dep, see pyproject.toml

    if not timecodes_s:
        return []
    order = sorted(range(len(timecodes_s)), key=lambda i: timecodes_s[i])
    grabbed: list[Image.Image | None] = [None] * len(timecodes_s)
    container = av.open(io.BytesIO(video_bytes))
    try:
        stream = container.streams.video[0]
        cursor = -1.0  # presentation time of the last decoded frame
        for idx in order:
            target = max(0.0, float(timecodes_s[idx]))
            if target < cursor or target - cursor > 3.0:
                # Rewind or long jump: land on the keyframe before the target.
                container.seek(
                    max(0, int((target - 0.5) / stream.time_base)),
                    stream=stream,
                )
                cursor = -1.0
            img: Image.Image | None = None
            for frame in container.decode(stream):
                cursor = float(frame.time or 0)
                img = frame.to_image()
                if cursor >= target:
                    break
            if img is None:
                break  # zero-frame video — nothing more to grab
            grabbed[idx] = img
    finally:
        container.close()
    if not any(grabbed):
        raise ValueError("video: no frames decoded")
    return grabbed


# ----- Text measurement (D13/D14, 2026-08-27) ---------------------------------


def _is_cjk_dominant(text: str) -> bool:
    """CJK share of the text > 0.3 — drives per-script wrapping (D13) and
    per-script font sizing (D14)."""
    if not text:
        return False
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return cjk / len(text) > 0.3


def _wrap_text(
    text: str, char_budget: int, *, max_lines: int, cjk: bool
) -> list[str]:
    """Greedy wrap into at most ``max_lines`` lines (overflow is folded into
    the last line with a trailing "…").

    Latin wraps on spaces. CJK has no spaces to split on (D13 — a CJK
    sentence used to be ONE token and overflowed the strip in a single
    unwrappable line), so CJK wraps per character with an empty joiner.
    """
    joiner = "" if cjk else " "
    tokens = list(text) if cjk else text.split()
    if not tokens:
        return []
    lines: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for tok in tokens:
        tlen = len(tok) + (len(joiner) if cur else 0)
        if cur and cur_len + tlen > char_budget:
            lines.append(joiner.join(cur))
            cur = [tok]
            cur_len = len(tok)
        else:
            cur.append(tok)
            cur_len += tlen
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(joiner.join(cur))
    elif cur:
        lines[-1] = lines[-1] + "…" if cjk else lines[-1] + " …"
    return lines


# ----- Composite --------------------------------------------------------------

# Layout constants for the chain variant.
CHAIN_CANVAS_W = 1080
CHAIN_CANVAS_H = 1920
CHAIN_SPEAKER_H = 960  # 50% of canvas when needs_speaker_frame
CHAIN_BG = (10, 10, 14)
CHAIN_PADDING_X = 60
CHAIN_STRIP_OVERLAP_PX = 1260  # max cascade overlap (RECIPES §4.6.2)
# Reviewed peek floor (2026-08-27): the visible window each back strip
# keeps below the strip covering it. 220 = the reviewed N=3 full-canvas
# value (v9 demo bake). The fixed 1260 overlap was tuned for the
# full-canvas deck (S=1920 → peek 220@N3); with a speaker frame
# (S=960) it drove the peek NEGATIVE and the cascade inverted
# (text clipped under covering strips). The overlap now yields to
# hold this floor — see composite_chain_quote_card.
CHAIN_PEEK_MIN = 220
# Caption anchor: the block ends this many px above the strip body's
# bottom (the 80px tail stays until D17/P3 moves the overlay's example
# label pill off the image — shell yields to image, not the reverse).
# Tight cascades (peek < floor) relax it proportionally.
CHAIN_BOTTOM_ANCHOR = 80
CHAIN_BLOCK_GAP = 18  # primary ↔ secondary block gap (px)

# Per-script caption sizing (D14, 2026-08-27): the font follows the LINE's
# script, not the line's role — CJK lines are the visual mains (big), Latin
# lines the secondaries (small). Bilingual strips draw both.
CHAIN_CJK_FONT_MAX = 36
CHAIN_CJK_FONT_MIN = 22
CHAIN_CJK_RATIO = 0.10  # font size = strip_h * ratio, capped at MAX
CHAIN_CJK_LINE_GAP = 10
CHAIN_LATIN_FONT_MAX = 32
CHAIN_LATIN_FONT_MIN = 22
CHAIN_LATIN_RATIO = 0.07
CHAIN_LATIN_LINE_GAP = 22

# Speaker label (poster-style text). Drawn ONCE at the top-left corner of
# the canvas — no chip, no background, no rounded box; white text with a
# subtle dark stroke, like a movie-poster credit line.
SPEAKER_LABEL_FONT_SIZE = 40  # px — poster-credit size
SPEAKER_LABEL_MARGIN_X = 44   # px from canvas left edge
SPEAKER_LABEL_MARGIN_Y = 48   # px from canvas top edge


def _crop_to_card(img: Image.Image, *, w: int, h: int) -> Image.Image:
    """Fit (preserve aspect) an arbitrary-resolution image into the card
    slot, letterboxing with CHAIN_BG when the source aspect differs — the
    source's edges are preserved, never center-cropped away."""
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


def _layout_caption_line(
    text: str,
    *,
    max_lines: int,
    font_cjk: ImageFont.FreeTypeFont,
    font_latin: ImageFont.FreeTypeFont,
    inner_w: int,
) -> tuple[list[str], ImageFont.FreeTypeFont, int]:
    """Wrap one caption line set with the per-script font (D13/D14):
    the font follows the TEXT's script (CJK big / Latin small), and the
    wrap budget matches — CJK wraps per character at 1.0em, Latin on
    spaces at 0.55em. Returns (lines, font, line_height)."""
    cjk = _is_cjk_dominant(text)
    font = font_cjk if cjk else font_latin
    em = 1.0 if cjk else 0.55
    budget = max(4, int(inner_w / max(1, font.size * em)))
    lines = _wrap_text(text, budget, max_lines=max_lines, cjk=cjk)
    line_h = font.size + (CHAIN_CJK_LINE_GAP if cjk else CHAIN_LATIN_LINE_GAP)
    return lines, font, line_h


def _measure_caption_block(
    cap: ChainCaption,
    *,
    font_cjk: ImageFont.FreeTypeFont,
    font_latin: ImageFont.FreeTypeFont,
    inner_w: int,
    max_primary: int,
    max_secondary: int,
) -> int:
    """The strip's caption block height at these fonts/line caps — the
    value the cascade's font-fit loop holds against the peek budget."""
    lines_p, _, lh_p = _layout_caption_line(
        cap.primary,
        max_lines=max_primary,
        font_cjk=font_cjk,
        font_latin=font_latin,
        inner_w=inner_w,
    )
    total = lh_p * len(lines_p)
    if cap.secondary:
        lines_s, _, lh_s = _layout_caption_line(
            cap.secondary,
            max_lines=max_secondary,
            font_cjk=font_cjk,
            font_latin=font_latin,
            inner_w=inner_w,
        )
        total += CHAIN_BLOCK_GAP + lh_s * len(lines_s)
    return total


def composite_chain_quote_card(
    *,
    speaker_frame: Image.Image | None,
    chain: list[ChainCaption],
    chain_frames: list[Image.Image | None] | None = None,
    speaker_label: str | None = None,
) -> bytes:
    """Chain-variant composite (RECIPES §4.6.2).

    Layout:

    - Canvas 1080×1920 (9:16), dark base.
    - If ``speaker_frame`` is provided: it occupies the top half
      (1080×960, letterbox-fit). Below it, N caption strips share the
      bottom 960px; without one, strips fill the full 1920px.
    - Each strip = one VIDEO FRAME as the card body (``chain_frames[i]``,
      grabbed at the chain entry's ``frame_at`` midpoint). None holes or
      a short list fall back to dark fill with caption-only (graceful
      degrade for the no-video path).
    - Strips overlap: each strip is ``vh`` tall and offset by
      ``vh - overlap`` from the previous one, so the upper strip paints
      over the lower strip's top rows — the stacked-cascade reading.
      Drawing order is back-first (chain[N-1] at the canvas bottom) so
      the front quote (chain[0]) lands visually on top.

    Returns PNG bytes for the caller to upload. An empty chain returns
    the plain dark canvas (graceful degradation).
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

    # Stack geometry: total content height = n*vh - (n-1)*overlap, solved
    # for vh so the cascade fills the strip area exactly.
    #
    # The overlap yields to the peek floor (CHAIN_PEEK_MIN, 2026-08-27):
    # the fixed 1260 was tuned for the full-canvas deck (S=1920 → peek
    # 220@N3, 94@N7); with a speaker frame (S=960) it drove the peek
    # NEGATIVE (stride < 0 — strips painted over each other's caption
    # bands and the front strip's text landed off-canvas). peek =
    # (S - overlap)/n, so clamping overlap ≤ S - n*PEEK_MIN holds the
    # reviewed floor in every regime; S < n*PEEK_MIN degrades to flat
    # tiles (overlap 0, peek = S/n).
    overlap_px = min(
        CHAIN_STRIP_OVERLAP_PX,
        max(0, strips_visible_total - n * CHAIN_PEEK_MIN),
    )
    vh = max(
        80,
        (strips_visible_total + (n - 1) * overlap_px) // n,
    )
    strip_h = vh
    peek_px = vh - overlap_px

    # Caption budget: a strip's text must live inside its visible
    # window — the FRONT strip shows its whole body (vh), back strips
    # keep only their bottom ``peek_px`` rows (everything above is
    # painted over by the covering strip). The 80px tail anchor relaxes
    # when the cascade is tighter than the reviewed floor.
    anchor = (
        CHAIN_BOTTOM_ANCHOR if peek_px >= CHAIN_PEEK_MIN else max(16, peek_px // 4)
    )
    budgets = [
        max(40, (vh if i == 0 else peek_px) - anchor) for i in range(n)
    ]

    # Cascade-wide font fit: nominal sizes scale with vh (the per-card
    # body height), capped — then step down until EVERY strip's caption
    # block fits ITS window budget (front strip keeps the roomiest
    # window, so a long back-strip caption alone drags the type down).
    # Line caps tighten only at the floor sizes. The final clip is
    # _wrap_text's ellipsis, never a paint-over.
    size_cjk = max(
        CHAIN_CJK_FONT_MIN, min(CHAIN_CJK_FONT_MAX, int(vh * CHAIN_CJK_RATIO))
    )
    size_latin = max(
        CHAIN_LATIN_FONT_MIN,
        min(CHAIN_LATIN_FONT_MAX, int(vh * CHAIN_LATIN_RATIO)),
    )
    inner_w = CHAIN_CANVAS_W - 2 * CHAIN_PADDING_X
    max_primary, max_secondary = 3, 2
    while True:
        font_cjk = _load_font(size_cjk)
        font_latin = _load_font(size_latin)
        if all(
            _measure_caption_block(
                cap,
                font_cjk=font_cjk,
                font_latin=font_latin,
                inner_w=inner_w,
                max_primary=max_primary,
                max_secondary=max_secondary,
            )
            <= budgets[i]
            for i, cap in enumerate(chain)
        ):
            break
        if size_cjk > CHAIN_CJK_FONT_MIN or size_latin > CHAIN_LATIN_FONT_MIN:
            size_cjk = max(CHAIN_CJK_FONT_MIN, size_cjk - 2)
            size_latin = max(CHAIN_LATIN_FONT_MIN, size_latin - 2)
        elif max_secondary > 1:
            max_secondary -= 1
        elif max_primary > 1:
            max_primary -= 1
        else:
            break

    draw = ImageDraw.Draw(canvas)
    speaker_offset = CHAIN_SPEAKER_H if speaker_frame is not None else 0
    frames_supplied = chain_frames or []
    # Drawing order: BACK first (chain[N-1], canvas bottom), FRONT last
    # (chain[0], canvas top) — the later draw paints over the previous
    # card's overlap zone, so the front of the stack sits at the top.
    for i in reversed(range(n)):
        cap = chain[i]
        y_top = speaker_offset + i * (vh - overlap_px)
        card_w = CHAIN_CANVAS_W
        x_offset = 0
        card_body = (
            frames_supplied[i]
            if i < len(frames_supplied) and frames_supplied[i] is not None
            else None
        )
        if card_body is not None:
            body = _crop_to_card(card_body, w=card_w, h=strip_h)
            canvas.paste(body, (x_offset, y_top))
        else:
            # Always paste SOMETHING — the strip's top overlap rows must
            # cover the previous strip's body, or it bleeds through and
            # the cascade reads as a single tall card.
            canvas.paste(
                Image.new("RGB", (card_w, strip_h), CHAIN_BG),
                (x_offset, y_top),
            )
        _draw_caption_strip(
            draw,
            y_top,
            vh,
            card_w,
            x_offset,
            cap.primary,
            cap.secondary,
            font_cjk,
            font_latin,
            anchor=anchor,
            max_primary=max_primary,
            max_secondary=max_secondary,
        )

    # Speaker label — drawn last so it sits above every card body and
    # caption strip, anchoring the speaker's identity across the cascade.
    if speaker_label:
        _draw_speaker_label(draw, speaker_label)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_speaker_label(
    draw: ImageDraw.ImageDraw,
    label: str,
) -> None:
    """Top-left speaker attribution — poster-style text: no chip, no
    rounded box, no background fill, just white text with a subtle dark
    stroke so it reads against any underlying card body."""
    font = _load_font(SPEAKER_LABEL_FONT_SIZE)
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
    font_cjk: ImageFont.FreeTypeFont,
    font_latin: ImageFont.FreeTypeFont,
    *,
    anchor: int,
    max_primary: int,
    max_secondary: int,
) -> None:
    """One chain caption strip: primary line on top, alt line below,
    anchored near the BOTTOM of the card body so the body extends above
    the text — each card reads as a "card" with body on top.

    The fonts and line caps arrive pre-fitted (the composite's
    cascade-wide budget loop): every strip's block lands inside its
    visible window, so a covering strip never paints over text.
    """
    if not primary:
        return

    inner_w = card_w - 2 * CHAIN_PADDING_X

    primary_lines, font_p, lh_p = _layout_caption_line(
        primary,
        max_lines=max_primary,
        font_cjk=font_cjk,
        font_latin=font_latin,
        inner_w=inner_w,
    )
    secondary_lines: list[str] = []
    font_s = font_latin
    lh_s = 0
    if secondary:
        secondary_lines, font_s, lh_s = _layout_caption_line(
            secondary,
            max_lines=max_secondary,
            font_cjk=font_cjk,
            font_latin=font_latin,
            inner_w=inner_w,
        )

    # Vertical layout — caption block near the BOTTOM of the card body.
    gap = CHAIN_BLOCK_GAP if secondary_lines else 0
    block_total = lh_p * len(primary_lines) + gap + lh_s * len(secondary_lines)
    # Anchor: caption block ends ``anchor`` px above the bottom of the
    # card body.
    y_text = y_top + vh - block_total - anchor

    # Primary
    for line in primary_lines:
        bbox = draw.textbbox((0, 0), line, font=font_p)
        text_w = bbox[2] - bbox[0]
        x_text = x_offset + (card_w - text_w) // 2
        # Subtle dark stroke for legibility on the frame body
        for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text(
                (x_text + offset[0], y_text),
                line,
                font=font_p,
                fill=(0, 0, 0, 200),
            )
        draw.text((x_text, y_text), line, font=font_p, fill=(255, 255, 255, 255))
        y_text += lh_p

    y_text += gap

    # Secondary (alt translation)
    for line in secondary_lines:
        bbox = draw.textbbox((0, 0), line, font=font_s)
        text_w = bbox[2] - bbox[0]
        x_text = x_offset + (card_w - text_w) // 2
        draw.text(
            (x_text, y_text),
            line,
            font=font_s,
            fill=(220, 220, 220, 230),
        )
        y_text += lh_s

    # No hairline separator — the gap between strips is the separator.
