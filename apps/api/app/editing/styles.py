"""First-class orthogonal CompositionStyle registry & deterministic token resolver.

Zero SQL tables: ``CompositionStyle`` persists in ``CompositionVersion.settings.style``
and ``SkillBlueprintV1.style``. Discovery metadata (``name``, ``desc``, ``bgm_mood``,
``sfx_palette``) lives in ``STYLE_PRESET_CATALOG`` and NEVER enters ``content_digest``
or ``video-spec``.

Mirror contract: ``packages/video-remotion/src/engine/styles.ts`` implements the
exact same presets and W3C relative-luminance contrast algorithm. Core tests verify
zero drift across all presets and custom override combinations via Node subprocess.
"""

from __future__ import annotations

import math
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.editing.text_presets import (
    TEXT_STYLE_PRESETS,
    TextShadowToken,
    TextStrokeToken,
    TextStylePresetToken,
    copy_text_preset_token,
)

StylePresetId = Literal[
    "institutional_dark",
    "swiss_paper",
    "vox_editorial",
    "kinetic_anime",
]

BackdropStyle = Literal[
    "ambient_mesh",
    "architectural_grid",
    "editorial_paper",
    "kinetic_diagonal",
    "studio_spotlight",
    "warm_obsidian",
    "editorial_studio",
    "clean",
]

CardTreatment = Literal[
    "glass_soft",
    "minimal_hairline",
    "editorial_rule",
    "brutal_offset",
]

HeadlineTreatment = Literal[
    "clean",
    "swiss_rule",
    "highlight_tape",
    "outlined_impact",
]

StyleTransitionKind = Literal[
    "crossfade",
    "whip_pan",
    "wipe_reveal",
    "zoom_through",
    "iris_focus",
]

# Motion block prop keys inherited from CompositionStyle unless explicitly overridden per block.
INHERITABLE_BLOCK_STYLE_KEYS: dict[str, tuple[str, ...]] = {
    "kinetic_title": ("accent_color", "text_color", "surface_style"),
    "product_showcase": ("theme", "accent_color", "backdrop_style"),
    "statement_hook": ("theme", "accent_color", "backdrop_style"),
    "metric_grid": ("theme", "accent_color", "backdrop_style"),
    "closing_cta": ("theme", "accent_color", "backdrop_style"),
    "chat_demo": ("theme", "accent_color", "backdrop_style"),
    "kinetic_beat": ("theme", "backdrop_style", "accent_color", "show_backdrop"),
    "ui_montage": ("theme", "backdrop_style", "accent_color", "show_backdrop"),
    "cursor_magnetic_click": ("theme", "accent_color", "backdrop_style"),
    "zoom_follows_click": ("theme", "backdrop_style"),
    "browser_url_load": ("theme", "backdrop_style"),
    "code_terminal": ("theme", "accent_color", "backdrop_style"),
    "logo_wall": ("theme", "accent_color", "backdrop_style"),
    "device_mockup": ("theme", "accent_color", "backdrop_style"),
    "flow_diagram": ("theme", "accent_color", "backdrop_style"),
    "split_compare": ("theme", "accent_color", "backdrop_style"),
    "step_timeline": ("theme", "accent_color", "backdrop_style"),
    "bento_features": ("theme", "accent_color", "backdrop_style"),
    "data_chart": ("theme", "accent_color", "backdrop_style"),
    "quote_proof": ("theme", "accent_color", "backdrop_style"),
}


class CompositionStyle(BaseModel):
    """Minimal serializable style declaration stored on VersionSettings & SkillBlueprintV1."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    preset_id: StylePresetId
    accent_color: str | None = Field(
        default=None, pattern=r"^#[0-9a-fA-F]{6}$", exclude_if=lambda v: v is None
    )
    backdrop_style: BackdropStyle | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    theme: Literal["dark", "light"] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )


CaptionStrokeToken = TextStrokeToken
CaptionShadowToken = TextShadowToken
CaptionStyleToken = TextStylePresetToken


class ResolvedStyleTokens(TypedDict):
    preset_id: StylePresetId
    theme: Literal["dark", "light"]
    backdrop_style: BackdropStyle
    canvas_bg: str
    surface_bg: str
    ink: str
    secondary_ink: str
    line_color: str
    accent: str
    accent_secondary: str
    accent_ink: str
    accent_text: str
    card_treatment: CardTreatment
    headline_treatment: HeadlineTreatment
    heading_weight: Literal[700, 900]
    default_transition: StyleTransitionKind
    caption_style: CaptionStyleToken


# Closed deterministic token table (mirrors packages/video-remotion/src/engine/styles.ts).
STYLE_PRESETS: dict[StylePresetId, ResolvedStyleTokens] = {
    "institutional_dark": {
        "preset_id": "institutional_dark",
        "theme": "dark",
        "backdrop_style": "ambient_mesh",
        "canvas_bg": "#0A0F16",
        "surface_bg": "#141E28",
        "ink": "#F4F7FA",
        "secondary_ink": "#B8C7D4",
        "line_color": "#2D3F4F",
        "accent": "#14B8A6",
        "accent_secondary": "#38BDF8",
        "accent_ink": "#061318",
        "accent_text": "#5EEAD4",
        "card_treatment": "glass_soft",
        "headline_treatment": "clean",
        "heading_weight": 700,
        "default_transition": "crossfade",
        "caption_style": copy_text_preset_token(TEXT_STYLE_PRESETS["clean_broadcast"]),
    },
    "swiss_paper": {
        "preset_id": "swiss_paper",
        "theme": "light",
        "backdrop_style": "architectural_grid",
        "canvas_bg": "#F6F5F0",
        "surface_bg": "#FFFFFF",
        "ink": "#111820",
        "secondary_ink": "#455360",
        "line_color": "#CBD3DA",
        "accent": "#D94626",
        "accent_secondary": "#111820",
        "accent_ink": "#FFFFFF",
        "accent_text": "#B93216",
        "card_treatment": "minimal_hairline",
        "headline_treatment": "swiss_rule",
        "heading_weight": 700,
        "default_transition": "wipe_reveal",
        "caption_style": copy_text_preset_token(TEXT_STYLE_PRESETS["minimal_light"]),
    },
    "vox_editorial": {
        "preset_id": "vox_editorial",
        "theme": "light",
        "backdrop_style": "editorial_paper",
        "canvas_bg": "#F4EFE2",
        "surface_bg": "#FFFDF7",
        "ink": "#141413",
        "secondary_ink": "#3E3D39",
        "line_color": "#141413",
        "accent": "#FACC15",
        "accent_secondary": "#2563EB",
        "accent_ink": "#141413",
        "accent_text": "#1D4ED8",
        "card_treatment": "editorial_rule",
        "headline_treatment": "highlight_tape",
        "heading_weight": 900,
        "default_transition": "wipe_reveal",
        "caption_style": copy_text_preset_token(TEXT_STYLE_PRESETS["vox_label"]),
    },
    "kinetic_anime": {
        "preset_id": "kinetic_anime",
        "theme": "dark",
        "backdrop_style": "kinetic_diagonal",
        "canvas_bg": "#0D0B14",
        "surface_bg": "#181426",
        "ink": "#FFFFFF",
        "secondary_ink": "#D4D0E8",
        "line_color": "#3F345C",
        "accent": "#FF2E63",
        "accent_secondary": "#00F0FF",
        "accent_ink": "#FFFFFF",
        "accent_text": "#FF6B8E",
        "card_treatment": "brutal_offset",
        "headline_treatment": "outlined_impact",
        "heading_weight": 900,
        "default_transition": "whip_pan",
        "caption_style": copy_text_preset_token(TEXT_STYLE_PRESETS["kinetic_impact"]),
    },
}

# Discovery & creative guidance metadata (never enters video-spec or content_digest).
STYLE_PRESET_CATALOG: dict[StylePresetId, dict[str, Any]] = {
    "institutional_dark": {
        "id": "institutional_dark",
        "name": "Institutional Dark",
        "desc": "Deep obsidian canvas with soft glass cards, teal-cyan accents, and restrained authority for flagship tech, research, and executive product films.",
        "visual_signature": "dark ambient_mesh, 22px soft glass cards, 700 weight clean headings, crossfade transitions",
        "default_transition": "crossfade",
        "bgm_mood": "Composed tech / restrained pulse",
        "sfx_palette": ["sub_swell", "deep_hit", "velvet_pass", "metric_chime", "callout_ping", "studio_air"],
    },
    "swiss_paper": {
        "id": "swiss_paper",
        "name": "Swiss Paper",
        "desc": "International Typographic Style on crisp alabaster coordinate grid with razor 1.5px hairlines, zero drop shadows, and vermilion accents.",
        "visual_signature": "light architectural_grid, 6px hairline cards, 700 weight swiss_rule headings, wipe_reveal transitions",
        "default_transition": "wipe_reveal",
        "bgm_mood": "Clean minimal / low intrusion",
        "sfx_palette": ["velvet_pass", "select_tick", "soft_pop", "callout_ping", "title_bloom"],
    },
    "vox_editorial": {
        "id": "vox_editorial",
        "name": "Vox Editorial",
        "desc": "Warm newsprint paper with 900 Black display headlines, left-to-right highlighter tape sweeps, 2px ink borders with hard print shadows, and compact dark editorial captions.",
        "visual_signature": "light editorial_paper, 4px ink-bordered cards with 4px hard shadow, 900 weight highlight_tape headings, wipe_reveal transitions",
        "default_transition": "wipe_reveal",
        "bgm_mood": "Curious narrative / crisp groove",
        "sfx_palette": ["page_turn", "soft_pop", "callout_ping", "velvet_pass", "confirm_chime", "metric_chime"],
    },
    "kinetic_anime": {
        "id": "kinetic_anime",
        "name": "Kinetic Anime",
        "desc": "High-energy dark poster aesthetic with 900 Black impact type, neon magenta & cyan accents, brutal 6px accent offset shadows, and diagonal kinetic scanlines.",
        "visual_signature": "dark kinetic_diagonal, 2px sharp brutal_offset cards, 900 weight outlined_impact headings, whip_pan transitions",
        "default_transition": "whip_pan",
        "bgm_mood": "High-energy beat / punchy impact",
        "sfx_palette": ["swoosh_cut", "kinetic_thud", "shimmer_lift", "stinger", "sub_drop", "toggle_on"],
    },
}

_THEME_BASES: dict[Literal["dark", "light"], dict[str, str]] = {
    "dark": {
        "canvas_bg": "#0A0F16",
        "surface_bg": "#141E28",
        "ink": "#F4F7FA",
        "secondary_ink": "#B8C7D4",
        "line_color": "#2D3F4F",
    },
    "light": {
        "canvas_bg": "#F6F5F0",
        "surface_bg": "#FFFFFF",
        "ink": "#111820",
        "secondary_ink": "#455360",
        "line_color": "#CBD3DA",
    },
}


def _parse_hex(hex_color: str) -> tuple[int, int, int]:
    clean = hex_color.lstrip("#")
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def _round_half_up(value: float) -> int:
    """Match JS Math.round for non-negative color channels."""
    return max(0, min(255, math.floor(value + 0.5)))


def _to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def relative_luminance(hex_color: str) -> float:
    """W3C WCAG 2.x relative luminance."""
    r, g, b = _parse_hex(hex_color)
    channels = []
    for raw in (r, g, b):
        c = raw / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """W3C WCAG 2.x contrast ratio in [1, 21]."""
    lum_a = relative_luminance(hex_a)
    lum_b = relative_luminance(hex_b)
    hi = max(lum_a, lum_b)
    lo = min(lum_a, lum_b)
    return (hi + 0.05) / (lo + 0.05)


def mix_hex(hex_a: str, hex_b: str, t: float) -> str:
    r1, g1, b1 = _parse_hex(hex_a)
    r2, g2, b2 = _parse_hex(hex_b)
    return _to_hex(
        _round_half_up(r1 + (r2 - r1) * t),
        _round_half_up(g1 + (g2 - g1) * t),
        _round_half_up(b1 + (b2 - b1) * t),
    )


def pick_contrast_ink(
    bg_hex: str,
    *,
    dark_candidate: str = "#111820",
    light_candidate: str = "#FFFFFF",
) -> str:
    c_dark = contrast_ratio(bg_hex, dark_candidate)
    c_light = contrast_ratio(bg_hex, light_candidate)
    return dark_candidate if c_dark >= c_light else light_candidate


def ensure_contrast_text(
    fg_hex: str,
    canvas_bg: str,
    surface_bg: str,
    *,
    dark_surface: bool,
    min_ratio: float = 4.5,
) -> str:
    """Adjust an arbitrary accent hex until contrast >= min_ratio on both canvas and surface."""
    base = fg_hex.upper()
    if contrast_ratio(base, canvas_bg) >= min_ratio and contrast_ratio(base, surface_bg) >= min_ratio:
        return base
    target = "#FFFFFF" if dark_surface else "#111820"
    for step in range(1, 21):
        candidate = mix_hex(base, target, step / 20.0)
        if (
            contrast_ratio(candidate, canvas_bg) >= min_ratio
            and contrast_ratio(candidate, surface_bg) >= min_ratio
        ):
            return candidate
    return target


def resolve_style_tokens(style: CompositionStyle) -> ResolvedStyleTokens:
    """Deterministically expand a CompositionStyle into closed render tokens."""
    preset = STYLE_PRESETS[style.preset_id]
    tokens: ResolvedStyleTokens = {
        **preset,
        "caption_style": copy_text_preset_token(preset["caption_style"]),
    }

    theme_changed = style.theme is not None and style.theme != preset["theme"]
    if theme_changed and style.theme is not None:
        base = _THEME_BASES[style.theme]
        tokens["theme"] = style.theme
        tokens["canvas_bg"] = base["canvas_bg"]
        tokens["surface_bg"] = base["surface_bg"]
        tokens["ink"] = base["ink"]
        tokens["secondary_ink"] = base["secondary_ink"]
        tokens["line_color"] = base["line_color"]
        if tokens["caption_style"]["background"] is None:
            preserved_weight = tokens["caption_style"]["weight"]
            fallback_id = "clean_broadcast" if style.theme == "dark" else "minimal_light"
            tokens["caption_style"] = copy_text_preset_token(TEXT_STYLE_PRESETS[fallback_id])
            tokens["caption_style"]["weight"] = preserved_weight

    if style.backdrop_style is not None:
        tokens["backdrop_style"] = style.backdrop_style

    is_dark = tokens["theme"] == "dark"
    if style.accent_color is not None:
        accent = style.accent_color.upper()
        tokens["accent"] = accent
        tokens["accent_ink"] = pick_contrast_ink(accent)
        tokens["accent_text"] = ensure_contrast_text(
            accent,
            tokens["canvas_bg"],
            tokens["surface_bg"],
            dark_surface=is_dark,
            min_ratio=4.5,
        )
    elif theme_changed:
        tokens["accent_text"] = ensure_contrast_text(
            tokens["accent"],
            tokens["canvas_bg"],
            tokens["surface_bg"],
            dark_surface=is_dark,
            min_ratio=4.5,
        )

    return tokens
