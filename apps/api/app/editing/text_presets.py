"""Closed caption and title tokens. Discovery metadata stays outside composition content."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
from typing_extensions import NotRequired, TypedDict

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
    "apple_minimal_dark",
    "apple_minimal_light",
    "chrome_cinema",
    "neon_pulse",
    "frosted_badge",
    "editorial_serif",
    "brutal_stamp",
    "terminal_mono",
    "soft_gradient_pill",
    "outline_ghost",
    "split_accent_hook",
    "news_ticker_bar",
    "subtitle_netflix_clean",
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
    typeface: NotRequired[Literal["editorial-serif", "terminal-mono"]]
    finish: NotRequired[Literal["chrome", "outline", "gradient_pill", "split_ink", "neon"]]
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
        "weight": 600,
        "background": "#FFFFFF",
        "background_mode": "pill",
        "background_opacity": 0.92,
        "background_padding": [20.0, 8.0],
        "background_radius": 10.0,
        "border": {"color": "#CBD3DA", "width": 1.0},
        "stroke": None,
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
        "background": "#111318",
        "background_mode": "pill",
        "background_opacity": 0.76,
        "background_padding": [20.0, 10.0],
        "background_radius": 10.0,
        "border": None,
        "stroke": None,
        "shadow": {"color": "#0A0F16", "offset": [0.0, 1.0], "blur": 4.0},
        "text_transform": "none",
        "secondary_line_scale": 0.74,
        "secondary_line_opacity": 0.88,
    },
    "apple_minimal_dark": {
        "color": "#F5F5F7",
        "weight": 600,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [
            0.0,
            0.0
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "apple_minimal_light": {
        "color": "#1D1D1F",
        "weight": 600,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [
            0.0,
            0.0
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "chrome_cinema": {
        "finish": "chrome",
        "color": "#DFE7F0",
        "weight": 900,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [
            0.0,
            0.0
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": {
            "color": "#69798B",
            "width": 2
        },
        "shadow": {
            "color": "#435160",
            "offset": [
                0,
                3
            ],
            "blur": 1
        },
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "neon_pulse": {
        "finish": "neon",
        "color": "#B9FFF8",
        "weight": 900,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [
            0.0,
            0.0
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": {
            "color": "#198A89",
            "width": 1
        },
        "shadow": {
            "color": "#13C9C0",
            "offset": [
                0,
                0
            ],
            "blur": 16
        },
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "frosted_badge": {
        "color": "#18232E",
        "weight": 700,
        "background": "#E5EEF2",
        "background_mode": "pill",
        "background_opacity": 0.86,
        "background_padding": [
            22.0,
            10.0
        ],
        "background_radius": 10.0,
        "border": {
            "color": "#F5FBFF",
            "width": 1
        },
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "editorial_serif": {
        "typeface": "editorial-serif",
        "color": "#302923",
        "weight": 400,
        "background": "#FAF6ED",
        "background_mode": "line",
        "background_opacity": 1.0,
        "background_padding": [
            14,
            6
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "brutal_stamp": {
        "color": "#141413",
        "weight": 900,
        "background": "#FF623D",
        "background_mode": "line",
        "background_opacity": 1.0,
        "background_padding": [
            20.0,
            8.0
        ],
        "background_radius": 0,
        "border": {
            "color": "#141413",
            "width": 2.0
        },
        "stroke": None,
        "shadow": {
            "color": "#141413",
            "offset": [
                5,
                5
            ],
            "blur": 0
        },
        "text_transform": "uppercase",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "terminal_mono": {
        "typeface": "terminal-mono",
        "color": "#A9EBC3",
        "weight": 500,
        "background": "#101B18",
        "background_mode": "line",
        "background_opacity": 1.0,
        "background_padding": [
            20.0,
            8.0
        ],
        "background_radius": 2,
        "border": None,
        "stroke": None,
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "soft_gradient_pill": {
        "finish": "gradient_pill",
        "color": "#30253C",
        "weight": 600,
        "background": "#EBDAF5",
        "background_mode": "pill",
        "background_opacity": 0.95,
        "background_padding": [
            26.0,
            10.0
        ],
        "background_radius": 32,
        "border": None,
        "stroke": None,
        "shadow": {
            "color": "#C6AFDF",
            "offset": [
                2,
                3
            ],
            "blur": 10
        },
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "outline_ghost": {
        "finish": "outline",
        "color": "#E9EDF2",
        "weight": 500,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [
            0.0,
            0.0
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": {
            "color": "#62768C",
            "width": 2
        },
        "shadow": None,
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "split_accent_hook": {
        "finish": "split_ink",
        "color": "#FFF2DC",
        "weight": 900,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [
            0.0,
            0.0
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": None,
        "shadow": {
            "color": "#ED694E",
            "offset": [
                5,
                1
            ],
            "blur": 0
        },
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "news_ticker_bar": {
        "color": "#FFFDF7",
        "weight": 700,
        "background": "#922B34",
        "background_mode": "line",
        "background_opacity": 1.0,
        "background_padding": [
            20.0,
            8.0
        ],
        "background_radius": 0,
        "border": None,
        "stroke": None,
        "shadow": None,
        "text_transform": "uppercase",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
    "subtitle_netflix_clean": {
        "color": "#FFFFFF",
        "weight": 600,
        "background": None,
        "background_mode": "box",
        "background_opacity": 1.0,
        "background_padding": [
            0.0,
            0.0
        ],
        "background_radius": 0.0,
        "border": None,
        "stroke": {
            "color": "#151515",
            "width": 1.5
        },
        "shadow": {
            "color": "#101010",
            "offset": [
                0,
                2
            ],
            "blur": 3
        },
        "text_transform": "none",
        "secondary_line_scale": 1.0,
        "secondary_line_opacity": 1.0
    },
}


# Discovery metadata projected into creative_catalog.text_style_presets (never enters content_digest).
TEXT_STYLE_PRESET_CATALOG: dict[TextStylePresetId, dict[str, Any]] = {
    "clean_broadcast": {
        "id": "clean_broadcast",
        "name_zh": "广播净字幕", "category": "captions_clean", "moods": ["crisp"],
        "energy": "subtle", "avoid": ["Poster-scale headlines"],
        "name": "Clean Broadcast",
        "use_for": ["Default broadcast, commercial, and tech film captions on dark or varied footage"],
        "visual_signature": "700 crisp white with 3px dark outer stroke and soft drop shadow, no background box",
    },
    "cinema_glass": {
        "id": "cinema_glass",
        "name_zh": "影院玻璃", "category": "captions_clean", "moods": ["cinematic"],
        "energy": "subtle", "avoid": ["Poster-scale headlines"],
        "name": "Cinema Glass",
        "use_for": ["Documentary, cinema, and busy live-action backgrounds needing subtle contrast backing"],
        "visual_signature": "600 off-white inside a tight 72%-opacity translucent obsidian rounded pill",
    },
    "minimal_light": {
        "id": "minimal_light",
        "name_zh": "极简浅色", "category": "captions_clean", "moods": ["minimal"],
        "energy": "subtle", "avoid": ["Poster-scale headlines"],
        "name": "Minimal Light",
        "use_for": ["Bright web pages, Swiss grid layouts, and light editorial backgrounds"],
        "visual_signature": "700 deep slate ink with 4px alabaster halo stroke, no background box",
    },
    "vox_label": {
        "id": "vox_label",
        "name_zh": "杂志标签", "category": "editorial_callout", "moods": ["editorial"],
        "energy": "subtle", "avoid": ["Dense dialogue"],
        "name": "Vox Label",
        "use_for": ["Editorial explainers and journalism captions with tight magazine-cut strips"],
        "visual_signature": "700 warm ivory on per-line tight charcoal sticker chips (line mode, 4px radius)",
    },
    "vox_highlighter": {
        "id": "vox_highlighter",
        "name_zh": "荧光标注", "category": "editorial_callout", "moods": ["bold"],
        "energy": "subtle", "avoid": ["Dense dialogue"],
        "name": "Vox Highlighter",
        "use_for": ["Key pull-quotes, thesis callouts, and bold editorial emphasis"],
        "visual_signature": "900 black ink on per-line highlighter yellow chips with 2px crisp ink border",
    },
    "creator_pop": {
        "id": "creator_pop",
        "name_zh": "创作者弹字", "category": "kinetic_headline", "moods": ["playful"],
        "energy": "high", "avoid": ["Dense dialogue"],
        "name": "Creator Pop",
        "use_for": ["High-retention talking-head, short-form reels, and punchy creator captions"],
        "visual_signature": "900 bold white with thick 6px dark outline and crisp hard drop shadow, no box",
    },
    "kinetic_impact": {
        "id": "kinetic_impact",
        "name_zh": "动感冲击", "category": "kinetic_headline", "moods": ["kinetic"],
        "energy": "high", "avoid": ["Dense dialogue"],
        "name": "Kinetic Impact",
        "use_for": ["Trailers, anime/poster kinetic hooks, and high-energy beat accents"],
        "visual_signature": "900 white with 5px dark outline and vibrant hard offset shadow, no box",
    },
    "editorial_callout": {
        "id": "editorial_callout",
        "name_zh": "编辑批注", "category": "editorial_callout", "moods": ["precise"],
        "energy": "subtle", "avoid": ["Dense dialogue"],
        "name": "Editorial Callout",
        "use_for": ["Product annotations, tutorial callout badges, and UI step labels"],
        "visual_signature": "700 dark ink inside a crisp 95%-opacity white pill with 1.5px hairline border",
    },
    "lower_third_tag": {
        "id": "lower_third_tag",
        "name_zh": "下三分之一题签", "category": "editorial_callout", "moods": ["formal"],
        "energy": "subtle", "avoid": ["Dense dialogue"],
        "name": "Lower Third Tag",
        "use_for": ["Speaker name tags, chapter markers, and corner location stamps"],
        "visual_signature": "700 uppercase light text on an 86%-opacity slate pill with 2px accent border",
    },
    "karaoke_focus": {
        "id": "karaoke_focus",
        "name_zh": "逐词聚焦", "category": "captions_karaoke", "moods": ["rhythmic"],
        "energy": "subtle", "avoid": ["Poster-scale headlines"],
        "name": "Karaoke Focus",
        "use_for": ["Active word-by-word highlighted spoken captions with subtle scale bounce"],
        "visual_signature": "900 creator-pop base with deterministic per-word highlight color and 1.08x active pop",
    },
    "bilingual_cinema": {
        "id": "bilingual_cinema",
        "name_zh": "双语影院", "category": "captions_bilingual", "moods": ["calm"],
        "energy": "subtle", "avoid": ["Poster-scale headlines"],
        "name": "Bilingual Cinema",
        "use_for": ["Dual-language subtitles in a single Clip (primary line + '\\n' + secondary translation line)"],
        "visual_signature": "700 white primary with 0.74x / 0.88-opacity secondary line inside a tight 76%-opacity dark-ink pill (20x10 padding, 10px radius, zero full-width bar)",
    },
    "apple_minimal_dark": {'id': 'apple_minimal_dark',
         'name': 'Apple Minimal Dark',
         'name_zh': '极简夜幕',
         'category': 'kinetic_headline',
         'moods': ['quiet'],
         'energy': 'subtle',
         'use_for': ['Product launch on black'],
         'avoid': ['Bright moving footage'],
         'visual_signature': 'Soft silver type on a dark stage'},
    "apple_minimal_light": {'id': 'apple_minimal_light',
         'name': 'Apple Minimal Light',
         'name_zh': '极简日光',
         'category': 'kinetic_headline',
         'moods': ['airy'],
         'energy': 'subtle',
         'use_for': ['Light studio opener'],
         'avoid': ['Dark textured scenes'],
         'visual_signature': 'Deep graphite with an unadorned silhouette'},
    "chrome_cinema": {'id': 'chrome_cinema',
         'name': 'Chrome Cinema',
         'name_zh': '银幕铬光',
         'category': 'fx_display',
         'moods': ['metallic'],
         'energy': 'high',
         'use_for': ['Hardware reveal'],
         'avoid': ['Long body copy'],
         'visual_signature': 'Cold silver edge with a graphite bevel'},
    "neon_pulse": {'id': 'neon_pulse',
         'name': 'Neon Pulse',
         'name_zh': '霓虹辉光',
         'category': 'fx_display',
         'moods': ['electric'],
         'energy': 'high',
         'use_for': ['Nightlife title'],
         'avoid': ['Daylight documentary'],
         'visual_signature': 'Ice cyan surrounded by a luminous teal halo'},
    "frosted_badge": {'id': 'frosted_badge',
         'name': 'Frosted Badge',
         'name_zh': '雾面徽标',
         'category': 'editorial_callout',
         'moods': ['soft'],
         'energy': 'subtle',
         'use_for': ['Product annotation'],
         'avoid': ['Low contrast skies'],
         'visual_signature': 'Frosted silver badge with a narrow rim'},
    "editorial_serif": {'id': 'editorial_serif',
         'name': 'Editorial Serif',
         'name_zh': '杂志题签',
         'category': 'editorial_callout',
         'moods': ['literary'],
         'energy': 'subtle',
         'use_for': ['Editorial pull quote'],
         'avoid': ['Sports scoreboards'],
         'visual_signature': 'Book-weight warm ink on ivory paper'},
    "brutal_stamp": {'id': 'brutal_stamp',
         'name': 'Brutal Stamp',
         'name_zh': '硬边印章',
         'category': 'kinetic_headline',
         'moods': ['defiant'],
         'energy': 'explosive',
         'use_for': ['Poster hook'],
         'avoid': ['Dialogue captions'],
         'visual_signature': 'Uppercase ink stamp on vermilion'},
    "terminal_mono": {'id': 'terminal_mono',
         'name': 'Terminal Mono',
         'name_zh': '终端字符',
         'category': 'editorial_callout',
         'moods': ['technical'],
         'energy': 'medium',
         'use_for': ['Console annotation'],
         'avoid': ['Romantic titles'],
         'visual_signature': 'Phosphor green terminal strip'},
    "soft_gradient_pill": {'id': 'soft_gradient_pill',
         'name': 'Soft Gradient Pill',
         'name_zh': '柔彩胶囊',
         'category': 'editorial_callout',
         'moods': ['gentle'],
         'energy': 'subtle',
         'use_for': ['Lifestyle label'],
         'avoid': ['Hard news'],
         'visual_signature': 'Lavender pill with a lilac feathered edge'},
    "outline_ghost": {'id': 'outline_ghost',
         'name': 'Outline Ghost',
         'name_zh': '空灵描边',
         'category': 'fx_display',
         'moods': ['ethereal'],
         'energy': 'medium',
         'use_for': ['Short silhouette title'],
         'avoid': ['Fine print'],
         'visual_signature': 'Pale lettering edged in slate'},
    "split_accent_hook": {'id': 'split_accent_hook',
         'name': 'Split Accent Hook',
         'name_zh': '错色标题',
         'category': 'kinetic_headline',
         'moods': ['punchy'],
         'energy': 'high',
         'use_for': ['Beat-aligned hook'],
         'avoid': ['Long interviews'],
         'visual_signature': 'Warm white with offset coral registration'},
    "news_ticker_bar": {'id': 'news_ticker_bar',
         'name': 'News Ticker Bar',
         'name_zh': '新闻滚条',
         'category': 'captions_clean',
         'moods': ['urgent'],
         'energy': 'medium',
         'use_for': ['News lower third'],
         'avoid': ['Quiet portrait'],
         'visual_signature': 'White uppercase type on a deep red band'},
    "subtitle_netflix_clean": {'id': 'subtitle_netflix_clean',
         'name': 'Subtitle Netflix Clean',
         'name_zh': '影院净字幕',
         'category': 'captions_clean',
         'moods': ['cinematic'],
         'energy': 'subtle',
         'use_for': ['Dialogue over mixed footage'],
         'avoid': ['Large hero titles'],
         'visual_signature': 'White subtitle with narrow charcoal edge'},
}


def copy_text_preset_token(token: TextStylePresetToken) -> TextStylePresetToken:
    """Return a deep copy of a preset token dictionary."""
    return {
        **token,
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


def resolve_text_preset_token(
    preset_id: TextStylePresetId,
    style_tokens: dict[str, Any] | None = None,
) -> TextStylePresetToken:
    """Expand a static text preset with optional CompositionStyle theme/accent awareness."""
    token = copy_text_preset_token(TEXT_STYLE_PRESETS[preset_id])
    if style_tokens is None:
        return token
    if preset_id == "lower_third_tag" and token["border"] is not None:
        token["border"]["color"] = style_tokens["accent"]
    elif preset_id == "bilingual_cinema" and style_tokens.get("theme") == "light":
        token["color"] = "#F8FAFC"
        token["background"] = "#111318"
        token["background_mode"] = "pill"
        token["background_opacity"] = 0.82
        token["background_padding"] = [20.0, 10.0]
        token["background_radius"] = 10.0
        token["stroke"] = None
        token["shadow"] = None
    return token


def text_style_updates_from_token(token: TextStylePresetToken) -> dict[str, Any]:
    """Convert a closed preset/caption token into TextStyle field updates."""
    from app.editing.fonts import DISPLAY_DIGESTS
    from app.editing.schemas import FontRef, TextBorder, TextShadow, TextStroke

    face = token.get("typeface")
    return {
        "font": FontRef(font_id=face, digest=DISPLAY_DIGESTS[face]) if face else FontRef(),
        "finish": token.get("finish"),
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
    from app.editing.schemas import TextStyle as _TextStyle

    updates = text_style_updates_from_token(token)
    if font is not None:
        updates["font"] = font

    return _TextStyle(
        font_size=font_size,
        align=align,
        line_height=line_height,
        letter_spacing=letter_spacing,
        **updates,
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
