/** User-visible work and receipts, projected from the original transcript. */
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { ChevronRight, TriangleAlert } from "lucide-react"

import type {
  ActivityReceipt,
  WorkTrailEntry,
  ActivityRowFrame,
  ComponentClipReceipt,
  NativeJobReceipt,
  NowRowPayload,
  MusicSearchReceipt,
  MusicSelectionReceipt,
  SfxImportReceipt,
  SfxSearchReceipt,
  ToolCallStatus,
  VideoReviewReceipt,
  VideoRevisionReceipt,
} from "./timeline/types"
import { activityCategoryKey, activityFailureKey } from "./timeline/activity"
import { formatElapsed } from "@/components/chat/workTiming"
import { useMessageScrollerViewportAnchor } from "@/components/chat/MessageScroller"
import { Button } from "@/components/ui/button-clean"
import { ThinkingState, type ThinkingTrailStep } from "@/components/ui/thinking-state-clean"
import { cn } from "@/lib/utils"

export type { NowRowPayload } from "./timeline/types"

export function activityText(activity: NowRowPayload, t: TFunction): string {
  const { status } = activity
  if (activity.jobReceipt) {
    const jobState = jobStatus(activity.jobReceipt)
    if (jobState !== "running" && jobState !== "success" && jobState !== "outputGenerated") {
      return t(`agentReceipt.${jobState}`)
    }
  }
  if (activity.call_state === "queued") return t("agentReceipt.queued")
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

function JobDetails({ job, onOpen }: { job: NativeJobReceipt; onOpen?: (id: string) => void }) {
  const { t } = useTranslation()
  const output = job.outputId
  return (
    <>
      {job.error && <p>{job.error}</p>}
      {job.chargedCredits !== undefined && <p>{t("agentReceipt.chargedCredits", { count: job.chargedCredits })}</p>}
      {job.reservedCredits !== undefined && job.reservedCredits > 0 && (
        <p>{t("agentReceipt.reservedCredits", { count: job.reservedCredits })}</p>
      )}
      {output && job.role === "export" && job.status === "available" && onOpen && (
        <Button size="sm" variant="secondary" onClick={() => onOpen(output)}>{t("common.preview")}</Button>
      )}
    </>
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
  search_music: "musicSearch",
  show_music_candidates: "musicSearch",
  select_music: "musicSelection",
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

function trailStep(entry: WorkTrailEntry, live: boolean, t: TFunction, onOpen?: (id: string) => void): ThinkingTrailStep {
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
    if (action) label = t(`chat.activity.${action}${success ? "Done" : ""}`)
    else if (row.key) label = activityText(row, t)
  } else if (failed && !tool) {
    label = activityText({ ...row, status: "failed" }, t)
  }
  const chips: string[] = []
  if (receipt?.kind === "video_revision") chips.push(`v${receipt.version}`)
  if (receipt?.kind === "music_selection" || receipt?.kind === "sfx_import") chips.push(receipt.title)
  if (receipt?.kind === "music_search" || receipt?.kind === "sfx_search") chips.push(receipt.topic)
  if (row.name && !label.includes(row.name) && !chips.includes(row.name)) chips.push(row.name)
  let statusMeta: string | undefined
  if (success && receipt?.kind === "video_revision") statusMeta = t("agentReceipt.versionSaved")
  else if (status === "running" && !live) statusMeta = t("agentReceipt.unsettled")
  else if (status !== "success" && !running && !(failed && !tool && !job)) statusMeta = t(`agentReceipt.${status}`)
  const duration = row.duration_ms != null ? formatElapsed(row.duration_ms) : undefined
  const hasDetail = Boolean((row.error && row.error !== job?.error) || job || receipt)
  return {
    id: entry.rowKey, label, chips, meta: [statusMeta, duration].filter(Boolean).join(" · "),
    kind: failed ? "error" : row.assetType === "web_page" || row.key?.includes("viewWebPage") || tool === "capture_web" ? "web" : "step",
    status: failed ? "error" : running ? "running" : "done",
    detail: hasDetail ? (
      <>
        {row.error && row.error !== job?.error && <p>{row.error}</p>}
        {job && <JobDetails job={job} onOpen={onOpen} />}
        {receipt && <CollapsibleReceipt receipt={receipt} />}
      </>
    ) : undefined,
  }
}

export function WorkSegmentRow({
  trail = [], elapsedMs, startedAtMs, liveLabel, postToolThinking, failure, onOpen,
}: {
  trail?: WorkTrailEntry[]
  elapsedMs?: number | null
  startedAtMs?: number | null
  liveLabel?: string | null
  postToolThinking?: { label: string; startedAtMs: number | null } | null
  failure?: ActivityRowFrame | null
  onOpen?: (id: string) => void
}) {
  const { t } = useTranslation()
  const live = liveLabel != null
  const rowRef = useRef<HTMLDivElement>(null)
  const anchor = useMessageScrollerViewportAnchor(rowRef, live)
  let error: ThinkingTrailStep | undefined
  let group: string | undefined
  const steps = trail.map(entry => {
    const step = trailStep(entry, live, t, onOpen)
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
  if (failure) {
    error = trailStep({ kind: "activity", activity: failure, rowKey: failure.activity_id }, false, t, onOpen)
    steps.push(error)
  }
  const elapsed = elapsedMs != null ? formatElapsed(elapsedMs) : null
  const header = liveLabel ?? (error
    ? [error.label, error.meta].filter(Boolean).join(" · ")
    : elapsed ? t("chat.activityFold.worked", { elapsed }) : t("chat.activityFold.workedWithoutTime"))
  const [override, setOverride] = useState<{ live: boolean; open: boolean } | null>(null)
  if (override && override.live !== live) setOverride(null)
  const open = override?.live === live ? override.open : live
  return (
    <div ref={rowRef}>
      <ThinkingState steps={steps} live={live} headerLabel={header} startedAtMs={startedAtMs}
        open={open}
        onOpenChange={nextOpen => {
          anchor(rowRef.current)
          setOverride({ live, open: nextOpen })
        }}
      />
    </div>
  )
}
