/** User-visible work and receipts, projected from the original transcript. */
import { lazy, Suspense, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { AlertCircle, CheckCircle2, ChevronRight, Circle, Film, MinusCircle, Play, TriangleAlert, Video } from "@/components/ui/icons"

import type {
  ActivityReceipt,
  ActivitySemanticDetail,
  WorkTrailEntry,
  ActivityRowFrame,
  ComponentClipReceipt,
  NativeJobReceipt,
  NowRowPayload,
  MusicSearchReceipt,
  MusicSelectionReceipt,
  SfxImportReceipt,
  SfxSearchReceipt,
  SkillSavedReceipt,
  StepPlanItem,
  ToolCallStatus,
  VideoReviewReceipt,
  VideoRevisionReceipt,
} from "./timeline/types"
import { activityCategoryKey, activityFailureKey } from "./timeline/activity"
import { formatElapsed } from "@/components/chat/workTiming"
import { OutputPosterImage } from "@/components/chat/OutputDeliveryCard"
import { useMessageScrollerViewportAnchor } from "@/components/chat/MessageScroller"
import { Button } from "@/components/ui/button-clean"
import { Card } from "@/components/ui/card-clean"
import { ThinkingState, type ThinkingTrailStep } from "@/components/ui/thinking-state-clean"
import { outputAspect } from "@/lib/outputAspect"
import type { Output } from "@/lib/types"
import { cn } from "@/lib/utils"

const LazySlotPreviewDialog = lazy(() =>
  import("@/components/skills/SlotPreviewDialog").then((m) => ({
    default: m.SlotPreviewDialog,
  })),
)

export type { NowRowPayload } from "./timeline/types"

function lookupSemanticToken(t: TFunction, key: string): string | null {
  const value = t(key, { defaultValue: "" })
  if (!value || value === key) return null
  return value
}

export function semanticActivityLabel(
  detail: ActivitySemanticDetail | undefined,
  completed: boolean,
  t: TFunction,
): string | null {
  if (!detail) return null
  const done = completed ? "Done" : ""
  const sep = lookupSemanticToken(t, "chat.activitySemantic.listSep") ?? " / "
  const withWindow = (base: string, window?: string) =>
    window ? t("chat.activitySemantic.withWindow", { base, window, defaultValue: `${base} (${window})` }) : base

  switch (detail.kind) {
    case "style": {
      if (!detail.preset) return null
      const preset = lookupSemanticToken(t, `chat.activitySemantic.styles.${detail.preset}`)
      if (!preset) return null
      return t(`chat.activitySemantic.style${done}`, { preset })
    }
    case "motion_block_insert": {
      if (!detail.block) return null
      const block = lookupSemanticToken(t, `chat.activitySemantic.blocks.${detail.block}`)
      if (!block) return null
      return detail.window
        ? t(`chat.activitySemantic.motionBlockInsertWindow${done}`, { block, window: detail.window })
        : t(`chat.activitySemantic.motionBlockInsert${done}`, { block })
    }
    case "motion_block_update": {
      const aspects = (detail.aspects ?? [])
        .map((a) => lookupSemanticToken(t, `chat.activitySemantic.aspects.${a}`))
        .filter((v): v is string => Boolean(v))
      return aspects.length > 0
        ? t(`chat.activitySemantic.motionBlockUpdateAspects${done}`, { aspects: aspects.join(sep) })
        : t(`chat.activitySemantic.motionBlockUpdate${done}`)
    }
    case "text_caption_from_audio": {
      const preset = detail.preset
        ? lookupSemanticToken(t, `chat.activitySemantic.textPresets.${detail.preset}`)
        : null
      return preset
        ? t(`chat.activitySemantic.textCaptionFromAudioPreset${done}`, { preset })
        : t(`chat.activitySemantic.textCaptionFromAudio${done}`)
    }
    case "text_insert": {
      const preset = detail.preset
        ? lookupSemanticToken(t, `chat.activitySemantic.textPresets.${detail.preset}`)
        : null
      const position = detail.position
        ? lookupSemanticToken(t, `chat.activitySemantic.positions.${detail.position}`)
        : null
      if (detail.bilingual || detail.preset === "bilingual_cinema") {
        const base = t(`chat.activitySemantic.textInsertBilingual${done}`)
        return withWindow(base, detail.window)
      }
      if (preset && position) {
        const base = t(`chat.activitySemantic.textInsertPresetPos${done}`, { position, preset })
        return detail.snippet ? `${base} · ${detail.snippet}` : withWindow(base, detail.window)
      }
      if (preset) {
        const base = t(`chat.activitySemantic.textInsertPreset${done}`, { preset })
        return detail.snippet ? `${base} · ${detail.snippet}` : withWindow(base, detail.window)
      }
      const base = t(`chat.activitySemantic.textInsertGeneric${done}`)
      const withText = detail.snippet ? `${base} · ${detail.snippet}` : base
      return withWindow(withText, detail.window)
    }
    case "text_edit": {
      const preset = detail.preset
        ? lookupSemanticToken(t, `chat.activitySemantic.textPresets.${detail.preset}`)
        : null
      if (preset) {
        return detail.scope === "all_derived_captions"
          ? t(`chat.activitySemantic.textEditPresetCaptions${done}`, { preset })
          : t(`chat.activitySemantic.textEditPreset${done}`, { preset })
      }
      if (detail.snippet) {
        return t(`chat.activitySemantic.textEditSnippet${done}`, { snippet: detail.snippet })
      }
      return t(`chat.activitySemantic.textEditGeneric${done}`)
    }
    case "sfx": {
      if (!detail.recipe) return null
      const recipe = lookupSemanticToken(t, `chat.activitySemantic.sfxRecipes.${detail.recipe}`)
      if (!recipe) return null
      return t(`chat.activitySemantic.sfx${done}`, { recipe })
    }
    case "audio_edit": {
      const aspects = (detail.aspects ?? [])
        .map((a) => lookupSemanticToken(t, `chat.activitySemantic.aspects.${a}`))
        .filter((v): v is string => Boolean(v))
      return aspects.length > 0
        ? t(`chat.activitySemantic.audioEditAspects${done}`, { aspects: aspects.join(sep) })
        : t(`chat.activitySemantic.audioEdit${done}`)
    }
    case "transition": {
      if (!detail.preset) return null
      const preset = lookupSemanticToken(t, `chat.activitySemantic.transitions.${detail.preset}`)
      if (!preset) return null
      return t(`chat.activitySemantic.transition${done}`, { preset })
    }
  }
}

export function activityText(activity: NowRowPayload, t: TFunction): string {
  const { status } = activity
  if (activity.jobReceipt) {
    const jobState = jobStatus(activity.jobReceipt)
    if (
      jobState !== "running" &&
      jobState !== "accepted" &&
      jobState !== "queued" &&
      jobState !== "success" &&
      jobState !== "outputGenerated"
    ) {
      return t(`agentReceipt.${jobState}`)
    }
  }
  if ((status === "active" || status === "completed") && activity.detail) {
    const semantic = semanticActivityLabel(activity.detail, status === "completed", t)
    if (semantic) return semantic
  }
  const action = activity.tool_name && TOOL_ACTIONS[activity.tool_name]
  if (!activity.key && action && (status === "active" || status === "completed")) {
    return t(`chat.activity.${action}${status === "completed" ? "Done" : ""}`)
  }
  // 归档归类目: a COMPLETED row drops the instance name and speaks the
  // category. A FAILED row uses terminal failure copy (an explicit failure
  // mirror may keep the target's name), never the active progressive label.
  const settled = status === "completed"
  const labelKey = settled
    ? activityCategoryKey(activity.key, activity.assetType)
    : status === "failed"
      ? activityFailureKey(activity.key)
      : activity.key
  return labelKey
    ? t(labelKey, {
        count: activity.count,
        total: settled ? undefined : activity.total,
        name: settled ? undefined : activity.name,
        // Unknown keys degrade by status: active thinks, failed says so,
        // and only a genuinely completed row may claim completion.
        defaultValue: t(
          status === "active"
            ? "chat.thinking"
            : status === "failed"
              ? "chat.failed"
              : "chat.completed",
        ),
      })
    : t(status === "failed" ? "chat.failed" : status === "completed" ? "chat.completed" : "chat.thinking")
}

/** A terminal failure without preceding work stays visible in the conversation. */
export function ActivityRow({ activity }: { activity: ActivityRowFrame }) {
  const { t } = useTranslation()
  const label = activityText(activity, t)
  const duration = activity.duration_ms != null ? formatElapsed(activity.duration_ms) : null
  const line = <>
    <TriangleAlert aria-hidden className="size-3 shrink-0" />
    <span>{label}</span>
    {duration && <span className="text-xs tabular-nums">· {duration}</span>}
  </>
  const style = "flex min-h-8 items-center gap-2 text-sm text-muted-foreground"
  return activity.count != null && activity.total == null ? (
    <details>
      <summary className={cn(style, "w-fit cursor-pointer")}>
        {line}<ChevronRight aria-hidden className="size-3" />
      </summary>
      <p className="ms-5 text-xs">{t("chat.activityMeta.count", { count: activity.count })}</p>
    </details>
  ) : <div className={style}>{line}{activity.error && <span>{activity.error}</span>}</div>
}

const REVIEW_SCOPE_KEYS = [
  "actual_output_decoded",
  "static_frames_checked",
  "deterministic_output_checks",
  "sampled_frame_signals_checked",
  "audio_signal_checked",
  "motion_and_transitions_checked",
  "audio_and_av_sync_checked",
] as const

function reviewFrameTime(seconds: number): string {
  return `${Number(seconds.toFixed(3))}s`
}

/** Review evidence from the exact delivered Output, never the report's
 * storage fields, metrics, summary, or raw JSON. */
function VideoReviewEvidence({ receipt }: { receipt: VideoReviewReceipt }) {
  const { t } = useTranslation()
  return (
    <div className="ml-5 flex flex-col gap-2 py-1 text-xs">
      <div className="flex flex-col gap-0.5">
        <span className="text-meta-foreground">{t("chat.activityReceipt.sampledFrames")}</span>
        {receipt.frames.map((frame) => (
          <span key={frame.frame_id} className="tabular-nums text-muted-foreground">
            {frame.frame_id} · {reviewFrameTime(frame.time_seconds)}
          </span>
        ))}
      </div>
      {receipt.findings.length === 0 ? (
        <span className="text-muted-foreground">{t("chat.activityReceipt.noFindings")}</span>
      ) : (
        receipt.findings.map((finding, index) => (
          <div key={`${finding.frame_id}:${index}`} className="flex flex-col gap-0.5">
            <span className="text-meta-foreground">
              {t(`chat.activityReceipt.${finding.kind}`, { frame: finding.frame_id })}
            </span>
            <span className="whitespace-pre-wrap text-muted-foreground">{finding.observed}</span>
          </div>
        ))
      )}
      {receipt.output_issue_codes.length > 0 && (
        <div className="flex flex-col gap-0.5">
          <span className="text-meta-foreground">{t("chat.activityReceipt.audioIssues")}</span>
          {receipt.output_issue_codes.map((code, index) => (
            <span key={`${code}:${index}`} className="text-muted-foreground">
              {t(`chat.activityReceipt.audio.${code}`)}
            </span>
          ))}
        </div>
      )}
      <div className="flex flex-col gap-0.5">
        <span className="text-meta-foreground">{t("chat.activityReceipt.checkedScope")}</span>
        {REVIEW_SCOPE_KEYS.map((key) => (
          <div key={key} className="flex items-start justify-between gap-3">
            <span className="text-muted-foreground">{t(`chat.activityReceipt.scope.${key}`)}</span>
            <span className="shrink-0 text-meta-foreground">
              {t(receipt.scope[key] ? "chat.activityReceipt.checked" : "chat.activityReceipt.notChecked")}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ComponentEvidence({
  components,
  nested = false,
}: {
  components: ComponentClipReceipt[]
  nested?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className={cn("flex flex-col gap-3 py-1 text-xs", !nested && "ml-5")}>
      {components.map((component) => (
        <div key={component.clip_id} className="flex flex-col gap-1">
          <span className="text-meta-foreground">
            {t("chat.activityReceipt.component.title", { clip: component.clip_id })}
          </span>
          <img
            src={component.poster_url}
            alt={t("chat.activityReceipt.component.posterAlt", { clip: component.clip_id })}
            className="w-full max-w-sm rounded-md"
          />
          <span className="text-muted-foreground">
            {t("chat.activityReceipt.component.previewFrame", { frame: component.preview_frame })}
          </span>
          <span className="text-muted-foreground">
            {t("chat.activityReceipt.component.dynamicSamples", {
              frames: component.dynamic_sample_frames.join(", "),
            })}
          </span>
          <span className="break-all text-meta-foreground" title={component.media_digest}>
            {t("chat.activityReceipt.component.fixedMedia", {
              digest: component.media_digest.slice(0, 12),
            })}
          </span>
        </div>
      ))}
    </div>
  )
}

function VideoRevisionEvidence({ receipt }: { receipt: VideoRevisionReceipt }) {
  const { t } = useTranslation()
  const fields = (changes: string[]) =>
    changes.map((change) => t(`chat.activityReceipt.revision.fields.${change}`)).join(", ")
  return (
    <div className="ml-5 flex flex-col gap-1 py-1 text-xs">
      <span className="text-meta-foreground">
        {t("chat.activityReceipt.revision.version", { version: receipt.version })}
      </span>
      {receipt.settings.length > 0 && (
        <span className="text-muted-foreground">
          {t("chat.activityReceipt.revision.settings", { fields: receipt.settings.join(", ") })}
        </span>
      )}
      {receipt.scenes.added.map((scene) => (
        <span key={`add-scene:${scene}`} className="text-muted-foreground">
          {t("chat.activityReceipt.revision.addedScene", { scene })}
        </span>
      ))}
      {receipt.scenes.removed.map((scene) => (
        <span key={`remove-scene:${scene}`} className="text-muted-foreground">
          {t("chat.activityReceipt.revision.removedScene", { scene })}
        </span>
      ))}
      {receipt.scenes.moved.map((move) => (
        <span key={`move-scene:${move.scene_id}`} className="text-muted-foreground">
          {t("chat.activityReceipt.revision.movedScene", {
            scene: move.scene_id,
            from: move.from_seconds,
            to: move.to_seconds,
          })}
        </span>
      ))}
      {receipt.clips.added.map((clip) => (
        <span key={`add-clip:${clip.clip_id}`} className="text-muted-foreground">
          {t("chat.activityReceipt.revision.addedClip", {
            clip: clip.clip_id,
            kind: t(`chat.activityReceipt.revision.kinds.${clip.kind}`),
          })}
        </span>
      ))}
      {receipt.clips.removed.map((clip) => (
        <span key={`remove-clip:${clip}`} className="text-muted-foreground">
          {t("chat.activityReceipt.revision.removedClip", { clip })}
        </span>
      ))}
      {receipt.clips.updated.map((clip) => (
        <span key={`update-clip:${clip.clip_id}`} className="text-muted-foreground">
          {t("chat.activityReceipt.revision.updatedClip", {
            clip: clip.clip_id,
            fields: fields(clip.changes),
          })}
        </span>
      ))}
      {receipt.transitions_changed && (
        <span className="text-muted-foreground">
          {t("chat.activityReceipt.revision.transitions")}
        </span>
      )}
      {receipt.components.length > 0 && <ComponentEvidence components={receipt.components} nested />}
    </div>
  )
}

function SfxSearchEvidence({ receipt }: { receipt: SfxSearchReceipt }) {
  const { t } = useTranslation()
  return (
    <div className="ml-5 flex flex-col gap-1 py-1 text-xs">
      <span className="text-meta-foreground">
        {t("chat.activityReceipt.sfx.searchTopic", { topic: receipt.topic })}
      </span>
      {receipt.members.map((member) => (
        <span key={member.member_index} className="text-muted-foreground">
          {t("chat.activityReceipt.sfx.candidate", {
            ordinal: member.ordinal,
            title: member.title,
            duration: Number(member.duration_seconds.toFixed(3)),
          })}
        </span>
      ))}
    </div>
  )
}

function SfxImportEvidence({ receipt }: { receipt: SfxImportReceipt }) {
  const { t } = useTranslation()
  return (
    <div className="ml-5 flex flex-col gap-1 py-1 text-xs">
      <span className="text-muted-foreground">
        {t("chat.activityReceipt.sfx.imported", {
          title: receipt.title,
          duration: Number(receipt.duration_seconds.toFixed(3)),
        })}
      </span>
      <span className="break-all text-meta-foreground">
        {t("chat.activityReceipt.sfx.snapshot", { id: receipt.snapshot_id })}
      </span>
    </div>
  )
}

function MusicSearchEvidence({ receipt }: { receipt: MusicSearchReceipt }) {
  const { t } = useTranslation()
  return (
    <div className="ml-5 flex flex-col gap-1 py-1 text-xs">
      <span className="text-meta-foreground">
        {t("chat.activityReceipt.music.searchTopic", { topic: receipt.topic })}
      </span>
      {receipt.members.map((member) => (
        <span key={member.member_index} className="text-muted-foreground">
          {t("chat.activityReceipt.music.candidate", {
            ordinal: member.ordinal,
            title: member.title,
            duration: Number(member.duration_seconds.toFixed(3)),
          })}
        </span>
      ))}
    </div>
  )
}

function MusicSelectionEvidence({ receipt }: { receipt: MusicSelectionReceipt }) {
  const { t } = useTranslation()
  return (
    <div className="ml-5 flex flex-col gap-1 py-1 text-xs">
      <span className="text-muted-foreground">
        {t("chat.activityReceipt.music.selected", {
          title: receipt.title,
          duration: Number(receipt.duration_seconds.toFixed(3)),
        })}
      </span>
    </div>
  )
}

function SkillSavedEvidence({ receipt }: { receipt: SkillSavedReceipt }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
      <div className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">
          {receipt.name} v{receipt.version}
        </span>
        {" · "}
        <span>
          {t("skills.slotPreview.receiptMeta", {
            acts: receipt.acts_count,
            sfx: receipt.sfx_cues_count,
          })}
        </span>
      </div>
      <Button
        size="sm"
        variant="secondary"
        icon={<Film className="size-3.5" />}
        onClick={() => setOpen(true)}
      >
        {t("skills.slotPreview.receiptCta")}
      </Button>
      {open && (
        <Suspense fallback={null}>
          <LazySlotPreviewDialog
            open={open}
            onOpenChange={setOpen}
            skillVersionId={receipt.skill_version_id}
            skillName={receipt.name}
          />
        </Suspense>
      )}
    </div>
  )
}

function ActivityEvidence({ receipt }: { receipt: ActivityReceipt }) {
  switch (receipt.kind) {
    case "video_review":
      return <VideoReviewEvidence receipt={receipt} />
    case "component":
      return <ComponentEvidence components={receipt.components} />
    case "video_revision":
      return <VideoRevisionEvidence receipt={receipt} />
    case "sfx_search":
      return <SfxSearchEvidence receipt={receipt} />
    case "sfx_import":
      return <SfxImportEvidence receipt={receipt} />
    case "music_search":
      return <MusicSearchEvidence receipt={receipt} />
    case "music_selection":
      return <MusicSelectionEvidence receipt={receipt} />
    case "skill_saved":
      return <SkillSavedEvidence receipt={receipt} />
  }
}

const callStatuses: Readonly<Record<string, ToolCallStatus | undefined>> = {
  accepted: "accepted", queued: "queued", active: "running", running: "running",
  completed: "success", succeeded: "success", failed: "error", cancelled: "cancelled",
  awaiting_authorization: "pending", declined: "denied", provider_unknown: "unknown",
  not_executed: "notExecuted",
}

function jobStatus(job: NativeJobReceipt): ToolCallStatus {
  if (job.status === "available") return job.role === "export" ? "outputGenerated" : "success"
  if (job.status === "dependencies_not_ready") return "notExecuted"
  return callStatuses[job.status] ?? "unknown"
}

function JobDetails({
  job,
  outputs,
  onOpen,
}: {
  job: NativeJobReceipt
  outputs?: Output[]
  onOpen?: (id: string) => void
}) {
  const { t } = useTranslation()
  const outputId = job.outputId
  const matchedOutput = outputId ? outputs?.find((item) => item.id === outputId) : undefined
  const showThumb = Boolean(outputId && job.role === "export" && job.status === "available" && onOpen)
  const aspect = matchedOutput ? outputAspect(matchedOutput) : 16 / 9
  const portrait = aspect < 1
  if (!job.error && !showThumb) return null
  return (
    <div className="mt-1.5 flex flex-col gap-1.5">
      {job.error && <p className="text-xs text-muted-foreground">{job.error}</p>}
      {showThumb && outputId && onOpen && (
        <button
          type="button"
          aria-label={t("common.preview")}
          onClick={() => onOpen(outputId)}
          className={
            portrait
              ? "group relative block h-28 w-fit overflow-hidden rounded-md border border-border bg-muted text-left transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-ring"
              : "group relative block w-36 overflow-hidden rounded-md border border-border bg-muted text-left transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-ring"
          }
          style={{ aspectRatio: aspect }}
        >
          {matchedOutput ? (
            <OutputPosterImage output={matchedOutput} />
          ) : (
            <span className="flex h-full w-full items-center justify-center text-muted-foreground">
              <Video className="size-4" />
            </span>
          )}
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/20 opacity-85 transition-opacity group-hover:opacity-100">
            <span className="flex size-7 items-center justify-center rounded-full bg-background/90 text-foreground shadow-sm">
              <Play className="ml-0.5 size-3.5 fill-current" />
            </span>
          </span>
        </button>
      )}
    </div>
  )
}

// Tool keys supply the verb even on thinner native frames with no copy key.
export const TOOL_ACTIONS: Readonly<Record<string, string>> = {
  // Composition creation & Skills
  create_video: "createVideo",
  save_composition_as_skill: "saveSkill",
  instantiate_skill_blueprint: "instantiateSkill",
  list_skill_shots: "skillRead",
  read_skill_reference: "skillRead",
  read_skill_demo: "skillRead",
  get_skill_preview: "skillPreview",
  // Timeline inspection & direct editing
  inspect_timeline: "inspectClips",
  inspect_clip: "inspectClip",
  insert_motion_block: "insertMotionBlock",
  update_motion_block: "updateMotionBlock",
  set_composition_style: "setCompositionStyle",
  insert_text: "insertText",
  edit_text: "editText",
  set_transition: "setTransition",
  insert_visual: "insertVisual",
  insert_audio: "insertAudio",
  edit_audio_clip: "editAudioClip",
  remove_clip: "removeClip",
  split_clip: "splitClip",
  trim_clip: "trimClip",
  move_clip: "moveClip",
  set_keyframe: "setKeyframe",
  translate: "translate",
  scale: "scale",
  extend_still: "extendStill",
  bind_clip_source: "bindClipSource",
  // Media generation & narration
  generate_voice: "recordVoice",
  generate_music: "generateMusic",
  generate_image: "generateImage",
  generate_sfx: "generateSfx",
  align_recording: "narrationPrepare",
  get_narration_alignment: "narrationRead",
  annotate_narration: "narrationAnnotate",
  // Materials, web capture, brand & music discovery
  prepare_video_materials: "videoMaterials",
  capture_web: "videoCapturePlan",
  analyze_brand: "brandAnalyze",
  search_web: "webSearch",
  get_web_page: "viewWebPage",
  load_skill: "skillRead",
  search_blocks: "searchBlocks",
  get_blocks: "getBlocks",
  search_text_presets: "searchTextPresets",
  get_text_presets: "getTextPresets",
  search_sfx_library: "searchSfxLibrary",
  get_sfx: "getSfx",
  get_music: "getMusic",
  get_voices: "getVoices",
  search_music: "musicSearch",
  show_music_candidates: "musicSearch",
  select_music: "musicSelection",
  search_voices: "voiceSearch",
  show_voice_candidates: "voiceSearch",
  select_voice: "voiceSelection",
  list_project_media: "listProjectMedia",
  get_asset: "inspectAsset",
  get_understanding: "inspectUnderstanding",
  search_transcript: "searchTranscript",
  read_conversation_context: "readHistory",
  // Preview, review, export & delivery
  preview_range: "previewRange",
  review_video: "videoReview",
  export_video: "exportVideo",
  deliver_video: "deliverVideo",
}

function CollapsibleReceipt({ receipt }: { receipt: ActivityReceipt }) {
  const { t } = useTranslation()
  return (
    <details className="ui-thinkc__receipt">
      <summary className="ui-thinkc__receipt-summary">
        <ChevronRight aria-hidden className="ui-thinkc__receipt-chevron" />
        <span>{t("chat.activityReceipt.details")}</span>
      </summary>
      <ActivityEvidence receipt={receipt} />
    </details>
  )
}

const INTERNAL_SCHEMA_ERROR_RE =
  /Invalid\s+\w+\s+props|Check\s+get_\w+|Field\s+required|Extra\s+inputs\s+are\s+not\s+permitted|Input\s+should\s+be|String\s+should\s+have|ValidationError|Include\s+the\s+complete\s+transition|Unknown\s+block_id|candidate_id|content_digest|base_version_id|already has these prop values/i

function visibleActivityError(error: string | undefined): string | undefined {
  if (!error) return undefined
  return INTERNAL_SCHEMA_ERROR_RE.test(error) ? undefined : error
}

function trailStep(
  entry: WorkTrailEntry,
  live: boolean,
  t: TFunction,
  onOpen?: (id: string) => void,
  outputs?: Output[],
): ThinkingTrailStep {
  if (entry.kind === "note") return { id: entry.rowKey, kind: "note", label: entry.text, status: "done" }
  const row = entry.activity
  const job = row.jobReceipt
  const receipt = row.receipt
  const status = job ? jobStatus(job) : callStatuses[row.call_state ?? row.status] ?? "unknown"
  const success = status === "success" || status === "outputGenerated"
  const running = live && status === "running"
  const failed = status === "error" || status === "unknown"
  const tool = row.tool_name ?? job?.operation
  const action = tool && TOOL_ACTIONS[tool]
  const toolLabel = tool ? t(`chat.toolName.${tool}`, { defaultValue: t("agentReceipt.job") }) : t("agentReceipt.job")
  let label = tool ? toolLabel : activityText(row, t)
  if (success || running) {
    const semantic = semanticActivityLabel(row.detail, success, t)
    if (semantic) label = semantic
    else if (action) label = t(`chat.activity.${action}${success ? "Done" : ""}`)
    else if (row.key) label = activityText(row, t)
  } else if (failed && !tool) {
    label = activityText({ ...row, status: "failed" }, t)
  }
  const chips: string[] = []
  if (receipt?.kind === "video_revision") chips.push(`v${receipt.version}`)
  if (receipt?.kind === "skill_saved") chips.push(`${receipt.name} v${receipt.version}`)
  if (receipt?.kind === "music_selection" || receipt?.kind === "sfx_import") chips.push(receipt.title)
  if (receipt?.kind === "music_search" || receipt?.kind === "sfx_search") chips.push(receipt.topic)
  if (row.name && !label.includes(row.name) && !chips.includes(row.name)) chips.push(row.name)
  let statusMeta: string | undefined
  if (success && receipt?.kind === "video_revision") statusMeta = t("agentReceipt.versionSaved")
  else if (status === "running" && !live) statusMeta = t("agentReceipt.unsettled")
  else if (status !== "success" && !running && !(failed && !tool && !job)) statusMeta = t(`agentReceipt.${status}`)
  const creditsMeta =
    job?.chargedCredits !== undefined
      ? t("agentReceipt.chargedCredits", { count: job.chargedCredits })
      : job?.reservedCredits !== undefined && job.reservedCredits > 0
        ? t("agentReceipt.reservedCredits", { count: job.reservedCredits })
        : undefined
  const duration = row.duration_ms != null ? formatElapsed(row.duration_ms) : undefined
  const cleanError = visibleActivityError(row.error)
  const hasJobMedia = Boolean(
    job &&
    (job.error || (job.outputId && job.role === "export" && job.status === "available" && onOpen)),
  )
  const hasDetail = Boolean((cleanError && cleanError !== job?.error) || hasJobMedia || receipt)
  return {
    id: entry.rowKey, label, chips, meta: [statusMeta, creditsMeta, duration].filter(Boolean).join(" · "),
    kind: failed ? "error" : row.assetType === "web_page" || row.key?.includes("viewWebPage") || tool === "capture_web" || tool === "search_web" || tool === "get_web_page" ? "web" : "step",
    status: failed ? "error" : running ? "running" : "done",
    detail: hasDetail ? (
      <>
        {cleanError && cleanError !== job?.error && <p className="text-xs text-muted-foreground">{cleanError}</p>}
        {hasJobMedia && job && <JobDetails job={job} outputs={outputs} onOpen={onOpen} />}
        {receipt && (
          receipt.kind === "skill_saved"
            ? <SkillSavedEvidence receipt={receipt} />
            : <CollapsibleReceipt receipt={receipt} />
        )}
      </>
    ) : undefined,
  }
}

export function StepsPlanCard({ steps }: { steps: StepPlanItem[] }) {
  const { t } = useTranslation()
  if (!steps.length) return null
  return (
    <Card
      as="section"
      data-testid="steps-plan-card"
      className="w-full"
      style={{
        ["--ui-crdc-pad" as string]: "12px 14px",
        ["--ui-crdc-radius" as string]: "12px",
      }}
    >
      <ul
        className="flex flex-col gap-2"
        aria-label={t("chat.steps.ariaLabel")}
      >
        {steps.map((item, idx) => (
          <li
            key={`${idx}:${item.title}`}
            data-status={item.status}
            className="flex items-center gap-2.5 text-[13px] leading-5"
          >
            <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden="true">
              {item.status === "done" ? (
                <CheckCircle2 className="size-3.5 text-muted-foreground/75" />
              ) : item.status === "in_progress" ? (
                <span className="ui-conv-dots">
                  <i className="bg-foreground/85" style={{ animationDelay: "0ms" }} />
                  <i className="bg-foreground/85" style={{ animationDelay: "180ms" }} />
                  <i className="bg-foreground/85" style={{ animationDelay: "180ms" }} />
                  <i className="bg-foreground/85" style={{ animationDelay: "360ms" }} />
                </span>
              ) : item.status === "failed" ? (
                <AlertCircle className="size-3.5 text-destructive" />
              ) : item.status === "skipped" ? (
                <MinusCircle className="size-3.5 text-muted-foreground/55" />
              ) : (
                <Circle className="size-3.5 text-muted-foreground/35" />
              )}
            </span>
            <span
              dir="auto"
              className={cn(
                "min-w-0 flex-1 break-words",
                item.status === "in_progress"
                  ? "font-medium text-foreground"
                  : item.status === "failed"
                    ? "text-destructive"
                    : item.status === "skipped"
                      ? "text-muted-foreground/65 line-through"
                      : "text-muted-foreground",
              )}
            >
              {item.title}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export function WorkSegmentRow({
  trail = [], elapsedMs, startedAtMs, liveLabel, postToolThinking, failure, recovered = false, onOpen, outputs, stepsPlan, attachedSteps,
}: {
  trail?: WorkTrailEntry[]
  elapsedMs?: number | null
  startedAtMs?: number | null
  liveLabel?: string | null
  postToolThinking?: { label: string; startedAtMs: number | null } | null
  failure?: ActivityRowFrame | null
  /** True when later steps in the same turn continued past this fold. */
  recovered?: boolean
  onOpen?: (id: string) => void
  outputs?: Output[]
  stepsPlan?: StepPlanItem[]
  /** Standalone macro step plan paired with this work segment: open above while
   * live/in-progress, collapsed to a compact toggle pill beside "Worked for …" once settled. */
  attachedSteps?: StepPlanItem[]
}) {
  const { t } = useTranslation()
  const live = liveLabel != null
  const rowRef = useRef<HTMLDivElement>(null)
  const anchor = useMessageScrollerViewportAnchor(rowRef, live)
  let error: ThinkingTrailStep | undefined
  let group: string | undefined
  const succeededTools = new Set<string>()
  for (const entry of trail) {
    if (
      entry.kind === "activity" &&
      entry.activity.tool_name &&
      entry.activity.status === "completed"
    ) {
      succeededTools.add(entry.activity.tool_name)
    }
  }
  const filteredTrail = trail.filter((entry) => {
    if (entry.kind !== "activity") return true
    const { status, call_state, tool_name, error: rawError, key, kind } = entry.activity
    // Synthetic non-tool repair/exhaustion markers ("这次没能完成 · 0s") belong
    // to the assistant's own status reply, never inside the tool work trail.
    if (!tool_name && (kind === "repair" || key === "chat.activity.repair")) {
      return false
    }
    // Hide self-healed internal schema validation retries and non-batchable
    // sibling skips once the same tool runs or succeeds in the segment.
    if (
      call_state === "not_executed" &&
      !entry.activity.jobReceipt &&
      (tool_name === "ask_user" ||
        tool_name === "answer" ||
        (tool_name &&
          trail.some(
            (other) =>
              other !== entry &&
              other.kind === "activity" &&
              other.activity.tool_name === tool_name &&
              other.activity.group_id !== entry.activity.group_id &&
              (other.activity.status === "completed" || other.activity.status === "active"),
          )))
    ) {
      return false
    }
    if (
      status === "failed" &&
      tool_name &&
      succeededTools.has(tool_name) &&
      (!rawError || INTERNAL_SCHEMA_ERROR_RE.test(rawError))
    ) {
      return false
    }
    return true
  })
  const steps = filteredTrail.map(entry => {
    const step = trailStep(entry, live, t, onOpen, outputs)
    if (entry.kind === "activity" && (entry.activity.status !== "cancelled" || step.kind === "error")) {
      // Keep failures in the final batch visible. A later successful call
      // leaves earlier errors inspectable inside the completed trail.
      if (!group || group !== entry.activity.group_id) error = undefined
      if (step.kind === "error") error = step
      group = entry.activity.group_id
    }
    return step
  })
  if (live && postToolThinking) {
    steps.push({
      id: "__post_tool_thinking__",
      kind: "thinking",
      label: postToolThinking.label,
      status: "running",
      startedAtMs: postToolThinking.startedAtMs,
    })
  }
  if (failure && !(!failure.tool_name && (failure.kind === "repair" || failure.key === "chat.activity.repair"))) {
    error = trailStep({ kind: "activity", activity: failure, rowKey: failure.activity_id }, false, t, onOpen)
    steps.push(error)
  }
  const elapsed = elapsedMs != null ? formatElapsed(elapsedMs) : null
  const header = liveLabel ?? (error && !recovered
    ? [error.label, error.meta].filter(Boolean).join(" · ")
    : elapsed ? t("chat.activityFold.worked", { elapsed }) : t("chat.activityFold.workedWithoutTime"))
  const [override, setOverride] = useState<{ live: boolean; open: boolean } | null>(null)
  if (override && override.live !== live) setOverride(null)
  // All status rows default collapsed (both live and settled); users can click
  // any row to inspect its underlying tool trail on demand. While live and
  // collapsed, surface the latest stage notes as a clean narrative brief stream
  // that automatically folds away into the single "Worked for …" row on finish.
  const open = override?.live === live ? override.open : false
  const hasAttachedSteps = Boolean(attachedSteps && attachedSteps.length >= 2)
  const attachedStepsSettled =
    hasAttachedSteps &&
    !live &&
    !attachedSteps!.some((s) => s.status === "in_progress" || s.status === "failed")
  const doneStepsCount = stepsPlan?.filter((s) => s.status === "done").length ?? 0
  const stepsProgressLabel =
    stepsPlan && stepsPlan.length > 0
      ? t("chat.activityFold.stepsProgress", { done: doneStepsCount, total: stepsPlan.length })
      : undefined
  const [fallbackLiveStartMs, setFallbackLiveStartMs] = useState<number | null>(() =>
    live && startedAtMs == null ? Date.now() : null,
  )
  useEffect(() => {
    if (live && startedAtMs == null) {
      setFallbackLiveStartMs((prev) => prev ?? Date.now())
    } else {
      setFallbackLiveStartMs(null)
    }
  }, [live, startedAtMs])
  const effectiveStartedAtMs = startedAtMs ?? fallbackLiveStartMs
  return (
    <div ref={rowRef}>
      {hasAttachedSteps && !attachedStepsSettled && attachedSteps ? (
        <div className="mb-2.5">
          <StepsPlanCard steps={attachedSteps} />
        </div>
      ) : null}
      <ThinkingState steps={steps} live={live} headerLabel={header} startedAtMs={effectiveStartedAtMs}
        open={open}
        stepsPlan={stepsPlan}
        stepsProgressLabel={stepsProgressLabel}
        stepsAriaLabel={t("chat.steps.ariaLabel")}
        onOpenChange={nextOpen => {
          anchor(rowRef.current)
          setOverride({ live, open: nextOpen })
        }}
      />
    </div>
  )
}
