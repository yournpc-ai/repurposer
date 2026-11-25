"""Deterministic numbered Slot Promo compiler & wireframe placeholder renderer.

Given any ``SkillBlueprintV1`` (all 15 native MotionBlock types), compiles a
ready-to-preview and ready-to-render ``CompositionContent`` + sequential
``[01]..[N]`` ``SlotManifestItem`` list + copyable checklist, preserving 100%
of act durations, transitions, 3D camera settings, reveal timings, overlays,
and ``sfx_cues``.

Zero new SQL tables: pure deterministic Python + Pillow wireframe PNGs drawn
with the repository's pinned ``NotoSansSC`` font files.
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field

from app.editing.catalog import MotionBlockId
from app.editing.fonts import FONT_FILES, font_storage_key
from app.editing.schemas import (
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    LayoutBox,
    MotionBlockObject,
    RemotionResource,
    Scene,
    SourceBinding,
    TextObject,
    TimeRange,
    Timeline,
    Track,
    Transition,
    VersionSettings,
)
from app.editing.styles import (
    INHERITABLE_BLOCK_STYLE_KEYS,
    CompositionStyle,
    ResolvedStyleTokens,
    StylePresetId,
    mix_hex,
    resolve_style_tokens,
)
from app.editing.text_presets import resolve_text_preset_token, text_style_from_token
from app.editing.timing import (
    SOURCE_TIMEBASE,
    frames_to_ticks,
    output_ticks_to_source_ticks,
    seconds_to_ticks,
    source_ticks_to_output_ticks,
    ticks_to_frames,
)
from app.editing.video_spec import compile_video_spec
from app.models.schemas import canonical_json_hash
from app.skills.blueprint import BlueprintAct, SkillBlueprintV1

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
FONT_BOLD_PATH = FONTS_DIR / "NotoSansSC-Bold.otf"
FONT_REGULAR_PATH = FONTS_DIR / "NotoSansSC-Regular.otf"

ALLOWED_FONT_FILENAMES: frozenset[str] = frozenset(
    str(item["filename"]) for item in FONT_FILES
)
_FONT_STORAGE_KEY_TO_FILENAME: dict[str, str] = {
    font_storage_key(str(item["filename"]), str(item["digest"])): str(item["filename"])
    for item in FONT_FILES
}


class SlotManifestItem(BaseModel):
    """One sequential numbered replaceable slot inside a template blueprint."""

    model_config = ConfigDict(extra="forbid")

    slot_number: int = Field(ge=1)
    code: str = Field(min_length=4, max_length=8)
    act_index: int = Field(ge=0)
    act_id: str = Field(min_length=1, max_length=64)
    block_id: MotionBlockId
    slot_key: str = Field(min_length=1, max_length=64)
    kind: Literal["text", "image", "metric", "chart_point", "message", "callout"]
    label_zh: str = Field(min_length=1, max_length=120)
    label_en: str = Field(min_length=1, max_length=120)
    example_value: str = Field(min_length=1, max_length=320)
    aspect_ratio: str | None = None


class PlaceholderImageAsset(BaseModel):
    """Deterministic in-memory wireframe PNG generated for an image slot."""

    model_config = ConfigDict(extra="forbid")

    slot_code: str
    path: str
    snapshot_id: UUID
    digest: str
    width: int
    height: int
    content_type: Literal["image/png"] = "image/png"
    png_bytes: bytes = Field(exclude=True)

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.png_bytes).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def to_remotion_resource(self) -> RemotionResource:
        return RemotionResource(
            path=self.path,
            snapshot_id=self.snapshot_id,
            snapshot_digest=self.digest,
            content_type="image/png",
        )


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    clean = hex_color.lstrip("#")
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default()


def _truncate(text: str, max_len: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max(1, max_len - 1)].rstrip() + "…"


def render_slot_placeholder_png(
    slot_code: str,
    title: str,
    subtitle: str,
    *,
    width: int,
    height: int,
    tokens: ResolvedStyleTokens,
) -> bytes:
    """Draw a deterministic vector-style wireframe placeholder PNG using pinned NotoSansSC."""
    is_dark = tokens["theme"] == "dark"
    bg_hex = tokens["surface_bg"]
    grid_hex = mix_hex(bg_hex, tokens["line_color"], 0.38 if is_dark else 0.45)
    frame_hex = mix_hex(bg_hex, tokens["line_color"], 0.78)
    skeleton_hex = mix_hex(bg_hex, tokens["line_color"], 0.30 if is_dark else 0.25)
    accent_hex = tokens["accent"]
    accent_ink_hex = tokens["accent_ink"]
    ink_hex = tokens["ink"]
    sec_ink_hex = tokens["secondary_ink"]

    img = Image.new("RGB", (width, height), _hex_rgb(bg_hex))
    draw = ImageDraw.Draw(img)

    # Subtle architectural coordinate grid
    step = max(36, min(width, height) // 12)
    grid_rgb = _hex_rgb(grid_hex)
    for x in range(step, width, step):
        draw.line([(x, 0), (x, height)], fill=grid_rgb, width=1)
    for y in range(step, height, step):
        draw.line([(0, y), (width, y)], fill=grid_rgb, width=1)

    # Outer wireframe border + subtle diagonal framing hairlines
    pad = max(24, min(width, height) // 22)
    x0, y0, x1, y1 = pad, pad, width - pad, height - pad
    frame_rgb = _hex_rgb(frame_hex)
    draw.rectangle([x0, y0, x1, y1], outline=frame_rgb, width=2)
    diag_rgb = _hex_rgb(mix_hex(bg_hex, tokens["line_color"], 0.22))
    draw.line([(x0 + 2, y0 + 2), (x1 - 2, y1 - 2)], fill=diag_rgb, width=1)
    draw.line([(x1 - 2, y0 + 2), (x0 + 2, y1 - 2)], fill=diag_rgb, width=1)

    # Four corner viewfinder L-brackets in accent color
    arm = max(28, min(width, height) // 14)
    bw = 4
    accent_rgb = _hex_rgb(accent_hex)
    for cx, cy, dx, dy in (
        (x0, y0, 1, 1),
        (x1, y0, -1, 1),
        (x0, y1, 1, -1),
        (x1, y1, -1, -1),
    ):
        draw.line([(cx, cy), (cx + dx * arm, cy)], fill=accent_rgb, width=bw)
        draw.line([(cx, cy), (cx, cy + dy * arm)], fill=accent_rgb, width=bw)

    # Subtle top wireframe chrome bar & bottom UI skeleton cards
    skel_rgb = _hex_rgb(skeleton_hex)
    bar_h = max(30, height // 18)
    draw.rectangle([x0 + 18, y0 + 18, x1 - 18, y0 + 18 + bar_h], fill=skel_rgb)
    dot_r = max(4, bar_h // 6)
    for i in range(3):
        dx = x0 + 36 + i * (dot_r * 3)
        dy = y0 + 18 + bar_h // 2
        draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=frame_rgb)

    # Bottom wireframe skeleton blocks for realistic UI placeholder depth
    foot_top = y1 - max(70, height // 6)
    gap = 18
    cols = 3 if width >= height else 2
    col_w = ((x1 - x0 - 36) - gap * (cols - 1)) // cols
    for i in range(cols):
        bx0 = x0 + 18 + i * (col_w + gap)
        draw.rounded_rectangle(
            [bx0, foot_top, bx0 + col_w, y1 - 20],
            radius=10,
            fill=skel_rgb,
            outline=frame_rgb,
            width=1,
        )

    # Centered card plate behind the [NN] badge and copy for razor legibility
    card_w = min(width - pad * 3, int(width * (0.72 if width >= height else 0.84)))
    card_h = min(height - pad * 4, int(height * (0.43 if width >= height else 0.36)))
    cx, cy = width // 2, int(height * (0.43 if width >= height else 0.47))
    card_box = [cx - card_w // 2, cy - card_h // 2, cx + card_w // 2, cy + card_h // 2]
    draw.rounded_rectangle(
        card_box,
        radius=16,
        fill=_hex_rgb(bg_hex),
        outline=accent_rgb,
        width=3,
    )

    # Centered [NN] pill badge
    scale = min(width, height) / 720.0
    badge_font = _load_font(FONT_BOLD_PATH, max(28, int(round(46 * scale))))
    title_font = _load_font(FONT_BOLD_PATH, max(22, int(round(32 * scale))))
    sub_font = _load_font(FONT_REGULAR_PATH, max(16, int(round(20 * scale))))
    meta_font = _load_font(FONT_REGULAR_PATH, max(13, int(round(16 * scale))))

    b_bbox = draw.textbbox((0, 0), slot_code, font=badge_font)
    bw_px = b_bbox[2] - b_bbox[0]
    bh_px = b_bbox[3] - b_bbox[1]
    pill_px = int(round(26 * scale))
    pill_py = int(round(12 * scale))
    pill_w = bw_px + pill_px * 2
    pill_h = bh_px + pill_py * 2
    pill_y = cy - card_h // 2 + int(round(34 * scale))
    draw.rounded_rectangle(
        [cx - pill_w // 2, pill_y, cx + pill_w // 2, pill_y + pill_h],
        radius=max(10, int(round(12 * scale))),
        fill=accent_rgb,
    )
    draw.text(
        (cx - bw_px // 2 - b_bbox[0], pill_y + pill_py - b_bbox[1]),
        slot_code,
        font=badge_font,
        fill=_hex_rgb(accent_ink_hex),
    )

    # Title (shrink slightly if wider than inner card)
    max_text_w = card_w - int(round(48 * scale))
    t_size = max(22, int(round(32 * scale)))
    while t_size > 16:
        title_font = _load_font(FONT_BOLD_PATH, t_size)
        t_bbox = draw.textbbox((0, 0), title, font=title_font)
        if (t_bbox[2] - t_bbox[0]) <= max_text_w:
            break
        t_size -= 2
    t_bbox = draw.textbbox((0, 0), title, font=title_font)
    tw_px = t_bbox[2] - t_bbox[0]
    th_px = t_bbox[3] - t_bbox[1]
    title_y = pill_y + pill_h + int(round(24 * scale))
    draw.text(
        (cx - tw_px // 2 - t_bbox[0], title_y - t_bbox[1]),
        title,
        font=title_font,
        fill=_hex_rgb(ink_hex),
    )

    # Subtitle
    s_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    sw_px = s_bbox[2] - s_bbox[0]
    sub_y = title_y + th_px + int(round(16 * scale))
    draw.text(
        (cx - sw_px // 2 - s_bbox[0], sub_y - s_bbox[1]),
        subtitle,
        font=sub_font,
        fill=_hex_rgb(sec_ink_hex),
    )

    # Top-right resolution stamp inside top chrome bar
    aspect_str = "16:9" if width > height else "9:16"
    stamp = f"SLOT {slot_code} · {width}×{height} ({aspect_str})"
    m_bbox = draw.textbbox((0, 0), stamp, font=meta_font)
    draw.text(
        (x1 - 30 - (m_bbox[2] - m_bbox[0]), y0 + 18 + (bar_h - (m_bbox[3] - m_bbox[1])) // 2 - m_bbox[1]),
        stamp,
        font=meta_font,
        fill=_hex_rgb(sec_ink_hex),
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class _SlotAllocator:
    def __init__(self, locale: Literal["zh", "en"]) -> None:
        self.locale = locale
        self.items: list[SlotManifestItem] = []

    def next(
        self,
        *,
        act_index: int,
        act_id: str,
        block_id: MotionBlockId,
        slot_key: str,
        kind: Literal["text", "image", "metric", "chart_point", "message", "callout"],
        label_zh: str,
        label_en: str,
        example_zh: str,
        example_en: str,
        aspect_ratio: str | None = None,
    ) -> SlotManifestItem:
        num = len(self.items) + 1
        code = f"[{num:02d}]"
        raw_example = example_zh if self.locale == "zh" else example_en
        example = raw_example.replace("{code}", code)
        item = SlotManifestItem(
            slot_number=num,
            code=code,
            act_index=act_index,
            act_id=act_id,
            block_id=block_id,
            slot_key=slot_key,
            kind=kind,
            label_zh=label_zh,
            label_en=label_en,
            example_value=example,
            aspect_ratio=aspect_ratio,
        )
        self.items.append(item)
        return item


def _make_placeholder_asset(
    *,
    slot: SlotManifestItem,
    path: str,
    width: int,
    height: int,
    tokens: ResolvedStyleTokens,
    locale: Literal["zh", "en"],
    generate_png: bool,
) -> PlaceholderImageAsset:
    title = slot.label_zh if locale == "zh" else slot.label_en
    subtitle = (
        f"替换为你自己的 {slot.aspect_ratio or '16:9'} 实景截图或界面"
        if locale == "zh"
        else f"Replace with your own {slot.aspect_ratio or '16:9'} product screenshot"
    )
    if generate_png:
        png_bytes = render_slot_placeholder_png(
            slot.code,
            title,
            subtitle,
            width=width,
            height=height,
            tokens=tokens,
        )
    else:
        png_bytes = f"stub:{path}:{slot.code}:{width}x{height}".encode("utf-8")
    digest = hashlib.sha256(png_bytes).hexdigest()
    snap_id = uuid5(NAMESPACE_URL, f"slot-placeholder-v1:{path}:{digest}")
    return PlaceholderImageAsset(
        slot_code=slot.code,
        path=path,
        snapshot_id=snap_id,
        digest=digest,
        width=width,
        height=height,
        png_bytes=png_bytes,
    )


def _sanitized_style_defaults(
    act: BlueprintAct, *, override_style: bool
) -> dict[str, Any]:
    defaults = dict(act.style_defaults)
    if override_style:
        strip = set(INHERITABLE_BLOCK_STYLE_KEYS.get(act.block_id, ()))
        defaults = {k: v for k, v in defaults.items() if k not in strip}
    return defaults


def _plan_act_slots(
    act: BlueprintAct,
    act_index: int,
    allocator: _SlotAllocator,
    *,
    tokens: ResolvedStyleTokens,
    locale: Literal["zh", "en"],
    override_style: bool,
    generate_png: bool,
    placeholder_resources: dict[str, RemotionResource] | None,
) -> tuple[dict[str, Any], list[RemotionResource], list[PlaceholderImageAsset]]:
    """Build deterministic numbered replacement props & image placeholders for one act."""
    is_zh = locale == "zh"
    bid = act.block_id
    defaults = _sanitized_style_defaults(act, override_style=override_style)
    act_for_bind = act.model_copy(update={"style_defaults": defaults})
    resources: list[RemotionResource] = []
    generated_assets: list[PlaceholderImageAsset] = []

    def add_image_slot(
        slot_key: str,
        label_zh: str,
        label_en: str,
        *,
        width: int,
        height: int,
        aspect_ratio: str,
        res_index: int,
    ) -> SlotManifestItem:
        slot = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key=slot_key,
            kind="image",
            label_zh=label_zh,
            label_en=label_en,
            example_zh=f"{{code}} {label_zh}",
            example_en=f"{{code}} {label_en}",
            aspect_ratio=aspect_ratio,
        )
        override_key = f"{act.act_id}:{slot_key}"
        if placeholder_resources and override_key in placeholder_resources:
            resources.append(placeholder_resources[override_key])
        elif placeholder_resources and slot.code in placeholder_resources:
            resources.append(placeholder_resources[slot.code])
        else:
            path = f"media/slot_{slot.slot_number:02d}_act_{act_index + 1}_{res_index}.png"
            asset = _make_placeholder_asset(
                slot=slot,
                path=path,
                width=width,
                height=height,
                tokens=tokens,
                locale=locale,
                generate_png=generate_png,
            )
            generated_assets.append(asset)
            resources.append(asset.to_remotion_resource())
        return slot

    replacement: dict[str, Any] = {}

    def copy_slot(key: str, zh: str, en: str) -> str:
        slot = allocator.next(
            act_index=act_index, act_id=act.act_id, block_id=bid, slot_key=key, kind="text",
            label_zh=zh, label_en=en, example_zh="{code} " + zh, example_en="{code} " + en,
        )
        return slot.example_value

    if bid == "kinetic_beat":
        mode = defaults.get("mode", "impact_cut")
        if mode == "impact_cut":
            replacement["headline"] = copy_slot("headline", "核心观点", "Main idea")
            if "highlight_phrase" in act.optional_slots:
                replacement["highlight_phrase"] = replacement["headline"]
        elif mode in {"slot_flip", "typewriter_swap"}:
            if mode == "slot_flip" and "prefix" in act.optional_slots:
                replacement["prefix"] = copy_slot("prefix", "前缀", "Prefix")
            count = sum(key.startswith("words[") for key in act.required_slots) or 3
            replacement["words"] = [copy_slot(f"words[{i}]", "关键词", "Keyword") for i in range(count)]
        elif mode == "inline_badge_split":
            replacement["left_text"] = copy_slot("left_text", "起句", "Opening")
            replacement["right_text"] = copy_slot("right_text", "落点", "Landing")
            if "badge_text" in act.optional_slots:
                replacement["badge_text"] = copy_slot("badge_text", "徽标", "Badge")
        elif mode == "marquee_wall":
            count = sum(key.startswith("items[") for key in act.required_slots) or 3
            icons = ("bolt", "play", "layers")
            replacement["items"] = [
                {"text": copy_slot(f"items[{i}].text", "关键词", "Keyword"), "icon": icons[i % len(icons)]}
                for i in range(count)
            ]
    elif bid == "ui_montage":
        for i in range(act.resource_count or 3):
            add_image_slot(f"resources[{i}]", "产品界面", "Product screen",
                           width=640, height=400, aspect_ratio="16:10", res_index=i)
        for key, zh, en in (("headline", "标题", "Headline"), ("badge", "徽标", "Badge")):
            if key in act.optional_slots:
                replacement[key] = copy_slot(key, zh, en)
    elif bid == "statement_hook":
        hl_zh, hl_en = "一句话击中核心痛点", "Your Core Hook"
        s_head = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="headline",
            kind="text",
            label_zh="开场核心主张",
            label_en="Opening Headline",
            example_zh=f"{{code}} 开场核心主张 · {hl_zh}",
            example_en=f"{{code}} Opening Statement · {hl_en}",
        )
        replacement["headline"] = _truncate(s_head.example_value, 160)
        replacement["highlight_phrase"] = hl_zh if is_zh else hl_en
        replacement["eyebrow"] = f"ACT {act_index + 1:02d}"
        if "subheadline" in act.required_slots or "subheadline" in act.optional_slots:
            s_sub = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key="subheadline",
                kind="text",
                label_zh="副标题补充说明",
                label_en="Supporting Subheadline",
                example_zh="{code} 补充一句话说明适用场景或目标人群",
                example_en="{code} One concise line framing the audience or context",
            )
            replacement["subheadline"] = _truncate(s_sub.example_value, 200)

    elif bid == "kinetic_title":
        s_head = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="headline",
            kind="text",
            label_zh="屏幕强调标题",
            label_en="Screen Impact Title",
            example_zh="{code} 屏幕强调标题 · 核心观点",
            example_en="{code} Screen Impact Title · Key Thesis",
        )
        replacement["headline"] = _truncate(s_head.example_value, 140)
        if "subheadline" in act.required_slots or "subheadline" in act.optional_slots:
            s_sub = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key="subheadline",
                kind="text",
                label_zh="标题副文",
                label_en="Title Subheadline",
                example_zh="{code} 简短展开说明或节奏承接",
                example_en="{code} Brief supporting subtitle or transition line",
            )
            replacement["subheadline"] = _truncate(s_sub.example_value, 180)

    elif bid == "product_showcase":
        add_image_slot(
            "image_resource",
            "官网/产品界面截图 (16:9)",
            "Website / Product UI Screenshot (16:9)",
            width=1280,
            height=720,
            aspect_ratio="16:9",
            res_index=0,
        )
        s_url = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="url_bar",
            kind="text",
            label_zh="浏览器网址栏",
            label_en="Browser URL Bar",
            example_zh="{code} your-product.com",
            example_en="{code} your-product.com",
        )
        replacement["url_bar"] = _truncate(s_url.example_value, 80)

        # Preserve exact blueprint callout windows aligned cleanly to wireframe skeleton regions
        # (never slicing across the centered [NN] placeholder title plate).
        default_boxes = [
            (0.05, 0.76, 0.29, 0.18),
            (0.66, 0.76, 0.29, 0.18),
            (0.355, 0.76, 0.29, 0.18),
            (0.05, 0.06, 0.90, 0.09),
        ]
        windows = list(act.callout_windows_s)
        if not windows and "callout_steps" in act.required_slots:
            win_end = min(max(1.8, act.target_duration_s - 0.6), 3.6)
            windows = [(0.8, win_end)]
        if windows:
            steps: list[dict[str, Any]] = []
            for idx, (st, en) in enumerate(windows[:4]):
                bx, by, bw, bh = default_boxes[idx % len(default_boxes)]
                s_co = allocator.next(
                    act_index=act_index,
                    act_id=act.act_id,
                    block_id=bid,
                    slot_key=f"callout_steps[{idx}]",
                    kind="callout",
                    label_zh=f"界面焦点标注 #{idx + 1}",
                    label_en=f"UI Spotlight Callout #{idx + 1}",
                    example_zh=f"{{code}} 界面焦点标注 #{idx + 1}",
                    example_en=f"{{code}} Feature Spotlight #{idx + 1}",
                )
                steps.append({
                    "x": bx,
                    "y": by,
                    "width": bw,
                    "height": bh,
                    "start_s": float(st),
                    "end_s": float(en),
                    "label": _truncate(s_co.example_value, 64),
                })
            replacement["callout_steps"] = steps
        if act.cursor_click_at_s is not None:
            replacement["cursor"] = {
                "x": 0.20,
                "y": 0.85,
                "start_x": 0.09,
                "start_y": 0.91,
                "click_at_s": float(act.cursor_click_at_s),
            }

    elif bid == "device_mockup":
        layout = str(defaults.get("layout") or "dual")
        if layout not in {"dual", "desktop", "mobile"}:
            layout = "dual"
        defaults["layout"] = layout
        if layout in {"dual", "desktop"}:
            add_image_slot(
                "image_resource",
                "桌面端界面图 (16:9)",
                "Desktop UI Screenshot (16:9)",
                width=1280,
                height=720,
                aspect_ratio="16:9",
                res_index=0,
            )
        if layout == "mobile":
            add_image_slot(
                "image_resource",
                "移动端界面图 (9:16)",
                "Mobile UI Screenshot (9:16)",
                width=540,
                height=960,
                aspect_ratio="9:16",
                res_index=0,
            )
        elif layout == "dual":
            add_image_slot(
                "mobile_image_resource",
                "移动端界面图 (9:16)",
                "Mobile UI Screenshot (9:16)",
                width=540,
                height=960,
                aspect_ratio="9:16",
                res_index=1,
            )
        s_head = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="headline",
            kind="text",
            label_zh="设备展示主标题",
            label_en="Device Showcase Headline",
            example_zh="{code} 桌面与移动端无缝协同",
            example_en="{code} Seamless Across Desktop & Mobile",
        )
        replacement["eyebrow"] = "多端展示" if is_zh else "MULTI-DEVICE"
        replacement["headline"] = _truncate(s_head.example_value, 80)

    elif bid == "chat_demo":
        msg_count = max(2, min(4, len(act.item_reveals_s) or 2))
        messages: list[dict[str, Any]] = []
        for i in range(msg_count):
            role = "user" if i % 2 == 0 else "assistant"
            s_msg = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"messages[{i}]",
                kind="message",
                label_zh=f"对话消息 #{i + 1} ({'用户' if role == 'user' else 'AI'})",
                label_en=f"Chat Message #{i + 1} ({'User' if role == 'user' else 'Assistant'})",
                example_zh=(
                    f"{{code}} 输入用户的真实指令或问题 #{i // 2 + 1}"
                    if role == "user"
                    else f"{{code}} 展示系统即时给出的精准回复 #{i // 2 + 1}"
                ),
                example_en=(
                    f"{{code}} User prompt or question #{i // 2 + 1}"
                    if role == "user"
                    else f"{{code}} Grounded AI response #{i // 2 + 1}"
                ),
            )
            msg: dict[str, Any] = {"role": role, "text": _truncate(s_msg.example_value, 120)}
            if i < len(act.item_reveals_s) and act.item_reveals_s[i] is not None:
                msg["at_s"] = float(act.item_reveals_s[i])
            messages.append(msg)
        replacement["title"] = "对话演示" if is_zh else "Live Chat Demo"
        replacement["messages"] = messages

        if act.secondary_reveals_s or "work_steps" in act.required_slots or "work_steps" in act.optional_slots:
            step_count = max(2, min(4, len(act.secondary_reveals_s) or 2))
            work_steps: list[dict[str, Any]] = []
            for i in range(step_count):
                s_ws = allocator.next(
                    act_index=act_index,
                    act_id=act.act_id,
                    block_id=bid,
                    slot_key=f"work_steps[{i}]",
                    kind="text",
                    label_zh=f"执行步骤 #{i + 1}",
                    label_en=f"Agent Work Step #{i + 1}",
                    example_zh=f"{{code}} 执行步骤 #{i + 1}",
                    example_en=f"{{code}} Execution Step #{i + 1}",
                )
                ws: dict[str, Any] = {"label": _truncate(s_ws.example_value, 80)}
                if i < len(act.secondary_reveals_s) and act.secondary_reveals_s[i] is not None:
                    ws["at_s"] = float(act.secondary_reveals_s[i])
                work_steps.append(ws)
            replacement["work_steps"] = work_steps

        s_res = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="result_card",
            kind="text",
            label_zh="输出成果卡",
            label_en="Output Result Card",
            example_zh="{code} 输出成果卡片标题",
            example_en="{code} Generated Result Title",
        )
        replacement["result_card"] = {
            "title": _truncate(s_res.example_value, 80),
            "subtitle": "一句话说明产出价值" if is_zh else "Concise summary of the deliverable",
            "badge": "READY",
        }
        if "preview_resource" in act.required_slots:
            add_image_slot(
                "preview_resource",
                "成果预览图 (16:9)",
                "Result Preview Image (16:9)",
                width=1280,
                height=720,
                aspect_ratio="16:9",
                res_index=0,
            )

    elif bid == "metric_grid":
        s_title = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="title",
            kind="text",
            label_zh="指标幕主标题",
            label_en="Metric Section Title",
            example_zh="{code} 核心成效与量化证明",
            example_en="{code} Quantified Proof & Key Metrics",
        )
        replacement["eyebrow"] = "KEY METRICS"
        replacement["title"] = _truncate(s_title.example_value, 120)
        count = max(2, min(4, len(act.metric_reveals_s) or 3))
        sample_values = ["98%", "4.2×", "120+", "3.6s"]
        items: list[dict[str, Any]] = []
        for i in range(count):
            val = sample_values[i % len(sample_values)]
            s_item = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"items[{i}]",
                kind="metric",
                label_zh=f"数据指标 #{i + 1}（数值 + 标签）",
                label_en=f"Metric Card #{i + 1} (Value + Label)",
                example_zh=f"{{code}} 核心指标 #{i + 1}",
                example_en=f"{{code}} Key Metric #{i + 1}",
            )
            entry: dict[str, Any] = {
                "value": val,
                "label": _truncate(s_item.example_value, 48),
                "detail": (
                    f"替换为你的真实数据说明 #{i + 1}"
                    if is_zh
                    else f"Replace with verified proof #{i + 1}"
                ),
            }
            if i < len(act.metric_reveals_s) and act.metric_reveals_s[i] is not None:
                entry["reveal_at_s"] = float(act.metric_reveals_s[i])
            items.append(entry)
        replacement["items"] = items
        defaults["columns"] = 2 if count in (2, 4) else 3

    elif bid == "bento_features":
        s_title = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="title",
            kind="text",
            label_zh="卖点矩阵标题",
            label_en="Feature Grid Title",
            example_zh="{code} 核心产品能力矩阵",
            example_en="{code} Core Capability Matrix",
        )
        replacement["eyebrow"] = "FEATURES"
        replacement["title"] = _truncate(s_title.example_value, 80)
        count = max(3, min(4, len(act.item_reveals_s) or 3))
        cards: list[dict[str, Any]] = []
        for i in range(count):
            s_card = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"cards[{i}]",
                kind="text",
                label_zh=f"核心卖点卡 #{i + 1}",
                label_en=f"Feature Card #{i + 1}",
                example_zh=f"{{code}} 核心卖点 #{i + 1}",
                example_en=f"{{code}} Core Feature #{i + 1}",
            )
            card: dict[str, Any] = {
                "tag": s_card.code,
                "title": _truncate(s_card.example_value, 80),
                "detail": (
                    f"用 1 句话概括第 {i + 1} 项产品差异化价值"
                    if is_zh
                    else f"One concise sentence explaining feature #{i + 1}"
                ),
            }
            if i < len(act.item_reveals_s) and act.item_reveals_s[i] is not None:
                card["reveal_at_s"] = float(act.item_reveals_s[i])
            cards.append(card)
        replacement["cards"] = cards
        if isinstance(defaults.get("highlight_index"), int) and defaults["highlight_index"] >= count:
            defaults["highlight_index"] = count - 1

    elif bid == "flow_diagram":
        s_title = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="title",
            kind="text",
            label_zh="流程图标题",
            label_en="Flow Diagram Title",
            example_zh="{code} 端到端工作原理",
            example_en="{code} How The Pipeline Works",
        )
        replacement["eyebrow"] = "WORKFLOW"
        replacement["title"] = _truncate(s_title.example_value, 80)
        count = max(3, min(5, len(act.item_reveals_s) or 4))
        nodes: list[dict[str, Any]] = []
        for i in range(count):
            s_node = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"nodes[{i}]",
                kind="text",
                label_zh=f"流程节点 #{i + 1}",
                label_en=f"Flow Node #{i + 1}",
                example_zh=f"{{code}} 步骤节点 #{i + 1}",
                example_en=f"{{code}} Process Node #{i + 1}",
            )
            node: dict[str, Any] = {
                "step_label": f"0{i + 1}",
                "title": _truncate(s_node.example_value, 80),
                "detail": (
                    f"填入第 {i + 1} 环节的输入或处理机制"
                    if is_zh
                    else f"Describe stage #{i + 1} transformation"
                ),
            }
            if i < len(act.item_reveals_s) and act.item_reveals_s[i] is not None:
                node["reveal_at_s"] = float(act.item_reveals_s[i])
            nodes.append(node)
        replacement["nodes"] = nodes

    elif bid == "step_timeline":
        s_title = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="title",
            kind="text",
            label_zh="时间线标题",
            label_en="Timeline Section Title",
            example_zh="{code} 三步落地路径",
            example_en="{code} Step-by-Step Roadmap",
        )
        replacement["eyebrow"] = "TIMELINE"
        replacement["title"] = _truncate(s_title.example_value, 80)
        count = max(3, min(4, len(act.item_reveals_s) or 3))
        steps_list: list[dict[str, Any]] = []
        for i in range(count):
            s_step = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"steps[{i}]",
                kind="text",
                label_zh=f"阶段里程碑 #{i + 1}",
                label_en=f"Milestone Step #{i + 1}",
                example_zh=f"{{code}} 阶段里程碑 #{i + 1}",
                example_en=f"{{code}} Milestone #{i + 1}",
            )
            step_item: dict[str, Any] = {
                "number": f"{i + 1:02d}",
                "title": _truncate(s_step.example_value, 80),
                "detail": (
                    f"描述第 {i + 1} 步的具体动作与结果"
                    if is_zh
                    else f"Outline action and outcome for step #{i + 1}"
                ),
            }
            if i < len(act.item_reveals_s) and act.item_reveals_s[i] is not None:
                step_item["reveal_at_s"] = float(act.item_reveals_s[i])
            steps_list.append(step_item)
        replacement["steps"] = steps_list
        if isinstance(defaults.get("active_step"), int) and defaults["active_step"] > count:
            defaults["active_step"] = count

    elif bid == "split_compare":
        s_title = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="title",
            kind="text",
            label_zh="对比幕主标题",
            label_en="Comparison Title",
            example_zh="{code} 传统方式 vs 全新方案",
            example_en="{code} Old Way vs New Way",
        )
        replacement["eyebrow"] = "COMPARISON"
        replacement["title"] = _truncate(s_title.example_value, 80)

        s_lh = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="left_heading",
            kind="text",
            label_zh="左栏标题（旧方案）",
            label_en="Left Column Heading",
            example_zh="{code} 传统流程痛点",
            example_en="{code} Legacy Bottlenecks",
        )
        replacement["left_heading"] = _truncate(s_lh.example_value, 80)
        left_count = max(2, min(4, len(act.item_reveals_s) or 3))
        left_items: list[dict[str, Any]] = []
        for i in range(left_count):
            s_li = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"left_items[{i}]",
                kind="text",
                label_zh=f"左栏对比项 #{i + 1}",
                label_en=f"Left Comparison Item #{i + 1}",
                example_zh=f"{{code}} 旧方案痛点 #{i + 1}",
                example_en=f"{{code}} Legacy Limitation #{i + 1}",
            )
            li: dict[str, Any] = {"text": _truncate(s_li.example_value, 120)}
            if i < len(act.item_reveals_s) and act.item_reveals_s[i] is not None:
                li["reveal_at_s"] = float(act.item_reveals_s[i])
            left_items.append(li)
        replacement["left_items"] = left_items

        s_rh = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="right_heading",
            kind="text",
            label_zh="右栏标题（新方案）",
            label_en="Right Column Heading",
            example_zh="{code} 新方案突破",
            example_en="{code} Modern Advantage",
        )
        replacement["right_heading"] = _truncate(s_rh.example_value, 80)
        right_count = max(2, min(4, len(act.secondary_reveals_s) or left_count))
        right_items: list[dict[str, Any]] = []
        for i in range(right_count):
            s_ri = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"right_items[{i}]",
                kind="text",
                label_zh=f"右栏对比项 #{i + 1}",
                label_en=f"Right Comparison Item #{i + 1}",
                example_zh=f"{{code}} 新方案优势 #{i + 1}",
                example_en=f"{{code}} Modern Benefit #{i + 1}",
            )
            ri: dict[str, Any] = {"text": _truncate(s_ri.example_value, 120)}
            if i < len(act.secondary_reveals_s) and act.secondary_reveals_s[i] is not None:
                ri["reveal_at_s"] = float(act.secondary_reveals_s[i])
            right_items.append(ri)
        replacement["right_items"] = right_items

    elif bid == "data_chart":
        s_title = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="title",
            kind="text",
            label_zh="数据图表标题",
            label_en="Data Chart Title",
            example_zh="{code} 核心增长趋势图",
            example_en="{code} Measured Growth Trend",
        )
        chart_type = defaults.get("chart_type")
        if chart_type not in {"bar", "line"}:
            chart_type = "bar"
        defaults["chart_type"] = chart_type
        replacement["eyebrow"] = "DATA PROOF"
        replacement["title"] = _truncate(s_title.example_value, 80)
        replacement["subtitle"] = (
            "替换为实测周期或对比维度数据"
            if is_zh
            else "Replace with observed benchmark values"
        )
        replacement["unit"] = "%"
        count = max(3, min(8, len(act.item_reveals_s) or 4))
        points: list[dict[str, Any]] = []
        for i in range(count):
            val = float(28 + i * 21)
            s_pt = allocator.next(
                act_index=act_index,
                act_id=act.act_id,
                block_id=bid,
                slot_key=f"points[{i}]",
                kind="chart_point",
                label_zh=f"图表维度 #{i + 1}（标签 + 数值）",
                label_en=f"Chart Point #{i + 1} (Label + Value)",
                example_zh=f"{{code}} 维度{i + 1}",
                example_en=f"{{code}} Metric {i + 1}",
            )
            pt: dict[str, Any] = {
                "label": _truncate(s_pt.example_value, 32),
                "value": val,
                "display_value": f"{int(val)}%",
            }
            if i < len(act.item_reveals_s) and act.item_reveals_s[i] is not None:
                pt["reveal_at_s"] = float(act.item_reveals_s[i])
            points.append(pt)
        replacement["points"] = points
        if isinstance(defaults.get("highlight_index"), int) and defaults["highlight_index"] >= count:
            defaults["highlight_index"] = count - 1

    elif bid == "quote_proof":
        hl_zh, hl_en = "真实用户评价或权威背书", "verified customer quote"
        s_quote = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="quote",
            kind="text",
            label_zh="核心引证金句",
            label_en="Proof Quote",
            example_zh=f"{{code}} 在这里放入{hl_zh}原话，直接放大产品可信度。",
            example_en=f"{{code}} Place a {hl_en} or press citation here to build instant trust.",
        )
        s_author = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="author",
            kind="text",
            label_zh="引证来源 / 作者",
            label_en="Author / Source",
            example_zh="{code} 客户姓名 / 媒体机构",
            example_en="{code} Customer Name / Publication",
        )
        replacement["quote"] = _truncate(s_quote.example_value, 320)
        replacement["highlight_phrase"] = hl_zh if is_zh else hl_en
        replacement["author"] = _truncate(s_author.example_value, 80)
        replacement["role_or_source"] = (
            "职务头衔 · 真实来源出处" if is_zh else "Title · Verified Source"
        )
        replacement["verification_badge"] = "VERIFIED"

    elif bid == "closing_cta":
        s_brand = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="brand_name",
            kind="text",
            label_zh="品牌名称",
            label_en="Brand Name",
            example_zh="{code} 你的品牌名",
            example_en="{code} Your Brand Name",
        )
        s_tag = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="tagline",
            kind="text",
            label_zh="收尾行动口号",
            label_en="Closing Tagline",
            example_zh="{code} 用一句话收尾并给出明确行动理由",
            example_en="{code} One crisp closing line with a clear reason to act",
        )
        s_cta = allocator.next(
            act_index=act_index,
            act_id=act.act_id,
            block_id=bid,
            slot_key="url_text",
            kind="text",
            label_zh="网址 / CTA 按钮",
            label_en="Website URL / CTA",
            example_zh="{code} your-brand.com",
            example_en="{code} your-brand.com",
        )
        replacement["brand_name"] = _truncate(s_brand.example_value, 80)
        replacement["tagline"] = _truncate(s_tag.example_value, 160)
        replacement["cta_label"] = "立即体验" if is_zh else "Start Now"
        replacement["url_text"] = _truncate(s_cta.example_value, 80)

    else:  # pragma: no cover - exhaustive over all 15 MotionBlockIds
        raise ValueError(f"Unsupported motion block: {bid}")

    # Guarantee opaque canvas backdrop on main acts so blueprint transitions validate cleanly
    if bid not in {"kinetic_title", "kinetic_beat", "ui_montage"}:
        replacement.setdefault("show_backdrop", True)

    merged_props = act_for_bind.bind_props(replacement)
    return merged_props, resources, generated_assets


def count_blueprint_slots(blueprint: SkillBlueprintV1) -> int:
    """Fast deterministic count of numbered replaceable slots across all blueprint acts."""
    style = blueprint.style or CompositionStyle(preset_id="institutional_dark")
    tokens = resolve_style_tokens(style)
    allocator = _SlotAllocator("zh")
    for idx, act in enumerate(blueprint.acts):
        _plan_act_slots(
            act,
            idx,
            allocator,
            tokens=tokens,
            locale="zh",
            override_style=False,
            generate_png=False,
            placeholder_resources=None,
        )
        for ov_idx, _ in enumerate(act.overlays):
            allocator.next(
                act_index=idx,
                act_id=act.act_id,
                block_id="kinetic_title",
                slot_key=f"overlay[{ov_idx}].headline",
                kind="text",
                label_zh=f"叠加角标标题 #{ov_idx + 1}",
                label_en=f"Overlay Title #{ov_idx + 1}",
                example_zh="{code} 叠加标注短句",
                example_en="{code} Overlay Callout",
            )
    return len(allocator.items)


def format_slot_checklist(
    slots: list[SlotManifestItem],
    locale: Literal["zh", "en"] = "zh",
    *,
    template_name: str | None = None,
) -> str:
    """Format a ready-to-paste social media / user checklist for [01]..[N] slots."""
    is_zh = locale == "zh"
    header = (
        f"🎬 模板槽位清单（共 {len(slots)} 个可替换槽位）"
        if is_zh
        else f"🎬 Template Slot Checklist ({len(slots)} replaceable slots)"
    )
    if template_name:
        header = f"{header} · {template_name}"
    lines = [header, ""]
    current_act: int | None = None
    for item in slots:
        if item.act_index != current_act:
            current_act = item.act_index
            act_heading = (
                f"── ACT {item.act_index + 1:02d} ({item.block_id}) ──"
            )
            if len(lines) > 2:
                lines.append("")
            lines.append(act_heading)
        label = item.label_zh if is_zh else item.label_en
        ratio_tag = f" [{item.aspect_ratio}]" if item.aspect_ratio else ""
        lines.append(f"{item.code} {label}{ratio_tag}")
    return "\n".join(lines)


def _resolve_effective_style(
    blueprint: SkillBlueprintV1,
    style_preset: StylePresetId | None,
    accent_color: str | None,
) -> tuple[CompositionStyle, ResolvedStyleTokens, bool]:
    if style_preset is not None:
        style = CompositionStyle(preset_id=style_preset, accent_color=accent_color)
        return style, resolve_style_tokens(style), True
    if blueprint.style is not None:
        style = (
            blueprint.style.model_copy(update={"accent_color": accent_color})
            if accent_color is not None
            else blueprint.style
        )
        return style, resolve_style_tokens(style), False
    style = CompositionStyle(preset_id="institutional_dark", accent_color=accent_color)
    return style, resolve_style_tokens(style), True


def compile_blueprint_slot_preview(
    blueprint: SkillBlueprintV1,
    *,
    style_preset: StylePresetId | None = None,
    accent_color: str | None = None,
    locale: Literal["zh", "en"] = "zh",
    sfx_snapshots: dict[str, tuple[UUID, str, int]] | None = None,
    placeholder_resources: dict[str, RemotionResource] | None = None,
) -> tuple[CompositionContent, list[SlotManifestItem]]:
    """Compile a SkillBlueprintV1 into a numbered slot preview CompositionContent + manifest.

    ``sfx_snapshots`` maps ``cue_id`` -> ``(snapshot_id, digest, duration_ticks_at_SOURCE_TIMEBASE)``.
    """
    content, manifest, _ = compile_blueprint_slot_preview_with_assets(
        blueprint,
        style_preset=style_preset,
        accent_color=accent_color,
        locale=locale,
        sfx_snapshots=sfx_snapshots,
        placeholder_resources=placeholder_resources,
    )
    return content, manifest


def compile_blueprint_slot_preview_with_assets(
    blueprint: SkillBlueprintV1,
    *,
    style_preset: StylePresetId | None = None,
    accent_color: str | None = None,
    locale: Literal["zh", "en"] = "zh",
    sfx_snapshots: dict[str, tuple[UUID, str, int]] | None = None,
    placeholder_resources: dict[str, RemotionResource] | None = None,
) -> tuple[CompositionContent, list[SlotManifestItem], list[PlaceholderImageAsset]]:
    """Compile a SkillBlueprintV1 and also return generated Pillow placeholder assets."""
    style, tokens, override_style = _resolve_effective_style(
        blueprint, style_preset, accent_color
    )
    width = int(blueprint.canvas.get("width", 1920))
    height = int(blueprint.canvas.get("height", 1080))
    fps_num = int(blueprint.canvas.get("fps_num", 30))
    fps_den = int(blueprint.canvas.get("fps_den", 1))
    settings_obj = VersionSettings(
        width=width,
        height=height,
        fps={"num": fps_num, "den": fps_den},
        background=tokens["canvas_bg"],
        style=style,
    )
    tb = settings_obj.timebase

    def quantize_up_ticks(sec: float) -> int:
        frames = max(1, math.ceil(sec * fps_num / fps_den - 1e-9))
        return frames_to_ticks(frames, tb, fps_num, fps_den)

    allocator = _SlotAllocator(locale)
    all_assets: list[PlaceholderImageAsset] = []
    bound_snapshots: dict[UUID, str] = {}

    scenes: list[Scene] = []
    main_clips: list[Clip] = []
    title_clips: list[Clip] = []
    hud_clips: list[Clip] = []
    act_windows: list[tuple[int, int, str]] = []

    hud_token = resolve_text_preset_token("lower_third_tag", tokens)
    hud_font_size = max(18, round(width * 22 / 1920))
    hud_style = text_style_from_token(
        hud_token,
        font_size=hud_font_size,
        align="right",
        line_height=1.2,
    )
    hud_w = min(width - 80, round(width * 0.34))
    hud_h = max(44, round(hud_font_size * 2.4))
    hud_layout = LayoutBox(
        x=float(width - hud_w - 40),
        y=26.0,
        width=float(hud_w),
        height=float(hud_h),
    )

    cursor = 0
    for idx, act in enumerate(blueprint.acts):
        first_slot_before = len(allocator.items)
        merged_props, act_resources, act_assets = _plan_act_slots(
            act,
            idx,
            allocator,
            tokens=tokens,
            locale=locale,
            override_style=override_style,
            generate_png=True,
            placeholder_resources=placeholder_resources,
        )
        all_assets.extend(act_assets)
        for res in act_resources:
            bound_snapshots[res.snapshot_id] = res.snapshot_digest

        dur_ticks = quantize_up_ticks(act.target_duration_s)
        start = cursor
        end = cursor + dur_ticks
        cursor = end
        scene_id = f"scene_{idx + 1}"
        clip_id = f"clp_slot_act_{idx + 1}"
        act_windows.append((start, end, clip_id))
        scenes.append(Scene(scene_id=scene_id, range=TimeRange(start=start, end=end)))

        main_obj = MotionBlockObject(
            kind="motion_block",
            object_id=f"obj_slot_act_{idx + 1}",
            block_id=act.block_id,
            block_version=act.block_version,
            props=merged_props,
            resources=act_resources,
            layout=LayoutBox(x=0, y=0, width=float(width), height=float(height)),
            fit="cover" if act.block_id != "kinetic_title" else "contain",
        )
        main_clips.append(
            Clip(
                clip_id=clip_id,
                range=TimeRange(start=start, end=end),
                scene_id=scene_id,
                source=None,
                object=main_obj,
                animations=[],
            )
        )

        # Preserve act overlays with numbered headline slots
        for ov_idx, ov in enumerate(act.overlays):
            s_ov = allocator.next(
                act_index=idx,
                act_id=act.act_id,
                block_id="kinetic_title",
                slot_key=f"overlay[{ov_idx}].headline",
                kind="text",
                label_zh=f"叠加角标标题 #{ov_idx + 1}",
                label_en=f"Overlay Title #{ov_idx + 1}",
                example_zh="{code} 叠加标注短句",
                example_en="{code} Overlay Callout",
            )
            ov_defaults = dict(ov.style_defaults)
            if override_style:
                for k in INHERITABLE_BLOCK_STYLE_KEYS["kinetic_title"]:
                    ov_defaults.pop(k, None)
            ov_props = {**ov_defaults, "headline": _truncate(s_ov.example_value, 140)}
            ov_start = max(start, min(end - quantize_up_ticks(0.4), start + quantize_up_ticks(ov.rel_start_s)))
            ov_dur = max(1.0, ov.rel_end_s - ov.rel_start_s)
            ov_end = min(end - quantize_up_ticks(0.1), ov_start + quantize_up_ticks(ov_dur))
            if ov_end > ov_start:
                title_clips.append(
                    Clip(
                        clip_id=f"clp_slot_ov_{idx + 1}_{ov_idx + 1}",
                        range=TimeRange(start=ov_start, end=ov_end),
                        scene_id=scene_id,
                        source=None,
                        object=MotionBlockObject(
                            kind="motion_block",
                            object_id=f"obj_slot_ov_{idx + 1}_{ov_idx + 1}",
                            block_id="kinetic_title",
                            block_version=1,
                            props=ov_props,
                            resources=[],
                            layout=LayoutBox(x=0, y=0, width=float(width), height=float(height)),
                            fit="contain",
                        ),
                        animations=[],
                    )
                )

        # Per-act corner slot HUD badge on dedicated top caption track
        act_slots = allocator.items[first_slot_before:]
        if act_slots:
            first_code = act_slots[0].code
            last_code = act_slots[-1].code
            slot_span = first_code if first_code == last_code else f"{first_code}–{last_code}"
            hud_text = (
                f"ACT {idx + 1:02d} · 槽位 {slot_span}"
                if locale == "zh"
                else f"ACT {idx + 1:02d} · SLOTS {slot_span}"
            )
            hud_clips.append(
                Clip(
                    clip_id=f"clp_slot_hud_{idx + 1}",
                    range=TimeRange(start=start, end=end),
                    scene_id=scene_id,
                    source=None,
                    object=TextObject(
                        kind="text",
                        object_id=f"obj_slot_hud_{idx + 1}",
                        text=hud_text,
                        layout=hud_layout,
                        style=hud_style,
                    ),
                    animations=[],
                )
            )

    total_ticks = cursor

    # Preserve transitions between adjacent opaque main acts
    transitions: list[Transition] = []
    for idx, act in enumerate(blueprint.acts):
        if act.transition_after is None or idx + 1 >= len(act_windows):
            continue
        cur_start, cur_end, from_cid = act_windows[idx]
        nxt_start, nxt_end, to_cid = act_windows[idx + 1]
        if (
            main_clips[idx].object.opaque_backdrop
            and main_clips[idx + 1].object.opaque_backdrop
            and main_clips[idx].object.fit == "cover"
            and main_clips[idx + 1].object.fit == "cover"
        ):
            trn_s = min(
                act.transition_after.duration_s,
                (cur_end - cur_start) / tb,
                (nxt_end - nxt_start) / tb,
            )
            trn_ticks = seconds_to_ticks(trn_s, tb)
            if ticks_to_frames(trn_ticks, tb, fps_num, fps_den) >= 2:
                transitions.append(
                    Transition(
                        transition_id=f"trn_slot_{idx + 1}",
                        from_clip_id=from_cid,
                        to_clip_id=to_cid,
                        kind=act.transition_after.kind,
                        duration=trn_ticks,
                        alignment="center",
                    )
                )

    tracks: list[Track] = [
        Track(track_id="trk_slot_main", kind="visual", role="main", order=0, clips=main_clips),
    ]
    if title_clips:
        tracks.append(
            Track(track_id="trk_slot_title", kind="visual", role="title", order=1, clips=title_clips)
        )
    if hud_clips:
        tracks.append(
            Track(track_id="trk_slot_hud", kind="visual", role="caption", order=10, clips=hud_clips)
        )

    # Preserve SFX cues on collision-free effect audio tracks when snapshots are supplied
    if sfx_snapshots:
        audio_order = 0
        effect_tracks: list[Track] = []
        for sfx_idx, cue in enumerate(blueprint.sfx_cues):
            if cue.act_index >= len(act_windows) or cue.cue_id not in sfx_snapshots:
                continue
            snap_id, snap_digest, dur_src_ticks = sfx_snapshots[cue.cue_id]
            act_start, act_end, _ = act_windows[cue.act_index]
            anchor_ticks = act_start if cue.anchor == "act_start" else act_end
            offset_ticks = seconds_to_ticks(abs(cue.offset_s), tb)
            if cue.offset_s < 0:
                offset_ticks = -offset_ticks
            sfx_start = max(0, anchor_ticks + offset_ticks)
            sfx_out_dur = source_ticks_to_output_ticks(dur_src_ticks, tb)
            sfx_end = min(total_ticks, sfx_start + sfx_out_dur)
            if sfx_end <= sfx_start:
                continue
            used_src = min(dur_src_ticks, output_ticks_to_source_ticks(sfx_end - sfx_start, tb))
            if used_src <= 0:
                continue
            bound_snapshots[snap_id] = snap_digest
            sfx_clip = Clip(
                clip_id=f"clp_slot_sfx_{sfx_idx + 1}",
                range=TimeRange(start=sfx_start, end=sfx_end),
                scene_id=None,
                source=ClipSource(
                    snapshot_id=snap_id,
                    snapshot_digest=snap_digest,
                    source_range=TimeRange(start=0, end=used_src),
                ),
                object=AudioObject(
                    kind="audio",
                    object_id=f"obj_slot_sfx_{sfx_idx + 1}",
                    gain_db=cue.gain_db,
                ),
                animations=[],
            )
            placed = False
            for et in effect_tracks:
                if not any(c.range.start < sfx_end and sfx_start < c.range.end for c in et.clips):
                    et.clips.append(sfx_clip)
                    placed = True
                    break
            if not placed:
                tid = "trk_slot_effect" if not effect_tracks else f"trk_slot_effect_{len(effect_tracks) + 1}"
                effect_tracks.append(
                    Track(
                        track_id=tid,
                        kind="audio",
                        role="effect",
                        order=audio_order,
                        clips=[sfx_clip],
                    )
                )
                audio_order += 1
        tracks.extend(effect_tracks)

    sources = [SourceBinding(snapshot_id=sid, snapshot_digest=dig) for sid, dig in bound_snapshots.items()]
    content = CompositionContent(
        settings=settings_obj,
        sources=sources,
        scenes=scenes,
        timeline=Timeline(tracks=tracks, transitions=transitions),
    )
    return content, allocator.items, all_assets


def build_slot_preview_video_spec(
    blueprint: SkillBlueprintV1,
    *,
    skill_version_id: UUID,
    style_preset: StylePresetId | None = None,
    accent_color: str | None = None,
    locale: Literal["zh", "en"] = "zh",
    font_url_prefix: str = "/api/v1/skills/fonts",
    inline_placeholders: bool = True,
    placeholder_url_map: dict[UUID, str] | None = None,
    sfx_snapshots: dict[str, tuple[UUID, str, int, str]] | None = None,
) -> tuple[dict[str, Any], list[SlotManifestItem], list[PlaceholderImageAsset], float]:
    """Compile a SkillBlueprintV1 all the way into a video-spec dict ready for Player or Render.

    ``sfx_snapshots`` optionally maps ``cue_id`` -> ``(snapshot_id, digest, duration_ticks, url)``.
    """
    sfx_for_content = (
        {k: (v[0], v[1], v[2]) for k, v in sfx_snapshots.items()}
        if sfx_snapshots
        else None
    )
    content, slots, assets = compile_blueprint_slot_preview_with_assets(
        blueprint,
        style_preset=style_preset,
        accent_color=accent_color,
        locale=locale,
        sfx_snapshots=sfx_for_content,
    )

    snapshots: dict[UUID, dict[str, Any]] = {}
    for asset in assets:
        if placeholder_url_map and asset.snapshot_id in placeholder_url_map:
            url = placeholder_url_map[asset.snapshot_id]
        elif inline_placeholders:
            url = asset.data_url
        else:
            url = asset.path
        snapshots[asset.snapshot_id] = {"storage_key": url, "digest": asset.digest}

    if sfx_snapshots:
        for snap_id, digest, dur_ticks, url in sfx_snapshots.values():
            snapshots[snap_id] = {
                "storage_key": url,
                "digest": digest,
                "duration_ticks": dur_ticks,
            }

    content_digest = canonical_json_hash(content.model_dump(mode="json"))
    spec = compile_video_spec(
        content,
        snapshots,
        composition_id=uuid5(NAMESPACE_URL, f"slot-preview-comp:{skill_version_id}"),
        version_id=skill_version_id,
        content_digest=content_digest,
    )

    # Rewrite pinned font storage keys to the requested font URL prefix
    prefix = font_url_prefix.rstrip("/")
    for font in spec.get("fonts", []):
        filename = _FONT_STORAGE_KEY_TO_FILENAME.get(font["url"])
        if filename:
            font["url"] = f"{prefix}/{filename}"

    duration_s = round(
        spec["duration_frames"] * spec["fps"]["den"] / spec["fps"]["num"],
        2,
    )
    return spec, slots, assets, duration_s
