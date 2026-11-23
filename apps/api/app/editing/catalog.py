"""Unified two-level catalog metadata for Motion Blocks, Sound Recipes, and Voices.

Static registry (zero SQL tables). Discovery and decision metadata (name, desc,
domain, category, use_for, avoid) MUST NEVER enter content_digest or audio spec
hashes so refining model-facing copy never invalidates caches.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

SOUND_ENGINE_NAME = "repurposer-sound-engine"
SOUND_ENGINE_VERSION = 1
SOUND_SAMPLE_RATE = 48000
SOUND_CHANNELS = 2
DEFAULT_SOUND_SEED = 1248

SoundRecipeId = Literal["whoosh", "impact", "click", "riser", "stinger", "swoosh_cut"]
MotionBlockId = Literal[
    "kinetic_title",
    "product_showcase",
    "statement_hook",
    "metric_grid",
    "closing_cta",
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

# Mirrors packages/sound-engine/src/recipes.ts exactly for synthesis bounds.
SOUND_RECIPE_CATALOG: dict[str, dict[str, Any]] = {
    "whoosh": {
        "id": "whoosh",
        "version": 1,
        "domain": "video",
        "category": "motion",
        "name": "Air Whoosh",
        "desc": "Clean directional air sweep swelling across stereo and dissipating softly.",
        "use_for": ["kinetic title entrance", "product card slide-in", "scene motion cue"],
        "avoid": ["static text hold", "realistic outdoor wind"],
        "suggested_duration_ms": [320, 700],
        "sync_cue": "energy_peak",
        "mix_hint": "Align peak_offset_ms with fastest visual velocity; lower tone over speech.",
        "params": {
            "length": {"unit": "ms", "default": 540, "min": 180, "max": 1100, "step": 1},
            "pitch": {"unit": "Hz", "default": 410, "min": 180, "max": 760, "step": 1},
            "tone": {"unit": "%", "default": 54, "min": 10, "max": 90, "step": 1},
            "punch": {"unit": "%", "default": 46, "min": 15, "max": 90, "step": 1},
            "space": {"unit": "%", "default": 64, "min": 0, "max": 100, "step": 1},
        },
    },
    "impact": {
        "id": "impact",
        "version": 1,
        "domain": "video",
        "category": "impact",
        "name": "Soft Impact",
        "desc": "Restrained tactile settle with warm low-end body and clean studio reflections.",
        "use_for": ["title lock-in", "product card landing", "headline emphasis"],
        "avoid": ["rapid UI clicks", "cinematic explosion"],
        "suggested_duration_ms": [220, 560],
        "sync_cue": "onset",
        "mix_hint": "Align start (onset) with visual settle frame; lower pitch for deeper weight.",
        "params": {
            "pitch": {"unit": "Hz", "default": 112, "min": 48, "max": 185, "step": 1},
            "punch": {"unit": "%", "default": 48, "min": 5, "max": 95, "step": 1},
            "tone": {"unit": "%", "default": 44, "min": 10, "max": 90, "step": 1},
            "length": {"unit": "ms", "default": 380, "min": 140, "max": 820, "step": 1},
            "space": {"unit": "%", "default": 26, "min": 0, "max": 85, "step": 1},
        },
    },
    "click": {
        "id": "click",
        "version": 1,
        "domain": "interface",
        "category": "tap",
        "name": "Tactile Click",
        "desc": "Crisp micro interface tap with subtle cavity resonance.",
        "use_for": ["button tap", "cursor selection", "metric highlight"],
        "avoid": ["scene transitions", "dramatic landings"],
        "suggested_duration_ms": [45, 95],
        "sync_cue": "onset",
        "mix_hint": "Keep gain restrained (-12 to -8 dB) under speech.",
        "params": {
            "pitch": {"unit": "Hz", "default": 840, "min": 380, "max": 1500, "step": 1},
            "punch": {"unit": "%", "default": 54, "min": 5, "max": 95, "step": 1},
            "tone": {"unit": "%", "default": 50, "min": 10, "max": 90, "step": 1},
            "length": {"unit": "ms", "default": 65, "min": 32, "max": 130, "step": 1},
            "space": {"unit": "%", "default": 10, "min": 0, "max": 60, "step": 1},
        },
    },
    "riser": {
        "id": "riser",
        "version": 1,
        "domain": "video",
        "category": "riser",
        "name": "Tension Riser",
        "desc": "Smooth upward shimmer and harmonic swell building cleanly into a reveal cut.",
        "use_for": ["pre-reveal build", "interface zoom anticipation", "transition lead-in"],
        "avoid": ["after reveal", "background bed"],
        "suggested_duration_ms": [600, 1600],
        "sync_cue": "end_peak",
        "mix_hint": "End clip right at reveal frame so peak hands off into impact or cut.",
        "params": {
            "length": {"unit": "ms", "default": 1050, "min": 400, "max": 2400, "step": 1},
            "pitch": {"unit": "Hz", "default": 260, "min": 140, "max": 540, "step": 1},
            "tone": {"unit": "%", "default": 58, "min": 15, "max": 90, "step": 1},
            "punch": {"unit": "%", "default": 55, "min": 15, "max": 90, "step": 1},
            "space": {"unit": "%", "default": 42, "min": 0, "max": 90, "step": 1},
        },
    },
    "stinger": {
        "id": "stinger",
        "version": 1,
        "domain": "video",
        "category": "stinger",
        "name": "Brand Stinger",
        "desc": "Restrained institutional harmonic chime for logo or headline lockups.",
        "use_for": ["brand mark reveal", "opening statement accent", "closing lockup"],
        "avoid": ["dense narration syllables", "frequent UI actions"],
        "suggested_duration_ms": [480, 1200],
        "sync_cue": "onset",
        "mix_hint": "Place on open beat or title lockup; keep modest gain over harmonic BGM.",
        "params": {
            "pitch": {"unit": "Hz", "default": 330, "min": 196, "max": 587, "step": 1},
            "tone": {"unit": "%", "default": 54, "min": 15, "max": 90, "step": 1},
            "length": {"unit": "ms", "default": 760, "min": 350, "max": 1500, "step": 1},
            "punch": {"unit": "%", "default": 46, "min": 10, "max": 90, "step": 1},
            "space": {"unit": "%", "default": 48, "min": 10, "max": 90, "step": 1},
        },
    },
    "swoosh_cut": {
        "id": "swoosh_cut",
        "version": 1,
        "domain": "video",
        "category": "transition",
        "name": "Swoosh Cut",
        "desc": "Compact symmetrical bidirectional air-and-body sweep designed specifically for crossfade scene cuts.",
        "use_for": ["scene crossfade cut", "act-to-act handoff", "product view switch"],
        "avoid": ["static holds", "consecutive cuts less than 2s apart"],
        "suggested_duration_ms": [240, 420],
        "sync_cue": "energy_peak",
        "mix_hint": "Center peak_offset_ms right on the crossfade cut frame; keep gain -14 to -11 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 320, "min": 200, "max": 520, "step": 1},
            "pitch": {"unit": "Hz", "default": 520, "min": 260, "max": 920, "step": 1},
            "tone": {"unit": "%", "default": 48, "min": 12, "max": 88, "step": 1},
            "punch": {"unit": "%", "default": 56, "min": 15, "max": 92, "step": 1},
            "space": {"unit": "%", "default": 52, "min": 0, "max": 90, "step": 1},
        },
    },
}

MOTION_BLOCK_CATALOG: dict[str, dict[str, Any]] = {
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
            "highlight_phrase",
            "subheadline",
            "theme",
            "layout_variant",
            "accent_color",
            "entrance_duration_s",
            "exit_duration_s",
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
        "desc": "Precision light/dark studio frame presenting a captured web UI screenshot with damped 3D settle, push-in camera motion, optional frameless mode, and normalized callout spotlight.",
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
            "accent_color",
            "show_backdrop",
        ],
    },
    "metric_grid": {
        "id": "metric_grid",
        "version": 1,
        "domain": "visuals",
        "category": "charts_and_numbers",
        "name": "Metric Grid",
        "desc": "2-4 elevated institutional metric/capability cards with staggered spring settle, deterministic numeric count-up, top-edge specular sheen, and light/dark studio canvas.",
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
        val = round(clamped / step) * step if step >= 1 else round(clamped, 3)
        normalized[key] = int(val) if step >= 1 else float(val)
    return normalized


def build_sound_spec(
    recipe_id: str,
    params: dict[str, Any] | None = None,
    seed: int | None = None,
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
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def catalog_prompt_index() -> dict[str, Any]:
    """Compact two-level index projected into editor context for fast LLM selection."""
    return {
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
        "mixing_guidelines": {
            "bgm_under_dialogue_db": [-26, -24],
            "sfx_normalized_peak_dbfs": -2.0,
            "sfx_typical_gain_db": [-14, -10],
            "sfx_restraint": "Place SFX only on genuine visual kinetic beats (title entrances, scene cuts, card pops); omit SFX on static stretches.",
        },
    }
