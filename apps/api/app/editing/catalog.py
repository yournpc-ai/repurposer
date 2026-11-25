"""Unified two-level catalog metadata for Motion Blocks, Sound Recipes, and Voices.

Static registry (zero SQL tables). Discovery and decision metadata (name, desc,
domain, category, use_for, avoid) MUST NEVER enter content_digest or audio spec
hashes so refining model-facing copy never invalidates caches.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SOUND_ENGINE_NAME = "repurposer-sound-engine"
SOUND_MIRROR = json.loads((Path(__file__).parents[1] / "catalog" / "sound_engine_catalog.json").read_bytes())
SOUND_ENGINE_VERSION = SOUND_MIRROR["engine_version"]
SOUND_RECIPE_CATALOG = SOUND_MIRROR["recipes"]
SOUND_ACOUSTICS = SOUND_MIRROR["acoustics"]
TUNE_SCHEMA = SOUND_MIRROR["tune_schema"]
SOUND_SAMPLE_RATE = 48000
SOUND_CHANNELS = 2
DEFAULT_SOUND_SEED = 1248

SoundRecipeId = Literal[*SOUND_RECIPE_CATALOG]


def _tune_field(key: str):
    axis = TUNE_SCHEMA[key]
    return Field(default=None, ge=axis["min"], le=axis["max"], description=axis["description"])


class SoundTuneArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    pitch_st: float | None = _tune_field("pitch_st")
    tone_pct: float | None = _tune_field("tone_pct")
    length_scale: float | None = _tune_field("length_scale")
    space_pct: float | None = _tune_field("space_pct")
    punch_pct: float | None = _tune_field("punch_pct")
    variation_pct: float | None = _tune_field("variation_pct")
    volume_db: float | None = _tune_field("volume_db")


MotionBlockId = Literal[
    "kinetic_title",
    "product_showcase",
    "statement_hook",
    "metric_grid",
    "closing_cta",
    "chat_demo",
    "code_terminal", "logo_wall",
    "device_mockup",
    "flow_diagram",
    "split_compare",
    "step_timeline",
    "bento_features",
    "data_chart",
    "quote_proof",
    "kinetic_beat",
    "ui_montage",
]

# Verified against live MiniMax speech-2.6-hd `/get_voice` system catalog.
VOICE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "voice_id": "presenter_male",
        "languages": ("en", "zh", "fr", "de", "es", "it"),
        "style": "Clear neutral presenter (default multilingual male)",
    },
    {
        "voice_id": "English_Trustworthy_Man",
        "languages": ("en",),
        "style": "Authoritative, warm trustworthy US English male (institutional / tech founder)",
    },
    {
        "voice_id": "English_Graceful_Lady",
        "languages": ("en",),
        "style": "Refined British English female (academic / executive / European brand)",
    },
    {
        "voice_id": "English_Gentle-voiced_man",
        "languages": ("en",),
        "style": "Composed, resonant US English male (thoughtful explainer / advisory)",
    },
    {
        "voice_id": "Chinese (Mandarin)_Reliable_Executive",
        "languages": ("zh",),
        "style": "Composed authoritative Mandarin male executive (沉稳高管)",
    },
    {
        "voice_id": "Chinese (Mandarin)_News_Anchor",
        "languages": ("zh",),
        "style": "Crisp professional Mandarin female anchor (新闻女声)",
    },
    {
        "voice_id": "Chinese (Mandarin)_Male_Announcer",
        "languages": ("zh",),
        "style": "Resonant authoritative Mandarin male announcer (播报男声)",
    },
    {
        "voice_id": "French_FemaleAnchor",
        "languages": ("fr",),
        "style": "Mature professional French female anchor",
    },
    {
        "voice_id": "German_FriendlyMan",
        "languages": ("de",),
        "style": "Sincere poised German male presenter",
    },
    {
        "voice_id": "Spanish_RationalMan",
        "languages": ("es",),
        "style": "Measured rational Spanish male narrator",
    },
    {
        "voice_id": "Italian_Narrator",
        "languages": ("it",),
        "style": "Composed Italian male narrator",
    },
)

VERIFIED_VOICE_IDS = tuple(v["voice_id"] for v in VOICE_CATALOG)

VoiceId = Literal[
    "presenter_male",
    "English_Trustworthy_Man",
    "English_Graceful_Lady",
    "English_Gentle-voiced_man",
    "Chinese (Mandarin)_Reliable_Executive",
    "Chinese (Mandarin)_News_Anchor",
    "Chinese (Mandarin)_Male_Announcer",
    "French_FemaleAnchor",
    "German_FriendlyMan",
    "Spanish_RationalMan",
    "Italian_Narrator",
]

MOTION_BLOCK_CATALOG: dict[str, dict[str, Any]] = {
    "chat_demo": {
        "id": "chat_demo", "version": 1, "domain": "product", "category": "interfaces",
        "name": "Chat Demo",
        "desc": "2–4 alternating messages {role,text,at_s?}, optional work_steps {label,at_s?} and result_card {title,subtitle?,badge?}.",
        "use_for": ["Demonstrate an actual prompt, process and answer."],
        "avoid": ["Long transcripts and invented customer conversations."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["messages"],
        "optional_slots": ["title", "work_steps", "result_card", "preview_resource", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "kinetic_beat": {
        "id": "kinetic_beat", "version": 1, "domain": "typography", "category": "rhythm",
        "name": "Kinetic Beat",
        "desc": "impact_cut needs headline; typewriter_swap and slot_flip need 2–6 words; inline_badge_split needs left_text and right_text; marquee_wall needs 3–12 items with text.",
        "use_for": ["Beat-led launch typography and single-act polarity changes."],
        "avoid": ["Paragraphs or extended narration."],
        "supports_alpha": False, "suggested_duration_s": [0.4, 1.6],
        "required_slots": ["mode"],
        "optional_slots": ["headline", "highlight_phrase", "prefix", "words", "left_text", "right_text", "badge_text", "badge_icon", "items", "rows", "scale_emphasis", "theme", "backdrop_style", "accent_color", "show_backdrop", "entrance_duration_s"],
    },
    "ui_montage": {
        "id": "ui_montage", "version": 1, "domain": "product", "category": "interfaces",
        "name": "UI Montage",
        "desc": "Stage 1–16 ordered, pinned screenshots in rapid_cut, fan_slide or cascade_3d.",
        "use_for": ["Present several real interfaces on a strong beat."],
        "avoid": ["Unverified product imagery."],
        "supports_alpha": True, "suggested_duration_s": [0.35, 2.0],
        "required_slots": ["image_resource"],
        "optional_slots": ["headline", "badge", "layout_mode", "cut_interval_s", "theme", "backdrop_style", "accent_color", "show_backdrop", "entrance_duration_s"],
    },
    "code_terminal": {
        "id": "code_terminal", "version": 1, "domain": "product", "category": "code_terminal",
        "name": "Code Terminal", "desc": "Type CLI commands, review a diff or focus a command palette.",
        "use_for": ["Developer workflows", "Highlight a precise change"], "avoid": ["Paragraphs of code"],
        "supports_alpha": True, "suggested_duration_s": [2, 6], "required_slots": ["lines"],
        "optional_slots": ["title", "prompt_prefix", "highlight_line", "mode", "theme", "accent_color", "backdrop_style", "show_backdrop"],
    },
    "logo_wall": {
        "id": "logo_wall", "version": 1, "domain": "visuals", "category": "logos_partners",
        "name": "Logo Wall", "desc": "A rolling strip, staggered grid or spotlight of partner wordmarks.",
        "use_for": ["Integration roster", "Partner credits"], "avoid": ["Unverified endorsements"],
        "supports_alpha": True, "suggested_duration_s": [2, 5], "required_slots": ["items"],
        "optional_slots": ["eyebrow", "headline", "logo_resource", "mode", "theme", "accent_color", "backdrop_style", "show_backdrop"],
    },
    "device_mockup": {
        "id": "device_mockup", "version": 1, "domain": "product", "category": "interfaces",
        "name": "Device Mockup",
        "desc": "Order pinned images as primary then mobile. Choose dual, desktop, mobile, split_focus or hero_bleed. Split focus can show an unbranded material screen without a capture. Time the entrance with reveal_at_s.",
        "use_for": ["Show the same product across form factors."],
        "avoid": ["Uncaptured interfaces or moving footage."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["image_resource"],
        "optional_slots": ["mobile_image_resource", "eyebrow", "headline", "caption", "layout", "reveal_at_s", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "flow_diagram": {
        "id": "flow_diagram", "version": 1, "domain": "visuals", "category": "diagrams",
        "name": "Flow Diagram",
        "desc": "3–5 connected nodes {title,detail?,step_label?,badge?,reveal_at_s?}.",
        "use_for": ["Explain a mechanism, data flow or value chain."],
        "avoid": ["Unrelated feature lists."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["nodes"],
        "optional_slots": ["eyebrow", "title", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "split_compare": {
        "id": "split_compare", "version": 1, "domain": "visuals", "category": "comparisons",
        "name": "Split Compare",
        "desc": "Each heading has 2–4 items {text,reveal_at_s?}; dim_left strikes old points as their counterparts appear.",
        "use_for": ["Contrast two approaches using comparable points."],
        "avoid": ["Unrelated categories or numeric time series."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["left_heading", "left_items", "right_heading", "right_items"],
        "optional_slots": ["eyebrow", "title", "dim_left", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "step_timeline": {
        "id": "step_timeline", "version": 1, "domain": "visuals", "category": "diagrams",
        "name": "Step Timeline",
        "desc": "3–4 steps {number?,title,detail?,reveal_at_s?}; active_step selects a one-based focus.",
        "use_for": ["Explain a sequence of implementation steps."],
        "avoid": ["Independent features without an order."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["steps"],
        "optional_slots": ["eyebrow", "title", "active_step", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "bento_features": {
        "id": "bento_features", "version": 1, "domain": "visuals", "category": "features",
        "name": "Bento Features",
        "desc": "3–4 cards {tag?,title,detail,reveal_at_s?}; highlight_index selects a zero-based card.",
        "use_for": ["Introduce distinct qualitative product capabilities."],
        "avoid": ["Metrics without explanatory copy."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["cards"],
        "optional_slots": ["eyebrow", "title", "highlight_index", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "data_chart": {
        "id": "data_chart", "version": 1, "domain": "visuals", "category": "charts_and_numbers",
        "name": "Data Chart",
        "desc": "Bar or line chart with 3–8 points {label,value,display_value?,reveal_at_s?}, optional unit and zero-based highlight_index.",
        "use_for": ["Compare observed quantities or show a measured trend."],
        "avoid": ["Unsupported claims or mixed units."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["title", "chart_type", "points"],
        "optional_slots": ["eyebrow", "subtitle", "unit", "highlight_index", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "quote_proof": {
        "id": "quote_proof", "version": 1, "domain": "text", "category": "quotes",
        "name": "Quote Proof",
        "desc": "A quote and author, optional role_or_source, verification_badge and highlight_phrase timed by highlight_at_s.",
        "use_for": ["Present sourced research or an approved testimonial."],
        "avoid": ["Invented endorsements or unverified badges."],
        "supports_alpha": True, "suggested_duration_s": [4.0, 8.0],
        "required_slots": ["quote", "author"],
        "optional_slots": ["role_or_source", "verification_badge", "highlight_phrase", "highlight_at_s", "theme", "backdrop_style", "accent_color", "show_backdrop"],
    },
    "statement_hook": {
        "id": "statement_hook",
        "version": 1,
        "domain": "text",
        "category": "titles_and_phrases",
        "name": "Statement Hook",
        "desc": "Standalone editorial typography opener or act divider with masked word-by-word reveal, animated highlight sweep, and light/dark architectural studio canvas.",
        "use_for": [
            "opening hook act before showing product UI (avoids duplicating homepage hero text)",
            "mid-video thesis statement or chapter divider",
        ],
        "avoid": ["overlaying over busy webpage screenshots", "multi-sentence paragraphs"],
        "supports_alpha": True,
        "suggested_duration_s": [3.0, 6.0],
        "required_slots": ["headline"],
        "optional_slots": [
            "eyebrow",
            "highlight_at_s",
            "highlight_phrase",
            "subheadline",
            "theme",
            "layout_variant",
            "accent_color",
            "entrance_duration_s",
            "exit_duration_s",
            "backdrop_style",
            "show_backdrop",
        ],
    },
    "kinetic_title": {
        "id": "kinetic_title",
        "version": 1,
        "domain": "text",
        "category": "titles_and_phrases",
        "name": "Kinetic Title",
        "desc": "Transparent-ready headline lockup or compact pill_caption badge with masked rise and crisp typography.",
        "use_for": [
            "lightweight pill_caption context tag over a product_showcase view",
            "section title overlay over clean visual footage",
        ],
        "avoid": ["duplicating a headline already visible inside the captured webpage", "subtitles/captions"],
        "supports_alpha": True,
        "suggested_duration_s": [2.0, 8.0],
        "required_slots": ["headline"],
        "optional_slots": [
            "eyebrow",
            "subheadline",
            "align",
            "position",
            "entrance_duration_s",
            "accent_color",
            "text_color",
            "surface_style",
        ],
    },
    "product_showcase": {
        "id": "product_showcase",
        "version": 1,
        "domain": "product",
        "category": "interfaces",
        "name": "Product Showcase",
        "desc": "Precision light/dark studio frame presenting a captured web UI screenshot. camera_motion must be subtle_push|settle_tilt|drift_focus|static; camera_preset must be flat|tilt_left|tilt_right|dolly_zoom|scroll_reveal. Bind optional cursor {x,y,click_at_s} and up to 4 non-overlapping callout_steps [{start_s,end_s,label,x,y,width,height}] using normalized 0..1 coordinates (or element_id from capture).",
        "use_for": [
            "real website view reveal from capture_web",
            "zoomed UI workflow showcase with callout spotlight on a key feature region",
        ],
        "avoid": ["portrait talking-head footage", "text-only title cards"],
        "supports_alpha": True,
        "suggested_duration_s": [4.0, 10.0],
        "required_slots": ["image_resource"],
        "optional_slots": [
            "url_bar",
            "badge",
            "theme",
            "chrome_mode",
            "camera_motion",
            "entrance_duration_s",
            "zoom_scale",
            "focus_x",
            "focus_y",
            "callout",
            "callout_steps",
            "cursor",
            "camera_preset",
            "scroll_from_y",
            "scroll_to_y",
            "accent_color",
            "backdrop_style",
            "show_backdrop",
        ],
    },
    "metric_grid": {
        "id": "metric_grid",
        "version": 1,
        "domain": "visuals",
        "category": "charts_and_numbers",
        "name": "Metric Grid",
        "desc": "2-4 elevated institutional metric/capability cards with staggered spring settle, deterministic numeric count-up, top-edge specular sheen, and light/dark studio canvas. Each item supports reveal_at_s in act-local seconds and a short supporting detail. Each items[].value must include its unit or symbol (e.g. '3s', '85%', '4.2×', '$1.8M'), keeping items[].label strictly as the metric name.",
        "use_for": [
            "quantified proof points, valuation metrics, or core platform pillars",
            "mid-promo credibility section breaking up UI showcases",
        ],
        "avoid": ["single solitary sentence", "dense multi-column spreadsheets"],
        "supports_alpha": True,
        "suggested_duration_s": [5.0, 9.0],
        "required_slots": ["items"],
        "optional_slots": [
            "eyebrow",
            "title",
            "columns",
            "theme",
            "accent_color",
            "stagger_s",
            "count_up",
            "backdrop_style",
            "show_backdrop",
        ],
    },
    "closing_cta": {
        "id": "closing_cta",
        "version": 1,
        "domain": "text",
        "category": "endings_and_cta",
        "name": "Closing CTA",
        "desc": "Authoritative closing brand lockup with optional protected logo pill (light_pill/raw), expanding hairline rule, tagline, and glowing CTA/URL capsule.",
        "use_for": [
            "final 4-6s brand lockup and website CTA paired with brand stinger",
            "closing act with optional pinned logo image",
        ],
        "avoid": ["mid-video transitions", "long explanatory copy"],
        "supports_alpha": True,
        "suggested_duration_s": [4.0, 7.0],
        "required_slots": ["brand_name", "tagline"],
        "optional_slots": [
            "cta_label",
            "url_text",
            "logo_resource",
            "logo_surface",
            "theme",
            "accent_color",
            "entrance_duration_s",
            "backdrop_style",
            "show_backdrop",
        ],
    },
}


# Pure declarative Shot + Slot combinations (0 SQL tables; zero-rework base for
# future Skill/VideoTemplate slotification and passive user selection in Chat).
SHOT_SLOT_COMBINATIONS: dict[str, dict[str, Any]] = {
    "product_hero_card": {
        "id": "product_hero_card",
        "version": 1,
        "domain": "product",
        "category": "interfaces",
        "name": "Light Studio Hero + Frosted Headline Card",
        "recommended": True,
        "desc": "Option B baseline: bright alabaster studio canvas with floating browser UI and a high-contrast deep-slate frosted title card.",
        "use_for": ["light-themed SaaS or institutional web homepages", "opening product showcase with data dashboard"],
        "avoid": ["already-dark neon gaming sites"],
        "slots": {
            "required": ["image_snapshot", "headline"],
            "optional": ["url_bar", "badge", "eyebrow", "subheadline", "narration_script", "voice_id", "bgm_music_id"],
        },
        "blocks": [
            {
                "block_id": "product_showcase",
                "defaults": {"theme": "light", "camera_motion": "settle_tilt", "zoom_scale": 1.05, "focus_y": 0.35, "accent_color": "#0D9488"},
            },
            {
                "block_id": "kinetic_title",
                "defaults": {"surface_style": "glass_card", "position": "bottom_left", "align": "left", "entrance_duration_s": 0.85, "accent_color": "#14B8A6", "text_color": "#F8FAFC"},
            },
        ],
        "sfx_pair": ["whoosh", "impact"],
    },
    "dark_executive_scrim": {
        "id": "dark_executive_scrim",
        "version": 1,
        "domain": "product",
        "category": "interfaces",
        "name": "Dark Obsidian Showcase + Editorial Scrim",
        "recommended": False,
        "desc": "Moody dark architectural grid backdrop with subtle push-in and a soft bottom gradient scrim for dramatic executive reveals.",
        "use_for": ["dark-mode software UI", "core technology or architecture sections"],
        "avoid": ["pages with critical bright-bottom content"],
        "slots": {
            "required": ["image_snapshot", "headline"],
            "optional": ["url_bar", "badge", "eyebrow", "subheadline", "narration_script", "voice_id", "bgm_music_id"],
        },
        "blocks": [
            {
                "block_id": "product_showcase",
                "defaults": {"theme": "dark", "camera_motion": "drift_focus", "zoom_scale": 1.07, "focus_y": 0.35, "accent_color": "#14B8A6"},
            },
            {
                "block_id": "kinetic_title",
                "defaults": {"surface_style": "scrim", "position": "bottom_left", "align": "left", "entrance_duration_s": 0.85, "accent_color": "#14B8A6", "text_color": "#F8FAFC"},
            },
        ],
        "sfx_pair": ["riser", "impact"],
    },
    "editorial_statement_card": {
        "id": "editorial_statement_card",
        "version": 1,
        "domain": "text",
        "category": "titles_and_phrases",
        "name": "Centered Editorial Card + Studio UI Backdrop",
        "recommended": False,
        "desc": "Centered bright frosted statement card floating calmly over a gently pushing studio product frame, paired with a brand stinger.",
        "use_for": ["keynote thesis statement", "executive positioning opener", "closing brand lockup"],
        "avoid": ["shots where the center of the webpage must stay unobstructed"],
        "slots": {
            "required": ["image_snapshot", "headline"],
            "optional": ["url_bar", "badge", "eyebrow", "subheadline", "narration_script", "voice_id", "bgm_music_id"],
        },
        "blocks": [
            {
                "block_id": "product_showcase",
                "defaults": {"theme": "light", "camera_motion": "subtle_push", "zoom_scale": 1.04, "focus_y": 0.35, "accent_color": "#0D9488"},
            },
            {
                "block_id": "kinetic_title",
                "defaults": {"surface_style": "light_card", "position": "center", "align": "center", "entrance_duration_s": 0.85, "accent_color": "#0D9488", "text_color": "#0F172A"},
            },
        ],
        "sfx_pair": ["whoosh", "stinger"],
    },
}


def normalize_sound_params(recipe_id: str, overrides: dict[str, Any] | None = None) -> dict[str, int | float]:
    recipe = SOUND_RECIPE_CATALOG.get(recipe_id)
    if recipe is None:
        raise ValueError(f"Unknown sound recipe: {recipe_id}")
    specs = recipe["params"]
    overrides = overrides or {}
    unknown = set(overrides) - set(specs)
    if unknown:
        raise ValueError(f"Unknown parameters for {recipe_id}: {', '.join(sorted(unknown))}")
    normalized: dict[str, int | float] = {}
    for key in sorted(specs):
        spec = specs[key]
        raw = overrides.get(key, spec["default"])
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            raise ValueError(f"Parameter '{key}' must be a finite number.")
        clamped = max(spec["min"], min(spec["max"], float(raw)))
        step = spec["step"]
        # Match JS Math.round, including ties toward positive infinity.
        scaled = clamped / step if step >= 1 else clamped * 1000
        lower = math.floor(scaled)
        nearest = lower + int(scaled - lower >= 0.5)
        val = nearest * step if step >= 1 else nearest / 1000
        normalized[key] = int(val) if step >= 1 else float(val)
    return normalized


def normalize_sound_tune(overrides: dict[str, Any] | None = None) -> dict[str, float | int]:
    given = overrides or {}
    if set(given) - TUNE_SCHEMA.keys():
        raise ValueError("Unknown tune parameter")
    result = {}
    for key, axis in TUNE_SCHEMA.items():
        value = given.get(key, axis["default"])
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f"Invalid tune parameter {key}")
        bounded = min(axis["max"], max(axis["min"], value))
        units = bounded * 1_000_000 if key == "length_scale" else bounded / axis["step"]
        floor = math.floor(units)
        nearest = floor + int(units - floor >= 0.5)
        normalized = nearest / 1_000_000 if key == "length_scale" else nearest * axis["step"]
        result[key] = int(normalized) if normalized == int(normalized) else normalized
    return result


def build_sound_spec(
    recipe_id: str,
    params: dict[str, Any] | None = None,
    seed: int | None = None,
    tune: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recipe = SOUND_RECIPE_CATALOG.get(recipe_id)
    if recipe is None:
        raise ValueError(f"Unknown sound recipe: {recipe_id}")
    resolved_seed = DEFAULT_SOUND_SEED if seed is None else seed
    if isinstance(resolved_seed, bool) or not isinstance(resolved_seed, int) or not 0 <= resolved_seed <= 0xFFFFFFFF:
        raise ValueError("Seed must be an integer between 0 and 4294967295.")
    return {
        "channels": SOUND_CHANNELS,
        "engine": SOUND_ENGINE_NAME,
        "engine_version": SOUND_ENGINE_VERSION,
        "params": normalize_sound_params(recipe_id, params),
        "recipe_id": recipe["id"],
        "recipe_version": recipe["version"],
        "sample_rate": SOUND_SAMPLE_RATE,
        "seed": resolved_seed,
        "tune": normalize_sound_tune(tune),
    }


def sound_spec_digest(spec: dict[str, Any]) -> str:
    """Hash synthesis identity only; never includes discovery metadata."""
    canonical = json.dumps(
        {
            "channels": spec["channels"],
            "engine": spec["engine"],
            "engine_version": spec["engine_version"],
            "params": {k: spec["params"][k] for k in sorted(spec["params"])},
            "recipe_id": spec["recipe_id"],
            "recipe_version": spec["recipe_version"],
            "sample_rate": spec["sample_rate"],
            "seed": spec["seed"],
            **({"tune": spec["tune"]} if "tune" in spec else {}),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def editor_catalog_guidance() -> dict[str, Any]:
    """Bounded composition style and mixing guidance for the editor."""
    from app.editing.styles import STYLE_PRESET_CATALOG

    return {
        "style_presets": [
            {
                "id": s["id"],
                "name": s["name"],
                "desc": s["desc"],
                "visual_signature": s["visual_signature"],
                "default_transition": s["default_transition"],
                "bgm_mood": s["bgm_mood"],
                "sfx_palette": list(s["sfx_palette"]),
            }
            for s in STYLE_PRESET_CATALOG.values()
        ],
        "mixing_guidelines": {
            "bgm_under_dialogue_db": [-26, -22],
            "sfx_normalized_peak_dbfs": -2.0,
            "sfx_typical_gain_db": [-14, -10],
            "sfx_restraint": "Place SFX only on genuine visual kinetic beats (title entrances, scene cuts, card pops); omit SFX on static stretches.",
        },
        "directing_guidelines": {
            "audio_reuse_first": "Call search_voices and search_music before design_voice or generate_music so saved voiceprints and BGM tracks compound across projects.",
            "commercial_pacing_60s": "Aim for 8-10 tight voice-driven acts (4.5-7.5s each) rather than slow 10s static slides; declare 12-22 EN words or 22-38 ZH chars of spoken narration per act directly on create_video.motion_blocks with voice_id and music_id.",
            "anti_ppt_motion": "Never stack 3+ static text-card blocks consecutively without dynamic visual motion (product_showcase with zoom_scale 1.15-1.28, chat_demo, metric_grid count-up, data_chart) and alternate energetic transitions (whip_pan, zoom_through, wipe_reveal).",
        },
    }


def catalog_prompt_index() -> dict[str, Any]:
    """Full registry projection for explicit catalog consumers."""
    from app.editing.text_presets import TEXT_STYLE_PRESET_CATALOG

    return {
        **editor_catalog_guidance(),
        "text_style_presets": [
            {
                "id": t["id"],
                "name": t["name"],
                "use_for": t["use_for"],
                "visual_signature": t["visual_signature"],
            }
            for t in TEXT_STYLE_PRESET_CATALOG.values()
        ],
        "motion_blocks": [
            {
                "id": b["id"],
                "domain": b["domain"],
                "category": b["category"],
                "name": b["name"],
                "desc": b["desc"],
                "use_for": b["use_for"],
                "supports_alpha": b["supports_alpha"],
                "suggested_duration_s": b["suggested_duration_s"],
                "required_slots": b["required_slots"],
                "optional_slots": b["optional_slots"],
            }
            for b in MOTION_BLOCK_CATALOG.values()
        ],
        "sound_recipes": [
            {
                "id": r["id"],
                "domain": r["domain"],
                "category": r["category"],
                "name": r["name"],
                "desc": r["desc"],
                "sync_cue": r["sync_cue"],
                "suggested_duration_ms": r["suggested_duration_ms"],
                "params": {k: f"{v['min']}-{v['max']}{v['unit']} (def {v['default']})" for k, v in r["params"].items()},
            }
            for r in SOUND_RECIPE_CATALOG.values()
        ],
        "shot_combinations": [
            {
                "id": c["id"],
                "name": c["name"],
                "recommended": c["recommended"],
                "desc": c["desc"],
                "slots": c["slots"],
                "blocks": c["blocks"],
                "sfx_pair": c["sfx_pair"],
            }
            for c in SHOT_SLOT_COMBINATIONS.values()
        ],
        "voices": [
            {"voice_id": v["voice_id"], "languages": list(v["languages"]), "style": v["style"]}
            for v in VOICE_CATALOG
        ],
    }
