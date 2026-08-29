"""Chain quote card compositor (RECIPES §4.6.2, stacked = 卡本体).

v3 形态对齐 (2026-08-28, D15 — TikTok 图文帖参考两张): the composite is a
STATIC PNG in one of two forms, never the retired N-frame "帧墙" (形态 C):

- **形态 A (人像型, ``needs_speaker_frame=True``)**: top speaker region
  (1080×960, the CURATED frame — best face in the first quotable line's
  span, YuNet-picked) + dark fade into the strip area + N caption strips
  (semi-transparent black bodies, staggered ±40px) + attribution rails
  (name / source two lines, horizontal, speaker region bottom-left).
- **形态 B (全幅背景型, ``needs_speaker_frame=False``)**: one full-bleed
  background (the curated frame cover-cropped to 1080×1920) dimmed 30%,
  N caption lines centred straight down. No frame at all → the dark
  branch (纯文字 strip, 学术椅型).

The 帧卡 (frame card, §2.2) is the chain's per-entry standalone sibling:
one frame + one caption block, independently shareable, and the composite's
named parents on the results canvas (``source_ref.parents``).

Pipeline:
1. ``extract_video_frames(video_bytes, timecodes)`` — streaming PyAV
   grabber: seek to the keyframe before each target, decode until the
   target is reached, stop. Never a full-decode residency.
2. ``pick_curated_frame(video_bytes, start, end)`` — YuNet best-face
   picker over a small sample of the first quotable line's span
   (``providers/vision.py`` reuse, zero new engines); no faces → the
   span's midpoint frame.
3. ``composite_frame_card(...)`` / ``composite_chain_quote_card(...)`` —
   PIL composites with per-script sizing (CJK lines big / Latin lines
   small) and per-script wrapping (CJK per character, Latin on spaces).

Caller (``_materialize_quote_card_outputs``) uploads the PNGs to project
storage and hands the composite URL to ``build_stacked_quote_card_spec``.
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

# Layout constants (v3 forms A/B, 2026-08-28).
CHAIN_CANVAS_W = 1080
CHAIN_CANVAS_H = 1920
CHAIN_SPEAKER_H = 960  # 形态 A speaker region (top 50%)
CHAIN_BG = (10, 10, 14)
CHAIN_PADDING_X = 60

# 形态 A caption strips: semi-transparent black bodies staggered ±40px.
STRIP_GAP_Y = 28
STRIP_STAGGER = 40
STRIP_ALPHA = 168
STRIP_RADIUS = 28
STRIP_PAD_X = 36
STRIP_PAD_Y = 24
STRIP_AREA_MARGIN = 32  # gap above the first / below the last strip

# 形态 B: full-bleed background dimmed 30%, caption lines centred straight
# down inside a vertical band.
DIM_ALPHA = 77  # 30% black veil over the background frame
BAND_TOP = 240
BAND_BOTTOM = 200
ENTRY_GAP = 56  # between chain entries (form B / frame card has one)

# Attribution rails (横排版, D15): name line big + source line small, drawn
# in 形态 A's speaker region bottom-left (and the frame card's top-left).
ATTR_NAME_SIZE = 48
ATTR_SOURCE_SIZE = 36
ATTR_MARGIN_X = 56
ATTR_MARGIN_Y = 40

# Per-script caption sizing (D14): the font follows the LINE's script, not
# the line's role — CJK lines are the visual mains (big), Latin lines the
# secondaries (small). Bilingual strips draw both.
CHAIN_CJK_FONT_MAX = 40
CHAIN_CJK_FONT_MIN = 20
CHAIN_CJK_LINE_GAP = 10
CHAIN_LATIN_FONT_MAX = 32
CHAIN_LATIN_FONT_MIN = 20
CHAIN_LATIN_LINE_GAP = 22
CHAIN_BLOCK_GAP = 18  # primary ↔ secondary block gap (px)

# 形态 B / frame card type runs larger (full canvas, few strips).
FORM_B_CJK_MAX = 56
FORM_B_LATIN_MAX = 38


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


def _cover_crop(img: Image.Image, *, w: int, h: int) -> Image.Image:
    """Fill (cover) the slot, center-cropping the overflow — the full-bleed
    background form (形态 B / frame card). The product's own design choice,
    not a display crop (RECIPES 永不裁剪 governs display shells)."""
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new_w, new_h = int(round(src_w * scale)), int(round(src_h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    x0 = (new_w - w) // 2
    y0 = (new_h - h) // 2
    return img.crop((x0, y0, x0 + w, y0 + h))


def _split_attribution(attr: str) -> tuple[str, str | None]:
    """Split an attribution string into (name, source) on the first
    separator — the rails' two lines ("查理·芒格 | 伯克希尔副董事长")."""
    for sep in ("|", "，", ",", "·", "——", "—", " - "):
        if sep in attr:
            head, tail = attr.split(sep, 1)
            return head.strip(), (tail.strip() or None)
    return attr.strip(), None


@dataclass(frozen=True)
class ChainCaption:
    """One caption strip entry (RECIPES §4.6.2 chain variant).

    ``primary`` is the strip's main line — the verbatim source-language
    sentence for bilingual / source_only, the translator's alt line for
    target_only. ``secondary`` is the alt translation when
    ``caption_mode == "bilingual"`` — None otherwise (双译本收窄, D5:
    captions never mix the writer's ``quote`` draft with ``quote_alt``).
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


# ----- Curated frame (D15: 策展帧 — 治"中点帧表情差 + N 帧重复"两病) ----------


def _sharpness(img: Image.Image) -> float:
    """Laplacian-variance blur score — higher = crisper. Tie-break only."""
    import cv2  # lazy: heavy import
    import numpy as np

    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def pick_curated_frame(
    video_bytes: bytes, start: float, end: float
) -> Image.Image | None:
    """Pick the best frame inside the first quotable line's span (D15).

    The old design grabbed the span's MIDPOINT frame (often a bad
    expression) and repeated near-identical adjacent frames down the
    cascade. This samples a handful of frames across the span and picks
    the one with the largest detected face (YuNet via
    ``providers/vision.py`` — the engine is already vendored for
    speaker_map/reframe, zero new deps), sharpness as the tie-break.
    No faces anywhere → the span's midpoint frame (an honest fallback,
    never a t=0 black/title frame — invalid spans are rejected by the
    caller, never clamped).

    CPU-bound (decode + detection) — async callers wrap in
    ``asyncio.to_thread``. Returns None when no frame could be decoded.
    """
    import numpy as np

    from app.providers.vision import detect_faces

    if end <= start:
        return None
    span = end - start
    samples = [start + span * f for f in (0.15, 0.35, 0.5, 0.65, 0.85)]
    try:
        frames = extract_video_frames(video_bytes, samples)
    except ValueError:
        return None
    best: Image.Image | None = None
    best_key: tuple[float, float] = (-1.0, 0.0)
    for img in frames:
        if img is None:
            continue
        arr = np.array(img.convert("RGB"))[:, :, ::-1]  # RGB → BGR
        faces = detect_faces(arr, (640, 640))
        if not faces:
            continue
        area = max(f.bbox[2] * f.bbox[3] for f in faces)
        key = (area, _sharpness(img))
        if key > best_key:
            best_key = key
            best = img
    if best is not None:
        return best
    # No face in any sample — the span's midpoint frame.
    try:
        mid = extract_video_frames(video_bytes, [(start + end) / 2])
    except ValueError:
        return None
    return next((f for f in mid if f is not None), None)


# ----- Text drawing -----------------------------------------------------------


def _draw_text_line(
    draw: ImageDraw.ImageDraw,
    *,
    cx: int,
    y: int,
    line: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = (255, 255, 255),
    stroke: bool = True,
) -> None:
    """One horizontally-centred text line, with a subtle dark stroke so it
    reads against any underlying frame (movie-poster credit style)."""
    bbox = draw.textbbox((0, 0), line, font=font)
    text_w = bbox[2] - bbox[0]
    x = cx - text_w // 2
    if stroke:
        for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text(
                (x + offset[0], y + offset[1]),
                line,
                font=font,
                fill=(0, 0, 0),
            )
    draw.text((x, y), line, font=font, fill=fill)


def _draw_caption_block(
    draw: ImageDraw.ImageDraw,
    *,
    cx: int,
    y: int,
    cap: ChainCaption,
    font_cjk: ImageFont.FreeTypeFont,
    font_latin: ImageFont.FreeTypeFont,
    inner_w: int,
    max_primary: int,
    max_secondary: int,
) -> int:
    """Draw one entry's primary (+ secondary) lines centred at ``cx``,
    starting at ``y``. Returns the block's total height in px."""
    lines_p, font_p, lh_p = _layout_caption_line(
        cap.primary,
        max_lines=max_primary,
        font_cjk=font_cjk,
        font_latin=font_latin,
        inner_w=inner_w,
    )
    for line in lines_p:
        _draw_text_line(draw, cx=cx, y=y, line=line, font=font_p)
        y += lh_p
    if cap.secondary:
        y += CHAIN_BLOCK_GAP
        lines_s, font_s, lh_s = _layout_caption_line(
            cap.secondary,
            max_lines=max_secondary,
            font_cjk=font_cjk,
            font_latin=font_latin,
            inner_w=inner_w,
        )
        for line in lines_s:
            _draw_text_line(
                draw, cx=cx, y=y, line=line, font=font_s, fill=(224, 224, 224)
            )
            y += lh_s
        return lh_p * len(lines_p) + CHAIN_BLOCK_GAP + lh_s * len(lines_s)
    return lh_p * len(lines_p)


def _fit_fonts(
    caps: list[ChainCaption],
    *,
    inner_w: int,
    budget: int,
    cjk_max: int,
    latin_max: int,
    gap_per_entry: int = 0,
    max_primary: int = 3,
    max_secondary: int = 2,
    strip_overhead: int = 0,
) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, int, int]:
    """Cascade-wide font fit: step the per-script sizes down until every
    entry's caption block (+ per-entry gap + strip body overhead) fits the
    shared height ``budget``. Line caps tighten only at the floor sizes;
    the final clip is ``_wrap_text``'s ellipsis, never a paint-over.
    Returns (font_cjk, font_latin, max_primary, max_secondary)."""
    size_cjk, size_latin = cjk_max, latin_max
    while True:
        font_cjk = _load_font(size_cjk)
        font_latin = _load_font(size_latin)
        total = sum(
            _measure_caption_block(
                cap,
                font_cjk=font_cjk,
                font_latin=font_latin,
                inner_w=inner_w,
                max_primary=max_primary,
                max_secondary=max_secondary,
            )
            + gap_per_entry
            + strip_overhead
            for cap in caps
        )
        if total <= budget:
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
    return font_cjk, font_latin, max_primary, max_secondary


def _draw_attribution_rails(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y_bottom: int,
    attribution: str,
) -> None:
    """身份 rails 横排版 (D15): name line (48) + source line (36), stacked
    upward from ``y_bottom`` at the speaker region's bottom-left — white
    text with a dark stroke, poster-credit style. P2 ships the horizontal
    form; the vertical CJK rails of the reference stay a separate eval."""
    name, source = _split_attribution(attribution)
    y = y_bottom
    if source:
        font_s = _load_font(ATTR_SOURCE_SIZE)
        draw.text(
            (x, y - ATTR_SOURCE_SIZE),
            source,
            font=font_s,
            fill=(224, 224, 224),
            stroke_width=1,
            stroke_fill=(0, 0, 0),
        )
        y = y - ATTR_SOURCE_SIZE - 14
    font_n = _load_font(ATTR_NAME_SIZE)
    draw.text(
        (x, y - ATTR_NAME_SIZE),
        name,
        font=font_n,
        fill=(255, 255, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0),
    )


def _bottom_fade(canvas: Image.Image, *, y0: int, y1: int) -> None:
    """Paint a transparent→CHAIN_BG vertical fade over [y0, y1) — 形态 A's
    speaker region dissolves into the strip area instead of a hard cut."""
    draw = ImageDraw.Draw(canvas, "RGBA")
    span = max(1, y1 - y0)
    for i in range(span):
        alpha = int(255 * (i / span) ** 1.5)
        draw.line(
            [(0, y0 + i), (canvas.width, y0 + i)],
            fill=(CHAIN_BG[0], CHAIN_BG[1], CHAIN_BG[2], alpha),
        )


def _dim(canvas: Image.Image, alpha: int = DIM_ALPHA) -> None:
    """Flatten a black veil over the whole canvas (形态 B / frame card's
    30% darken — text stays readable over a busy frame)."""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, alpha))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"))


# ----- Frame card (§2.2: per-entry standalone sibling) -------------------------


def composite_frame_card(
    *,
    frame: Image.Image | None,
    caption: ChainCaption,
    attribution: str | None = None,
) -> bytes:
    """One 1080×1920 single-quote card: the entry's frame full-bleed
    (cover-crop) dimmed 30%, its caption block anchored in the lower
    third, attribution rails top-left. ``frame=None`` → the dark
    text-only card (no-material / photo-less path). Independently
    shareable — and the composite's named parent on the canvas.
    """
    canvas = Image.new("RGB", (CHAIN_CANVAS_W, CHAIN_CANVAS_H), CHAIN_BG)
    if frame is not None:
        canvas.paste(_cover_crop(frame, w=CHAIN_CANVAS_W, h=CHAIN_CANVAS_H), (0, 0))
        _dim(canvas)

    inner_w = CHAIN_CANVAS_W - 2 * CHAIN_PADDING_X
    band = CHAIN_CANVAS_H // 3  # lower-third anchor
    font_cjk, font_latin, max_p, max_s = _fit_fonts(
        [caption],
        inner_w=inner_w,
        budget=band,
        cjk_max=FORM_B_CJK_MAX,
        latin_max=FORM_B_LATIN_MAX,
        max_primary=4,
        max_secondary=3,
    )
    block_h = _measure_caption_block(
        caption,
        font_cjk=font_cjk,
        font_latin=font_latin,
        inner_w=inner_w,
        max_primary=max_p,
        max_secondary=max_s,
    )
    draw = ImageDraw.Draw(canvas)
    y = CHAIN_CANVAS_H - BAND_BOTTOM - block_h
    _draw_caption_block(
        draw,
        cx=CHAIN_CANVAS_W // 2,
        y=y,
        cap=caption,
        font_cjk=font_cjk,
        font_latin=font_latin,
        inner_w=inner_w,
        max_primary=max_p,
        max_secondary=max_s,
    )
    if attribution:
        rails_y = ATTR_MARGIN_Y + ATTR_NAME_SIZE + 14 + ATTR_SOURCE_SIZE
        _draw_attribution_rails(
            draw, x=ATTR_MARGIN_X, y_bottom=rails_y, attribution=attribution
        )
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ----- Chain composite (v3 forms A/B) ------------------------------------------


def composite_chain_quote_card(
    *,
    chain: list[ChainCaption],
    curated_frame: Image.Image | None,
    speaker_form: bool,
    attribution: str | None = None,
) -> bytes:
    """Chain composite (RECIPES §4.6.2 v3, D15 形态对齐).

    - ``speaker_form=True`` → 形态 A (人像型): the curated frame fills the
      top 1080×960 (letterbox), fades into the strip area; N caption
      strips (semi-transparent black bodies, staggered ±40px) stack
      below; attribution rails ride the speaker region's bottom-left.
    - ``speaker_form=False`` → 形态 B (全幅背景型): the curated frame
      cover-crops full-bleed, dimmed 30%; N caption lines centre
      straight down. ``curated_frame=None`` → the dark branch (纯文字
      叠卡, 学术椅型).

    Returns PNG bytes. An empty chain returns the plain dark canvas
    (graceful degradation).
    """
    canvas = Image.new("RGB", (CHAIN_CANVAS_W, CHAIN_CANVAS_H), CHAIN_BG)
    n = len(chain)
    if n == 0:
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    if speaker_form and curated_frame is not None:
        return _composite_form_a(canvas, chain, curated_frame, attribution)
    return _composite_form_b(canvas, chain, curated_frame, attribution)


def _composite_form_a(
    canvas: Image.Image,
    chain: list[ChainCaption],
    curated_frame: Image.Image,
    attribution: str | None,
) -> bytes:
    """形态 A (人像型) — see composite_chain_quote_card."""
    slot = _crop_to_card(curated_frame, w=CHAIN_CANVAS_W, h=CHAIN_SPEAKER_H)
    canvas.paste(slot, (0, 0))
    _bottom_fade(canvas, y0=CHAIN_SPEAKER_H - 200, y1=CHAIN_SPEAKER_H + 60)

    inner_w = CHAIN_CANVAS_W - 2 * (CHAIN_PADDING_X + STRIP_PAD_X)
    strip_w = CHAIN_CANVAS_W - 2 * CHAIN_PADDING_X
    area_top = CHAIN_SPEAKER_H + STRIP_AREA_MARGIN
    area_bottom = CHAIN_CANVAS_H - STRIP_AREA_MARGIN
    budget = area_bottom - area_top
    font_cjk, font_latin, max_p, max_s = _fit_fonts(
        chain,
        inner_w=inner_w,
        budget=budget,
        cjk_max=CHAIN_CJK_FONT_MAX,
        latin_max=CHAIN_LATIN_FONT_MAX,
        gap_per_entry=STRIP_GAP_Y,
        strip_overhead=2 * STRIP_PAD_Y,
    )

    # Strip bodies = one RGBA overlay (rounded semi-transparent rects),
    # text drawn after the composite so it stays crisp.
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    y = area_top
    blocks: list[tuple[int, int, int, ChainCaption]] = []  # (x, y, h, cap)
    for i, cap in enumerate(chain):
        block_h = _measure_caption_block(
            cap,
            font_cjk=font_cjk,
            font_latin=font_latin,
            inner_w=inner_w,
            max_primary=max_p,
            max_secondary=max_s,
        )
        strip_h = block_h + 2 * STRIP_PAD_Y
        x = CHAIN_PADDING_X + (STRIP_STAGGER if i % 2 else -STRIP_STAGGER)
        x = max(16, min(x, CHAIN_CANVAS_W - strip_w - 16))
        od.rounded_rectangle(
            [x, y, x + strip_w, y + strip_h],
            radius=STRIP_RADIUS,
            fill=(0, 0, 0, STRIP_ALPHA),
        )
        blocks.append((x, y, strip_h, cap))
        y += strip_h + STRIP_GAP_Y
    composed = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    canvas.paste(composed)

    draw = ImageDraw.Draw(canvas)
    for x, y, strip_h, cap in blocks:
        _draw_caption_block(
            draw,
            cx=x + strip_w // 2,
            y=y + STRIP_PAD_Y,
            cap=cap,
            font_cjk=font_cjk,
            font_latin=font_latin,
            inner_w=inner_w,
            max_primary=max_p,
            max_secondary=max_s,
        )
    if attribution:
        _draw_attribution_rails(
            draw,
            x=ATTR_MARGIN_X,
            y_bottom=CHAIN_SPEAKER_H - ATTR_MARGIN_Y,
            attribution=attribution,
        )
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _composite_form_b(
    canvas: Image.Image,
    chain: list[ChainCaption],
    curated_frame: Image.Image | None,
    attribution: str | None,
) -> bytes:
    """形态 B (全幅背景型) — see composite_chain_quote_card. No frame →
    the dark branch (纯文字叠卡)."""
    if curated_frame is not None:
        canvas.paste(
            _cover_crop(curated_frame, w=CHAIN_CANVAS_W, h=CHAIN_CANVAS_H), (0, 0)
        )
        _dim(canvas)

    inner_w = CHAIN_CANVAS_W - 2 * CHAIN_PADDING_X
    budget = CHAIN_CANVAS_H - BAND_TOP - BAND_BOTTOM
    font_cjk, font_latin, max_p, max_s = _fit_fonts(
        chain,
        inner_w=inner_w,
        budget=budget,
        cjk_max=FORM_B_CJK_MAX,
        latin_max=FORM_B_LATIN_MAX,
        gap_per_entry=ENTRY_GAP,
    )
    total = sum(
        _measure_caption_block(
            cap,
            font_cjk=font_cjk,
            font_latin=font_latin,
            inner_w=inner_w,
            max_primary=max_p,
            max_secondary=max_s,
        )
        for cap in chain
    ) + ENTRY_GAP * (len(chain) - 1)
    draw = ImageDraw.Draw(canvas)
    y = BAND_TOP + max(0, (budget - total) // 2)
    for cap in chain:
        y += _draw_caption_block(
            draw,
            cx=CHAIN_CANVAS_W // 2,
            y=y,
            cap=cap,
            font_cjk=font_cjk,
            font_latin=font_latin,
            inner_w=inner_w,
            max_primary=max_p,
            max_secondary=max_s,
        )
        y += ENTRY_GAP
    if attribution:
        _draw_attribution_rails(
            draw,
            x=ATTR_MARGIN_X,
            y_bottom=CHAIN_CANVAS_H - ATTR_MARGIN_Y,
            attribution=attribution,
        )
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
