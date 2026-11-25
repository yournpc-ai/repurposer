"""CompositionVersion <-> SkillVersion (slot_blueprint_v1) extraction and instantiation.

Zero new SQL tables: persists directly into the existing owner-scoped
`UserSkill` + immutable `SkillVersion` tables via `import_external_skill`,
storing standard `SKILL.md` in `instructions` and a pure-declarative,
privacy-stripped `references/blueprint.json`.

Transaction guardrail: instantiation synthesizes all SFX snapshots OUTSIDE
`apply_composition_edits` (no HTTP calls under DB write locks), adapts act
durations to measured narration + breathing pauses, resolves SFX offsets
relative to adapted act/cut boundaries, and commits atomically via the single
Composition write gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.catalog import (
    MOTION_BLOCK_CATALOG,
    SOUND_RECIPE_CATALOG,
    MotionBlockId,
    SoundRecipeId,
)
from app.editing.revisions import build_audio_gain_animation
from app.editing.schemas import (
    Animation,
    AudioObject,
    Clip,
    ClipSource,
    CompositionContent,
    CueSecond,
    LayoutBox,
    MotionBlockObject,
    ProductShowcaseProps,
    RemotionResource,
    Scene,
    SourceBinding,
    TimeRange,
    Timeline,
    Track,
    Transition,
    TransitionKind,
    VersionSettings,
)
from app.editing.store import (
    RequestMismatch,
    apply_composition_edits,
    content_of,
    get_video_version,
)
from app.editing.styles import (
    INHERITABLE_BLOCK_STYLE_KEYS,
    CompositionStyle,
    StylePresetId,
    resolve_style_tokens,
)
from app.editing.timing import (
    SOURCE_TIMEBASE,
    frames_to_ticks,
    output_ticks_to_source_ticks,
    seconds_to_ticks,
    source_ticks_to_output_ticks,
    ticks_to_frames,
)
from app.models.schemas import canonical_json_hash
from app.models.tables import (
    Asset,
    Composition,
    CompositionVersion,
    Message,
    Project,
    SourceSnapshot,
)
from app.skills.external import (
    SkillCapabilityReport,
    SkillDraft,
    SkillInputDeclaration,
    SkillPolicy,
    SkillSource,
)
from app.skills.store import get_skill_version, import_external_skill

BLUEPRINT_PATH = "references/blueprint.json"
BLUEPRINT_CAPABILITY = "slot_blueprint_v1"

# Props that carry brand/project-specific content (stripped during extraction).
_CONTENT_PROP_KEYS: dict[str, set[str]] = {
    "kinetic_beat": {"headline", "highlight_phrase", "prefix", "words", "left_text", "right_text", "badge_text", "items"},
    "ui_montage": {"headline", "badge"},
    "code_terminal": {"title", "lines", "prompt_prefix"},
    "logo_wall": {"eyebrow", "headline", "items"},
    "chat_demo": {"messages", "title", "work_steps", "result_card"},
    "device_mockup": {"eyebrow", "headline", "caption"},
    "flow_diagram": {"nodes", "eyebrow", "title"},
    "split_compare": {"left_heading", "left_items", "right_heading", "right_items", "eyebrow", "title"},
    "step_timeline": {"steps", "eyebrow", "title"},
    "bento_features": {"cards", "eyebrow", "title"},
    "data_chart": {"title", "points", "eyebrow", "subtitle", "unit"},
    "quote_proof": {"quote", "author", "role_or_source", "verification_badge", "highlight_phrase"},
    "statement_hook": {"eyebrow", "headline", "highlight_phrase", "subheadline"},
    "kinetic_title": {"eyebrow", "headline", "subheadline"},
    "product_showcase": {"url_bar", "badge", "callout", "callout_steps", "cursor"},
    "metric_grid": {"eyebrow", "title", "items"},
    "closing_cta": {"brand_name", "tagline", "cta_label", "url_text"},
}

_NARRATIVE_STYLE = {"theme", "backdrop_style", "accent_color", "show_backdrop"}

_STYLE_PROP_KEYS: dict[str, set[str]] = {
    "kinetic_beat": _NARRATIVE_STYLE | {"mode", "rows", "badge_icon", "scale_emphasis", "entrance_duration_s"},
    "ui_montage": _NARRATIVE_STYLE | {"layout_mode", "cut_interval_s", "entrance_duration_s"},
    "code_terminal": _NARRATIVE_STYLE | {"mode", "highlight_line"},
    "logo_wall": _NARRATIVE_STYLE | {"mode"},
    "chat_demo": _NARRATIVE_STYLE,
    "device_mockup": _NARRATIVE_STYLE | {"layout", "reveal_at_s"},
    "flow_diagram": _NARRATIVE_STYLE,
    "split_compare": _NARRATIVE_STYLE | {"dim_left"},
    "step_timeline": _NARRATIVE_STYLE | {"active_step"},
    "bento_features": _NARRATIVE_STYLE | {"highlight_index"},
    "data_chart": _NARRATIVE_STYLE | {"highlight_index", "chart_type"},
    "quote_proof": _NARRATIVE_STYLE | {"highlight_at_s"},
    "statement_hook": {"backdrop_style", "highlight_at_s", "theme", "layout_variant", "accent_color", "entrance_duration_s", "exit_duration_s", "show_backdrop"},
    "kinetic_title": {"align", "position", "entrance_duration_s", "exit_duration_s", "accent_color", "text_color", "surface_style"},
    "product_showcase": {"camera_preset", "backdrop_style", "scroll_from_y", "scroll_to_y", "theme", "chrome_mode", "camera_motion", "entrance_duration_s", "zoom_scale", "focus_x", "focus_y", "accent_color", "show_backdrop"},
    "metric_grid": {"backdrop_style", "columns", "theme", "accent_color", "stagger_s", "count_up", "show_backdrop"},
    "closing_cta": {"backdrop_style", "theme", "accent_color", "entrance_duration_s", "logo_surface", "show_backdrop"},
}


# Ordered pairs of (content slot, cue field); only the seconds cross projects.
_ITEM_CUES = {
    "chat_demo": (("messages", "at_s"), ("work_steps", "at_s")),
    "flow_diagram": (("nodes", "reveal_at_s"),),
    "split_compare": (("left_items", "reveal_at_s"), ("right_items", "reveal_at_s")),
    "step_timeline": (("steps", "reveal_at_s"),),
    "bento_features": (("cards", "reveal_at_s"),),
    "data_chart": (("points", "reveal_at_s"),),
}


class BlueprintTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: TransitionKind = "crossfade"
    duration_s: float = Field(gt=0, allow_inf_nan=False)


class BlueprintOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overlay_id: str
    block_id: Literal["kinetic_title"] = "kinetic_title"
    block_version: Literal[1] = 1
    rel_start_s: float = Field(ge=0.0)
    rel_end_s: float = Field(gt=0.0)
    style_defaults: dict[str, Any] = Field(default_factory=dict)
    required_slots: list[str] = Field(default_factory=lambda: ["headline"])


class BlueprintAct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    act_id: str
    block_id: MotionBlockId
    block_version: Literal[1] = 1
    role: str
    target_duration_s: float = Field(ge=0.2, le=60.0)
    min_duration_s: float = Field(ge=0.2, le=30.0)
    style_defaults: dict[str, Any] = Field(default_factory=dict)
    required_slots: list[str] = Field(default_factory=list)
    optional_slots: list[str] = Field(default_factory=list)
    resource_count: int | None = Field(default=None, ge=1, le=16, exclude_if=lambda v: v is None)
    has_narration: bool = False
    transition_after: BlueprintTransition | None = None
    overlays: list[BlueprintOverlay] = Field(default_factory=list)

    # Timing survives a remake. Only the replacement slot supplies geometry or copy.
    cursor_click_at_s: CueSecond | None = None
    callout_windows_s: list[tuple[CueSecond, CueSecond]] = Field(default_factory=list, max_length=4)
    metric_reveals_s: list[CueSecond | None] = Field(default_factory=list, max_length=4)

    item_reveals_s: list[CueSecond | None] = Field(default_factory=list, max_length=8, exclude_if=lambda x: not x)
    secondary_reveals_s: list[CueSecond | None] = Field(default_factory=list, max_length=4, exclude_if=lambda x: not x)

    def bind_props(self, replacement: dict[str, Any]) -> dict:
        props = {**self.style_defaults, **replacement}
        if isinstance(props.get("cursor"), dict) and self.cursor_click_at_s is not None:
            props["cursor"] = {"click_at_s": self.cursor_click_at_s, **props["cursor"]}
        if isinstance(props.get("callout_steps"), list):
            steps = list(props["callout_steps"])
            for i, (step, (start, end)) in enumerate(zip(steps, self.callout_windows_s)):
                if isinstance(step, dict):
                    steps[i] = {"start_s": start, "end_s": end, **step}
            props["callout_steps"] = steps
        if isinstance(props.get("items"), list):
            items = list(props["items"])
            for i, (item, reveal) in enumerate(zip(items, self.metric_reveals_s)):
                if isinstance(item, dict) and reveal is not None:
                    items[i] = {"reveal_at_s": reveal, **item}
            props["items"] = items
        groups = _ITEM_CUES.get(self.block_id, ())
        for (slot, key), times in zip(groups, (self.item_reveals_s, self.secondary_reveals_s)):
            if not times or not isinstance(props.get(slot), list):
                continue
            items = list(props[slot])
            for i, (item, time) in enumerate(zip(items, times)):
                if time is not None and isinstance(item, dict):
                    items[i] = {key: time, **item}
            props[slot] = items
        return props


class BlueprintAudioProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    breathing_s: float = Field(default=0.5, ge=0.2, le=1.5)
    narration_gain_db: float = Field(default=0.0, ge=-24.0, le=12.0)
    has_bgm: bool = False
    bgm_gain_db: float = Field(default=-25.0, ge=-60.0, le=0.0)
    bgm_fade_in_s: float | None = Field(default=None, ge=0.0, le=10.0)
    bgm_fade_out_s: float | None = Field(default=None, ge=0.0, le=10.0)


class BlueprintSfxCue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cue_id: str
    recipe_id: SoundRecipeId
    params: dict[str, int | float] = Field(default_factory=dict)
    seed: int = Field(default=1248, ge=0, le=0xFFFFFFFF)
    gain_db: float = Field(default=-13.0, ge=-60.0, le=6.0)
    act_index: int = Field(ge=0)
    anchor: Literal["act_start", "act_end", "cut_after"] = "cut_after"
    offset_s: float = Field(default=0.0, ge=-2.0, le=2.0)


class SkillBlueprintV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    source_composition_uri: str | None = None
    canvas: dict[str, Any]
    style: CompositionStyle | None = Field(default=None, exclude_if=lambda v: v is None)
    acts: list[BlueprintAct] = Field(min_length=1, max_length=48)
    audio_profile: BlueprintAudioProfile = Field(default_factory=BlueprintAudioProfile)
    sfx_cues: list[BlueprintSfxCue] = Field(default_factory=list, max_length=96)


def normalize_skill_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", raw.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:64].strip("-")
    if not slug or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise ValueError("Skill name must contain letters or digits (kebab-case slug).")
    return slug


def _extract_bgm_fades(clip: Clip, timebase: int) -> tuple[float | None, float | None]:
    gain_anim = next((a for a in clip.animations if a.property == "audio.gain"), None)
    if gain_anim is None or len(gain_anim.keyframes) < 2:
        return None, None
    kfs = sorted(gain_anim.keyframes, key=lambda k: k.at)
    dur = clip.range.duration
    fade_in: float | None = None
    fade_out: float | None = None
    if float(kfs[0].value) <= 0.05 and float(kfs[1].value) >= 0.9:
        fi = round((kfs[1].at - kfs[0].at) / timebase, 2)
        if fi > 0:
            fade_in = fi
    if float(kfs[-1].value) <= 0.05 and float(kfs[-2].value) >= 0.9:
        fo = round((dur - kfs[-2].at) / timebase, 2)
        if fo > 0:
            fade_out = fo
    return fade_in, fade_out


def music_clips_for_window(
    *, settings: VersionSettings, start: int, end: int, source_id: UUID, digest: str,
    source_ticks: int, id_stem: str, gain_db: float,
    fade_in_seconds: float | None, fade_out_seconds: float | None,
) -> list[Clip]:
    rate = settings.timebase
    loop_ticks = source_ticks_to_output_ticks(source_ticks, rate)
    frame_clock = (rate, settings.fps.num, settings.fps.den)
    frame_ticks = frames_to_ticks(1, *frame_clock)
    if loop_ticks < max(1, frame_ticks):
        raise ValueError("Music duration must span at least one output frame.")
    cuts = [*range(start, end, loop_ticks), end]
    # Leave the tail a visible frame if an almost-exact multiple collapses its last cut.
    if len(cuts) > 2 and ticks_to_frames(cuts[-2], *frame_clock) == ticks_to_frames(end, *frame_clock):
        cuts[-2] = max(end - loop_ticks, cuts[-2] - frame_ticks)
    clips = []
    for index, (left, right) in enumerate(zip(cuts, cuts[1:])):
        if ticks_to_frames(left, *frame_clock) >= ticks_to_frames(right, *frame_clock):
            raise ValueError("Each music slice must span an output frame.")
        used_src = source_ticks if right - left == loop_ticks else output_ticks_to_source_ticks(right - left, rate)
        stem = id_stem if index == 0 else f"{id_stem}_{index + 1}"
        gain = build_audio_gain_animation(
            object_id=f"obj_{stem}", clip_start_ticks=left, clip_end_ticks=right,
            timebase=rate, fps_num=settings.fps.num, fps_den=settings.fps.den,
            fade_in_seconds=fade_in_seconds if left == start else None,
            fade_out_seconds=fade_out_seconds if right == end else None,
        )
        clips.append(Clip(
            clip_id=f"clp_{stem}", range=TimeRange(start=left, end=right),
            source=ClipSource(snapshot_id=source_id, snapshot_digest=digest,
                              source_range=TimeRange(start=0, end=used_src)),
            object=AudioObject(kind="audio", object_id=f"obj_{stem}", gain_db=gain_db),
            animations=[Animation.model_validate(gain)] if gain else [],
        ))
    return clips


def _render_skill_md(name: str, description: str, bp: SkillBlueprintV1) -> str:
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        "---",
        "",
        f"# {name}",
        "",
        description,
        "",
        "## Reusable Multi-Act Structure (`references/blueprint.json`)",
        "",
        "This reusable Skill preserves the visual cadence, motion blocks, transitions, "
        "BGM envelope, and sound-effect cues of the saved master composition while keeping "
        "all copy, metrics, screenshots, language, and narration as replaceable slots.",
        "",
        "| Act | `act_id` | Block | Role | Baseline | Suggested narration | Required Slots | Optional Slots |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for idx, act in enumerate(bp.acts, 1):
        req = ", ".join(act.required_slots) or "—"
        if act.resource_count:
            req += f" ({act.resource_count} ordered images)"
        opt_parts = list(act.optional_slots)
        if act.overlays:
            opt_parts.append("overlay_props (kinetic_title pill_caption headline)")
        opt = ", ".join(opt_parts) or "—"
        overlay_note = f" (+{len(act.overlays)} overlay)" if act.overlays else ""
        lines.append(
            f"| {idx} | `{act.act_id}` | `{act.block_id}`{overlay_note} | {act.role} | "
            f"{act.target_duration_s:g}s | Keep dialogue within {1.5 * act.target_duration_s:g}s | {req} | {opt} |"
        )
    lines.extend([
        "",
        *(
            [
                "## Visual Style Profile",
                f"- Default style preset: `{bp.style.preset_id}`"
                + (f" (accent `{bp.style.accent_color}`)" if bp.style.accent_color else "")
                + " — orthogonal to act structure; override via `style_preset` / `accent_color` during instantiation.",
                "",
            ]
            if bp.style is not None
            else []
        ),
        "## Audio & Sound Design Profile",
        f"- Narration pacing: adapt each act duration to measured narration + `{bp.audio_profile.breathing_s:g}s` breathing room.",
        f"- BGM: {'included' if bp.audio_profile.has_bgm else 'optional'} at `{bp.audio_profile.bgm_gain_db:g} dB`"
        + (
            f" (fade-in `{bp.audio_profile.bgm_fade_in_s or 0:g}s`, fade-out `{bp.audio_profile.bgm_fade_out_s or 0:g}s`)"
            if bp.audio_profile.bgm_fade_in_s or bp.audio_profile.bgm_fade_out_s
            else ""
        )
        + ".",
        f"- SFX cues: {len(bp.sfx_cues)} anchored sound recipes (automatically synthesized outside write locks and aligned to the adapted act/cut boundaries).",
        "",
        "## How to Instantiate (Remake Workflow)",
        "1. Gather fresh target materials (`capture_web` / `prepare_video_materials` for screenshots, `search_music` + `prepare_video_materials` for BGM if desired).",
        "2. Keep silent beats silent. When the brief calls for narration, prepare per-act voice in the requested language.",
        "3. Call `instantiate_skill_blueprint` once with `skill_version_id` from `skill_reference.skill_version_id` and the ordered `acts` slot values (`act_id`, `props`, `resources`/`view_id`, `narration_snapshot_id`, optional `overlay_props`) plus optional `bgm_snapshot_id`. Replace ALL headlines, copy, metrics, URLs, and voiceovers with the new target brief.",
        "For each visual cue in the blueprint, bind a fresh target from the chosen capture. Match callout steps and timed list items in order to inherit their timing.",
        "4. The instantiated work is a normal editable `CompositionVersion` — preview and continue refining any individual act, audio clip, or transition in Chat.",
    ])
    return "\n".join(lines) + "\n"


def extract_skill_draft_from_composition(
    *,
    composition_id: UUID,
    version_number: int,
    content: CompositionContent,
    snapshot_origins: dict[UUID, dict[str, Any]],
    name: str,
    description: str,
) -> tuple[SkillDraft, SkillBlueprintV1]:
    """Deterministically extract a privacy-stripped slot blueprint & SKILL.md."""
    slug = normalize_skill_slug(name)
    desc = description.strip()
    if not desc:
        raise ValueError("Provide a short description for the saved Skill.")

    tb = content.settings.timebase
    fps = content.settings.fps

    def frame_time(ticks: int) -> float:
        return ticks_to_frames(ticks, tb, fps.num, fps.den) * fps.den / fps.num

    main_blocks = sorted(
        (
            clip
            for track in content.timeline.tracks
            if track.kind == "visual" and track.role == "main"
            for clip in track.clips
            if isinstance(clip.object, MotionBlockObject)
        ),
        key=lambda c: c.range.start,
    )
    if not main_blocks:
        raise ValueError(
            "This composition has no main-track MotionBlockObject acts to extract as a slot blueprint."
        )

    title_overlays = sorted(
        (
            clip
            for track in content.timeline.tracks
            if track.kind == "visual" and track.role == "title"
            for clip in track.clips
            if isinstance(clip.object, MotionBlockObject) and clip.object.block_id == "kinetic_title"
        ),
        key=lambda c: c.range.start,
    )
    dialogue_clips = [
        clip
        for track in content.timeline.tracks
        if track.kind == "audio" and track.role == "dialogue"
        for clip in track.clips
    ]
    music_clips = [
        clip
        for track in content.timeline.tracks
        if track.kind == "audio" and track.role == "music"
        for clip in track.clips
    ]
    effect_clips = [
        clip
        for track in content.timeline.tracks
        if track.kind == "audio" and track.role == "effect"
        for clip in track.clips
    ]
    transitions_by_from = {t.from_clip_id: t for t in content.timeline.transitions}

    role_by_block = {
        "statement_hook": "opener",
        "product_showcase": "showcase",
        "metric_grid": "metrics",
        "closing_cta": "closing",
        "kinetic_title": "title",
    }

    acts: list[BlueprintAct] = []
    act_ranges_s: list[tuple[float, float]] = []
    for idx, clip in enumerate(main_blocks):
        obj = clip.object
        assert isinstance(obj, MotionBlockObject)
        s_s = frame_time(clip.range.start)
        e_s = frame_time(clip.range.end)
        duration_frames = ticks_to_frames(clip.range.end, tb, fps.num, fps.den) - ticks_to_frames(
            clip.range.start, tb, fps.num, fps.den
        )
        dur_s = duration_frames * fps.den / fps.num
        if dur_s < 0.2:
            dur_s = clip.range.duration / tb
        act_ranges_s.append((s_s, e_s))

        cue_lists = [
            [item.get(field) for item in (obj.props.get(slot) or [])]
            for slot, field in _ITEM_CUES.get(obj.block_id, ())
        ]
        allowed_style = _STYLE_PROP_KEYS.get(obj.block_id, set())
        inheritable = set(INHERITABLE_BLOCK_STYLE_KEYS.get(obj.block_id, ()))
        comp_tokens = resolve_style_tokens(content.settings.style) if content.settings.style is not None else None
        style_defaults: dict[str, Any] = {}
        for k, v in obj.props.items():
            if k not in allowed_style:
                continue
            if comp_tokens is not None and k in inheritable:
                # Omit keys that merely mirror the composition-level style so Template x Style stays orthogonal.
                if (
                    (k == "theme" and v == comp_tokens["theme"])
                    or (k == "backdrop_style" and v == comp_tokens["backdrop_style"])
                    or (k == "accent_color" and str(v).upper() == comp_tokens["accent"])
                ):
                    continue
            style_defaults[k] = v
        cat = MOTION_BLOCK_CATALOG[obj.block_id]
        content_keys = _CONTENT_PROP_KEYS.get(obj.block_id, set())
        req_slots = [k for k in cat["required_slots"] if k not in style_defaults]
        opt_slots = [k for k in cat["optional_slots"] if k in content_keys or k.endswith("_resource")]

        if obj.block_id in {"code_terminal","logo_wall"}:
            group = "lines" if obj.block_id == "code_terminal" else "items"
            req_slots = [f"{group}[{i}]" for i in range(len(obj.props[group]))]
            if obj.block_id == "logo_wall":
                for i,item in enumerate(obj.props["items"]):
                    if item.get("resource_index") is not None:
                        req_slots.append(f"items[{i}].image[{item['resource_index']}]")
        if obj.block_id == "kinetic_beat":
            mode = obj.props["mode"]
            if mode in {"typewriter_swap", "slot_flip", "marquee_wall"}:
                group = "items" if mode == "marquee_wall" else "words"
                req_slots = [f"{group}[{i}]" for i in range(len(obj.props[group]))]
            else:
                req_slots = ["left_text", "right_text"] if mode == "inline_badge_split" else ["headline"]
        if obj.block_id in {"kinetic_beat", "ui_montage"}:
            opt_slots = [key for key in opt_slots if key not in req_slots and key not in {"words", "items"} and obj.props.get(key)]

        has_narr = any(
            d.range.start < clip.range.end and clip.range.start < d.range.end
            for d in dialogue_clips
        )

        trn_after = None
        trn = transitions_by_from.get(clip.clip_id)
        if trn is not None and idx + 1 < len(main_blocks) and trn.to_clip_id == main_blocks[idx + 1].clip_id:
            trn_after = BlueprintTransition(kind=trn.kind, duration_s=trn.duration / tb)

        # Anchor overlapping title overlays to this main act
        overlays: list[BlueprintOverlay] = []
        for ov_idx, ov in enumerate(title_overlays):
            if ov.range.start < clip.range.end and clip.range.start < ov.range.end:
                ov_obj = ov.object
                assert isinstance(ov_obj, MotionBlockObject)
                ov_style = {k: v for k, v in ov_obj.props.items() if k in _STYLE_PROP_KEYS["kinetic_title"]}
                rel_start = max(0.0, frame_time(ov.range.start) - s_s)
                rel_end = min(dur_s, frame_time(ov.range.end) - s_s)
                if rel_end > rel_start + 0.2:
                    overlays.append(BlueprintOverlay(
                        overlay_id=f"act_{idx + 1}_overlay_{ov_idx + 1}",
                        block_id="kinetic_title",
                        rel_start_s=rel_start,
                        rel_end_s=rel_end,
                        style_defaults=ov_style,
                    ))

        acts.append(BlueprintAct(
            act_id=f"act_{idx + 1}",
            block_id=obj.block_id,
            block_version=obj.block_version,
            role=role_by_block.get(obj.block_id, "scene"),
            target_duration_s=dur_s,
            resource_count=len(obj.resources) if obj.resources and obj.block_id in {"ui_montage","logo_wall"} else None,
            min_duration_s=min(dur_s, 3.5),
            style_defaults=style_defaults,
            required_slots=req_slots,
            optional_slots=opt_slots,
            callout_windows_s=[(s["start_s"], s["end_s"]) for s in obj.props.get("callout_steps", [])],
            cursor_click_at_s=(obj.props.get("cursor") or {}).get("click_at_s"),
            item_reveals_s=cue_lists[0] if cue_lists else [],
            secondary_reveals_s=cue_lists[1] if len(cue_lists) > 1 else [],
            metric_reveals_s=[item.get("reveal_at_s") for item in obj.props.get("items", [])] if obj.block_id == "metric_grid" else [],
            has_narration=has_narr,
            transition_after=trn_after,
            overlays=overlays,
        ))

    # Audio profile (BGM gain + fades)
    bgm_gain = -25.0
    fade_in_s = None
    fade_out_s = None
    if music_clips:
        music_clips.sort(key=lambda clip: clip.range.start)
        bgm = music_clips[0]
        if isinstance(bgm.object, AudioObject):
            bgm_gain = float(bgm.object.gain_db)
        fade_in_s, _ = _extract_bgm_fades(bgm, tb)
        _, fade_out_s = _extract_bgm_fades(music_clips[-1], tb)
    audio_profile = BlueprintAudioProfile(
        breathing_s=0.5,
        narration_gain_db=0.0,
        has_bgm=bool(music_clips),
        bgm_gain_db=bgm_gain,
        bgm_fade_in_s=fade_in_s,
        bgm_fade_out_s=fade_out_s,
    )

    # Anchor every sound_recipe SFX clip relative to nearest act boundary
    sfx_cues: list[BlueprintSfxCue] = []
    for sfx_idx, sfx in enumerate(sorted(effect_clips, key=lambda c: c.range.start)):
        if sfx.source is None or not isinstance(sfx.object, AudioObject):
            continue
        origin = snapshot_origins.get(sfx.source.snapshot_id)
        if not origin or origin.get("recipe_id") not in SOUND_RECIPE_CATALOG:
            continue
        sfx_start_s = sfx.range.start / tb
        # Choose nearest boundary among (cut_after of act i) and (act_start of act i)
        best: tuple[float, int, Literal["act_start", "act_end", "cut_after"], float] | None = None
        for i, (as_, ae_) in enumerate(act_ranges_s):
            candidates: list[tuple[Literal["act_start", "act_end", "cut_after"], float]] = [
                ("act_start", sfx_start_s - as_),
            ]
            if i + 1 < len(act_ranges_s):
                candidates.append(("cut_after", sfx_start_s - ae_))
            else:
                candidates.append(("act_end", sfx_start_s - ae_))
            for anchor, offset in candidates:
                dist = abs(offset)
                if best is None or dist < best[0]:
                    best = (dist, i, anchor, offset)
        assert best is not None
        _, best_idx, best_anchor, best_offset = best
        clamped_offset = round(max(-2.0, min(2.0, best_offset)), 3)
        sfx_cues.append(BlueprintSfxCue(
            cue_id=f"sfx_{sfx_idx + 1}",
            recipe_id=origin["recipe_id"],
            params=dict(origin.get("params") or {}),
            seed=int(origin.get("seed") if origin.get("seed") is not None else 1248),
            gain_db=float(sfx.object.gain_db),
            act_index=best_idx,
            anchor=best_anchor,
            offset_s=clamped_offset,
        ))

    source_uri = f"composition://{composition_id}@v{version_number}"
    bp = SkillBlueprintV1(
        schema_version=1,
        canvas={
            "width": content.settings.width,
            "height": content.settings.height,
            "fps_num": content.settings.fps.num,
            "fps_den": content.settings.fps.den,
            "background": content.settings.background,
        },
        style=content.settings.style,
        acts=acts,
        audio_profile=audio_profile,
        sfx_cues=sfx_cues,
    )

    bp_text = json.dumps(
        bp.model_dump(mode="json", exclude={"source_composition_uri"}),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    bp_digest = hashlib.sha256(bp_text.encode("utf-8")).hexdigest()
    skill_md = _render_skill_md(slug, desc, bp)

    declared_inputs: list[SkillInputDeclaration] = [
        SkillInputDeclaration(
            name="target_brief",
            description="Target product, audience, language, and angle for the remake.",
            binding="instruction",
            required=True,
        ),
    ]
    for act in acts:
        has_media = "image_resource" in act.required_slots
        declared_inputs.append(SkillInputDeclaration(
            name=act.act_id,
            description=(
                f"{act.block_id} ({act.role}, ~{act.target_duration_s:g}s) — "
                f"required: {', '.join(act.required_slots)}"
            ),
            binding="media" if has_media else "text",
            required=True,
        ))
    if audio_profile.has_bgm:
        declared_inputs.append(SkillInputDeclaration(
            name="bgm",
            description="Optional curated or project BGM audio snapshot.",
            binding="media",
            required=False,
        ))

    source_hash = canonical_json_hash({"instructions": skill_md, "blueprint": bp_digest})
    total_s = sum(a.target_duration_s for a in acts)
    draft = SkillDraft(
        name=slug,
        description=desc,
        instructions=skill_md,
        references=[
            SkillSource(
                path=BLUEPRINT_PATH,
                role="reference",
                digest=bp_digest,
                text=bp_text,
            )
        ],
        media=[],
        source_hash=source_hash,
        source_uri=source_uri,
        source_revision=f"v{version_number}",
        capability_report=SkillCapabilityReport(
            supported=["native_motion_graphics", "sound_recipes", BLUEPRINT_CAPABILITY],
        ),
        declared_inputs=declared_inputs,
        policy=SkillPolicy(
            mode="adaptive",
            scene_count=len(acts),
            duration_seconds=round(min(118.0, max(1.0, total_s)), 2),
            adaptation_bounds=[
                "Act durations adapt automatically to measured narration + breathing room",
                "All copy, metrics, screenshots, language, and voices are replaceable slots",
            ],
        ),
    )
    return draft, bp


async def save_composition_as_skill(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    composition_id: UUID,
    version_id: UUID,
    name: str,
    description: str,
    opening_id: UUID | None = None,
    conversation_id: UUID | None = None,
    lock_on_session: bool = True,
) -> dict[str, Any]:
    """Persist a saved CompositionVersion as an owner-scoped immutable SkillVersion (0 new tables)."""
    if opening_id is not None:
        from app.chat.editor_recovery import editor_lock_key
        from app.chat.service import TurnStopped, _lock_turn_for_transcript_write

        if lock_on_session:
            await db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(opening_id))))
        opening = await _lock_turn_for_transcript_write(db, opening_id)
        if opening.role != "user" or (conversation_id is not None and opening.conversation_id != conversation_id):
            raise ValueError("The opening message is unavailable.")
        if opening.turn_state != "in_flight":
            raise TurnStopped(str(opening_id))

    composition, version = await get_video_version(db, owner_id=owner_id, version_id=version_id)
    if composition.id != composition_id or composition.origin_project_id != project_id:
        raise ValueError("This composition version is outside the selected project.")
    content = content_of(version)

    # Load sound_recipe origins for effect audio clips
    audio_ids = {
        c.source.snapshot_id
        for t in content.timeline.tracks
        for c in t.clips
        if c.object.kind == "audio" and c.source is not None
    }
    origins: dict[UUID, dict[str, Any]] = {}
    if audio_ids:
        rows = await db.scalars(select(SourceSnapshot).where(SourceSnapshot.id.in_(audio_ids)))
        for snap in rows:
            origin = (snap.meta or {}).get("origin") or {}
            if origin.get("kind") == "sound_recipe":
                origins[snap.id] = {
                    "recipe_id": origin.get("recipe_id"),
                    "params": origin.get("params") or {},
                    "seed": origin.get("seed"),
                }

    draft, bp = extract_skill_draft_from_composition(
        composition_id=composition.id,
        version_number=version.version,
        content=content,
        snapshot_origins=origins,
        name=name,
        description=description,
    )
    skill_ver, reused = await import_external_skill(db, owner_id=owner_id, draft=draft)
    await db.commit()
    return {
        "saved": True,
        "reused": reused,
        "skill_id": str(skill_ver.skill_id),
        "skill_version_id": str(skill_ver.id),
        "version": skill_ver.version,
        "name": draft.name,
        "description": draft.description,
        "source_uri": draft.source_uri,
        "acts_count": len(bp.acts),
        "sfx_cues_count": len(bp.sfx_cues),
        "has_bgm": bp.audio_profile.has_bgm,
        "declared_inputs": [item.model_dump(mode="json") for item in draft.declared_inputs],
    }


class BlueprintActSlotInput(BaseModel):
    """Per-act replacement slot values supplied when instantiating a Skill blueprint."""

    model_config = ConfigDict(extra="forbid")

    act_id: str | None = Field(default=None, max_length=64, description="Optional act_id matching blueprint order.")
    props: dict[str, Any] = Field(description="Replacement content props. Bind callout, callout_steps and cursor to fresh captured element_ids. Step windows, click and per-item reveal times inherit by position unless overridden.")
    resources: list[UUID] | None = Field(
        default=None, max_length=16,
        description="Pinned image or captured webpage snapshot IDs (product_showcase needs an image; device_mockup takes primary then optional mobile; chat_demo accepts a result preview).",
    )
    view_id: str | None = Field(
        default=None, max_length=120,
        description="Optional captured webpage view_id when passing a webpage snapshot in resources.",
    )
    narration_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional fixed voice narration snapshot for this act; act duration auto-adapts to measured voice + breathing.",
    )
    overlay_props: dict[str, Any] | None = Field(
        default=None,
        description="Optional replacement props for this act's anchored kinetic_title overlay (e.g. pill_caption headline).",
    )
    duration_seconds: float | None = Field(
        default=None, ge=0.2, le=60.0, allow_inf_nan=False,
        description="Optional explicit act duration override when no narration_snapshot_id is provided.",
    )


class InstantiateSkillBlueprintArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_version_id: UUID = Field(description="Immutable SkillVersion UUID of the saved slot_blueprint_v1 Skill.")
    name: str = Field(min_length=1, max_length=120, description="Name for the new editable Composition.")
    acts: list[BlueprintActSlotInput] = Field(min_length=1, max_length=48, description="Ordered slot values matching blueprint acts.")
    style_preset: StylePresetId | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Optional orthogonal CompositionStyle preset override (institutional_dark, swiss_paper, vox_editorial, kinetic_anime).",
    )
    accent_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        exclude_if=lambda v: v is None,
        description="Optional hex brand accent color override combined with style_preset or blueprint.style.",
    )
    bgm_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional fixed music snapshot; looped or trimmed to the adapted total duration with blueprint fade-in/out.",
    )
    bgm_gain_db: float | None = Field(default=None, ge=-60.0, le=0.0, allow_inf_nan=False)
    breathing_seconds: float | None = Field(
        default=None, ge=0.2, le=1.5, allow_inf_nan=False,
        description="Optional breathing room added to each act's measured narration duration (defaults to blueprint 0.5s).",
    )


def load_blueprint_from_skill_version(skill_ver: Any) -> SkillBlueprintV1:
    refs = skill_ver.references or []
    bp_ref = next((r for r in refs if isinstance(r, dict) and r.get("path") == BLUEPRINT_PATH), None)
    if bp_ref is None or not bp_ref.get("text"):
        raise ValueError("This SkillVersion does not contain a slot_blueprint_v1 blueprint.")
    return SkillBlueprintV1.model_validate_json(bp_ref["text"])


def _instantiate_result_from_version(
    *,
    turn: Any,
    saved: CompositionVersion,
    read: dict[str, Any],
) -> dict[str, Any]:
    saved_content = content_of(saved)
    tb = saved_content.settings.timebase
    main_clips = sorted(
        (
            c
            for t in saved_content.timeline.tracks
            if t.kind == "visual" and t.role == "main"
            for c in t.clips
        ),
        key=lambda c: c.range.start,
    )
    total_ticks = max((c.range.end for c in main_clips), default=0)
    sfx_count = sum(
        len(t.clips)
        for t in saved_content.timeline.tracks
        if t.kind == "audio" and t.role == "effect"
    )
    turn._video_presentation_pending = read
    from app.chat.editor import _remember_labels

    _remember_labels(
        turn, [], saved.id, saved.content_digest, saved.version, composition_id=saved.composition_id
    )
    return {
        "composition_id": str(saved.composition_id),
        "version_id": str(saved.id),
        "version": saved.version,
        "content_digest": saved.content_digest,
        "saved": True,
        "duration_seconds": round(total_ticks / tb, 3),
        "acts": [
            {
                "act_id": f"act_{i + 1}",
                "clip_id": c.clip_id,
                "block_id": c.object.block_id if isinstance(c.object, MotionBlockObject) else c.object.kind,
                "start_seconds": round(c.range.start / tb, 3),
                "end_seconds": round(c.range.end / tb, 3),
            }
            for i, c in enumerate(main_clips)
        ],
        "transitions_count": len(saved_content.timeline.transitions),
        "sfx_clips_count": sfx_count,
    }


async def instantiate_skill_blueprint(
    *,
    turn: Any,
    args: InstantiateSkillBlueprintArgs,
    call_id: str,
) -> dict[str, Any]:
    """Instantiate a Skill blueprint into a fresh editable CompositionVersion.

    Strictly synthesizes SFX snapshots OUTSIDE `apply_composition_edits` write locks,
    adapts each act's duration to measured narration + breathing room, and re-anchors
    every SFX cue to the adapted act/cut timestamps.
    """
    from app.chat.service import TurnStopped, _lock_turn_for_transcript_write
    from app.editing.service import video_version_read
    from app.editing.sources import register_web_view_snapshot
    from app.models.database import AsyncSessionLocal
    from app.tools.video.sfx_synthesis import synthesize_project_sfx

    owner = turn.project.user_id
    project = turn.project.id
    identity = str(uuid5(turn.turn_id, call_id))
    fingerprint = canonical_json_hash({"tool": "instantiate_skill_blueprint", "args": args.model_dump(mode="json")})

    # ── Phase 1: Lightweight read-only precheck, then resolve media & synthesize SFX OUTSIDE write lock ──
    async with AsyncSessionLocal() as db:
        opening = await db.get(Message, turn.turn_id)
        if opening is None or opening.role != "user" or opening.conversation_id != turn.conversation_id:
            raise ValueError("The opening message is unavailable.")
        pre_markers = (opening.intent or {}).get("editor_commits", [])
        pre_marker = next((item for item in pre_markers if item["request"] == identity), None)
        if pre_marker is not None:
            if pre_marker["fingerprint"] != fingerprint:
                raise RequestMismatch("This call already saved different content.")
            existing_saved = await db.scalar(
                select(CompositionVersion)
                .join(Composition, Composition.id == CompositionVersion.composition_id)
                .where(
                    CompositionVersion.request_id == identity,
                    Composition.owner_id == owner,
                    Composition.origin_project_id == project,
                )
            )
            if existing_saved is None:
                raise ValueError("The saved version is unavailable.")
            read = await video_version_read(db, owner_id=owner, version_id=existing_saved.id)
            return _instantiate_result_from_version(turn=turn, saved=existing_saved, read=read)
        if opening.turn_state != "in_flight":
            raise TurnStopped(str(turn.turn_id))

        skill_ver = await get_skill_version(db, owner_id=owner, skill_version_id=args.skill_version_id)
        bp = load_blueprint_from_skill_version(skill_ver)
        if len(args.acts) != len(bp.acts):
            raise ValueError(
                f"Blueprint expects {len(bp.acts)} acts ({[a.act_id for a in bp.acts]}), got {len(args.acts)}."
            )

        fps_num = int(bp.canvas.get("fps_num", 30))
        fps_den = int(bp.canvas.get("fps_den", 1))
        effective_style: CompositionStyle | None = None
        if args.style_preset is not None:
            effective_style = CompositionStyle(
                preset_id=args.style_preset,
                accent_color=args.accent_color,
            )
        elif bp.style is not None:
            effective_style = (
                bp.style.model_copy(update={"accent_color": args.accent_color})
                if args.accent_color is not None
                else bp.style
            )
        effective_bg = (
            resolve_style_tokens(effective_style)["canvas_bg"]
            if effective_style is not None
            else str(bp.canvas.get("background", "#070B11"))
        )
        settings_obj = VersionSettings(
            width=int(bp.canvas.get("width", 1920)),
            height=int(bp.canvas.get("height", 1080)),
            fps={"num": fps_num, "den": fps_den},
            background=effective_bg,
            style=effective_style,
        )

        legacy_asset = select(Asset.id).where(Asset.user_id == owner, Asset.project_id == project)
        ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

        resolved_acts: list[dict[str, Any]] = []
        bound_snapshots: dict[UUID, str] = {}

        for idx, (bp_act, slot) in enumerate(zip(bp.acts, args.acts)):
            if slot.act_id and slot.act_id != bp_act.act_id:
                raise ValueError(f"Act #{idx + 1} expected act_id={bp_act.act_id!r}, got {slot.act_id!r}.")
            if args.style_preset is not None:
                # Cross-style instantiation: strip inheritable visual style defaults from the blueprint
                # so every act inherits the newly requested style_preset unless overridden in slot.props.
                strip_keys = set(INHERITABLE_BLOCK_STYLE_KEYS.get(bp_act.block_id, ()))
                act_for_bind = bp_act.model_copy(
                    update={"style_defaults": {k: v for k, v in bp_act.style_defaults.items() if k not in strip_keys}}
                )
                merged_props = act_for_bind.bind_props(slot.props)
            else:
                merged_props = bp_act.bind_props(slot.props)

            # Resolve visual resources (supports image snapshots & captured webpage views)
            if bp_act.resource_count and len(slot.resources or []) != bp_act.resource_count:
                raise ValueError(f"Act {bp_act.act_id} requires {bp_act.resource_count} images.")
            act_resources: list[RemotionResource] = []
            for r_idx, res_id in enumerate(slot.resources or []):
                snap = await db.scalar(select(SourceSnapshot).where(
                    SourceSnapshot.id == res_id,
                    SourceSnapshot.owner_id == owner,
                    (SourceSnapshot.origin_project_id == project)
                    | (SourceSnapshot.origin_project_id.is_(None) & SourceSnapshot.asset_id.in_(legacy_asset)),
                ))
                if snap is None:
                    raise ValueError(f"Act {bp_act.act_id}: resource snapshot {res_id} is unavailable in this project.")
                if snap.kind == "web":
                    views = (snap.meta or {}).get("views") or []
                    chosen_view = slot.view_id or (views[0].get("view_id") if views else None)
                    if not chosen_view:
                        raise ValueError(f"Act {bp_act.act_id}: captured webpage has no rendered views.")
                    if r_idx == 0 and bp_act.block_id == "product_showcase":
                        merged_props = ProductShowcaseProps.resolve_props(merged_props, views, chosen_view)
                    snap = await register_web_view_snapshot(
                        db, owner_id=owner, web_snapshot=snap, view_id=chosen_view,
                    )
                    await db.flush()
                if snap.kind != "image" or not snap.storage_key:
                    raise ValueError(f"Act {bp_act.act_id}: resources must be fixed images or captured webpage views.")
                ctype = (snap.meta or {}).get("content_type") or (
                    "image/jpeg" if snap.storage_key.lower().endswith((".jpg", ".jpeg"))
                    else "image/webp" if snap.storage_key.lower().endswith(".webp")
                    else "image/png"
                )
                if ctype not in ext_map:
                    ctype = "image/png"
                act_resources.append(RemotionResource(
                    path=f"media/act_{idx + 1}_img_{r_idx}{ext_map[ctype]}",
                    snapshot_id=snap.id,
                    snapshot_digest=snap.digest,
                    content_type=ctype,
                ))
                bound_snapshots[snap.id] = snap.digest

            # Resolve optional per-act narration snapshot
            narr_info = None
            if slot.narration_snapshot_id is not None:
                nsnap = await db.get(SourceSnapshot, slot.narration_snapshot_id)
                if (
                    nsnap is None
                    or nsnap.owner_id != owner
                    or nsnap.origin_project_id != project
                    or nsnap.kind != "audio"
                    or not nsnap.duration_ticks
                ):
                    raise ValueError(f"Act {bp_act.act_id}: narration snapshot is unavailable in this project.")
                narr_info = {
                    "snapshot_id": nsnap.id,
                    "digest": nsnap.digest,
                    "duration_ticks": int(nsnap.duration_ticks),
                }
                bound_snapshots[nsnap.id] = nsnap.digest

            main_obj = MotionBlockObject(
                kind="motion_block",
                object_id=f"obj_bp_act_{idx + 1}",
                block_id=bp_act.block_id,
                block_version=bp_act.block_version,
                props=merged_props,
                resources=act_resources,
                layout=LayoutBox(x=0, y=0, width=settings_obj.width, height=settings_obj.height),
                fit="cover" if bp_act.block_id != "kinetic_title" else "contain",
            )
            resolved_acts.append({
                "bp": bp_act,
                "slot": slot,
                "object": main_obj,
                "narration": narr_info,
            })

        bgm_info = None
        if args.bgm_snapshot_id is not None:
            bsnap = await db.get(SourceSnapshot, args.bgm_snapshot_id)
            if (
                bsnap is None
                or bsnap.owner_id != owner
                or bsnap.origin_project_id != project
                or bsnap.kind != "audio"
                or not bsnap.duration_ticks
            ):
                raise ValueError("BGM snapshot is unavailable in this project.")
            bgm_info = {
                "snapshot_id": bsnap.id,
                "digest": bsnap.digest,
                "duration_ticks": int(bsnap.duration_ticks),
            }
            bound_snapshots[bsnap.id] = bsnap.digest
        # Commit any newly registered web_view snapshots before external SFX HTTP calls
        await db.commit()

    # Synthesize all blueprint SFX cues strictly OUTSIDE any DB transaction lock (Guardrail #2)
    sfx_snapshots: dict[str, dict[str, Any]] = {}
    for cue in bp.sfx_cues:
        sfx_res = await synthesize_project_sfx(
            owner_id=owner,
            project_id=project,
            recipe_id=cue.recipe_id,
            params=cue.params,
            seed=cue.seed,
        )
        snap_uuid = UUID(sfx_res["audio_snapshot_id"])
        snap_digest = sfx_res["audio_digest"]
        dur_s = float(sfx_res.get("duration_seconds") or (sfx_res["acoustics"]["duration_ms"] / 1000.0))
        sfx_snapshots[cue.cue_id] = {
            "snapshot_id": snap_uuid,
            "digest": snap_digest,
            "duration_ms": int(round(dur_s * 1000)),
            "duration_ticks": seconds_to_ticks(dur_s, SOURCE_TIMEBASE),
        }
        bound_snapshots[snap_uuid] = snap_digest

    # ── Phase 2: Pure deterministic adaptive timeline assembly ──
    tb = settings_obj.timebase
    breathing_s = args.breathing_seconds if args.breathing_seconds is not None else bp.audio_profile.breathing_s

    def quantize_up_ticks(sec: float) -> int:
        frames = max(1, math.ceil(sec * fps_num / fps_den - 1e-9))
        return frames_to_ticks(frames, tb, fps_num, fps_den)

    scenes: list[Scene] = []
    main_clips: list[Clip] = []
    title_clips: list[Clip] = []
    dialogue_clips: list[Clip] = []
    act_windows: list[tuple[int, int, str]] = []  # (start_ticks, end_ticks, clip_id)

    cursor = 0
    for idx, item in enumerate(resolved_acts):
        bp_act: BlueprintAct = item["bp"]
        slot: BlueprintActSlotInput = item["slot"]
        narr = item["narration"]

        if narr is not None:
            narr_out_ticks = source_ticks_to_output_ticks(narr["duration_ticks"], tb)
            narr_s = narr_out_ticks / tb
            dur_ticks = quantize_up_ticks(max(bp_act.min_duration_s, narr_s + breathing_s))
        elif slot.duration_seconds is not None:
            dur_ticks = quantize_up_ticks(slot.duration_seconds)
        else:
            dur_ticks = quantize_up_ticks(bp_act.target_duration_s)

        start = cursor
        end = cursor + dur_ticks
        cursor = end
        scene_id = f"scene_{idx + 1}"
        clip_id = f"clp_bp_act_{idx + 1}"
        act_windows.append((start, end, clip_id))
        scenes.append(Scene(scene_id=scene_id, range=TimeRange(start=start, end=end)))

        main_clips.append(Clip(
            clip_id=clip_id,
            range=TimeRange(start=start, end=end),
            scene_id=scene_id,
            source=None,
            object=item["object"],
            animations=[],
        ))

        # Optional anchored overlay (e.g., pill_caption) when caller supplies overlay_props
        if bp_act.overlays and slot.overlay_props:
            ov = bp_act.overlays[0]
            ov_props = {**ov.style_defaults, **slot.overlay_props}
            ov_start = max(start, min(end - quantize_up_ticks(0.5), start + quantize_up_ticks(ov.rel_start_s)))
            ov_dur_target = max(1.5, ov.rel_end_s - ov.rel_start_s)
            ov_end = min(end - quantize_up_ticks(0.2), ov_start + quantize_up_ticks(ov_dur_target))
            if ov_end > ov_start:
                ov_obj = MotionBlockObject(
                    kind="motion_block",
                    object_id=f"obj_bp_ov_{idx + 1}",
                    block_id="kinetic_title",
                    block_version=1,
                    props=ov_props,
                    resources=[],
                    layout=LayoutBox(x=0, y=0, width=settings_obj.width, height=settings_obj.height),
                    fit="contain",
                )
                title_clips.append(Clip(
                    clip_id=f"clp_bp_ov_{idx + 1}",
                    range=TimeRange(start=ov_start, end=ov_end),
                    scene_id=scene_id,
                    source=None,
                    object=ov_obj,
                    animations=[],
                ))

        # Per-act narration with centered breathing margin
        if narr is not None:
            narr_out_ticks = source_ticks_to_output_ticks(narr["duration_ticks"], tb)
            lead = quantize_up_ticks(min(breathing_s * 0.5, 0.3))
            n_start = start + lead
            n_end = min(end, n_start + narr_out_ticks)
            used_src_end = min(narr["duration_ticks"], output_ticks_to_source_ticks(n_end - n_start, tb))
            dialogue_clips.append(Clip(
                clip_id=f"clp_bp_vo_{idx + 1}",
                range=TimeRange(start=n_start, end=n_end),
                scene_id=None,
                source=ClipSource(
                    snapshot_id=narr["snapshot_id"],
                    snapshot_digest=narr["digest"],
                    source_range=TimeRange(start=0, end=used_src_end),
                ),
                object=AudioObject(
                    kind="audio",
                    object_id=f"obj_bp_vo_{idx + 1}",
                    gain_db=bp.audio_profile.narration_gain_db,
                ),
                animations=[],
            ))

    total_ticks = cursor

    # Re-attach transitions between adjacent opaque main acts
    transitions: list[Transition] = []
    for idx, item in enumerate(resolved_acts):
        bp_act: BlueprintAct = item["bp"]
        if bp_act.transition_after is None or idx + 1 >= len(act_windows):
            continue
        cur_start, cur_end, from_cid = act_windows[idx]
        nxt_start, nxt_end, to_cid = act_windows[idx + 1]
        if (
            main_clips[idx].object.opaque_backdrop
            and main_clips[idx + 1].object.opaque_backdrop
        ):
            trn_s = bp_act.transition_after.duration_s
            # A shortened replacement act must leave space for both adjacent cuts.
            for length, original in (
                (cur_end - cur_start, bp_act.target_duration_s),
                (nxt_end - nxt_start, bp.acts[idx + 1].target_duration_s),
            ):
                if length / tb < original - 1e-9:
                    trn_s = min(trn_s, length / tb)
            trn_ticks = seconds_to_ticks(trn_s, tb)
            if ticks_to_frames(trn_ticks, tb, fps_num, fps_den) >= 2:
                transitions.append(Transition(
                    transition_id=f"trn_bp_{idx + 1}",
                    from_clip_id=from_cid,
                    to_clip_id=to_cid,
                    kind=bp_act.transition_after.kind,
                    duration=trn_ticks,
                    alignment="center",
                ))

    tracks: list[Track] = [
        Track(track_id="trk_mg_main", kind="visual", role="main", order=0, clips=main_clips),
    ]
    if title_clips:
        tracks.append(Track(track_id="trk_mg_title", kind="visual", role="title", order=1, clips=title_clips))

    audio_order = 0
    if dialogue_clips:
        tracks.append(Track(
            track_id="trk_editor_dialogue", kind="audio", role="dialogue", order=audio_order, clips=dialogue_clips
        ))
        audio_order += 1

    if bgm_info is not None:
        music = music_clips_for_window(
            settings=settings_obj, start=0, end=total_ticks,
            source_id=bgm_info["snapshot_id"], digest=bgm_info["digest"],
            source_ticks=bgm_info["duration_ticks"], id_stem="bp_bgm",
            gain_db=args.bgm_gain_db if args.bgm_gain_db is not None else bp.audio_profile.bgm_gain_db,
            fade_in_seconds=bp.audio_profile.bgm_fade_in_s,
            fade_out_seconds=bp.audio_profile.bgm_fade_out_s,
        )
        tracks.append(Track(track_id="trk_editor_music", kind="audio", role="music", order=audio_order, clips=music))
        audio_order += 1

    # Place re-anchored SFX cues on collision-free effect tracks
    effect_tracks: list[Track] = []
    for sfx_idx, cue in enumerate(bp.sfx_cues):
        if cue.act_index >= len(act_windows):
            continue
        act_start, act_end, _ = act_windows[cue.act_index]
        anchor_ticks = act_start if cue.anchor == "act_start" else act_end
        offset_ticks = seconds_to_ticks(abs(cue.offset_s), tb)
        if cue.offset_s < 0:
            offset_ticks = -offset_ticks
        sfx_start = max(0, anchor_ticks + offset_ticks)
        info = sfx_snapshots[cue.cue_id]
        sfx_out_dur = source_ticks_to_output_ticks(info["duration_ticks"], tb)
        sfx_end = min(total_ticks, sfx_start + sfx_out_dur)
        if sfx_end <= sfx_start:
            continue
        used_src = min(info["duration_ticks"], output_ticks_to_source_ticks(sfx_end - sfx_start, tb))
        sfx_clip = Clip(
            clip_id=f"clp_bp_sfx_{sfx_idx + 1}",
            range=TimeRange(start=sfx_start, end=sfx_end),
            scene_id=None,
            source=ClipSource(
                snapshot_id=info["snapshot_id"],
                snapshot_digest=info["digest"],
                source_range=TimeRange(start=0, end=used_src),
            ),
            object=AudioObject(
                kind="audio",
                object_id=f"obj_bp_sfx_{sfx_idx + 1}",
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
            tid = "trk_editor_effect" if not effect_tracks else f"trk_editor_effect_{len(effect_tracks) + 1}"
            effect_tracks.append(Track(
                track_id=tid, kind="audio", role="effect", order=audio_order, clips=[sfx_clip]
            ))
            audio_order += 1
    tracks.extend(effect_tracks)

    sources = [SourceBinding(snapshot_id=sid, snapshot_digest=dig) for sid, dig in bound_snapshots.items()]
    content = CompositionContent(
        settings=settings_obj,
        sources=sources,
        scenes=scenes,
        timeline=Timeline(tracks=tracks, transitions=transitions),
    )

    provenance = {
        "skill_reference": {"kind": "external", "skill_version_id": str(args.skill_version_id)},
        "slot_blueprint_v1": {
            "skill_version_id": str(args.skill_version_id),
            "source_composition_uri": bp.source_composition_uri or skill_ver.source_uri,
            "breathing_seconds": breathing_s,
        },
    }

    # ── Phase 3: Atomic commit through single Composition write gate ──
    from app.chat.editor_recovery import editor_lock_key

    async with AsyncSessionLocal() as db:
        await db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id))))
        opening = await _lock_turn_for_transcript_write(db, turn.turn_id)
        if opening.role != "user" or opening.conversation_id != turn.conversation_id:
            raise ValueError("The opening message is unavailable.")
        markers = (opening.intent or {}).get("editor_commits", [])
        marker = next((item for item in markers if item["request"] == identity), None)
        if marker:
            if marker["fingerprint"] != fingerprint:
                raise RequestMismatch("This call already saved different content.")
            saved = await db.scalar(
                select(CompositionVersion)
                .join(Composition, Composition.id == CompositionVersion.composition_id)
                .where(
                    CompositionVersion.request_id == identity,
                    Composition.owner_id == owner,
                    Composition.origin_project_id == project,
                )
            )
            if saved is None:
                raise ValueError("The saved version is unavailable.")
        else:
            if opening.turn_state != "in_flight":
                raise TurnStopped(str(turn.turn_id))
            await db.execute(
                select(Project.id).where(Project.id == project, Project.user_id == owner).with_for_update(key_share=True)
            )
            if await db.scalar(select(Composition.id).where(Composition.origin_project_id == project).limit(1)):
                raise ValueError("This project already has a saved work. Inspect it before editing.")
            activity = await db.scalar(
                select(Message.id)
                .where(
                    Message.turn_id == opening.id,
                    Message.intent["frame"]["call_id"].astext == call_id,
                    Message.intent["frame"]["status"].astext == "active",
                )
                .limit(1)
            )
            opening.intent = {
                **(opening.intent or {}),
                "editor_commits": [
                    *markers,
                    {
                        "request": identity,
                        "tool": "instantiate_skill_blueprint",
                        "fingerprint": fingerprint,
                        "activity_row": str(activity) if activity else None,
                    },
                ],
            }
            _, saved, _ = await apply_composition_edits(
                db,
                owner_id=owner,
                origin_project_id=project,
                name=args.name,
                content=content.model_dump(mode="json"),
                request_id=identity,
                skill_provenance=provenance,
            )
        read = await video_version_read(db, owner_id=owner, version_id=saved.id)

    return _instantiate_result_from_version(turn=turn, saved=saved, read=read)
