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
SOUND_ENGINE_VERSION = 2
SOUND_SAMPLE_RATE = 48000
SOUND_CHANNELS = 2
DEFAULT_SOUND_SEED = 1248

SoundRecipeId = Literal[
    "whoosh", "impact", "click", "riser",
    "stinger", "swoosh_cut", "sub_swell", "shimmer_lift",
    "deep_hit", "sub_drop", "kinetic_thud", "velvet_pass",
    "page_turn", "title_bloom", "metric_chime", "callout_ping",
    "studio_air", "pulse_bed", "soft_pop", "toggle_on",
    "select_tick", "confirm_chime",
]
MotionBlockId = Literal[
    "kinetic_title",
    "product_showcase",
    "statement_hook",
    "metric_grid",
    "closing_cta",
    "chat_demo",
    "device_mockup",
    "flow_diagram",
    "split_compare",
    "step_timeline",
    "bento_features",
    "data_chart",
    "quote_proof",
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
        "version": 2,
        "domain": "video",
        "category": "motion",
        "name": "Air Whoosh",
        "desc": "Clean directional air sweep that swells across the stereo field and dissipates softly.",
        "use_for": ["kinetic title entrance", "product card slide-in", "scene motion cue"],
        "avoid": ["static text hold", "realistic outdoor wind"],
        "suggested_duration_ms": [320, 700],
        "sync_cue": "energy_peak",
        "mix_hint": "Align peak_offset_ms with fastest visual velocity; lower tone over sibilant narration.",
        "params": {
            "length": {"unit": "ms", "default": 540, "min": 180, "max": 1100, "step": 1, "description": "Total air sweep duration."},
            "pitch": {"unit": "Hz", "default": 410, "min": 180, "max": 760, "step": 1, "description": "Center resonance of body airflow and subtle tonal glide."},
            "tone": {"unit": "%", "default": 54, "min": 10, "max": 90, "step": 1, "description": "High-frequency air sheen; lower to sit cleanly under speech."},
            "punch": {"unit": "%", "default": 46, "min": 15, "max": 90, "step": 1, "description": "Tightness of the central swell crest."},
            "space": {"unit": "%", "default": 64, "min": 0, "max": 100, "step": 1, "description": "Stereo travel width and subtle spatial spread."},
        },
    },
    "impact": {
        "id": "impact",
        "version": 2,
        "domain": "video",
        "category": "impact",
        "name": "Soft Impact",
        "desc": "Restrained tactile settle with warm low-end body and clean studio reflections.",
        "use_for": ["title lock-in", "product card landing", "headline emphasis"],
        "avoid": ["rapid UI clicks", "cinematic explosion"],
        "suggested_duration_ms": [220, 560],
        "sync_cue": "onset",
        "mix_hint": "Align clip start (onset) with visual settle frame; lower pitch for deeper weight.",
        "params": {
            "pitch": {"unit": "Hz", "default": 112, "min": 48, "max": 185, "step": 1, "description": "Fundamental body resonance; lower values sound deeper and heavier."},
            "punch": {"unit": "%", "default": 48, "min": 5, "max": 95, "step": 1, "description": "Initial transient attack sharpness and upper harmonic click."},
            "tone": {"unit": "%", "default": 44, "min": 10, "max": 90, "step": 1, "description": "Brightness of the overtone and filtered thump."},
            "length": {"unit": "ms", "default": 380, "min": 140, "max": 820, "step": 1, "description": "Low-end decay tail length."},
            "space": {"unit": "%", "default": 26, "min": 0, "max": 85, "step": 1, "description": "Stereo early-reflection ambience."},
        },
    },
    "click": {
        "id": "click",
        "version": 2,
        "domain": "interface",
        "category": "tap",
        "name": "Tactile Click",
        "desc": "Crisp micro interface tap with subtle cavity resonance and zero harshness.",
        "use_for": ["button tap", "cursor selection", "metric highlight"],
        "avoid": ["scene transitions", "dramatic landings"],
        "suggested_duration_ms": [45, 95],
        "sync_cue": "onset",
        "mix_hint": "Keep gain restrained (-12 to -8 dB) so rapid interactions never distract from speech.",
        "params": {
            "pitch": {"unit": "Hz", "default": 840, "min": 380, "max": 1500, "step": 1, "description": "Primary cavity resonance pitch."},
            "punch": {"unit": "%", "default": 54, "min": 5, "max": 95, "step": 1, "description": "Attack crispness and short harmonic snap."},
            "tone": {"unit": "%", "default": 50, "min": 10, "max": 90, "step": 1, "description": "Upper overtone brightness."},
            "length": {"unit": "ms", "default": 65, "min": 32, "max": 130, "step": 1, "description": "Decay window of the tap."},
            "space": {"unit": "%", "default": 10, "min": 0, "max": 60, "step": 1, "description": "Subtle room reflection amount."},
        },
    },
    "riser": {
        "id": "riser",
        "version": 2,
        "domain": "video",
        "category": "riser",
        "name": "Tension Riser",
        "desc": "Smooth upward shimmer and harmonic swell building cleanly into a reveal cut.",
        "use_for": ["pre-reveal build", "interface zoom anticipation", "transition lead-in"],
        "avoid": ["after reveal", "background bed"],
        "suggested_duration_ms": [600, 1600],
        "sync_cue": "end_peak",
        "mix_hint": "End clip right at the reveal frame so peak_offset_ms hands off into the impact or cut.",
        "params": {
            "length": {"unit": "ms", "default": 1050, "min": 400, "max": 2400, "step": 1, "description": "Build duration leading into the reveal."},
            "pitch": {"unit": "Hz", "default": 260, "min": 140, "max": 540, "step": 1, "description": "Starting harmonic center of the upward sweep."},
            "tone": {"unit": "%", "default": 58, "min": 15, "max": 90, "step": 1, "description": "Upper shimmer brightness at the climax."},
            "punch": {"unit": "%", "default": 55, "min": 15, "max": 90, "step": 1, "description": "Steepness of the crescendo curve."},
            "space": {"unit": "%", "default": 42, "min": 0, "max": 90, "step": 1, "description": "Stereo widening and reflection tail."},
        },
    },
    "stinger": {
        "id": "stinger",
        "version": 2,
        "domain": "video",
        "category": "stinger",
        "name": "Brand Stinger",
        "desc": "Restrained institutional harmonic chime with crystalline overtones for logo or title lockups.",
        "use_for": ["brand mark reveal", "opening statement accent", "closing lockup"],
        "avoid": ["dense narration syllables", "frequent UI actions"],
        "suggested_duration_ms": [480, 1200],
        "sync_cue": "onset",
        "mix_hint": "Place on open beat or title lockup; keep gain modest if BGM already has strong harmony.",
        "params": {
            "pitch": {"unit": "Hz", "default": 330, "min": 196, "max": 587, "step": 1, "description": "Root note frequency (330 Hz ≈ E4, 262 Hz ≈ C4)."},
            "tone": {"unit": "%", "default": 54, "min": 15, "max": 90, "step": 1, "description": "Upper harmonic sheen and bell shimmer."},
            "length": {"unit": "ms", "default": 760, "min": 350, "max": 1500, "step": 1, "description": "Resonant sustain tail."},
            "punch": {"unit": "%", "default": 46, "min": 10, "max": 90, "step": 1, "description": "Attack clarity on the initial chime."},
            "space": {"unit": "%", "default": 48, "min": 10, "max": 90, "step": 1, "description": "Stereo spread and early reflections."},
        },
    },
    "swoosh_cut": {
        "id": "swoosh_cut",
        "version": 2,
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
            "length": {"unit": "ms", "default": 320, "min": 200, "max": 520, "step": 1, "description": "Total symmetrical cut-sweep duration."},
            "pitch": {"unit": "Hz", "default": 520, "min": 260, "max": 920, "step": 1, "description": "Center filter resonance of the cut body."},
            "tone": {"unit": "%", "default": 48, "min": 12, "max": 88, "step": 1, "description": "Upper air sheen; reduce under sibilant speech."},
            "punch": {"unit": "%", "default": 56, "min": 15, "max": 92, "step": 1, "description": "Tightness of the center crossing crest."},
            "space": {"unit": "%", "default": 52, "min": 0, "max": 90, "step": 1, "description": "Stereo cross-panning width and subtle room tail."},
        },
    },
    "sub_swell": {
        "id": "sub_swell",
        "version": 2,
        "domain": "video",
        "category": "riser",
        "name": "Sub Swell",
        "desc": "Low bowed octave rising gently into an opening frame.",
        "use_for": ["opening title reveal"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [420, 2000],
        "sync_cue": "end_peak",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 920, "min": 420, "max": 2000, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 68, "min": 45, "max": 110, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 29, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "shimmer_lift": {
        "id": "shimmer_lift",
        "version": 2,
        "domain": "video",
        "category": "riser",
        "name": "Shimmer Lift",
        "desc": "A climbing fifth with a fine, diffuse high register.",
        "use_for": ["reveal anticipation"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [510, 1900],
        "sync_cue": "end_peak",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 1150, "min": 510, "max": 1900, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 480, "min": 290, "max": 720, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 64, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "deep_hit": {
        "id": "deep_hit",
        "version": 2,
        "domain": "video",
        "category": "impact",
        "name": "Deep Hit",
        "desc": "A felted bass strike with a brief grain of contact.",
        "use_for": ["anchor a chapter heading"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [240, 960],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 530, "min": 240, "max": 960, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 67, "min": 48, "max": 105, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 38, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "sub_drop": {
        "id": "sub_drop",
        "version": 2,
        "domain": "video",
        "category": "drop",
        "name": "Sub Drop",
        "desc": "A falling low register leaves space after a change of argument.",
        "use_for": ["pain-point pivot"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [300, 1250],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 660, "min": 300, "max": 1250, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 105, "min": 74, "max": 165, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 22, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "kinetic_thud": {
        "id": "kinetic_thud",
        "version": 2,
        "domain": "video",
        "category": "impact",
        "name": "Kinetic Thud",
        "desc": "Two close contacts suggest a panel seating in its frame.",
        "use_for": ["product panel landing"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [140, 520],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 270, "min": 140, "max": 520, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 147, "min": 85, "max": 220, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 23, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "velvet_pass": {
        "id": "velvet_pass",
        "version": 2,
        "domain": "video",
        "category": "transition",
        "name": "Velvet Pass",
        "desc": "A dark fabric-like sweep crosses the frame.",
        "use_for": ["soft lateral crossfade"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [240, 920],
        "sync_cue": "energy_peak",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 510, "min": 240, "max": 920, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 340, "min": 195, "max": 580, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 71, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "page_turn": {
        "id": "page_turn",
        "version": 2,
        "domain": "video",
        "category": "transition",
        "name": "Page Turn",
        "desc": "A papery lift followed by the short brush of a settling leaf.",
        "use_for": ["document page change"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [210, 680],
        "sync_cue": "energy_peak",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 365, "min": 210, "max": 680, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 1300, "min": 780, "max": 2300, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 43, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "title_bloom": {
        "id": "title_bloom",
        "version": 2,
        "domain": "video",
        "category": "title",
        "name": "Title Bloom",
        "desc": "A slowly voiced open fifth comes into focus under a headline.",
        "use_for": ["opening title"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [400, 1350],
        "sync_cue": "energy_peak",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 780, "min": 400, "max": 1350, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 220, "min": 147, "max": 350, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 56, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "metric_chime": {
        "id": "metric_chime",
        "version": 2,
        "domain": "video",
        "category": "accent",
        "name": "Metric Chime",
        "desc": "A measured glass strike with a short, clear upper partial.",
        "use_for": ["data-card arrival"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [230, 800],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 460, "min": 230, "max": 800, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 659, "min": 370, "max": 990, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 36, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "callout_ping": {
        "id": "callout_ping",
        "version": 2,
        "domain": "video",
        "category": "accent",
        "name": "Callout Ping",
        "desc": "A single narrow focus tone settles a few cents downward.",
        "use_for": ["selection box focus"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [115, 470],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 235, "min": 115, "max": 470, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 910, "min": 520, "max": 1400, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 19, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "studio_air": {
        "id": "studio_air",
        "version": 2,
        "domain": "video",
        "category": "ambience",
        "name": "Studio Air",
        "desc": "A brief pocket of room air with a soft center and quiet edges.",
        "use_for": ["pause before an interview reveal"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [700, 2800],
        "sync_cue": "energy_peak",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 1550, "min": 700, "max": 2800, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 330, "min": 190, "max": 610, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 78, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "pulse_bed": {
        "id": "pulse_bed",
        "version": 2,
        "domain": "video",
        "category": "tension",
        "name": "Pulse Bed",
        "desc": "Five muted pulses grow toward a central editorial beat.",
        "use_for": ["brief analytical pause"],
        "avoid": ["static narration"],
        "suggested_duration_ms": [720, 2300],
        "sync_cue": "energy_peak",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 1380, "min": 720, "max": 2300, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 109, "min": 70, "max": 172, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 33, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "soft_pop": {
        "id": "soft_pop",
        "version": 2,
        "domain": "interface",
        "category": "tap",
        "name": "Soft Pop",
        "desc": "A rounded descending bubble for a light press.",
        "use_for": ["button press"],
        "avoid": ["continuous pointer movement"],
        "suggested_duration_ms": [55, 185],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 96, "min": 55, "max": 185, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 425, "min": 275, "max": 740, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 12, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "toggle_on": {
        "id": "toggle_on",
        "version": 2,
        "domain": "interface",
        "category": "toggle",
        "name": "Toggle On",
        "desc": "A compact upward latch with a softer answering contact.",
        "use_for": ["enable a switch"],
        "avoid": ["continuous pointer movement"],
        "suggested_duration_ms": [85, 220],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 138, "min": 85, "max": 220, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 540, "min": 330, "max": 820, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 14, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "select_tick": {
        "id": "select_tick",
        "version": 2,
        "domain": "interface",
        "category": "select",
        "name": "Select Tick",
        "desc": "A dry pin-sized contact with a hollow wooden resonance.",
        "use_for": ["single item selection"],
        "avoid": ["continuous pointer movement"],
        "suggested_duration_ms": [38, 112],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 64, "min": 38, "max": 112, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 1120, "min": 630, "max": 1780, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 7, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
    "confirm_chime": {
        "id": "confirm_chime",
        "version": 2,
        "domain": "interface",
        "category": "feedback",
        "name": "Confirm Chime",
        "desc": "Two consonant notes resolve upward on completion.",
        "use_for": ["successful form submission"],
        "avoid": ["continuous pointer movement"],
        "suggested_duration_ms": [180, 590],
        "sync_cue": "onset",
        "mix_hint": "Use sparingly at −14 to −10 dB under narration.",
        "params": {
            "length": {"unit": "ms", "default": 340, "min": 180, "max": 590, "step": 1, "description": "Duration including the release."},
            "pitch": {"unit": "Hz", "default": 523, "min": 349, "max": 784, "step": 1, "description": "Resonant center of the instrument."},
            "space": {"unit": "%", "default": 32, "min": 0, "max": 100, "step": 1, "description": "Room send and stereo width."},
        },
    },
}

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
    "device_mockup": {
        "id": "device_mockup", "version": 1, "domain": "product", "category": "interfaces",
        "name": "Device Mockup",
        "desc": "Ordered image resources: primary then optional mobile. Choose dual, desktop or mobile layout; reveal_at_s times the second device or solo entrance.",
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
        "desc": "Precision light/dark studio frame presenting a captured web UI screenshot with flat, tilt_left, tilt_right, dolly_zoom or scroll_reveal camera presets. Bind a cursor and up to four timed callout_steps to the chosen capture.",
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
        "desc": "2-4 elevated institutional metric/capability cards with staggered spring settle, deterministic numeric count-up, top-edge specular sheen, and light/dark studio canvas. Each item supports reveal_at_s in act-local seconds and a short supporting detail.",
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
    from app.editing.styles import STYLE_PRESET_CATALOG
    from app.editing.text_presets import TEXT_STYLE_PRESET_CATALOG

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
