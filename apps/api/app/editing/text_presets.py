"""Canonical 11-preset industry text & caption style registry.

Zero SQL tables: presets expand deterministically into closed ``TextStyle``
primitives (and deterministic ``TextPart`` word/grapheme animations for
``karaoke_focus``). Discovery metadata in ``TEXT_STYLE_PRESET_CATALOG`` never
enters ``content_digest`` or ``video-spec``.

Mirror contract: ``packages/video-remotion/src/engine/textPresets.ts`` holds
the exact same 11 preset tokens. Core tests verify zero drift via Node.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from app.editing.schemas import FontRef, TextStyle, VersionSettings

TextStylePresetId = Literal[
    "clean_broadcast",
    "cinema_glass",
    "minimal_light",
    "vox_label",
    "vox_highlighter",
    "creator_pop",
    "kinetic_impact",
    "editorial_callout",
    "lower_third_tag",
    "karaoke_focus",
    "bilingual_cinema",
]

TextBackgroundMode = Literal["box", "pill", "line"]
TextTransform = Literal["none", "uppercase"]

KARAOKE_DEFAULT_HIGHLIGHT_COLOR = "#FACC15"
KARAOKE_ACTIVE_SCALE = 1.08


class TextBorderToken(TypedDict):
    color: str
    width: float


class TextStrokeToken(TypedDict):
    color: str
    width: float


class TextShadowToken(TypedDict):
    color: str
    offset: list[float]
    blur: float


class TextStylePresetToken(TypedDict):
    color: str
    weight: Literal[400, 500, 600, 700, 800, 900]
    background: str | None
    background_mode: TextBackgroundMode
    background_opacity: float
    background_padding: list[float]
    background_radius: float
    border: TextBorderToken | None
    stroke: TextStrokeToken | None
    shadow: TextShadowToken | None
    text_transform: TextTransform
    secondary_line_scale: float
    secondary_line_opacity: float


# Closed deterministic table (mirrors packages/video-remotion/src/engine/textPresets.ts).
TEXT_STYLE_PRESETS: dict[TextStylePresetId, TextStylePresetToken] = {
    "clean_broadcast": {
        "color": "#F8FAFC",
        "weight": 700,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [0.0, 0.0],
        "background_radius": 0.0,
        "border": None,
        "stroke": {"color": "#0A0F16", "width": 3.0},
        "shadow": {"color": "#0A0F16", "offset": [0.0, 2.0], "blur": 8.0},
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "cinema_glass": {
        "color": "#F8FAFC",
        "weight": 600,
        "background": "#0B1016",
        "background_mode": "pill",
        "background_opacity": 0.72,
        "background_padding": [26.0, 10.0],
        "background_radius": 12.0,
        "border": None,
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "minimal_light": {
        "color": "#111820",
        "weight": 700,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [0.0, 0.0],
        "background_radius": 0.0,
        "border": None,
        "stroke": {"color": "#F6F5F0", "width": 4.0},
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "vox_label": {
        "color": "#FFFDF7",
        "weight": 700,
        "background": "#141413",
        "background_mode": "line",
        "background_opacity": 1.0,
        "background_padding": [20.0, 8.0],
        "background_radius": 4.0,
        "border": None,
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "vox_highlighter": {
        "color": "#141413",
        "weight": 900,
        "background": "#FACC15",
        "background_mode": "line",
        "background_opacity": 1.0,
        "background_padding": [20.0, 8.0],
        "background_radius": 4.0,
        "border": {"color": "#141413", "width": 2.0},
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "creator_pop": {
        "color": "#FFFFFF",
        "weight": 900,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [0.0, 0.0],
        "background_radius": 0.0,
        "border": None,
        "stroke": {"color": "#0B0D12", "width": 6.0},
        "shadow": {"color": "#0B0D12", "offset": [0.0, 4.0], "blur": 0.0},
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "kinetic_impact": {
        "color": "#FFFFFF",
        "weight": 900,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [0.0, 0.0],
        "background_radius": 0.0,
        "border": None,
        "stroke": {"color": "#0D0B14", "width": 5.0},
        "shadow": {"color": "#FF2E63", "offset": [4.0, 4.0], "blur": 0.0},
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "editorial_callout": {
        "color": "#111820",
        "weight": 700,
        "background": "#FFFFFF",
        "background_mode": "pill",
        "background_opacity": 0.95,
        "background_padding": [22.0, 10.0],
        "background_radius": 10.0,
        "border": {"color": "#CBD3DA", "width": 1.5},
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "lower_third_tag": {
        "color": "#F8FAFC",
        "weight": 700,
        "background": "#0F172A",
        "background_mode": "pill",
        "background_opacity": 0.86,
        "background_padding": [22.0, 10.0],
        "background_radius": 6.0,
        "border": {"color": "#14B8A6", "width": 2.0},
        "stroke": None,
        "shadow": None,
        "text_transform": "uppercase",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "karaoke_focus": {
        "color": "#FFFFFF",
        "weight": 900,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [0.0, 0.0],
        "background_radius": 0.0,
        "border": None,
        "stroke": {"color": "#0B0D12", "width": 6.0},
        "shadow": {"color": "#0B0D12", "offset": [0.0, 4.0], "blur": 0.0},
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0,
    },
    "bilingual_cinema": {
        "color": "#FFFFFF",
        "weight": 700,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [0.0, 0.0],
        "background_radius": 0.0,
        "border": None,
        "stroke": {"color": "#0A0F16", "width": 3.5},
        "shadow": {"color": "#0A0F16", "offset": [0.0, 2.0], "blur": 10.0},
        "text_transform": "none",
        "secondary_line_scale": 0.72,
        "secondary_line_opacity": 0.86,
    },
}


# Discovery metadata projected into creative_catalog.text_style_presets (never enters content_digest).
TEXT_STYLE_PRESET_CATALOG: dict[TextStylePresetId, dict[str, Any]] = {
    "clean_broadcast": {
        "id": "clean_broadcast",
        "name": "Clean Broadcast",
        "use_for": "Default broadcast, commercial, and tech film captions on dark or varied footage",
        "visual_signature": "700 crisp white with 3px dark outer stroke and soft drop shadow, no background box",
    },
    "cinema_glass": {
        "id": "cinema_glass",
        "name": "Cinema Glass",
        "use_for": "Documentary, cinema, and busy live-action backgrounds needing subtle contrast backing",
        "visual_signature": "600 off-white inside a tight 72%-opacity translucent obsidian rounded pill",
    },
    "minimal_light": {
        "id": "minimal_light",
        "name": "Minimal Light",
        "use_for": "Bright web pages, Swiss grid layouts, and light editorial backgrounds",
        "visual_signature": "700 deep slate ink with 4px alabaster halo stroke, no background box",
    },
    "vox_label": {
        "id": "vox_label",
        "name": "Vox Label",
        "use_for": "Editorial explainers and journalism captions with tight magazine-cut strips",
        "visual_signature": "700 warm ivory on per-line tight charcoal sticker chips (line mode, 4px radius)",
    },
    "vox_highlighter": {
        "id": "vox_highlighter",
        "name": "Vox Highlighter",
        "use_for": "Key pull-quotes, thesis callouts, and bold editorial emphasis",
        "visual_signature": "900 black ink on per-line highlighter yellow chips with 2px crisp ink border",
    },
    "creator_pop": {
        "id": "creator_pop",
        "name": "Creator Pop",
        "use_for": "High-retention talking-head, short-form reels, and punchy creator captions",
        "visual_signature": "900 bold white with thick 6px dark outline and crisp hard drop shadow, no box",
    },
    "kinetic_impact": {
        "id": "kinetic_impact",
        "name": "Kinetic Impact",
        "use_for": "Trailers, anime/poster kinetic hooks, and high-energy beat accents",
        "visual_signature": "900 white with 5px dark outline and vibrant hard offset shadow, no box",
    },
    "editorial_callout": {
        "id": "editorial_callout",
        "name": "Editorial Callout",
        "use_for": "Product annotations, tutorial callout badges, and UI step labels",
        "visual_signature": "700 dark ink inside a crisp 95%-opacity white pill with 1.5px hairline border",
    },
    "lower_third_tag": {
        "id": "lower_third_tag",
        "name": "Lower Third Tag",
        "use_for": "Speaker name tags, chapter markers, and corner location stamps",
        "visual_signature": "700 uppercase light text on an 86%-opacity slate pill with 2px accent border",
    },
    "karaoke_focus": {
        "id": "karaoke_focus",
        "name": "Karaoke Focus",
        "use_for": "Active word-by-word highlighted spoken captions with subtle scale bounce",
        "visual_signature": "900 creator-pop base with deterministic per-word highlight color and 1.08x active pop",
    },
    "bilingual_cinema": {
        "id": "bilingual_cinema",
        "name": "Bilingual Cinema",
        "use_for": "Dual-language subtitles in a single Clip (primary line + '\\n' + secondary translation line)",
        "visual_signature": "700 white primary line with 0.72x / 0.86-opacity secondary line, 3.5px halo and soft shadow",
    },
}


def copy_text_preset_token(token: TextStylePresetToken) -> TextStylePresetToken:
    """Return a deep copy of a preset token dictionary."""
    return {
        "color": token["color"],
        "weight": token["weight"],
        "background": token["background"],
        "background_mode": token["background_mode"],
        "background_opacity": token["background_opacity"],
        "background_padding": list(token["background_padding"]),
        "background_radius": token["background_radius"],
        "border": dict(token["border"]) if token["border"] is not None else None,
        "stroke": dict(token["stroke"]) if token["stroke"] is not None else None,
        "shadow": (
            {
                "color": token["shadow"]["color"],
                "offset": list(token["shadow"]["offset"]),
                "blur": token["shadow"]["blur"],
            }
            if token["shadow"] is not None
            else None
        ),
        "text_transform": token["text_transform"],
        "secondary_line_scale": token["secondary_line_scale"],
        "secondary_line_opacity": token["secondary_line_opacity"],
    }


def text_style_updates_from_token(token: TextStylePresetToken) -> dict[str, Any]:
    """Convert a closed preset/caption token into TextStyle field updates."""
    from app.editing.schemas import TextBorder, TextShadow, TextStroke

    return {
        "color": token["color"],
        "weight": token["weight"],
        "background": token["background"],
        "background_mode": token["background_mode"],
        "background_opacity": token["background_opacity"],
        "background_padding": (float(token["background_padding"][0]), float(token["background_padding"][1])),
        "background_radius": float(token["background_radius"]),
        "border": (
            TextBorder(color=token["border"]["color"], width=float(token["border"]["width"]))
            if token["border"] is not None
            else None
        ),
        "stroke": (
            TextStroke(color=token["stroke"]["color"], width=float(token["stroke"]["width"]))
            if token["stroke"] is not None
            else None
        ),
        "shadow": (
            TextShadow(
                color=token["shadow"]["color"],
                offset=(float(token["shadow"]["offset"][0]), float(token["shadow"]["offset"][1])),
                blur=float(token["shadow"]["blur"]),
            )
            if token["shadow"] is not None
            else None
        ),
        "text_transform": token["text_transform"],
        "secondary_line_scale": float(token["secondary_line_scale"]),
        "secondary_line_opacity": float(token["secondary_line_opacity"]),
    }


def text_style_from_token(
    token: TextStylePresetToken,
    *,
    font_size: int,
    align: Literal["left", "center", "right"] = "center",
    line_height: float = 1.3,
    letter_spacing: float = 0.0,
    font: FontRef | None = None,
) -> TextStyle:
    """Build a complete TextStyle instance from a canonical preset or caption token."""
    from app.editing.schemas import FontRef as _FontRef, TextStyle as _TextStyle

    return _TextStyle(
        font_size=font_size,
        align=align,
        line_height=line_height,
        letter_spacing=letter_spacing,
        font=font if font is not None else _FontRef(),
        **text_style_updates_from_token(token),
    )


def default_caption_text_style(
    settings: VersionSettings,
    *,
    font_size: int | None = None,
    align: Literal["left", "center", "right"] = "center",
    line_height: float = 1.3,
) -> TextStyle:
    """Resolve the default caption TextStyle from settings.style or clean_broadcast."""
    from app.editing.styles import resolve_style_tokens

    resolved_size = font_size if font_size is not None else max(28, round(settings.width * 38 / 1920))
    if settings.style is not None:
        token = resolve_style_tokens(settings.style)["caption_style"]
    else:
        token = TEXT_STYLE_PRESETS["clean_broadcast"]
    return text_style_from_token(
        token,
        font_size=resolved_size,
        align=align,
        line_height=line_height,
    )
