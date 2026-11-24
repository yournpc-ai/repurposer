"""Direct operations on the saved work selected in this Chat round."""

import json
import re
from fractions import Fraction
from typing import Annotated, Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.agents.tool_loop import ChatTool, ToolObservation, ToolPresentation
from app.agents.tool_progress import current_call_id, current_group_id
from app.chat.editor_create import CreateVideoArgs
from app.skills.blueprint import InstantiateSkillBlueprintArgs, music_clips_for_window
from app.editing.catalog import MotionBlockId, SoundRecipeId, VoiceId
from app.editing.edits import AddClip, AddTrack, BindSource, SetTransition, SplitClip, TemporalEdit, UpdateClip, UpdateScene
from app.editing.revisions import TextPosition
from app.editing.schemas import (
    Animation,
    AudioObject,
    CaptionDerivation,
    ClipSource,
    EditTarget,
    MotionBlockObject,
    ProductShowcaseProps,
    SourceCaptionDerivation,
    SpeechObject,
    TimeRange,
    Transition,
    TransitionKind,
    VideoObject,
    speech_text_digest,
)
from app.editing.styles import BackdropStyle, StylePresetId, resolve_style_tokens
from app.editing.text_presets import TextBackgroundMode, TextStylePresetId
from app.editing.store import (
    RequestMismatch,
    StaleBase,
    apply_composition_edits,
    content_of,
    get_video_version,
)
from app.editing.temporal import resolve_temporal_target, timeline_duration
from app.editing.timing import SOURCE_TIMEBASE
from app.models.database import AsyncSessionLocal
from app.models.schemas import VideoRangeScrubTarget, canonical_json_hash
from app.tools.music.score import GenerateMusicArgs
from app.models.tables import CompositionVersion, Message


class ExportVideoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InsertAudioArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID = Field(description="Owned fixed audio snapshot from the project or a generation result.")
    start_seconds: float = Field(ge=0, allow_inf_nan=False, description="Start on the composition timeline.")
    duration_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False,
                                           description="Use the full recording when omitted. Music loops to cover a longer requested duration.")
    gain_db: float = Field(default=0, ge=-60, le=12, description="Clip gain in decibels.")
    fade_in_seconds: float | None = Field(default=None, ge=0, le=10, description="Music entrance fade.")
    fade_out_seconds: float | None = Field(default=None, ge=0, le=10, description="Music ending fade.")


class InsertVisualArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID = Field(description="Fixed image snapshot returned by prepare_video_materials.")
    start_seconds: float = Field(ge=0, allow_inf_nan=False, description="Inclusive composition time.")
    end_seconds: float = Field(gt=0, allow_inf_nan=False, description="Exclusive composition time.")
    position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "top_right"
    width_ratio: float = Field(default=0.25, gt=0.05, le=1, allow_inf_nan=False,
                               description="Fraction of canvas width; preserves image proportions.")


class GenerateImageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(min_length=1, max_length=2000, description="Describe the image and its narrative purpose.")
    svg: str | None = Field(default=None, min_length=1, max_length=20000,
                            description="For vector artwork only, an original self-contained SVG.")
    evidence_snapshot_id: UUID | None = Field(default=None, description="Verified project webpage for brand facts.")


class GenerateVoiceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=9000)
    language: Literal["en", "zh", "fr", "de", "es", "it"]
    voice_id: VoiceId = "presenter_male"


class GenerateSfxArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe_id: SoundRecipeId | None = Field(
        default=None,
        description="Choose one of the 22 recipe IDs in creative_catalog.sound_recipes. Omit when revising base_clip_id with the same recipe.",
    )
    params: dict[str, float | int] | None = Field(
        default=None,
        description="Pass only parameters declared for the target recipe in creative_catalog.sound_recipes. The 16 new recipes support length, pitch, and space. The original six also support tone and punch. Overrides are merged over defaults or base_clip_id params.",
    )
    base_clip_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="Existing SFX clip_id whose recipe, params, and seed to inherit before applying params overrides.",
    )
    seed: int | None = Field(default=None, ge=0, le=0xFFFFFFFF)


class AudioDuckWindowArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_seconds: float = Field(ge=0, allow_inf_nan=False, description="Duck start in composition timeline seconds.")
    end_seconds: float = Field(gt=0, allow_inf_nan=False, description="Duck end in composition timeline seconds.")
    duck_db: float = Field(default=-6.0, ge=-24.0, le=0.0, allow_inf_nan=False, description="Relative attenuation in dB during this window.")
    ramp_seconds: float = Field(default=0.25, ge=0.05, le=1.5, allow_inf_nan=False, description="Smooth ramp-in/out duration.")

    @model_validator(mode="after")
    def check_window(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("duck window end_seconds must exceed start_seconds.")
        return self


class EditAudioClipArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip_id: str = Field(min_length=1, max_length=64)
    gain_db: float | None = Field(
        default=None, ge=-60, le=12, allow_inf_nan=False,
        description="Updated base clip gain in decibels for this single clip.",
    )
    source_id: UUID | None = Field(
        default=None,
        description="Replacement fixed audio snapshot ID for this clip only; preserves object_id and other instances.",
    )
    fade_in_seconds: float | None = Field(
        default=None, ge=0.0, le=10.0, allow_inf_nan=False,
        description="Smooth audio fade-in duration from clip start (0 removes fade-in).",
    )
    fade_out_seconds: float | None = Field(
        default=None, ge=0.0, le=10.0, allow_inf_nan=False,
        description="Smooth audio fade-out duration into clip end (0 removes fade-out).",
    )
    duck_windows: list[AudioDuckWindowArgs] | None = Field(
        default=None, max_length=16,
        description="Optional timeline-second attenuation windows (e.g. duck BGM cleanly under voice segments).",
    )

    @model_validator(mode="after")
    def check_change(self):
        if (
            self.gain_db is None
            and self.source_id is None
            and self.fade_in_seconds is None
            and self.fade_out_seconds is None
            and self.duck_windows is None
        ):
            raise ValueError("Provide gain_db, source_id, fade_in_seconds, fade_out_seconds, or duck_windows.")
        return self


class SetTransitionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_clip_id: str = Field(min_length=1, max_length=64, description="Outgoing clip_id on the visual track.")
    to_clip_id: str = Field(min_length=1, max_length=64, description="Adjacent incoming clip_id on the same visual track.")
    kind: TransitionKind = Field(
        default="crossfade",
        description="Transition style: 'crossfade', 'whip_pan', 'wipe_reveal', 'zoom_through', or 'iris_focus'.",
    )
    duration_seconds: float = Field(
        default=0.4, ge=0.1, le=2.0, allow_inf_nan=False,
        description="Centered transition overlap duration in seconds (typically 0.35-0.5s).",
    )


class InsertMotionBlockArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: MotionBlockId = Field(
        description="Native motion block ID from creative_catalog.motion_blocks (13 blocks: statement_hook, product_showcase, device_mockup, chat_demo, flow_diagram, step_timeline, split_compare, bento_features, metric_grid, data_chart, quote_proof, kinetic_title, closing_cta).",
    )
    start_seconds: float = Field(ge=0, allow_inf_nan=False, description="Inclusive start time on timeline.")
    end_seconds: float = Field(gt=0, allow_inf_nan=False, description="Exclusive end time on timeline.")
    props: dict[str, Any] = Field(description=(
        "Declarative props for the chosen motion block. Stage options include backdrop_style "
        "('ambient_mesh' | 'architectural_grid' | 'editorial_paper' | 'kinetic_diagonal' | 'clean'), highlight_at_s, "
        "and per-item items[].reveal_at_s in scene-local seconds. For product_showcase, set "
        "camera_preset ('flat' | 'tilt_left' | 'tilt_right' | 'dolly_zoom' | 'scroll_reveal'), "
        "scroll_from_y/scroll_to_y (0..1), real view target element_id for cursor (click_at_s) "
        "and up to 4 sequential callout_steps (start_s, end_s, label, target), or callout "
        "{element_id, label?} / {x, y, width, height, label?}."
    ))
    resources: list[UUID] | None = Field(
        default=None, max_length=16,
        description="Pinned image or captured webpage snapshot IDs (one or two ordered captures for device_mockup, required capture for product_showcase, optional chat result or CTA logo).",
    )
    view_id: str | None = Field(
        default=None, max_length=120,
        description="Optional view_id when passing a webpage snapshot in resources.",
    )

    @model_validator(mode="after")
    def check_range(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must exceed start_seconds.")
        return self


class UpdateMotionBlockArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip_id: str = Field(min_length=1, max_length=64)
    props_patch: dict[str, Any] = Field(
        min_length=1,
        description="Partial props to merge into this motion block only (e.g. entrance_duration_s, backdrop_style, camera_preset, callout_steps, cursor, highlight_at_s, items, theme); unrelated clips stay untouched.",
    )


class SetCompositionStyleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    preset_id: StylePresetId = Field(
        description="First-class orthogonal visual style preset: institutional_dark, swiss_paper, vox_editorial, or kinetic_anime."
    )
    accent_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="Optional hex accent color override (contrast-checked automatically against canvas/surface).",
    )
    backdrop_style: BackdropStyle | None = Field(
        default=None,
        description="Optional backdrop texture override (ambient_mesh, architectural_grid, editorial_paper, kinetic_diagonal, clean).",
    )
    theme: Literal["dark", "light"] | None = Field(
        default=None,
        description="Optional light/dark polarity override on top of the preset.",
    )
    override_block_styles: bool = Field(
        default=True,
        description="When true (default), strip per-block theme/accent/backdrop overrides so all motion blocks inherit the new style uniformly. Set false to keep existing local per-block overrides.",
    )
    update_captions: bool = Field(
        default=True,
        description="When true (default), update derived captions to match the style's caption tokens while preserving independent user-edited captions and non-caption text.",
    )
    update_transitions: bool = Field(
        default=False,
        description="When true, also switch existing adjacent scene transitions to the preset's default_transition. Defaults to false.",
    )


class InsertTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str | None = Field(
        default=None, min_length=1, max_length=600,
        description="Direct text content (supports '\\n' for single-clip bilingual subtitles). Mutually exclusive with from_audio_clip_id.",
    )
    start_seconds: float | None = Field(
        default=None, ge=0, allow_inf_nan=False,
        description="Required in direct text mode: inclusive start time on timeline.",
    )
    end_seconds: float | None = Field(
        default=None, gt=0, allow_inf_nan=False,
        description="Required in direct text mode: exclusive end time on timeline.",
    )
    from_audio_clip_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="Narration-aligned caption mode: existing audio/speech/video clip_id with READY/ALIGNED narration alignment or ASR words to generate a full derived caption track. Mutually exclusive with text.",
    )
    role: Literal["title", "caption"] = Field(
        default="title",
        description="Visual track role in direct text mode ('title' or 'caption'). Always 'caption' in from_audio_clip_id mode.",
    )
    position: TextPosition | None = Field(
        default=None,
        description="Safe-area placement ('bottom', 'top', 'center', 'bottom_left', 'top_left', 'bottom_right', 'top_right'). Defaults to 'bottom' for captions, 'bottom_left' for lower_third_tag, 'center' for titles.",
    )
    preset_id: TextStylePresetId | None = Field(
        default=None,
        description="Optional industry text/caption preset from creative_catalog.text_style_presets (clean_broadcast, cinema_glass, minimal_light, vox_label, vox_highlighter, creator_pop, kinetic_impact, editorial_callout, lower_third_tag, karaoke_focus, bilingual_cinema).",
    )
    font_size: int | None = Field(default=None, gt=0, le=400, description="Optional font size in canvas pixels.")
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$", description="Optional text fill hex color override.")
    highlight_color: str | None = Field(
        default=None, pattern=r"^#[0-9a-fA-F]{6}$",
        description="Optional active-word highlight hex color for karaoke_focus (defaults to style accent or #FACC15).",
    )
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$", description="Optional pill/chip background hex color.")
    background_mode: TextBackgroundMode | None = Field(default=None, description="Optional background wrap mode ('box', 'pill', 'line').")
    background_opacity: float | None = Field(default=None, ge=0.0, le=1.0, description="Optional background opacity in [0, 1].")
    align: Literal["left", "center", "right"] | None = Field(default=None, description="Optional horizontal text alignment.")
    secondary_line_scale: float | None = Field(
        default=None, ge=0.4, le=1.0,
        description="Optional scale factor for line 2+ in single-clip bilingual subtitles (e.g. 0.72).",
    )

    @model_validator(mode="after")
    def _validate_mode(self):
        has_text = self.text is not None
        has_audio = self.from_audio_clip_id is not None
        if has_text == has_audio:
            raise ValueError("Provide either direct text (with start_seconds/end_seconds) or from_audio_clip_id, not both.")
        if has_text:
            if self.start_seconds is None or self.end_seconds is None:
                raise ValueError("Direct text mode requires both start_seconds and end_seconds.")
            if self.end_seconds <= self.start_seconds:
                raise ValueError("end_seconds must exceed start_seconds.")
        else:
            if self.start_seconds is not None or self.end_seconds is not None:
                raise ValueError("from_audio_clip_id mode derives cue timings automatically; omit start_seconds/end_seconds.")
        return self


class EditTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    scope: Literal["clip", "track", "all_derived_captions"] = Field(
        description="Target scope: 'clip' (single clip_id), 'track' (all TextObjects on track_id), or 'all_derived_captions' (all derived captions only, strictly protecting independent user-edited captions and non-caption text)."
    )
    clip_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="Required when scope='clip'. Exact TextObject clip ID.",
    )
    track_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="Required when scope='track'. Exact visual track ID.",
    )
    text: str | None = Field(
        default=None, min_length=1, max_length=600,
        description="Optional updated text content (scope='clip' only; supports '\\n' for bilingual subtitles). Automatically rebuilds karaoke word animations if active.",
    )
    keep_derived: bool = Field(
        default=False,
        description="When editing text on a derived caption, set false (default) to promote it to independent (protecting manual edits), or true to keep it derived (e.g. appending a bilingual translation line that still follows style switches).",
    )
    preset_id: TextStylePresetId | None = Field(
        default=None,
        description="Optional industry text/caption preset from creative_catalog.text_style_presets (clean_broadcast, cinema_glass, minimal_light, vox_label, vox_highlighter, creator_pop, kinetic_impact, editorial_callout, lower_third_tag, karaoke_focus, bilingual_cinema).",
    )
    color: str | None = Field(
        default=None, pattern=r"^#[0-9a-fA-F]{6}$",
        description="Optional text fill hex color override.",
    )
    highlight_color: str | None = Field(
        default=None, pattern=r"^#[0-9a-fA-F]{6}$",
        description="Optional active-word highlight hex color for karaoke_focus (defaults to current style accent or #FACC15).",
    )
    font_size: int | None = Field(
        default=None, gt=0, le=400,
        description="Optional font size override in canvas pixels.",
    )
    background: str | None = Field(
        default=None, pattern=r"^#[0-9a-fA-F]{6}$",
        description="Optional background pill/chip hex color override.",
    )
    clear_background: bool = Field(
        default=False,
        description="Set true to clear background fill, padding, radius, and border back to transparent defaults.",
    )
    background_mode: TextBackgroundMode | None = Field(
        default=None,
        description="Optional background wrap mode: 'box' (full box), 'pill' (tight rounded pill), or 'line' (per-line tight sticker chips).",
    )
    background_opacity: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Optional background opacity in [0, 1].",
    )
    align: Literal["left", "center", "right"] | None = Field(
        default=None,
        description="Optional horizontal text alignment override.",
    )
    secondary_line_scale: float | None = Field(
        default=None, ge=0.4, le=1.0,
        description="Optional scale factor for line 2+ in single-clip bilingual subtitles (e.g. 0.72).",
    )
    position: TextPosition | None = Field(
        default=None,
        description="Optional safe-area position update ('bottom', 'top', 'center', 'bottom_left', 'top_left', 'bottom_right', 'top_right'); updates LayoutBox and resets static transform x/y to 0.",
    )

    @model_validator(mode="after")
    def _validate_edit(self):
        if self.text is not None and self.scope != "clip":
            raise ValueError("Editing text content requires scope='clip'.")
        if self.clear_background and self.background is not None:
            raise ValueError("Provide either background or clear_background=True, not both.")
        return self


class SaveCompositionAsSkillArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(
        min_length=2, max_length=64,
        description="Kebab-case Skill slug (e.g. 'oxvalue-promo-blueprint') shown in the / SkillPicker.",
    )
    description: str = Field(
        min_length=4, max_length=400,
        description="Short description of the multi-act style, pacing, and ideal remake use case.",
    )


class InspectTimelineArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0, description="First clip index, starting at zero.")


class ClipArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip_id: str = Field(min_length=1, max_length=64)


class ExtendStillArgs(ClipArgs):
    seconds: float = Field(gt=0, allow_inf_nan=False, description="Additional seconds of the final still.")


class DeliverVideoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_id: UUID = Field(description="Exact MP4 Output inspected and chosen for delivery.")


class BindClipSourceArgs(ClipArgs):
    source_id: UUID = Field(description="Fixed project snapshot to bind to this pending media clip.")


class SplitClipArgs(ClipArgs):
    time: float = Field(
        gt=0, allow_inf_nan=False, description="Seconds from the start of this clip."
    )


class TrimClipArgs(ClipArgs):
    start: float | None = Field(
        None,
        ge=0,
        allow_inf_nan=False,
        description="First clip-local second to keep. Defaults to zero.",
    )
    end: float | None = Field(
        None,
        gt=0,
        allow_inf_nan=False,
        description="Exclusive clip-local end to keep. Defaults to the clip duration.",
    )

    @model_validator(mode="after")
    def check_window(self):
        if self.start is None and self.end is None:
            raise ValueError("Specify a boundary to trim.")
        if self.end is not None and self.end <= (self.start or 0):
            raise ValueError("The retained window must have a positive duration.")
        return self


class MoveClipArgs(ClipArgs):
    time: float = Field(
        ge=0, allow_inf_nan=False, description="New absolute start in composition seconds."
    )


class ObjectArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(
        min_length=1, max_length=64, description="Visual object_id returned by inspection."
    )


class TranslateArgs(ObjectArgs):
    x: float = Field(
        allow_inf_nan=False,
        description="Absolute offset of the layout box in canvas pixels, positive right. 0 restores its layout x.",
    )
    y: float = Field(
        allow_inf_nan=False,
        description="Absolute offset of the layout box in canvas pixels, positive down. 0 restores its layout y.",
    )


class ScaleArgs(ObjectArgs):
    value: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Absolute scale relative to layout size, 1 = original. Preserve origin and position.",
    )


KeyframeNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class SetKeyframeArgs(ClipArgs):
    animation_id: str = Field(min_length=1, max_length=64)
    at: int = Field(ge=0, strict=True, description="Existing clip-local tick from inspect_clip.")
    value: KeyframeNumber | tuple[KeyframeNumber, KeyframeNumber] = Field(
        description="Absolute scale multiplier or animated [x, y] offset added to the static transform. "
                    "In canvas pixels, positive x moves the object right and positive y moves it down."
    )


def _editor_tool(name, description, args, key):
    return ChatTool(
        name,
        description,
        args,
        terminal=False,
        batchable=True,
        independent_media=name in {"generate_voice", "generate_music", "generate_image", "generate_sfx"},
        snapshot_read=name in {"inspect_timeline", "inspect_clip"},
        presentation=ToolPresentation(
            kind="read",
            active_key="chat.activity." + key,
            done_key="chat.activity." + key + "Done",
        ),
    )


EDITOR_TOOLS = (
    _editor_tool(
        "create_video",
        "Create the first editable version from ordered shots (title cards, images, video, webpage captures, and optional narration). A title card only needs headline, duration_seconds, and text_color. Save an editable draft without exporting.",
        CreateVideoArgs, "createVideo",
    ),
    _editor_tool(
        "instantiate_skill_blueprint",
        "Instantiate a bound slot_blueprint_v1 Skill into a fresh editable multi-act Composition by filling every act's replaceable slots (fresh copy, metrics, webpage/image resources, and per-act narration). Adapts act durations to measured narration + breathing room and re-anchors SFX automatically.",
        InstantiateSkillBlueprintArgs, "instantiateSkill",
    ),
    _editor_tool(
        "save_composition_as_skill",
        "Save the current multi-act Composition as an owner-scoped reusable Skill (SKILL.md + privacy-stripped references/blueprint.json) that appears immediately in the / SkillPicker for future remakes.",
        SaveCompositionAsSkillArgs, "saveSkill",
    ),
    _editor_tool(
        "deliver_video", "Attach the reviewed MP4 to this conversation when ready to hand it to the user.",
        DeliverVideoArgs, "deliverVideo",
    ),
    _editor_tool(
        "extend_still", "Extend the closing static image, shape or title by additional seconds. Other tracks retain their duration.",
        ExtendStillArgs, "extendStill",
    ),
    _editor_tool(
        "export_video", "Export the selected, previewed version as a formal MP4. Returns the exact Output for review.",
        ExportVideoArgs, "exportVideo",
    ),
    _editor_tool("bind_clip_source", "Bind a fixed project snapshot to a pending voice or image clip. Preserve timing and layout; inspect the saved version before export.",
                 BindClipSourceArgs, "bindClipSource"),
    _editor_tool(
        "insert_visual", "Place a fixed project image above the existing footage for a timeline window. "
        "Use the returned object ID for later position or scale changes.", InsertVisualArgs, "insertVisual",
    ),
    _editor_tool(
        "insert_audio", "Place fixed audio on the current timeline at original speed. Set the level using gain_db.",
        InsertAudioArgs, "insertAudio",
    ),
    _editor_tool(
        "edit_audio_clip",
        "Update absolute gain_db (e.g. -24 to -26 dB for BGM under narration, -14 to -10 dB for SFX accents), replace source_id, and/or set smooth fade_in_seconds, fade_out_seconds, or duck_windows (compiled to audio.gain keyframes) on one existing audio clip only, preserving object_id and all other clips. "
        "For relative gain requests (e.g. '-3 dB'), compute once from the pre-turn clip gain_db and check already_saved_this_turn so the delta is never applied twice.",
        EditAudioClipArgs, "editAudioClip",
    ),
    _editor_tool(
        "generate_sfx",
        "Synthesize a deterministic 48 kHz stereo sound effect with zero credit cost from 22 v2 recipes in creative_catalog.sound_recipes (UI ticks: click, soft_pop, toggle_on, select_tick, confirm_chime; motion/transitions: whoosh, swoosh_cut, velvet_pass, page_turn; impacts: impact, deep_hit, sub_drop, kinetic_thud; risers/swells: riser, sub_swell, shimmer_lift; stingers/accents: stinger, title_bloom, metric_chime, callout_ping; beds: studio_air, pulse_bed). "
        "Pass base_clip_id to revise an existing SFX clip while inheriting its recipe and seed. Returns acoustic metrics (duration_ms, peak_offset_ms, spectral_centroid_hz, peak_dbfs); align peak_offset_ms with visual sync cues (typical peak ~-2 dBFS; place at -14 to -10 dB under narration).",
        GenerateSfxArgs, "generateSfx",
    ),
    _editor_tool(
        "insert_motion_block",
        "Insert one of the 13 native declarative motion blocks from creative_catalog.motion_blocks onto the timeline below captions (statement_hook, product_showcase, device_mockup, chat_demo, flow_diagram, step_timeline, split_compare, bento_features, metric_grid, data_chart, quote_proof, kinetic_title, closing_cta). "
        "Pass captured webpage or image snapshot IDs in resources for product_showcase, device_mockup (primary then mobile), optional chat result, or CTA logo.",
        InsertMotionBlockArgs, "insertMotionBlock",
    ),
    _editor_tool(
        "update_motion_block",
        "Patch declarative props on one existing motion_block clip only (e.g. entrance_duration_s, backdrop_style, camera_preset, callout_steps, cursor, highlight_at_s, items[].reveal_at_s, theme), leaving all other tracks and clips unchanged. Check already_saved_this_turn props_before/after before relative adjustments.",
        UpdateMotionBlockArgs, "updateMotionBlock",
    ),
    _editor_tool(
        "set_composition_style",
        "Atomically apply a first-class orthogonal visual style preset (institutional_dark, swiss_paper, vox_editorial, kinetic_anime) across the entire composition — updating canvas background, motion block inheritance, derived captions (never touching independent captions or non-caption text), and optional transitions while leaving all audio tracks untouched.",
        SetCompositionStyleArgs, "setCompositionStyle",
    ),
    _editor_tool(
        "insert_text",
        "Insert a native TextObject title/overlay/caption clip (direct text with start_seconds/end_seconds, supporting '\\n' bilingual lines) OR generate a full aligned derived caption track from an existing aligned audio/speech/video clip (from_audio_clip_id). Supports safe-area position presets and all 11 industry presets in creative_catalog.text_style_presets (including karaoke_focus with word-level timings).",
        InsertTextArgs, "insertText",
    ),
    _editor_tool(
        "edit_text",
        "Atomically edit native TextObject content (scope='clip'), safe-area position, and/or style/preset across scope='clip', 'track', or 'all_derived_captions' using the 11 industry presets in creative_catalog.text_style_presets. With scope='all_derived_captions', strictly preserves independent user-edited captions, non-caption text, and all audio tracks.",
        EditTextArgs, "editText",
    ),
    _editor_tool(
        "set_transition",
        "Add or update a centered transition ('crossfade', 'whip_pan', 'wipe_reveal', 'zoom_through', or 'iris_focus') between two adjacent full-canvas opaque clips (including opaque motion blocks with show_backdrop=True) on the same visual track.",
        SetTransitionArgs, "setTransition",
    ),
    _editor_tool(
        "generate_image", "Create and review one image. Returns the actual pixels and a fixed project source.",
        GenerateImageArgs, "visualAssets",
    ),
    _editor_tool(
        "generate_voice",
        "Record the exact script at original speed. Return playable audio, measured duration and alignment status.",
        GenerateVoiceArgs,
        "recordVoice",
    ),
    _editor_tool(
        "generate_music",
        "Generate a playable electronic instrumental of the requested length. Returns measured audio for later editing.",
        GenerateMusicArgs,
        "musicPrepare",
    ),
    _editor_tool(
        "inspect_timeline",
        "Read clips in timeline order, their tracks, scene numbers, source windows and spatial object IDs.",
        InspectTimelineArgs,
        "inspectClips",
    ),
    _editor_tool(
        "inspect_clip",
        "Inspect one clip, its layout, transform, whole-object scale and position keyframes (clip-local ticks) and same-track neighbors on the current version.",
        ClipArgs,
        "inspectClip",
    ),
    _editor_tool(
        "remove_clip",
        "Remove one identified clip after inspecting its source, timing and relations. "
        "If asked to listen or watch first, preview the affected window before removing it. "
        "Linked clips and dependent captions must remain intact. Other clips keep their positions.",
        ClipArgs, "removeClip",
    ),
    _editor_tool(
        "split_clip",
        "Split a clip and its linked media at a clip-local second. Save one version.",
        SplitClipArgs,
        "splitClip",
    ),
    _editor_tool(
        "trim_clip",
        "Keep a subrange measured from this clip's start. Crop linked fixed sources at 1x, leave gaps, keep other clips in place. Reject broken transitions or loss of a linked member.",
        TrimClipArgs,
        "trimClip",
    ),
    _editor_tool(
        "move_clip",
        "Set a clip's start on the timeline, moving its linked clips equally. Preserve duration and source window, leave gaps. Reject same-track collisions, broken transitions and scene escape.",
        MoveClipArgs,
        "moveClip",
    ),
    _editor_tool(
        "set_keyframe",
        "Change the value of one existing whole-object scale or position keyframe on the inspected clip. "
        "Inspect its animation ID and local tick first. Preview the affected motion before and after adjusting it.",
        SetKeyframeArgs, "setKeyframe",
    ),
    _editor_tool(
        "translate",
        "Set one visual object's static offset relative to its layout box. Preserve other objects and time. Reject an animated position.",
        TranslateArgs,
        "translate",
    ),
    _editor_tool(
        "scale",
        "Set one visual object's static scale around its existing origin. Preserve other objects, including subtitles. Reject animated scale.",
        ScaleArgs,
        "scale",
    ),
    _editor_tool(
        "preview_range",
        "Play the current draft across all tracks and publish the selected window in Chat with sampled visual frames plus audio_windows and masking_warnings (respect audio_available_to_model before claiming subjective audio impressions). Choose a local edit, a join, or the whole short film as needed. Recently edited clip windows are suggestions. Honor an explicitly requested range exactly. Use absolute seconds (up to 12 seconds per window).",
        VideoRangeScrubTarget,
        "previewRange",
    ),
)
EDITOR_NAMES = frozenset(tool.name for tool in EDITOR_TOOLS)
WRITE_TOOLS = {
    t.name: t
    for t in EDITOR_TOOLS
    if t.name == "remove_clip" or t.params_model in (
        SplitClipArgs, TrimClipArgs, MoveClipArgs, TranslateArgs, ScaleArgs, SetKeyframeArgs,
        InsertVisualArgs, InsertAudioArgs, EditAudioClipArgs, InsertMotionBlockArgs, UpdateMotionBlockArgs,
        SetCompositionStyleArgs, InsertTextArgs, EditTextArgs, SetTransitionArgs, ExtendStillArgs, BindClipSourceArgs,
    )
}


def _ticks(seconds, timebase):
    ticks = Fraction(str(seconds)) * timebase
    if ticks.denominator != 1:
        raise ValueError("The time must fall on an exact composition tick.")
    return int(ticks)


def _transform_animations(animations):
    return [a.model_dump(mode="json") for a in animations
            if a.text_part is None and a.property in {"transform.scale", "transform.position"}]


async def _load_snapshot_origins(db, clips) -> dict[UUID, dict[str, Any]]:
    from app.models.tables import SourceSnapshot

    ids = {
        c.source.snapshot_id
        for c in clips
        if c.object.kind == "audio" and c.source is not None
    }
    if not ids:
        return {}
    rows = await db.scalars(select(SourceSnapshot).where(SourceSnapshot.id.in_(ids)))
    out: dict[UUID, dict[str, Any]] = {}
    for snap in rows:
        meta = snap.meta or {}
        origin = meta.get("origin") or {}
        if origin.get("kind") == "sound_recipe":
            out[snap.id] = {
                "recipe_id": origin.get("recipe_id"),
                "recipe_version": origin.get("recipe_version"),
                "params": origin.get("params"),
                "seed": origin.get("seed"),
                "acoustics": origin.get("acoustics"),
            }
    return out


def validate_motion_block_translate(
    obj: MotionBlockObject, *, x: float, y: float, width: float, height: float
) -> None:
    """Keep region-select micro-adjustments working while preventing off-canvas clipping."""
    if obj.block_id == "kinetic_title":
        pos = str(obj.props.get("position", "bottom_left"))
        min_x = -48.0 if pos.endswith("left") else -width * 0.35
        max_x = width * 0.45 if pos.endswith("left") else width * 0.35
        if pos.startswith("bottom"):
            min_y, max_y = -height * 0.55, 24.0
        elif pos.startswith("top"):
            min_y, max_y = -24.0, height * 0.55
        else:
            min_y, max_y = -height * 0.35, height * 0.35
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            raise ValueError(
                f"Translation (x={x:g}, y={y:g}) would push kinetic_title ({pos}) outside "
                f"the visible canvas safe area (allowed x:[{min_x:g},{max_x:g}], y:[{min_y:g},{max_y:g}]). "
                "Keep y <= 24 for bottom titles (0 resets layout, negative moves up) or change position via update_motion_block."
            )
    elif abs(x) > width * 0.15 or abs(y) > height * 0.15:
        raise ValueError(
            "Translation would shift the full-frame motion_block outside safe canvas bounds."
        )


def _composition_style_summary(content) -> dict[str, Any] | None:
    if content.settings.style is None:
        return None
    tokens = resolve_style_tokens(content.settings.style)
    return {
        "preset_id": tokens["preset_id"],
        "theme": tokens["theme"],
        "backdrop_style": tokens["backdrop_style"],
        "accent": tokens["accent"],
        "canvas_bg": tokens["canvas_bg"],
        "default_transition": tokens["default_transition"],
    }


async def _resolve_aligned_caption_cues(db, project, content, audio_clip) -> list[dict[str, Any]]:
    """Resolve aligned sentence/word cues for insert_text(from_audio_clip_id=...)."""
    from app.editing.alignment import NarrationPayload
    from app.editing.source_selection import source_sentences
    from app.editing.timing import seconds_to_ticks, source_ticks_to_output_ticks
    from app.models.tables import NarrationAlignment, SourceSnapshot

    obj = audio_clip.object
    if not isinstance(obj, (AudioObject, SpeechObject, VideoObject)):
        raise ValueError(
            f"Clip {audio_clip.clip_id!r} is not an audio, speech, or video clip."
        )
    if audio_clip.source is None or audio_clip.source.source_range is None:
        raise ValueError(
            f"Clip {audio_clip.clip_id!r} has no bound source media window. "
            "Align the recording first or pass direct text with start_seconds/end_seconds."
        )
    src = audio_clip.source
    sr = src.source_range
    timebase = content.settings.timebase

    def _cues_from_narration_payload(
        payload: NarrationPayload,
        *,
        alignment_row,
        is_speech: bool,
    ) -> list[dict[str, Any]]:
        cues: list[dict[str, Any]] = []
        for sentence in payload.sentences:
            s_start = max(sr.start, sentence.start_tick)
            s_end = min(sr.end, sentence.end_tick)
            if s_end <= s_start:
                continue
            out_start = audio_clip.range.start + source_ticks_to_output_ticks(
                s_start - sr.start, timebase
            )
            out_end = audio_clip.range.start + source_ticks_to_output_ticks(
                s_end - sr.start, timebase
            )
            if out_end <= out_start:
                continue
            text = sentence.text.strip()
            if not text:
                continue
            word_timings: list[dict[str, Any]] = []
            for w in sentence.words:
                ws = max(s_start, w.start_tick)
                we = min(s_end, w.end_tick)
                if we > ws:
                    word_timings.append(
                        {
                            "start_s": (ws - s_start) / SOURCE_TIMEBASE,
                            "end_s": (we - s_start) / SOURCE_TIMEBASE,
                            "text_start": w.text_start - sentence.text_start,
                            "text_end": w.text_end - sentence.text_start,
                        }
                    )
            if is_speech and isinstance(obj, SpeechObject) and obj.alignment is not None:
                if text == obj.text and out_start == audio_clip.range.start and out_end == audio_clip.range.end:
                    caption = CaptionDerivation(
                        speech_object_id=obj.object_id,
                        source_text_digest=speech_text_digest(obj.text),
                        alignment="faster-whisper-script-v1",
                        state="derived",
                        narration_alignment_id=obj.alignment.alignment_id,
                        narration_content_digest=obj.alignment.content_digest,
                        sentence_id=sentence.sentence_id,
                    )
                else:
                    caption = CaptionDerivation(
                        speech_object_id=obj.object_id,
                        source_text_digest=speech_text_digest(obj.text),
                        alignment="faster-whisper-script-v1",
                        state="derived",
                        narration_alignment_id=obj.alignment.alignment_id,
                        narration_content_digest=obj.alignment.content_digest,
                        sentence_id=sentence.sentence_id,
                        text_start=sentence.text_start,
                        text_end=sentence.text_end,
                    )
            else:
                has_ready_provenance = (
                    alignment_row.status == "READY" and bool(alignment_row.content_digest)
                )
                caption = SourceCaptionDerivation(
                    snapshot_id=src.snapshot_id,
                    snapshot_digest=src.snapshot_digest,
                    sentence_id=sentence.sentence_id,
                    source_range=TimeRange(start=s_start, end=s_end),
                    source_text_digest=speech_text_digest(text),
                    alignment=(
                        alignment_row.algorithm
                        if has_ready_provenance
                        else "faster-whisper-source-v1"
                    ),
                    state="derived",
                    narration_alignment_id=alignment_row.id if has_ready_provenance else None,
                    narration_content_digest=(
                        alignment_row.content_digest if has_ready_provenance else None
                    ),
                )
            cues.append(
                {
                    "sentence_id": sentence.sentence_id,
                    "text": text,
                    "output_start": out_start,
                    "output_end": out_end,
                    "caption": caption,
                    "word_timings": word_timings or None,
                }
            )
        return cues

    # 1. SpeechObject with explicit NarrationAlignmentRef
    if isinstance(obj, SpeechObject):
        if obj.alignment is None:
            raise ValueError(
                f"Speech clip {audio_clip.clip_id!r} has no narration alignment yet. "
                "Call align_recording first or pass direct text with start_seconds/end_seconds."
            )
        alignment_row = await db.scalar(
            select(NarrationAlignment).where(
                NarrationAlignment.id == obj.alignment.alignment_id,
                NarrationAlignment.owner_id == project.user_id,
                NarrationAlignment.status.in_(("READY", "ALIGNED")),
            )
        )
        if alignment_row is None or not alignment_row.payload:
            raise ValueError(
                f"Narration alignment for speech clip {audio_clip.clip_id!r} is not READY/ALIGNED yet."
            )
        payload = NarrationPayload.model_validate(alignment_row.payload)
        return _cues_from_narration_payload(payload, alignment_row=alignment_row, is_speech=True)

    # 2. Audio/Video clip with a READY or ALIGNED NarrationAlignment row for its snapshot
    alignment_rows = list(
        await db.scalars(
            select(NarrationAlignment)
            .where(
                NarrationAlignment.owner_id == project.user_id,
                NarrationAlignment.audio_snapshot_id == src.snapshot_id,
                NarrationAlignment.status.in_(("READY", "ALIGNED")),
            )
            .order_by(NarrationAlignment.created_at.desc())
        )
    )
    alignment_row = next(
        (r for r in alignment_rows if r.status == "READY"),
        alignment_rows[0] if alignment_rows else None,
    )
    if alignment_row is not None and alignment_row.payload:
        payload = NarrationPayload.model_validate(alignment_row.payload)
        cues = _cues_from_narration_payload(payload, alignment_row=alignment_row, is_speech=False)
        if cues:
            return cues

    # 3. Fallback: SourceSnapshot.meta ASR words (uploaded video/audio ASR)
    snapshot = await db.scalar(
        select(SourceSnapshot).where(
            SourceSnapshot.id == src.snapshot_id,
            SourceSnapshot.owner_id == project.user_id,
        )
    )
    raw_words = ((snapshot.meta or {}).get("words") if snapshot is not None else None) or []
    if snapshot is not None and raw_words and snapshot.duration_ticks:
        sentences = source_sentences(raw_words, duration_ticks=int(snapshot.duration_ticks))
        cues = []
        for sentence in sentences:
            s_start = max(sr.start, seconds_to_ticks(sentence.start))
            s_end = min(sr.end, seconds_to_ticks(sentence.end))
            if s_end <= s_start:
                continue
            out_start = audio_clip.range.start + source_ticks_to_output_ticks(
                s_start - sr.start, timebase
            )
            out_end = audio_clip.range.start + source_ticks_to_output_ticks(
                s_end - sr.start, timebase
            )
            if out_end <= out_start:
                continue
            text = sentence.text.strip()
            if not text:
                continue
            s_start_s = s_start / SOURCE_TIMEBASE
            s_end_s = s_end / SOURCE_TIMEBASE
            word_timings = [
                (
                    max(0.0, float(w["start"]) - s_start_s),
                    max(0.01, min(s_end_s, float(w["end"])) - s_start_s),
                )
                for w in raw_words
                if isinstance(w, dict)
                and float(w.get("end", 0)) > s_start_s
                and float(w.get("start", 0)) < s_end_s
                and str(w.get("word") or "").strip()
            ]
            cues.append(
                {
                    "sentence_id": sentence.sentence_id,
                    "text": text,
                    "output_start": out_start,
                    "output_end": out_end,
                    "caption": SourceCaptionDerivation(
                        snapshot_id=src.snapshot_id,
                        snapshot_digest=src.snapshot_digest,
                        sentence_id=sentence.sentence_id,
                        source_range=TimeRange(start=s_start, end=s_end),
                        source_text_digest=speech_text_digest(text),
                        alignment="faster-whisper-source-v1",
                        state="derived",
                    ),
                    "word_timings": word_timings or None,
                }
            )
        if cues:
            return cues

    raise ValueError(
        f"Clip {audio_clip.clip_id!r} has no READY/ALIGNED narration alignment or ASR word transcript. "
        "Call align_recording first, or call insert_text with direct text and start_seconds/end_seconds."
    )


def _clip_facts(track, clip, content, snapshot_origins: dict[UUID, dict[str, Any]] | None = None):
    rate = content.settings.timebase
    obj = clip.object
    transform = getattr(obj, "transform", None)
    scene_number = next(
        (i for i, scene in enumerate(content.scenes, 1) if scene.scene_id == clip.scene_id), None
    )
    sound_recipe = (
        (snapshot_origins or {}).get(clip.source.snapshot_id)
        if obj.kind == "audio" and clip.source is not None
        else None
    )
    text_fields: dict[str, Any] = {}
    if obj.kind == "text":
        text_fields = {
            "text": obj.text[:400],
            "style": {
                "font_size": obj.style.font_size,
                "color": obj.style.color,
                "weight": obj.style.weight,
                "align": obj.style.align,
                "background": obj.style.background,
                "background_mode": obj.style.background_mode,
                "background_opacity": obj.style.background_opacity,
                "secondary_line_scale": obj.style.secondary_line_scale,
                "has_stroke": obj.style.stroke is not None and obj.style.stroke.width > 0,
                "has_shadow": obj.style.shadow is not None,
                "has_border": obj.style.border is not None and obj.style.border.width > 0,
            },
            "caption_state": obj.caption.state if obj.caption is not None else None,
            "karaoke_active": any(a.animation_id.startswith("karaoke_") for a in clip.animations),
        }
    return {
        "clip_id": clip.clip_id,
        "object_id": obj.object_id,
        "kind": obj.kind,
        "track_id": track.track_id,
        "track_role": track.role,
        "track_order": track.order,
        "scene_id": clip.scene_id,
        "scene_number": scene_number,
        "linked_group_id": clip.linked_group_id,
        "start_seconds": clip.range.start / rate,
        "end_seconds": clip.range.end / rate,
        "source": clip.source.model_dump(mode="json") if clip.source else None,
        "layout": obj.layout.model_dump() if getattr(obj, "layout", None) else None,
        "transform": transform.model_dump() if transform else None,
        **({"fit": obj.fit} if hasattr(obj, "fit") else {}),
        "animated_properties": sorted({a.property for a in clip.animations if a.text_part is None}),
        **(
            {
                "gain_db": obj.gain_db,
                "has_gain_automation": any(a.property == "audio.gain" for a in clip.animations),
            }
            if obj.kind == "audio"
            else {}
        ),
        **({"sound_recipe": sound_recipe} if sound_recipe else {}),
        **({"block_id": obj.block_id, "block_version": obj.block_version, "props": obj.props,
            "resources": [r.model_dump(mode="json") for r in obj.resources]}
           if obj.kind == "motion_block" else {}),
        **text_fields,
        **({"text": obj.text, "language": obj.language, "voice_id": obj.voice_id,
            "alignment_id": str(obj.alignment.alignment_id) if obj.alignment else None}
           if obj.kind == "speech" else {}),
    }


def requests_observation_first(text: str) -> bool:
    """Honor an explicit watch-then-decide request before its first edit."""
    return bool(re.search(
        r"先(?:检查(?:并|后)|实际)?(?:预览|播放|试听)|"
        r"(?:实际|先).{0,8}(?:看片|看一下|预览|播放|试听).{0,65}(?:问题|不合适|发现|再).{0,20}(?:改|调|移除|删除)|"
        r"\b(?:watch|listen|preview|review)\b.{0,100}\b(?:if|before|then)\b.{0,65}\b(?:fix|edit|adjust|change|remove|delete)\w*",
        text, re.I | re.S,
    ))


async def edit_clip(
    db, *, name, project, opening_id, conversation_id, call_id, base, args, inspected_version=None, observed_preview=None
):
    from app.chat.service import TurnStopped, _lock_turn_for_transcript_write

    opening = await _lock_turn_for_transcript_write(db, opening_id)
    if opening.conversation_id != conversation_id or opening.role != "user":
        raise ValueError("The editing request is unavailable.")
    if name not in WRITE_TOOLS or not isinstance(args, WRITE_TOOLS[name].params_model):
        raise ValueError("Arguments do not match this editor operation.")
    identity = uuid5(opening_id, call_id)
    if str(identity) in (opening.intent or {}).get("media_replay_ids", {}) or await db.scalar(select(Message.id).where(
        Message.turn_id == opening_id, Message.intent["editor_media"].astext == str(identity),
    )):
        raise RequestMismatch("This call already belongs to a media request.")
    # A replay can arrive after the round reader has already observed our new
    # head. Reconstruct the original request against its immutable base and
    # let the store compare its digest before returning the committed row.
    previous = await db.scalar(
        select(CompositionVersion).where(
            CompositionVersion.request_id == str(identity),
            CompositionVersion.composition_id == UUID(base["composition_id"]),
        )
    )
    if previous is None:
        if opening.turn_state != "in_flight":
            raise TurnStopped(str(opening_id))
        if inspected_version and inspected_version != base["composition_version_id"]:
            raise ValueError(
                "The timeline changed since inspection. Inspect the current clips again."
            )
    composition, version = await get_video_version(
        db,
        owner_id=project.user_id,
        version_id=previous.base_version_id if previous else UUID(base["composition_version_id"]),
    )
    if (
        str(composition.id) != base["composition_id"]
        or composition.origin_project_id != project.id
        or (not previous and version.content_digest != base["content_digest"])
    ):
        raise ValueError("The selected work or version changed.")
    content = content_of(version)
    entries = [(track, clip) for track in content.timeline.tracks for clip in track.clips]
    clips = {clip.clip_id: clip for _, clip in entries}
    commits = (opening.intent or {}).get("editor_commits", [])
    if not previous and not commits and requests_observation_first(opening.content or ""):
        preview = observed_preview or {}
        if (preview.get("version_id") != str(version.id) or preview.get("content_digest") != version.content_digest
                or not preview.get("mp4_sha256") or current_group_id() and preview.get("decision") == current_group_id()):
            raise ValueError("The user asked to see the footage before deciding on an edit. Preview the affected window of this version and inspect the returned frames first.")
        if name == "remove_clip" and args.clip_id in clips:
            span = clips[args.clip_id].range
            rate = content.settings.timebase
            if not any(w["start"] < span.end / rate and w["end"] > span.start / rate for w in preview.get("windows", [])):
                raise ValueError("Preview the affected window containing this clip before removing it.")
    prior = next((c for c in commits if c["request"] == str(identity)), None)
    wire_args = args.model_dump(mode="json")
    if isinstance(args, InsertAudioArgs):
        # Preserve fingerprints of inserts committed before music fades were accepted.
        for field in ("fade_in_seconds", "fade_out_seconds"):
            if wire_args[field] is None:
                del wire_args[field]
    fingerprint = canonical_json_hash({"tool": name, "args": wire_args})
    if prior and prior["fingerprint"] != fingerprint:
        raise RequestMismatch("This native call already committed different parameters.")
    rate = content.settings.timebase
    extra = {}
    ops = []
    target = None
    if isinstance(args, BindClipSourceArgs):
        from app.tools.video.export import bind_clip_source_ops

        target = clips.get(args.clip_id)
        ops = await bind_clip_source_ops(db, project, content, target, args.source_id)
    elif isinstance(args, InsertVisualArgs):
        from app.editing.revisions import fixed_visual_ops
        from app.models.tables import Asset, SourceSnapshot

        # Older upload snapshots record the owning Asset but have no birth-project field.
        legacy_asset = select(Asset.id).where(Asset.user_id == project.user_id, Asset.project_id == project.id)
        source = await db.scalar(select(SourceSnapshot).where(
            SourceSnapshot.id == args.source_id,
            SourceSnapshot.owner_id == project.user_id,
            SourceSnapshot.kind == "image",
            (SourceSnapshot.origin_project_id == project.id)
            | (SourceSnapshot.origin_project_id.is_(None) & SourceSnapshot.asset_id.in_(legacy_asset)),
        ))
        if source is None or not source.storage_key:
            raise ValueError("Select a fixed image from this project.")
        start = _ticks(args.start_seconds, rate)
        end = _ticks(args.end_seconds, rate)
        if not start < end <= timeline_duration(content):
            raise ValueError("The visual window must fit inside the composition.")
        scene = next((s for s in content.scenes if s.range.start <= start and end <= s.range.end), None)
        fact = {"kind": source.kind, "digest": source.digest, "meta": source.meta or {}}
        margin = min(content.settings.height * 0.04, content.settings.width * (1 - args.width_ratio) / 2)
        ops = fixed_visual_ops(content, fact, source_id=source.id, identity=identity.hex,
                               scene_id=scene.scene_id if scene else None, start=start, end=end,
                               position=args.position, width_ratio=args.width_ratio, margin_px=margin)
    elif isinstance(args, InsertAudioArgs):
        from app.editing.revisions import fixed_audio_ops
        from app.editing.timing import output_ticks_to_source_ticks, source_ticks_to_output_ticks
        from app.models.tables import SourceSnapshot

        snapshot = await db.get(SourceSnapshot, args.source_id)
        if (snapshot is None or snapshot.owner_id != project.user_id or snapshot.origin_project_id != project.id
                or snapshot.kind != "audio" or not snapshot.duration_ticks):
            raise ValueError("Select a fixed audio source from the current project.")
        start = _ticks(args.start_seconds, rate)
        source_end = (snapshot.duration_ticks if args.duration_seconds is None else
                      output_ticks_to_source_ticks(_ticks(args.duration_seconds, rate), rate))
        end = start + source_ticks_to_output_ticks(source_end, rate)
        limit = max([c.range.end for _, c in entries] + [scene.range.end for scene in content.scenes] + [0])
        if not start < end <= limit:
            raise ValueError("The audio must fit the source and the current composition duration.")
        meta = snapshot.meta or {}
        origin = meta.get("origin") or {}
        is_music = (
            origin.get("kind") in {"programmatic_score", "library_music"}
            or bool(meta.get("music"))
        )
        role = "music" if is_music else (
            "dialogue" if origin.get("video_narration_hash") else "effect"
        )
        if role != "music" and (source_end > snapshot.duration_ticks or args.fade_in_seconds is not None
                                or args.fade_out_seconds is not None):
            raise ValueError("Only music can loop or use insertion fades.")
        if role == "effect":
            def _overlaps(t):
                return any(c.range.start < end and start < c.range.end for c in t.clips)

            existing_effects = sorted(
                (t for t in content.timeline.tracks if t.kind == "audio" and t.role == "effect"),
                key=lambda t: t.order,
            )
            free_track = next((t for t in existing_effects if not _overlaps(t)), None)
            if free_track is not None:
                track_id = free_track.track_id
            else:
                used_ids = {t.track_id for t in content.timeline.tracks}
                track_id = "trk_editor_effect"
                idx = 2
                while track_id in used_ids:
                    track_id = f"trk_editor_effect_{idx}"
                    idx += 1
        else:
            track_id = f"trk_editor_{role}"
            track = next((t for t in content.timeline.tracks if t.track_id == track_id), None)
            if track and (track.kind != "audio" or track.role != role):
                raise ValueError("The destination track has a different role.")
        if role == "music":
            music = music_clips_for_window(
                settings=content.settings, start=start, end=end, source_id=snapshot.id, digest=snapshot.digest,
                source_ticks=snapshot.duration_ticks, id_stem=identity.hex, gain_db=args.gain_db,
                fade_in_seconds=args.fade_in_seconds, fade_out_seconds=args.fade_out_seconds,
            )
            if snapshot.id not in {source.snapshot_id for source in content.sources}:
                ops.append(BindSource(op="bind_source", snapshot_id=snapshot.id))
            if track is None:
                order = max((t.order for t in content.timeline.tracks if t.kind == "audio"), default=-1) + 1
                ops.append(AddTrack(op="add_track", track={
                    "track_id": track_id, "kind": "audio", "role": role, "order": order, "clips": [],
                }))
            ops.extend(AddClip(op="add_clip", track_id=track_id, clip=clip) for clip in music)
        else:
            ops = fixed_audio_ops(content, source_id=snapshot.id, source_digest=snapshot.digest,
                                  track_id=track_id, role=role, clip_id=f"clp_{identity.hex}",
                                  object_id=f"obj_{identity.hex}", scene_id=None, start=start, end=end,
                                  source_start=0, source_end=source_end, gain_db=args.gain_db)
    elif isinstance(args, EditAudioClipArgs):
        from app.editing.revisions import build_audio_gain_animation
        from app.editing.timing import source_ticks_to_output_ticks
        from app.models.tables import SourceSnapshot

        target = clips.get(args.clip_id)
        if target is None or target.object.kind != "audio":
            raise ValueError("Select an existing audio clip to edit.")
        updated_obj = (
            target.object.model_copy(update={"gain_db": args.gain_db})
            if args.gain_db is not None
            else target.object
        )
        old_source_id = str(target.source.snapshot_id) if target.source else None
        new_source_id = str(args.source_id) if args.source_id is not None else old_source_id
        update_fields: dict[str, Any] = {}
        if args.gain_db is not None and updated_obj.gain_db != target.object.gain_db:
            update_fields["object"] = updated_obj
        effective_range = target.range
        if args.source_id is not None and new_source_id != old_source_id:
            snapshot = await db.get(SourceSnapshot, args.source_id)
            if (
                snapshot is None
                or snapshot.owner_id != project.user_id
                or snapshot.origin_project_id != project.id
                or snapshot.kind != "audio"
                or not snapshot.duration_ticks
            ):
                raise ValueError("Select a fixed audio source from the current project.")
            if snapshot.id not in {b.snapshot_id for b in content.sources}:
                ops.append(BindSource(op="bind_source", snapshot_id=snapshot.id))
            limit = max([c.range.end for _, c in entries] + [scene.range.end for scene in content.scenes] + [0])
            new_out_dur = source_ticks_to_output_ticks(snapshot.duration_ticks, rate)
            new_end = min(limit, target.range.start + new_out_dur)
            if new_end <= target.range.start:
                raise ValueError("The replacement audio does not fit at this clip's start time.")
            from app.editing.timing import output_ticks_to_source_ticks

            used_source_end = min(
                snapshot.duration_ticks,
                output_ticks_to_source_ticks(new_end - target.range.start, rate),
            )
            update_fields["source"] = ClipSource(
                snapshot_id=snapshot.id,
                snapshot_digest=snapshot.digest,
                source_range=TimeRange(start=0, end=used_source_end),
            )
            if new_end != target.range.end:
                effective_range = TimeRange(start=target.range.start, end=new_end)
                update_fields["range"] = effective_range
        envelope_requested = (
            args.fade_in_seconds is not None
            or args.fade_out_seconds is not None
            or args.duck_windows is not None
        )
        if envelope_requested:
            gain_anim_dict = build_audio_gain_animation(
                object_id=target.object.object_id,
                clip_start_ticks=effective_range.start,
                clip_end_ticks=effective_range.end,
                timebase=rate,
                fps_num=content.settings.fps.num,
                fps_den=content.settings.fps.den,
                fade_in_seconds=args.fade_in_seconds,
                fade_out_seconds=args.fade_out_seconds,
                duck_windows=[w.model_dump() for w in args.duck_windows] if args.duck_windows else None,
            )
            kept = [a for a in target.animations if a.property != "audio.gain"]
            new_animations = [*kept, Animation.model_validate(gain_anim_dict)] if gain_anim_dict else kept
            if [a.model_dump(mode="json") for a in new_animations] != [a.model_dump(mode="json") for a in target.animations]:
                update_fields["animations"] = new_animations
                extra["audio_gain_keyframes"] = len(gain_anim_dict["keyframes"]) if gain_anim_dict else 0
                extra["fade_in_seconds"] = args.fade_in_seconds
                extra["fade_out_seconds"] = args.fade_out_seconds
        if not update_fields:
            raise ValueError("The audio clip already has these settings.")
        extra["gain_db_before"] = target.object.gain_db
        extra["gain_db_after"] = updated_obj.gain_db
        extra["source_before"] = old_source_id
        extra["source_after"] = new_source_id
        ops.append(UpdateClip(op="update_clip", clip_id=target.clip_id, **update_fields))
    elif isinstance(args, SetTransitionArgs):
        if args.from_clip_id not in clips or args.to_clip_id not in clips:
            raise ValueError("Both from_clip_id and to_clip_id must exist on the current timeline.")
        existing = next(
            (
                t for t in content.timeline.transitions
                if t.from_clip_id == args.from_clip_id and t.to_clip_id == args.to_clip_id
            ),
            None,
        )
        duration_ticks = _ticks(args.duration_seconds, rate)
        transition_id = existing.transition_id if existing else f"trn_{identity.hex[:16]}"
        transition = Transition(
            transition_id=transition_id,
            from_clip_id=args.from_clip_id,
            to_clip_id=args.to_clip_id,
            kind=args.kind,
            duration=duration_ticks,
            alignment="center",
        )
        if existing is not None and existing == transition:
            raise ValueError("This transition already has these settings.")
        extra["transition"] = {
            "transition_id": transition_id,
            "from_clip_id": args.from_clip_id,
            "to_clip_id": args.to_clip_id,
            "kind": args.kind,
            "duration_seconds": args.duration_seconds,
        }
        ops.append(SetTransition(op="set_transition", transition=transition))
    elif isinstance(args, InsertMotionBlockArgs):
        from app.editing.revisions import motion_block_ops
        from app.editing.sources import register_web_view_snapshot
        from app.models.tables import Asset, SourceSnapshot

        start = _ticks(args.start_seconds, rate)
        end = _ticks(args.end_seconds, rate)
        limit = max([c.range.end for _, c in entries] + [scene.range.end for scene in content.scenes] + [0])
        if not 0 <= start < end <= limit:
            raise ValueError("The motion block window must fit inside the composition duration.")
        legacy_asset = select(Asset.id).where(Asset.user_id == project.user_id, Asset.project_id == project.id)
        props = args.props
        resolved_resources: list[dict[str, Any]] = []
        ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        for idx, res_id in enumerate(args.resources or []):
            snap = await db.scalar(select(SourceSnapshot).where(
                SourceSnapshot.id == res_id,
                SourceSnapshot.owner_id == project.user_id,
                (SourceSnapshot.origin_project_id == project.id)
                | (SourceSnapshot.origin_project_id.is_(None) & SourceSnapshot.asset_id.in_(legacy_asset)),
            ))
            if snap is None:
                raise ValueError(f"Resource snapshot {res_id} is unavailable in this project.")
            if snap.kind == "web":
                views = (snap.meta or {}).get("views") or []
                chosen_view = args.view_id or (views[0].get("view_id") if views else None)
                if not chosen_view:
                    raise ValueError("The captured webpage has no rendered views.")
                if idx == 0 and args.block_id == "product_showcase":
                    props = ProductShowcaseProps.resolve_props(props, views, chosen_view)
                snap = await register_web_view_snapshot(
                    db, owner_id=project.user_id, web_snapshot=snap, view_id=chosen_view,
                )
                await db.flush()
            if snap.kind != "image" or not snap.storage_key:
                raise ValueError("Motion block resources must be fixed images or captured webpage views.")
            ctype = (snap.meta or {}).get("content_type") or (
                "image/jpeg" if snap.storage_key.lower().endswith((".jpg", ".jpeg"))
                else "image/webp" if snap.storage_key.lower().endswith(".webp")
                else "image/png"
            )
            if ctype not in ext_map:
                ctype = "image/png"
            resolved_resources.append({
                "path": f"media/img_{idx}{ext_map[ctype]}",
                "snapshot_id": str(snap.id),
                "snapshot_digest": snap.digest,
                "content_type": ctype,
            })
        scene = next((s for s in content.scenes if s.range.start <= start and end <= s.range.end), None)
        ops = motion_block_ops(
            content,
            block_id=args.block_id,
            props=props,
            resources=resolved_resources,
            clip_id=f"clp_mg_{identity.hex}",
            object_id=f"obj_mg_{identity.hex}",
            scene_id=scene.scene_id if scene else None,
            start=start,
            end=end,
        )
    elif isinstance(args, SetCompositionStyleArgs):
        from app.editing.revisions import set_composition_style_ops

        ops, summary = set_composition_style_ops(
            content,
            preset_id=args.preset_id,
            accent_color=args.accent_color,
            backdrop_style=args.backdrop_style,
            theme=args.theme,
            override_block_styles=args.override_block_styles,
            update_captions=args.update_captions,
            update_transitions=args.update_transitions,
        )
        if not ops:
            raise ValueError("The composition already uses this exact visual style.")
        extra["style_summary"] = summary
        extra["style"] = summary["style"]
    elif isinstance(args, InsertTextArgs):
        from app.editing.revisions import insert_aligned_captions_ops, insert_text_ops

        if args.from_audio_clip_id is not None:
            audio_target = clips.get(args.from_audio_clip_id)
            if audio_target is None:
                raise ValueError(f"Audio clip {args.from_audio_clip_id!r} does not exist in this version.")
            cues = await _resolve_aligned_caption_cues(db, project, content, audio_target)
            ops, summary = insert_aligned_captions_ops(
                content,
                audio_clip=audio_target,
                cues=cues,
                id_prefix=identity.hex[:10],
                position=args.position,
                preset_id=args.preset_id,
                font_size=args.font_size,
                color=args.color,
                highlight_color=args.highlight_color,
                background=args.background,
                background_mode=args.background_mode,
                background_opacity=args.background_opacity,
                align=args.align,
                secondary_line_scale=args.secondary_line_scale,
            )
            extra["text_summary"] = summary
        else:
            assert args.text is not None and args.start_seconds is not None and args.end_seconds is not None
            start = _ticks(args.start_seconds, rate)
            end = _ticks(args.end_seconds, rate)
            duration = timeline_duration(content)
            if duration > 0 and not (start < end <= duration):
                raise ValueError("The text window must fit inside the composition's current duration.")
            scene = next(
                (s for s in content.scenes if s.range.start <= start and end <= s.range.end), None
            )
            ops, summary = insert_text_ops(
                content,
                text=args.text,
                start=start,
                end=end,
                clip_id=f"clp_txt_{identity.hex[:12]}",
                object_id=f"obj_txt_{identity.hex[:12]}",
                scene_id=scene.scene_id if scene else None,
                role=args.role,
                position=args.position,
                preset_id=args.preset_id,
                font_size=args.font_size,
                color=args.color,
                highlight_color=args.highlight_color,
                background=args.background,
                background_mode=args.background_mode,
                background_opacity=args.background_opacity,
                align=args.align,
                secondary_line_scale=args.secondary_line_scale,
            )
            extra["text_summary"] = summary
    elif isinstance(args, EditTextArgs):
        from app.editing.revisions import edit_text_ops

        ops, summary = edit_text_ops(
            content,
            scope=args.scope,
            clip_id=args.clip_id,
            track_id=args.track_id,
            text=args.text,
            keep_derived=args.keep_derived,
            preset_id=args.preset_id,
            color=args.color,
            highlight_color=args.highlight_color,
            font_size=args.font_size,
            background=args.background,
            clear_background=args.clear_background,
            background_mode=args.background_mode,
            background_opacity=args.background_opacity,
            align=args.align,
            secondary_line_scale=args.secondary_line_scale,
            position=args.position,
        )
        if not ops:
            raise ValueError("The target text already has these exact values.")
        extra["text_summary"] = summary
    elif isinstance(args, UpdateMotionBlockArgs):
        target = clips.get(args.clip_id)
        if target is None or not isinstance(target.object, MotionBlockObject):
            raise ValueError("Select an existing motion_block clip to update.")
        merged_props = {**target.object.props, **args.props_patch}
        updated_obj = MotionBlockObject.model_validate({
            **target.object.model_dump(mode="json"),
            "props": merged_props,
        })
        if updated_obj.props == target.object.props:
            raise ValueError("The motion block already has these prop values.")
        extra["props_before"] = target.object.props
        extra["props_after"] = updated_obj.props
        op = UpdateClip(op="update_clip", clip_id=target.clip_id, object=updated_obj)
    elif isinstance(args, ObjectArgs):
        target = next((clip for _, clip in entries if clip.object.object_id == args.id), None)
        if target is None or not getattr(target.object, "transform", None):
            raise ValueError("Select a visual object with an editable transform.")
        prop = "transform.scale" if name == "scale" else "transform.position"
        if any(a.property == prop and a.text_part is None for a in target.animations):
            raise ValueError(
                "Keyframes control this property. Its static transform cannot make this edit."
            )
        updates = {"scale": args.value} if name == "scale" else {"x": args.x, "y": args.y}
        if name == "translate" and isinstance(target.object, MotionBlockObject):
            validate_motion_block_translate(
                target.object,
                x=args.x,
                y=args.y,
                width=float(content.settings.width),
                height=float(content.settings.height),
            )
        transform = target.object.transform.model_copy(update=updates)
        extra["transform_before"] = target.object.transform.model_dump()
        extra["transform_after"] = transform.model_dump()
        if transform == target.object.transform:
            raise ValueError("The object already has this transform.")
        op = UpdateClip(
            op="update_clip",
            clip_id=target.clip_id,
            object=target.object.model_copy(update={"transform": transform}),
        )
    else:
        target = clips.get(args.clip_id)
        if target is None:
            raise ValueError("The selected clip does not exist in this version.")
        if isinstance(args, SetKeyframeArgs):
            animations = list(target.animations)
            animation = next((a for a in animations if a.animation_id == args.animation_id), None)
            if (animation is None or animation.target_object_id != target.object.object_id
                    or animation.text_part is not None
                    or animation.property not in {"transform.scale", "transform.position"}):
                raise ValueError("Select a whole-object scale or position animation from this clip.")
            frames = list(animation.keyframes)
            frame = next((f for f in frames if f.at == args.at), None)
            if frame is None:
                raise ValueError("Select an existing keyframe tick from this animation.")
            if frame.value == args.value:
                raise ValueError("The keyframe already has this value.")
            frames[frames.index(frame)] = frame.model_copy(update={"value": args.value})
            animations[animations.index(animation)] = animation.model_copy(update={"keyframes": frames})
            op = UpdateClip(op="update_clip", clip_id=target.clip_id, animations=animations)
            extra["keyframe"] = {"animation_id": animation.animation_id, "property": animation.property,
                                 "at": frame.at, "before": frame.value, "after": args.value}
            extra["transform_animations"] = _transform_animations(animations)
        elif isinstance(args, ExtendStillArgs):
            if (target.object.kind not in {"text", "image", "shape"} or target.animations
                    or target.linked_group_id or getattr(target.object, "caption", None)
                    or (target.source and target.source.source_range)
                    or target.range.end != timeline_duration(content)):
                raise ValueError("Select an unanimated, unlinked closing still or title at the end of this work.")
            end = target.range.end + _ticks(args.seconds, rate)
            scene = next((s for s in content.scenes if s.scene_id == target.scene_id), None)
            if scene:
                ops.append(UpdateScene(op="update_scene", scene_id=scene.scene_id,
                                       range=TimeRange(start=scene.range.start, end=end)))
            ops.append(UpdateClip(op="update_clip", clip_id=target.clip_id,
                                  range=TimeRange(start=target.range.start, end=end)))
        elif name == "remove_clip":
            from app.editing.revisions import RemoveClipOp, expand_revision_op

            related = resolve_temporal_target(content, EditTarget(kind="clip", id=target.clip_id), action="delete")
            if related.clip_ids != {target.clip_id}:
                raise ValueError("Removing this clip would also remove linked clips or derived captions.")
            ops = expand_revision_op(RemoveClipOp(op="remove_clip", clip_id=target.clip_id), content, facts={})
            remaining_end = max(
                (c.range.end for _, c in entries if c.clip_id != target.clip_id),
                default=0,
            )
            for scene in content.scenes:
                if scene.range.start < remaining_end < scene.range.end:
                    ops.append(UpdateScene(
                        op="update_scene",
                        scene_id=scene.scene_id,
                        range=TimeRange(start=scene.range.start, end=remaining_end),
                    ))
            extra["removed_clip_id"] = target.clip_id
        elif name == "split_clip":
            cut = target.range.start + _ticks(args.time, rate)
            if not target.range.start < cut < target.range.end:
                raise ValueError("The cut must be strictly inside the selected clip.")
            # A short stable native id is also a useful handle in a later round.
            # Historical requests must reproduce their original store digest.
            right = target.clip_id[:56] + "_right"
            if right in clips or (previous and not prior):
                right = f"clp_{identity.hex}"
            op = SplitClip(
                op="split_clip",
                clip_id=target.clip_id,
                at=cut,
                new_clip_id=right,
                new_object_id=f"obj_{identity.hex}",
            )
            extra = {
                "left_clip_id": target.clip_id,
                "right_clip_id": right,
                "cut_seconds": cut / rate,
            }
        elif name == "trim_clip":
            start = target.range.start + _ticks(args.start or 0, rate)
            end = (
                target.range.start + _ticks(args.end, rate)
                if args.end is not None
                else target.range.end
            )
            if (start, end) == (target.range.start, target.range.end):
                raise ValueError("The requested window already covers this clip.")
            op = TemporalEdit(
                op="temporal_edit",
                action="trim",
                target=EditTarget(kind="clip", id=target.clip_id),
                start=start,
                end=end,
                source_policy="crop_1x",
            )
        else:
            start = _ticks(args.time, rate)
            if start == target.range.start:
                raise ValueError("The clip is already at that start time.")
            op = TemporalEdit(
                op="temporal_edit",
                action="move",
                target=EditTarget(kind="clip", id=target.clip_id),
                start=start,
            )
    if previous is None:
        # The pointer and the immutable version live in the same store transaction.
        # Neither becomes visible unless the version passes validation and CAS.
        active = await db.scalar(
            select(Message.id)
            .where(
                Message.turn_id == opening_id,
                Message.intent["frame"]["status"].astext == "active",
                Message.intent["frame"]["call_id"].astext == call_id,
            )
            .order_by(Message.seq.desc())
            .limit(1)
        )
        marker = {
            "request": str(identity),
            "tool": name,
            "fingerprint": fingerprint,
            "activity_row": str(active) if active else None,
        }
        opening.intent = {**(opening.intent or {}), "editor_commits": [*commits, marker]}
    _, saved, replayed = await apply_composition_edits(
        db,
        owner_id=project.user_id,
        composition_id=composition.id,
        base_version_id=version.id,
        base_digest=version.content_digest,
        request_id=str(identity),
        skill_provenance=version.skill_provenance,
        ops=ops or [op],
    )
    saved_content = content_of(saved)
    saved_clips = [c for t in saved_content.timeline.tracks for c in t.clips if c != clips.get(c.clip_id)]
    origins = await _load_snapshot_origins(db, saved_clips)
    changed = [
        _clip_facts(t, c, saved_content, origins)
        for t in saved_content.timeline.tracks
        for c in t.clips
        if c != clips.get(c.clip_id)
    ]

    return {
        "composition_id": str(composition.id),
        "base_version_id": str(version.id),
        "version_id": str(saved.id),
        "version": saved.version,
        "content_digest": saved.content_digest,
        **extra,
        "target_before_seconds": [target.range.start / rate, target.range.end / rate] if target else None,
        "replayed": replayed,
        "changed_clips": changed,
        "added_clips": [c["clip_id"] for c in changed if c["clip_id"] not in clips],
    }


def project_editor_reply(text, labels, user_text):
    if not text or not labels:
        return text
    zh = any("\u4e00" <= c <= "\u9fff" for c in user_text)
    pattern = (
        r"(?<![\w-])`?("
        + "|".join(re.escape(key) for key in sorted(labels, key=len, reverse=True))
        + r")`?(?![\w-])"
    )
    return re.sub(pattern, lambda m: labels[m[1]][0 if zh else 1], text, flags=re.ASCII)


def _remember_labels(turn, facts, version_id, digest, number):
    labels = turn.__dict__.setdefault("_editor_labels", {})
    for identity in (str(version_id), digest):
        for token in (identity, identity[:8], identity[:12]):
            labels[token] = (f"第 {number} 版", f"version {number}")
    for item in facts:
        window = f"{item['start_seconds']:g}–{item['end_seconds']:g}"
        labels[item["clip_id"]] = (window + " 秒的片段", "the " + window + " s clip")
        labels[item["object_id"]] = (window + " 秒的对象", "the object at " + window + " s")


async def execute_editor(turn, name, args):
    base = getattr(turn, "_video_base_ref", None)
    exported = getattr(turn, "_editor_export", None) or {}
    if name == "deliver_video" and exported.get("output_id") == str(args.output_id):
        # This receipt belongs to the original opening even if another edit advanced the head.
        base = {k: exported[k] for k in ("composition_id", "composition_version_id", "content_digest")}
    elif name == "deliver_video":
        pin = getattr(turn, "_editor_output_pin", None) or {}
        review = getattr(turn, "_video_review_report", None) or {}
        if (pin.get("output_id") == str(args.output_id) == review.get("output_id")
                and pin.get("output_version_id") == review.get("composition_version_id")):
            base = {k: review[k] for k in ("composition_id", "composition_version_id", "content_digest")}
    if name == "instantiate_skill_blueprint":
        from app.skills.blueprint import instantiate_skill_blueprint

        if not turn.project or not turn.turn_id or not current_call_id():
            return ToolObservation("A project and persisted opening are required.", ok=False)
        try:
            result = await instantiate_skill_blueprint(
                turn=turn, args=args, call_id=current_call_id()
            )
            return ToolObservation(
                json.dumps(result),
                version_saved=True,
                valid_for_key=f"composition:{result['version_id']}:{result['content_digest']}",
            )
        except ValueError as exc:
            return ToolObservation(str(exc), ok=False, user_error=str(exc))
    if name == "create_video":
        from app.chat.editor_create import create_video
        from app.chat.editor_recovery import editor_lock_key

        if not turn.project or not turn.turn_id or not current_call_id():
            return ToolObservation("A project and persisted opening are required.", ok=False)
        await turn.db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id))))
        async with AsyncSessionLocal() as db:
            try:
                result = await create_video(db, turn, args)
                return ToolObservation(json.dumps(result), version_saved=True, valid_for_key=f"composition:{result['version_id']}:{result['content_digest']}")
            except ValueError as exc:
                return ToolObservation(str(exc), ok=False, user_error=str(exc))
    if not base and turn.project is not None and name == "generate_sfx":
        from app.chat.editor_media import execute_generate_sfx

        try:
            return await execute_generate_sfx(turn, args, None, None)
        except (ValueError, PermissionError) as exc:
            return ToolObservation(str(exc), ok=False, user_error=str(exc))
    if not base and turn.project is not None and name in {"generate_music", "generate_voice", "generate_image"}:
        from app.chat.editor_media import generate_media

        try:
            return await generate_media(turn, name, args, None, None)
        except (ValueError, PermissionError) as exc:
            return ToolObservation(str(exc), ok=False)
    if not base or turn.project is None:
        return ToolObservation(
            "Select one accessible, current saved work before editing.", ok=False
        )
    async with AsyncSessionLocal() as db:
        try:
            if name in WRITE_TOOLS:
                group = current_group_id()
                if (group and isinstance(args, (InsertAudioArgs, InsertVisualArgs, BindClipSourceArgs)) and
                        getattr(turn, "_generated_in_response", {}).get(str(args.source_id)) == group):
                    raise ValueError("Use the fixed source returned by generation in the next response.")
                previous_write = getattr(turn, "_batch_commit", None)
                if group and previous_write and previous_write[0] == group:
                    base = previous_write[1]
                    target_id = getattr(args, "clip_id", None) or getattr(args, "id", None)
                    if target_id in previous_write[2]:
                        raise ValueError("Observe the saved split before addressing the new clip or object.")
                if not turn.turn_id or not current_call_id():
                    raise ValueError("A persisted turn and native call identity are required.")
                from app.chat.editor_recovery import editor_lock_key

                await turn.db.execute(
                    select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id)))
                )
                result = await edit_clip(
                    db,
                    name=name,
                    project=turn.project,
                    opening_id=turn.turn_id,
                    conversation_id=turn.conversation_id,
                    call_id=current_call_id(),
                    base=base,
                    args=args,
                    observed_preview=getattr(turn, "_editor_last_preview", None),
                    inspected_version=(base["composition_version_id"] if group and previous_write and previous_write[0] == group
                                       else getattr(turn, "_inspected_version", None)),
                )
                _remember_labels(
                    turn,
                    result["changed_clips"],
                    result["version_id"],
                    result["content_digest"],
                    result["version"],
                )
                recent = getattr(turn, "_editor_recent", {})
                focused = (
                    dict(recent.get("clips", {}))
                    if recent.get("version_id") == result["base_version_id"]
                    else {}
                )
                if name == "remove_clip":
                    focused.pop(result["removed_clip_id"], None)
                for clip in result["changed_clips"]:
                    entry = {
                        k: clip[k]
                        for k in ("clip_id", "object_id", "kind", "start_seconds", "end_seconds")
                    }
                    if clip.get("kind") == "motion_block":
                        entry["block_id"] = clip.get("block_id")
                        entry["props"] = clip.get("props")
                    elif clip.get("kind") == "audio":
                        entry["gain_db"] = clip.get("gain_db")
                        entry["has_gain_automation"] = clip.get("has_gain_automation")
                        if clip.get("source"):
                            entry["source_snapshot_id"] = clip["source"].get("snapshot_id")
                    elif clip.get("kind") == "text":
                        entry["text"] = clip.get("text")
                        entry["style"] = clip.get("style")
                        entry["caption_state"] = clip.get("caption_state")
                        entry["karaoke_active"] = clip.get("karaoke_active")
                    focused[clip["clip_id"]] = entry
                if name == "set_keyframe":
                    focused[args.clip_id]["transform_animations"] = result["transform_animations"]
                applied = (
                    list(recent.get("applied", []))
                    if recent.get("composition_id") == result["composition_id"]
                    else []
                )
                if not any(item["version"] == result["version"] for item in applied):
                    receipt = {
                        "version": result["version"],
                        "tool": name,
                        "arguments": args.model_dump(mode="json", exclude_none=True),
                    }
                    if name in {"split_clip", "trim_clip", "move_clip", "extend_still"}:
                        receipt["target_before_seconds"] = result["target_before_seconds"]
                        receipt["target_after_seconds"] = {
                            c["clip_id"]: [c["start_seconds"], c["end_seconds"]]
                            for c in result["changed_clips"]
                        }
                    if name in {"translate", "scale"}:
                        receipt.update(transform_before=result["transform_before"], transform_after=result["transform_after"])
                    if name == "update_motion_block":
                        receipt.update(
                            clip_id=args.clip_id,
                            props_before=result["props_before"],
                            props_after=result["props_after"],
                        )
                    if name == "edit_audio_clip":
                        g_before = result["gain_db_before"]
                        g_after = result["gain_db_after"]
                        receipt.update(
                            clip_id=args.clip_id,
                            gain_db_before=g_before,
                            gain_db_after=g_after,
                            gain_delta_db=round(g_after - g_before, 2),
                            source_before=result["source_before"],
                            source_after=result["source_after"],
                        )
                        if "audio_gain_keyframes" in result:
                            receipt["audio_gain_keyframes"] = result["audio_gain_keyframes"]
                            receipt["fade_in_seconds"] = result.get("fade_in_seconds")
                            receipt["fade_out_seconds"] = result.get("fade_out_seconds")
                    if name == "set_composition_style":
                        receipt["style_summary"] = result["style_summary"]
                    if name in {"insert_text", "edit_text"}:
                        receipt["text_summary"] = result["text_summary"]
                    if name == "set_transition":
                        receipt["transition"] = result["transition"]
                    if name == "split_clip":
                        receipt["right_clip_id"] = result["right_clip_id"]
                    before = getattr(turn, "_editor_last_preview", None)
                    if before and before["version_id"] == result["base_version_id"]:
                        receipt["previewed_before_edit"] = before["window_seconds"]
                    applied.append(receipt)
                turn._editor_recent = {
                    "composition_id": result["composition_id"],
                    "version_id": result["version_id"],
                    "clips": dict(list(focused.items())[-24:]),
                    "applied": applied,
                }
                if group:
                    new_ids = set(result["added_clips"])
                    new_ids.update(c["object_id"] for c in result["changed_clips"] if c["clip_id"] in new_ids)
                    if previous_write and previous_write[0] == group:
                        new_ids.update(previous_write[2])
                    turn._batch_commit = (group, {**base, "composition_version_id": result["version_id"],
                                                  "content_digest": result["content_digest"]}, new_ids)
                turn._inspected_version = result["version_id"]
                if getattr(turn, "_editor_output_pin", None):
                    turn._editor_output_pin["version_id"] = result["version_id"]
                turn._video_presentation_pending = None
                return ToolObservation(
                    json.dumps(result), version_saved=True,
                    valid_for_key=f"composition:{result['version_id']}:{result['content_digest']}",
                )
            composition, version = await get_video_version(
                db,
                owner_id=turn.project.user_id,
                version_id=UUID(base["composition_version_id"]),
            )
            if (
                composition.origin_project_id != turn.project.id
                or version.content_digest != base["content_digest"]
                or str(composition.id) != base["composition_id"]
            ):
                raise ValueError("This version is outside the selected project.")
            version_key = f"composition:{version.id}:{version.content_digest}"
            if name in {"inspect_timeline", "inspect_clip"}:
                turn._inspected_version = str(version.id)
                content = content_of(version)
                clips = sorted(
                    ((track, c) for track in content.timeline.tracks for c in track.clips),
                    key=lambda pair: (pair[1].range.start, pair[0].order, pair[1].clip_id),
                )
                if name == "inspect_clip":
                    target = next((item for item in clips if item[1].clip_id == args.clip_id), None)
                    if target is None:
                        raise ValueError("The selected clip does not exist in this version.")
                    neighbors = [item for item in clips if item[0].track_id == target[0].track_id]
                    index = neighbors.index(target)
                    page = neighbors[max(0, index - 1) : index + 2]
                    scope = {
                        "target_clip_id": args.clip_id,
                        "transform_animations": _transform_animations(target[1].animations),
                    }
                else:
                    page = clips[args.offset : args.offset + 24]
                    next_offset = args.offset + len(page)
                    scope = {
                        "offset": args.offset,
                        "next_offset": next_offset if next_offset < len(clips) else None,
                        "transitions": [
                            {
                                "transition_id": t.transition_id,
                                "from_clip_id": t.from_clip_id,
                                "to_clip_id": t.to_clip_id,
                                "kind": t.kind,
                                "duration_seconds": t.duration / content.settings.timebase,
                            }
                            for t in content.timeline.transitions
                        ],
                    }
                origins = await _load_snapshot_origins(db, [clip for _, clip in page])
                facts = [_clip_facts(track, clip, content, origins) for track, clip in page]
                _remember_labels(turn, facts, version.id, version.content_digest, version.version)
                return ToolObservation(
                    json.dumps(
                        {
                            **base,
                            "version_id": str(version.id),
                            "count": len(clips),
                            **scope,
                            "canvas_px": [content.settings.width, content.settings.height],
                            "background": content.settings.background,
                            "composition_style": _composition_style_summary(content),
                            "timebase": content.settings.timebase,
                            "source_timebase": SOURCE_TIMEBASE,
                            "clips": facts,
                        }
                    ),
                    valid_for_key=version_key,
                )
            if name == "save_composition_as_skill":
                from app.chat.editor_recovery import editor_lock_key
                from app.skills.blueprint import save_composition_as_skill

                if not turn.turn_id:
                    raise ValueError("A persisted turn is required.")
                await turn.db.execute(
                    select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id)))
                )
                result = await save_composition_as_skill(
                    db,
                    owner_id=turn.project.user_id,
                    project_id=turn.project.id,
                    composition_id=composition.id,
                    version_id=version.id,
                    name=args.name,
                    description=args.description,
                    opening_id=turn.turn_id,
                    conversation_id=turn.conversation_id,
                    lock_on_session=False,
                )
                return ToolObservation(json.dumps(result), valid_for_key=version_key)
            if name == "deliver_video":
                from app.chat.editor_media import deliver_video

                return await deliver_video(db, turn, args.output_id, base)
            if name == "generate_sfx":
                from app.chat.editor_media import execute_generate_sfx

                await db.close()
                return await execute_generate_sfx(turn, args, composition, version)
            if name in {"export_video", "generate_music", "generate_voice", "generate_image"}:
                from app.chat.editor_media import generate_media

                # Submission rechecks ownership and head in its own transaction.
                await db.close()
                return await generate_media(turn, name, args, composition, version)
            if name != "preview_range":
                raise ValueError("Unknown editor operation.")
            from app.editing.service import storyboard_block, video_version_read
            from app.tools.video.preview import prepare_saved_video_scrub, saved_preview_media, source_framing

            read = await video_version_read(
                db, owner_id=turn.project.user_id, version_id=version.id
            )
            read = await prepare_saved_video_scrub(
                db, read, owner_id=turn.project.user_id, target=args
            )
            preview = read["video_preview"]
            if preview["status"] != "ready":
                reason = preview.get("reason") or preview["status"]
                if preview.get("detail"):
                    reason += f": {preview['detail']}"
                raise ValueError(reason)
            # The renderer consumes the prepared immutable specification.
            await db.close()
            media, evidence = await saved_preview_media(preview, version.id)
            covered = set(preview["scope"]["clip_ids"])
            sources = {
                (str(clip.source.snapshot_id), clip.source.snapshot_digest)
                for track in content_of(version).timeline.tracks for clip in track.clips
                if clip.clip_id in covered and clip.source
            }
            evidence.update(base, sources=[
                {"snapshot_id": sid, "digest": digest} for sid, digest in sorted(sources)
            ])
            if not media:
                raise ValueError("The configured model cannot receive visual evidence for this window.")
            previous = getattr(turn, "_editor_last_preview", {}) or {}
            windows = list(previous.get("windows", [])) if previous.get("version_id") == str(version.id) else []
            window = preview["scope"]["source_range_seconds"]
            if window not in windows:
                windows.append(window)
            # Keep one decoded contact sheet across a version change, only for
            # the same work, observation window and actual sample times.
            current_sheet = next((item for item in media if item.type == "image"), None)
            prior_sheet = getattr(turn, "_editor_comparison_sheet", None)
            sample_key = (str(composition.id), window, evidence["sample_seconds"])
            if current_sheet is not None:
                if prior_sheet and prior_sheet[0] == sample_key and prior_sheet[1] != version.id:
                    historical = prior_sheet[2].model_copy(update={
                        "caption": f"Earlier observation, version {prior_sheet[1]}. Compare the matching times with the current frames."
                    })
                    evidence["comparison"] = {
                        "earlier_version_id": str(prior_sheet[1]), "earlier_mp4_sha256": prior_sheet[3],
                        "current_version_id": str(version.id), "sample_seconds": evidence["sample_seconds"],
                    }
                    media = (historical, *media)
                turn._editor_comparison_sheet = (sample_key, version.id, current_sheet, evidence["mp4_sha256"])
            if current_sheet is not None and evidence.get("sample_seconds"):
                framing, source_frame = await source_framing(
                    db, turn.project.user_id, content_of(version), covered, evidence["sample_seconds"][0]
                )
                if framing:
                    evidence["source_framing"] = framing
                if source_frame:
                    media = (*media, source_frame)
            evidence["model_media"] = [item.type for item in media]
            turn._editor_last_preview = {
                **base, "version_id": str(version.id), "mp4_sha256": evidence["mp4_sha256"],
                "decision": current_group_id(), "window_seconds": window, "windows": windows,
                "sample_seconds": evidence["sample_seconds"],
                "model_media": evidence["model_media"],
                "audio_available_to_model": evidence["audio_available_to_model"],
            }
            block = storyboard_block(read)
            blocks = turn.__dict__.setdefault("_editor_preview_blocks", [])
            if block not in blocks:
                blocks.append(block)
            turn._video_presentation_pending = read
            evidence["coverage"] = (
                "Exact requested window of this version, across all tracks. Reuse for this window until the work changes."
            )
            return ToolObservation(json.dumps(evidence), images=media, valid_for_key=version_key)
        except StaleBase:
            return ToolObservation(
                f"Version conflict. This call checked base {base['composition_version_id']}, "
                "which is no longer current. This call made no change. "
                "If the user asked to stop on conflict, report it now and do not retry. "
                "Otherwise inspect the new version before choosing another edit.",
                ok=False, fold_after_delivery=True,
                user_error="Another edit changed the saved work. This change was not applied.",
            )
        except ValueError as exc:
            return ToolObservation(str(exc), ok=False, fold_after_delivery=True, user_error=str(exc))
