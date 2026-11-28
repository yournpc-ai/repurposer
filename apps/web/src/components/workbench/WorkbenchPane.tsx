"use client"

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react"
import {
  Check,
  Copy,
  Crop,
  Download,
  FileText,
  Film,
  Image as ImageIcon,
  MessageSquarePlus,
  Play,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  Video as VideoIcon,
  X,
} from "@/components/ui/icons"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Streamdown } from "streamdown"

import { MediaRegionSelectionOverlay } from "@/components/results/MediaRegionSelectionOverlay"
import { Badge } from "@/components/ui/badge-clean"
import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { EmptyState } from "@/components/ui/empty-state-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { Select } from "@/components/ui/select-clean"
import { Loading, Skeleton } from "@/components/ui/skeleton-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { useIsMobile } from "@/hooks/use-mobile"
import { apiFetch } from "@/lib/api"
import type { MediaRegionSelection } from "@/lib/mediaRegionSelection"
import { cn, formatDuration, formatTimestamp } from "@/lib/utils"
import type { WorkbenchAsset, WorkbenchOutput } from "@/lib/workbench"
import {
  useWorkbench,
  type WorkbenchArtifact,
  type WorkbenchPresetKind,
} from "./WorkbenchContext"

const LazyWorkbenchDraftPlayer = lazy(() =>
  import("./WorkbenchDraftPlayer").then((m) => ({
    default: m.WorkbenchDraftPlayer,
  })),
)

const LazySlotPreviewContent = lazy(() =>
  import("@/components/skills/SlotPreviewDialog").then((m) => ({
    default: m.SlotPreviewContent,
  })),
)

const VisualPresetGalleryPanel = lazy(() => import("./VisualPresetGalleryPanel"))
const MusicLibraryPanel = lazy(() => import("./MusicLibraryPanel"))
const VoiceLibraryPanel = lazy(() => import("./VoiceLibraryPanel"))
const SoundLabPanel = lazy(() => import("./SoundLabPanel"))

const WIDTH_STORAGE_KEY = "repurposer-workbench-width"
const DEFAULT_WIDTH = 480
const MIN_WIDTH = 360
const MAX_SCRUB_WINDOW_S = 12

interface RawStoryboardScene {
  scene_id?: string
  number?: number
  label?: string | null
  intent?: string | null
  visual_description?: string | null
  description?: string | null
  narration?: string | null
  block_id?: string | null
  visual_highlights?: string[] | null
  transition_after?: string | null
  sfx_count?: number | null
  duration_seconds?: number
  start_seconds?: number
  end_seconds?: number
  range_seconds?: { start?: number; end?: number }
}

interface NormalizedScene {
  id: string
  number: number
  title: string
  blockId: string | null
  blockRole: string | null
  summary: string | null
  narration: string | null
  visualHighlights: string[]
  transitionAfter: string | null
  sfxCount: number
  startSeconds: number
  endSeconds: number
  durationSeconds: number
}

interface StoryboardResponse {
  composition_id: string
  composition_version_id: string
  version: number
  content_digest: string
  video_preview?: {
    status: "ready" | "pending_media" | "unavailable"
    video_spec?: unknown
  }
  storyboard?: {
    duration_seconds?: number
    scenes?: RawStoryboardScene[]
  }
  scenes?: RawStoryboardScene[]
}

function resolveOutputVideoUrl(
  output: WorkbenchOutput | undefined,
): string | null {
  if (!output?.files) return null
  for (const key of ["video", "mp4", "stream", "url", "final"]) {
    const val = output.files[key]
    if (typeof val === "string" && val.trim()) return val
  }
  const firstVideo = Object.values(output.files).find(
    (v): v is string =>
      typeof v === "string" && /\.(mp4|webm|mov)(\?|$)/i.test(v),
  )
  return firstVideo ?? null
}

function resolveOutputPosterUrl(
  output: WorkbenchOutput | undefined,
): string | null {
  if (!output?.files) return null
  for (const key of ["poster", "thumbnail", "cover", "image"]) {
    const val = output.files[key]
    if (typeof val === "string" && val.trim()) return val
  }
  return null
}

function normalizeScenes(
  raw: RawStoryboardScene[] | undefined,
  fallbackScenePrefix: string,
  opts?: {
    compName?: string | null
    translate?: (key: string, options?: Record<string, unknown>) => string
  },
): NormalizedScene[] {
  if (!raw || raw.length === 0) return []
  const normalizedCompName = opts?.compName?.trim().toLowerCase() || ""
  let cursor = 0
  return raw.map((scene, idx) => {
    const start =
      typeof scene.range_seconds?.start === "number"
        ? scene.range_seconds.start
        : typeof scene.start_seconds === "number"
          ? scene.start_seconds
          : cursor
    const rawDuration =
      typeof scene.range_seconds?.end === "number"
        ? Math.max(0, scene.range_seconds.end - start)
        : typeof scene.end_seconds === "number"
          ? Math.max(0, scene.end_seconds - start)
          : typeof scene.duration_seconds === "number"
            ? Math.max(0, scene.duration_seconds)
            : 0
    const end =
      typeof scene.range_seconds?.end === "number"
        ? scene.range_seconds.end
        : typeof scene.end_seconds === "number"
          ? scene.end_seconds
          : start + rawDuration
    cursor = Math.max(cursor, end)

    const number = typeof scene.number === "number" ? scene.number : idx + 1
    const blockId = scene.block_id?.trim() || null
    const rawRole =
      blockId && opts?.translate
        ? opts.translate(`workbench.storyboard.blockRoles.${blockId}`, {
            defaultValue: "",
          })
        : ""
    const blockRole =
      rawRole && !rawRole.startsWith("workbench.storyboard.blockRoles.")
        ? rawRole
        : null

    const rawTitle = scene.label?.trim() || scene.intent?.trim() || ""
    const isRedundantCompName =
      Boolean(normalizedCompName) &&
      rawTitle.toLowerCase() === normalizedCompName
    const title =
      (!isRedundantCompName && rawTitle) ||
      blockRole ||
      `${fallbackScenePrefix} ${number}`
    const summary =
      scene.visual_description?.trim() ||
      scene.description?.trim() ||
      null
    const narration = scene.narration?.trim() || null
    const visualHighlights = Array.isArray(scene.visual_highlights)
      ? scene.visual_highlights.filter(
          (item): item is string => typeof item === "string" && item.trim().length > 0,
        )
      : []
    const transitionRaw = scene.transition_after?.trim() || null
    const transitionTranslated =
      transitionRaw && opts?.translate
        ? opts.translate(`workbench.storyboard.transitions.${transitionRaw}`, {
            defaultValue: transitionRaw,
          })
        : transitionRaw
    const transitionAfter =
      transitionTranslated &&
      !transitionTranslated.startsWith("workbench.storyboard.transitions.")
        ? transitionTranslated
        : transitionRaw

    return {
      id: scene.scene_id ?? `scene-${number}`,
      number,
      title,
      blockId,
      blockRole,
      summary,
      narration,
      visualHighlights,
      transitionAfter,
      sfxCount: typeof scene.sfx_count === "number" ? scene.sfx_count : 0,
      startSeconds: start,
      endSeconds: end,
      durationSeconds: rawDuration > 0 ? rawDuration : Math.max(0, end - start),
    }
  })
}

function formatTimeRange(start: number, end: number): string {
  return `${formatTimestamp(Math.max(0, start))}–${formatTimestamp(Math.max(start, end))}`
}

function DirectorSceneList({
  scenes,
  activeSceneId,
  onSelectScene,
  onCiteScene,
}: {
  scenes: NormalizedScene[]
  activeSceneId: string | null
  onSelectScene?: (scene: NormalizedScene) => void
  onCiteScene?: (scene: NormalizedScene) => void
}) {
  const { t } = useTranslation()
  if (scenes.length === 0) return null

  return (
    <div className="flex flex-col gap-2 pt-1">
      <div className="flex items-center justify-between text-[11px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
        <span>
          {t("workbench.player.scenesHeading")} ({scenes.length})
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {scenes.map((scene) => {
          const isActive = activeSceneId === scene.id
          const secondaryText = scene.summary || scene.narration
          return (
            <div
              key={scene.id}
              className={cn(
                "group flex items-start gap-2.5 rounded-lg border px-2.5 py-2 text-xs transition-colors",
                isActive
                  ? "border-foreground/25 bg-accent"
                  : "border-subtle bg-card hover:bg-accent/60",
              )}
            >
              <button
                type="button"
                onClick={() => onSelectScene?.(scene)}
                className="flex min-w-0 flex-1 items-start gap-2.5 text-left focus-visible:outline-2 focus-visible:outline-ring"
              >
                <span className="mt-0.5 shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                  {String(scene.number).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-medium text-foreground">
                      {scene.title}
                    </span>
                    {scene.durationSeconds > 0 ? (
                      <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                        {formatTimeRange(scene.startSeconds, scene.endSeconds)}
                      </span>
                    ) : null}
                  </div>
                  {secondaryText ? (
                    <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                      {secondaryText}
                    </p>
                  ) : null}
                </div>
              </button>
              {onCiteScene ? (
                <IconButton
                  size="sm"
                  variant="ghost"
                  icon={<MessageSquarePlus className="size-3.5" />}
                  label={t("workbench.player.citeScene")}
                  onClick={() => onCiteScene(scene)}
                  className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 group-has-[:focus-visible]:opacity-100 max-md:opacity-100"
                />
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function OutputArtifactView({
  outputId,
  initialSelectRegion = false,
  seekSeconds,
  seekNonce,
}: {
  outputId: string
  initialSelectRegion?: boolean
  seekSeconds?: number
  seekNonce?: number
}) {
  const { t } = useTranslation()
  const { workbench, openArtifact, citeMention } = useWorkbench()

  const output = useMemo(
    () => (workbench?.outputs ?? []).find((o) => o.id === outputId) ?? null,
    [workbench?.outputs, outputId],
  )
  const videoUrl = resolveOutputVideoUrl(output ?? undefined)
  const posterUrl = resolveOutputPosterUrl(output ?? undefined)

  const matchingComp = useMemo(() => {
    if (!output?.composition_id) return workbench?.compositions[0] ?? null
    return (
      (workbench?.compositions ?? []).find(
        (c) => c.composition_id === output.composition_id,
      ) ?? null
    )
  }, [workbench?.compositions, output?.composition_id])

  const hasNewerDraft = Boolean(
    matchingComp?.current_version_id &&
      output?.composition_version_id &&
      matchingComp.current_version_id !== output.composition_version_id,
  )

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [selecting, setSelecting] = useState(initialSelectRegion)
  const [region, setRegion] = useState<MediaRegionSelection | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [scenes, setScenes] = useState<NormalizedScene[]>([])

  useEffect(() => {
    setRegion(null)
    setSelecting(initialSelectRegion)
    setCurrentTime(0)
  }, [outputId, initialSelectRegion])

  useEffect(() => {
    if (seekSeconds == null || seekNonce == null) return
    const target = Math.max(0, seekSeconds)
    if (videoRef.current) {
      videoRef.current.currentTime = target
      void videoRef.current.play().catch(() => {})
    }
    setCurrentTime(target)
  }, [seekSeconds, seekNonce])

  useEffect(() => {
    const versionId = output?.composition_version_id
    if (!versionId) {
      setScenes([])
      return
    }
    let cancelled = false
    void apiFetch(`/api/v1/chat/video/versions/${versionId}/storyboard`, {
      toast: false,
    })
      .then(async (res) => {
        if (!res.ok) return
        const data = (await res.json()) as StoryboardResponse
        if (!cancelled) {
          setScenes(
            normalizeScenes(
              data.storyboard?.scenes ?? data.scenes,
              t("workbench.player.scenePrefix"),
              { compName: matchingComp?.name, translate: t },
            ),
          )
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [output?.composition_version_id, matchingComp?.name, t])

  const activeScene = useMemo(() => {
    if (scenes.length === 0) return null
    return (
      scenes.find(
        (s) => currentTime >= s.startSeconds && currentTime < s.endSeconds,
      ) ?? scenes[0]
    )
  }, [scenes, currentTime])

  const totalSceneDuration = useMemo(
    () => scenes.reduce((acc, s) => Math.max(acc, s.endSeconds), 0),
    [scenes],
  )

  const label = matchingComp?.name || t("workbench.chip.output")

  const handleToggleRegion = () => {
    setSelecting((prev) => {
      const next = !prev
      if (next && videoRef.current && !videoRef.current.paused) {
        videoRef.current.pause()
      }
      if (!next) setRegion(null)
      return next
    })
  }

  const handleCite = useCallback(
    (includeRegion: boolean) => {
      if (!output) return
      const ok = citeMention({
        type: "output",
        id: output.id,
        label,
        ...(includeRegion && region ? { region } : {}),
      })
      if (ok) {
        toast.success(t("workbench.inspector.regionCited"))
        if (includeRegion) {
          setRegion(null)
          setSelecting(false)
        }
      }
    },
    [output, citeMention, label, region, t],
  )

  const openStoryboardTab = useCallback(() => {
    if (!output?.composition_version_id) return
    openArtifact({
      key: `storyboard:${output.composition_version_id}`,
      kind: "storyboard",
      versionId: output.composition_version_id,
      title: t("workbench.storyboard.shortTabTitle"),
    })
  }, [output?.composition_version_id, openArtifact, t])

  if (!output || !videoUrl) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          bare
          icon={<Film className="size-5" />}
          title={t("workbench.player.noOutputs")}
          text={t("workbench.player.emptyText")}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4 thin-scroll">
      {hasNewerDraft && matchingComp?.current_version_id ? (
        <div className="flex shrink-0 items-center justify-between gap-2 rounded-lg border border-subtle bg-muted px-3 py-2 text-xs">
          <span className="text-muted-foreground">
            {t("workbench.player.newerDraftAvailable")}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              openArtifact({
                key: `version:${matchingComp.current_version_id!}`,
                kind: "version",
                versionId: matchingComp.current_version_id!,
                title: matchingComp.name ?? undefined,
              })
            }
          >
            {t("workbench.player.switchToDraft")}
          </Button>
        </div>
      ) : null}

      {/* Full-length Video Stage with inline Pause-and-Select Region */}
      <div className="relative shrink-0 overflow-hidden rounded-lg border border-subtle bg-black">
        <video
          key={output.id}
          ref={videoRef}
          src={videoUrl}
          poster={posterUrl ?? undefined}
          controls={!selecting}
          playsInline
          onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
          className="aspect-video w-full object-contain"
        />
        <MediaRegionSelectionOverlay
          mediaRef={videoRef}
          control={{
            enabled: selecting,
            value: region,
            onChange: setRegion,
            onReselect: () => setRegion(null),
            onCancel: () => {
              setRegion(null)
              setSelecting(false)
            },
            onDone: () => handleCite(true),
          }}
        />
      </div>

      {/* Compact Chapter Strip + Active Scene Cue (full script lives in its own Storyboard tab) */}
      {scenes.length > 0 && activeScene ? (
        <div className="flex shrink-0 flex-col gap-2 rounded-lg border border-subtle bg-card/60 px-3 py-2.5">
          {totalSceneDuration > 0 ? (
            <div className="flex h-1.5 w-full items-center gap-0.5">
              {scenes.map((scene) => {
                const isActive = scene.id === activeScene.id
                const flexGrow = Math.max(0.4, scene.durationSeconds)
                return (
                  <button
                    key={scene.id}
                    type="button"
                    title={`${String(scene.number).padStart(2, "0")} · ${scene.title} (${formatTimeRange(scene.startSeconds, scene.endSeconds)})`}
                    aria-label={t("workbench.storyboard.jumpToScene", {
                      range: formatTimeRange(scene.startSeconds, scene.endSeconds),
                    })}
                    onClick={() => {
                      if (videoRef.current) {
                        videoRef.current.currentTime = scene.startSeconds
                        setCurrentTime(scene.startSeconds)
                      }
                    }}
                    style={{ flexGrow }}
                    className={cn(
                      "h-full rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                      isActive
                        ? "bg-foreground"
                        : "bg-foreground/15 hover:bg-foreground/35",
                    )}
                  />
                )
              })}
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-2 text-xs">
            <div className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                {String(activeScene.number).padStart(2, "0")}/{String(scenes.length).padStart(2, "0")}
              </span>
              <span className="truncate font-medium text-foreground">
                {activeScene.title}
              </span>
            </div>
            <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
              {formatTimeRange(activeScene.startSeconds, activeScene.endSeconds)}
            </span>
          </div>
        </div>
      ) : null}

      {/* Clean Single-Row Action Bar */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            size="sm"
            variant={selecting ? "primary" : "secondary"}
            icon={<Crop className="size-3.5" />}
            onClick={handleToggleRegion}
          >
            {t(
              selecting
                ? "workbench.inspector.selectingRegion"
                : "workbench.inspector.selectRegion",
            )}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            icon={<MessageSquarePlus className="size-3.5" />}
            onClick={() => handleCite(Boolean(region))}
          >
            {t(
              region
                ? "workbench.inspector.citeRegionInChat"
                : "workbench.inspector.citeInChat",
            )}
          </Button>
          {output.composition_version_id ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<FileText className="size-3.5" />}
              onClick={openStoryboardTab}
            >
              {t("workbench.storyboard.openAction")}
            </Button>
          ) : null}
        </div>
        <a
          href={videoUrl}
          download
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex"
        >
          <Button
            size="sm"
            variant="secondary"
            icon={<Download className="size-3.5" />}
          >
            {t("workbench.player.download")}
          </Button>
        </a>
      </div>

      {selecting ? (
        <p className="text-[11px] text-muted-foreground">
          {t("workbench.inspector.dragRegionHint")}
        </p>
      ) : null}
    </div>
  )
}

function VersionArtifactView({
  versionId,
  initialStartSeconds,
  initialEndSeconds,
}: {
  versionId: string
  initialStartSeconds?: number
  initialEndSeconds?: number
}) {
  const { t } = useTranslation()
  const { workbench, setSelectedVersionId, openArtifact, citeText } =
    useWorkbench()

  const allVersions = useMemo(() => {
    const list: {
      compositionId: string
      compositionName: string
      version_id: string
      version: number
      duration_seconds: number
      style_preset: string | null
      is_head: boolean
    }[] = []
    for (const comp of workbench?.compositions ?? []) {
      for (const ver of comp.versions) {
        list.push({
          compositionId: comp.composition_id,
          compositionName: comp.name || t("workbench.tabs.player"),
          ...ver,
        })
      }
    }
    return list
  }, [workbench?.compositions, t])

  const activeVersion =
    allVersions.find((v) => v.version_id === versionId) ??
    allVersions[0] ??
    null

  const matchingOutput = useMemo(() => {
    const outputs = (workbench?.outputs ?? []).filter((o) =>
      Boolean(resolveOutputVideoUrl(o)),
    )
    if (!activeVersion) return outputs[0] ?? null
    return (
      outputs.find(
        (o) => o.composition_version_id === activeVersion.version_id,
      ) ??
      outputs.find((o) => o.composition_id === activeVersion.compositionId) ??
      null
    )
  }, [workbench?.outputs, activeVersion])

  const totalDuration = Math.max(
    1,
    Number(activeVersion?.duration_seconds) || MAX_SCRUB_WINDOW_S,
  )

  const [windowRange, setWindowRange] = useState<{ start: number; end: number }>(
    () => {
      const start = Math.max(0, initialStartSeconds ?? 0)
      const requestedEnd =
        initialEndSeconds ?? Math.min(totalDuration, start + MAX_SCRUB_WINDOW_S)
      const end = Math.min(
        totalDuration,
        Math.max(start + 1, Math.min(start + MAX_SCRUB_WINDOW_S, requestedEnd)),
      )
      return { start, end }
    },
  )

  useEffect(() => {
    const start = Math.max(0, initialStartSeconds ?? 0)
    const requestedEnd =
      initialEndSeconds ?? Math.min(totalDuration, start + MAX_SCRUB_WINDOW_S)
    const end = Math.min(
      totalDuration,
      Math.max(start + 1, Math.min(start + MAX_SCRUB_WINDOW_S, requestedEnd)),
    )
    setWindowRange({ start, end })
  }, [versionId, initialStartSeconds, initialEndSeconds, totalDuration])

  const [storyboard, setStoryboard] = useState<StoryboardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadNonce, setReloadNonce] = useState(0)
  const [seekRequest, setSeekRequest] = useState<{
    localSeconds: number
    nonce: number
  } | null>(null)
  const [playheadSeconds, setPlayheadSeconds] = useState(0)

  useEffect(() => {
    if (!activeVersion) {
      setStoryboard(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    const scrubParam = encodeURIComponent(
      JSON.stringify({
        kind: "range",
        start_seconds: windowRange.start,
        end_seconds: windowRange.end,
      }),
    )
    const load = async () => {
      try {
        let res = await apiFetch(
          `/api/v1/chat/video/versions/${activeVersion.version_id}/storyboard?scrub=${scrubParam}`,
          { toast: false },
        )
        if (!res.ok) {
          res = await apiFetch(
            `/api/v1/chat/video/versions/${activeVersion.version_id}/storyboard`,
            { toast: false },
          )
        }
        if (!res.ok) throw new Error(t("workbench.player.loadError"))
        const data = (await res.json()) as StoryboardResponse
        if (!cancelled) {
          setStoryboard(data)
          setPlayheadSeconds(windowRange.start)
          setLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : t("workbench.player.loadError"),
          )
          setLoading(false)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [activeVersion, windowRange.start, windowRange.end, reloadNonce, t])

  const scenes = useMemo(
    () =>
      normalizeScenes(
        storyboard?.storyboard?.scenes ?? storyboard?.scenes,
        t("workbench.player.scenePrefix"),
        { compName: activeVersion?.compositionName, translate: t },
      ),
    [storyboard, activeVersion?.compositionName, t],
  )

  const activeSceneId = useMemo(() => {
    const hit = scenes.find(
      (s) => playheadSeconds >= s.startSeconds && playheadSeconds < s.endSeconds,
    )
    return hit?.id ?? null
  }, [scenes, playheadSeconds])

  const handleSelectScene = useCallback(
    (scene: NormalizedScene) => {
      if (
        scene.startSeconds >= windowRange.start &&
        scene.startSeconds < windowRange.end
      ) {
        setSeekRequest((prev) => ({
          localSeconds: scene.startSeconds - windowRange.start,
          nonce: (prev?.nonce ?? 0) + 1,
        }))
        setPlayheadSeconds(scene.startSeconds)
        return
      }
      const nextStart = Math.max(0, scene.startSeconds)
      const nextEnd = Math.min(
        totalDuration,
        Math.max(
          nextStart + 1,
          Math.min(nextStart + MAX_SCRUB_WINDOW_S, Math.max(scene.endSeconds, nextStart + 6)),
        ),
      )
      setWindowRange({ start: nextStart, end: nextEnd })
    },
    [windowRange.start, windowRange.end, totalDuration],
  )

  const handleCiteScene = useCallback(
    (scene: NormalizedScene) => {
      const citation = t("workbench.player.sceneCitation", {
        number: scene.number,
        range: formatTimeRange(scene.startSeconds, scene.endSeconds),
        title: scene.title,
      })
      if (citeText(citation)) {
        toast.success(t("workbench.inspector.regionCited"))
      }
    },
    [citeText, t],
  )

  if (!activeVersion) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          bare
          icon={<Film className="size-5" />}
          title={t("workbench.player.emptyTitle")}
          text={t("workbench.player.emptyText")}
        />
      </div>
    )
  }

  const previewSpec =
    storyboard?.video_preview?.status === "ready"
      ? storyboard.video_preview.video_spec
      : null
  const isPartialWindow = totalDuration > MAX_SCRUB_WINDOW_S + 0.1
  const exactOutputMatches =
    matchingOutput?.composition_version_id === activeVersion.version_id

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4 thin-scroll">
      {/* Quiet Version Metadata & Switcher */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium text-foreground">
            {activeVersion.compositionName}
          </span>
          {activeVersion.style_preset ? (
            <Badge tone="neutral" size="sm">
              {t(`skills.picker.styles.${activeVersion.style_preset}`, {
                defaultValue: activeVersion.style_preset,
              })}
            </Badge>
          ) : null}
        </div>
        <div className="flex items-center gap-1.5">
          {allVersions.length > 1 ? (
            <Select
              size="sm"
              aria-label={t("workbench.player.versionLabel")}
              value={activeVersion.version_id}
              onChange={(val) => setSelectedVersionId(val)}
              options={allVersions.map((v) => ({
                value: v.version_id,
                label: t("workbench.player.versionOption", {
                  version: v.version,
                  duration: Math.round(v.duration_seconds * 10) / 10,
                }),
                description: v.is_head
                  ? t("workbench.player.latestBadge")
                  : undefined,
              }))}
            />
          ) : (
            <span className="tabular-nums">
              {`v${activeVersion.version} · ${Math.round(activeVersion.duration_seconds * 10) / 10}s`}
            </span>
          )}
        </div>
      </div>

      {/* Main Live Draft Stage */}
      <div className="shrink-0">
        {loading ? (
          <Loading label={t("common.loading")} className="aspect-video w-full">
            <Skeleton width="100%" height="100%" radius={10} />
          </Loading>
        ) : error ? (
          <div className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-lg border border-subtle bg-muted p-4 text-center">
            <p className="text-xs text-muted-foreground">{error}</p>
            <Button
              size="sm"
              variant="secondary"
              icon={<RefreshCw className="size-3.5" />}
              onClick={() => setReloadNonce((n) => n + 1)}
            >
              {t("workbench.player.retry")}
            </Button>
          </div>
        ) : previewSpec ? (
          <Suspense
            fallback={
              <Loading label={t("common.loading")} className="aspect-video w-full">
                <Skeleton width="100%" height="100%" radius={10} />
              </Loading>
            }
          >
            <LazyWorkbenchDraftPlayer
              rawSpec={previewSpec}
              windowStartSeconds={windowRange.start}
              seekRequest={seekRequest}
              onTimeSecondsChange={setPlayheadSeconds}
            />
          </Suspense>
        ) : (
          <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-lg border border-subtle bg-muted p-4 text-center text-xs text-muted-foreground">
            <Play className="size-5 opacity-60" />
            <span>{`${activeVersion.compositionName} · v${activeVersion.version}`}</span>
          </div>
        )}
      </div>

      {/* Window Hint + Quick Actions */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 text-xs">
        {isPartialWindow ? (
          <span className="font-mono text-[11px] text-muted-foreground">
            {t("workbench.player.previewWindowHint", {
              range: formatTimeRange(windowRange.start, windowRange.end),
              total: formatDuration(totalDuration),
            })}
          </span>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-1.5">
          {matchingOutput ? (
            <Button
              size="sm"
              variant={exactOutputMatches ? "primary" : "secondary"}
              icon={<Play className="size-3.5" />}
              onClick={() =>
                openArtifact({
                  key: `output:${matchingOutput.id}`,
                  kind: "output",
                  outputId: matchingOutput.id,
                  title: activeVersion.compositionName,
                })
              }
            >
              {t("workbench.player.watchFullMp4")}
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            icon={<FileText className="size-3.5" />}
            onClick={() =>
              openArtifact({
                key: `storyboard:${activeVersion.version_id}`,
                kind: "storyboard",
                versionId: activeVersion.version_id,
                title: t("workbench.storyboard.shortTabTitle"),
              })
            }
          >
            {t("workbench.storyboard.openAction")}
          </Button>
        </div>
      </div>

      <DirectorSceneList
        scenes={scenes}
        activeSceneId={activeSceneId}
        onSelectScene={handleSelectScene}
        onCiteScene={handleCiteScene}
      />
    </div>
  )
}

function StoryboardMarkdownView({ versionId }: { versionId: string }) {
  const { t } = useTranslation()
  const { workbench, openArtifact, citeText } = useWorkbench()
  const [data, setData] = useState<StoryboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  const versionMeta = useMemo(() => {
    for (const comp of workbench?.compositions ?? []) {
      const hit = comp.versions.find((v) => v.version_id === versionId)
      if (hit) {
        return {
          compId: comp.composition_id,
          compName: comp.name || t("workbench.tabs.player"),
          ver: hit,
        }
      }
    }
    return null
  }, [workbench?.compositions, versionId, t])

  const matchingOutput = useMemo(() => {
    const outputs = (workbench?.outputs ?? []).filter((o) =>
      Boolean(resolveOutputVideoUrl(o)),
    )
    return (
      outputs.find((o) => o.composition_version_id === versionId) ??
      (versionMeta?.compId
        ? outputs.find((o) => o.composition_id === versionMeta.compId)
        : null) ??
      null
    )
  }, [workbench?.outputs, versionId, versionMeta?.compId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void apiFetch(`/api/v1/chat/video/versions/${versionId}/storyboard`, {
      toast: false,
    })
      .then(async (res) => {
        if (!res.ok) return
        const payload = (await res.json()) as StoryboardResponse
        if (!cancelled) {
          setData(payload)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [versionId])

  const scenes = useMemo(
    () =>
      normalizeScenes(
        data?.storyboard?.scenes ?? data?.scenes,
        t("workbench.player.scenePrefix"),
        { compName: versionMeta?.compName, translate: t },
      ),
    [data, versionMeta?.compName, t],
  )

  const title = versionMeta?.compName || t("workbench.storyboard.defaultTitle")
  const versionNum = data?.version ?? versionMeta?.ver.version
  const durationSeconds =
    data?.storyboard?.duration_seconds ??
    versionMeta?.ver.duration_seconds ??
    scenes.reduce((acc, s) => Math.max(acc, s.endSeconds), 0)

  const markdown = useMemo(() => {
    const lines: string[] = [
      `# ${title}${versionNum != null ? ` (v${versionNum})` : ""}`,
      "",
      `- **${t("workbench.storyboard.durationLabel")}**: ${Math.round(durationSeconds * 10) / 10}s`,
      `- **${t("workbench.player.scenesHeading")}**: ${scenes.length}`,
      "",
    ]
    for (const scene of scenes) {
      const roleSuffix =
        scene.blockRole && scene.blockRole !== scene.title
          ? ` · ${scene.blockRole}`
          : ""
      lines.push(
        `### ${String(scene.number).padStart(2, "0")} · ${scene.title}${roleSuffix} \`${formatTimeRange(scene.startSeconds, scene.endSeconds)}\``,
      )
      lines.push("")
      if (scene.visualHighlights.length > 0) {
        lines.push(`- ${scene.visualHighlights.join(" · ")}`)
        lines.push("")
      } else if (scene.summary) {
        lines.push(scene.summary)
        lines.push("")
      }
      if (scene.narration) {
        lines.push(`> ${scene.narration}`)
        lines.push("")
      }
    }
    return lines.join("\n")
  }, [title, versionNum, durationSeconds, scenes, t])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      // Ignore clipboard permission errors
    }
  }

  const handleJumpToScene = useCallback(
    (scene: NormalizedScene) => {
      if (matchingOutput) {
        openArtifact({
          key: `output:${matchingOutput.id}`,
          kind: "output",
          outputId: matchingOutput.id,
          title: versionMeta?.compName,
          seekSeconds: scene.startSeconds,
          seekNonce: Date.now(),
        })
        return
      }
      openArtifact({
        key: `version:${versionId}`,
        kind: "version",
        versionId,
        title: versionMeta?.compName,
        startSeconds: scene.startSeconds,
        endSeconds: Math.min(durationSeconds || scene.endSeconds, Math.max(scene.endSeconds, scene.startSeconds + 6)),
      })
    },
    [matchingOutput, openArtifact, versionId, versionMeta?.compName, durationSeconds],
  )

  const handleCiteScene = useCallback(
    (scene: NormalizedScene) => {
      const citation = t("workbench.player.sceneCitation", {
        number: scene.number,
        range: formatTimeRange(scene.startSeconds, scene.endSeconds),
        title: scene.title,
      })
      if (citeText(citation)) {
        toast.success(t("workbench.inspector.regionCited"))
      }
    },
    [citeText, t],
  )

  if (loading) {
    return (
      <Loading label={t("common.loading")} className="flex flex-1 flex-col overflow-hidden">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-subtle px-4 py-2.5">
          <Skeleton width={132} height={18} radius={6} />
          <Skeleton width={68} height={24} radius={6} />
        </div>
        <div className="flex flex-col gap-3 p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex flex-col gap-2 rounded-lg border border-subtle p-3">
              <Skeleton width="55%" height={14} radius={4} />
              <Skeleton line width="92%" height={10} />
              <Skeleton line width="68%" height={10} />
            </div>
          ))}
        </div>
      </Loading>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-subtle px-4 py-2.5">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-foreground">
            {title}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px] tabular-nums text-muted-foreground">
            <span>{`${Math.round(durationSeconds * 10) / 10}s`}</span>
            <span>·</span>
            <span>{t("workbench.storyboard.scenesSummary", { count: scenes.length })}</span>
            {versionNum != null ? (
              <>
                <span>·</span>
                <span>{`v${versionNum}`}</span>
              </>
            ) : null}
          </div>
        </div>
        <Button
          size="sm"
          variant="ghost"
          icon={copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          onClick={handleCopy}
        >
          {t(copied ? "common.copied" : "workbench.storyboard.copyMarkdown")}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-3.5 thin-scroll">
        <div className="flex flex-col gap-2">
          {scenes.map((scene) => {
            const timeRange = formatTimeRange(scene.startSeconds, scene.endSeconds)
            const showRole =
              Boolean(scene.blockRole) && scene.blockRole !== scene.title
            const hasDetails =
              scene.visualHighlights.length > 0 ||
              Boolean(scene.transitionAfter) ||
              scene.sfxCount > 0
            return (
              <div
                key={scene.id}
                className="group rounded-lg border border-subtle bg-card px-3 py-2.5 transition-colors hover:border-foreground/20"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <span className="shrink-0 font-mono text-[11px] font-medium tabular-nums text-muted-foreground">
                      {String(scene.number).padStart(2, "0")}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleJumpToScene(scene)}
                      title={t("workbench.storyboard.jumpToScene", { range: timeRange })}
                      className="inline-flex shrink-0 items-center gap-1 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      <Play className="size-2.5" />
                      <span>{timeRange}</span>
                    </button>
                    <span className="truncate text-[13px] font-medium text-foreground">
                      {scene.title}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {showRole ? (
                      <Badge tone="neutral" size="sm">
                        {scene.blockRole}
                      </Badge>
                    ) : null}
                    <IconButton
                      size="sm"
                      variant="ghost"
                      icon={<MessageSquarePlus className="size-3.5" />}
                      label={t("workbench.player.citeScene")}
                      onClick={() => handleCiteScene(scene)}
                      className="opacity-0 transition-opacity group-hover:opacity-100 group-has-[:focus-visible]:opacity-100 max-md:opacity-100"
                    />
                  </div>
                </div>

                {scene.narration ? (
                  <p className="mt-2 border-l-2 border-foreground/15 pl-2.5 text-xs leading-relaxed text-foreground/90">
                    {scene.narration}
                  </p>
                ) : scene.blockId ? (
                  <p className="mt-1.5 text-[11px] italic text-muted-foreground">
                    {t("workbench.storyboard.silentBeat")}
                  </p>
                ) : null}

                {!scene.narration && scene.summary ? (
                  <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                    {scene.summary}
                  </p>
                ) : null}

                {hasDetails ? (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {scene.visualHighlights.map((chip) => (
                      <span
                        key={chip}
                        className="inline-flex max-w-[200px] truncate rounded bg-muted/80 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                      >
                        {chip}
                      </span>
                    ))}
                    {scene.transitionAfter ? (
                      <span className="inline-flex rounded bg-muted/60 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {`→ ${scene.transitionAfter}`}
                      </span>
                    ) : null}
                    {scene.sfxCount > 0 ? (
                      <span className="inline-flex rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground">
                        {t("workbench.storyboard.sfxCount", { count: scene.sfxCount })}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function MarkdownArtifactView({
  title,
  subtitle,
  content,
}: {
  title: string
  subtitle?: string
  content: string
}) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      // Ignore clipboard permission errors
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-subtle px-4 py-2.5">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-foreground">
            {title}
          </div>
          {subtitle ? (
            <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
          ) : null}
        </div>
        <Button
          size="sm"
          variant="ghost"
          icon={copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          onClick={handleCopy}
        >
          {t(copied ? "common.copied" : "common.copy")}
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-4 thin-scroll">
        <div className="max-w-none text-sm leading-relaxed text-foreground">
          <Streamdown mode="static">{content}</Streamdown>
        </div>
      </div>
    </div>
  )
}

type VisualAssetItem = {
  id: string
  label: string
  url: string
  mediaType: "image" | "video"
  asset: WorkbenchAsset
}

function AssetArtifactView({ assetId }: { assetId: string }) {
  const { t } = useTranslation()
  const { workbench, setSelectedAssetId, citeMention } = useWorkbench()

  const visualAssets = useMemo<VisualAssetItem[]>(() => {
    const out: VisualAssetItem[] = []
    for (const asset of workbench?.assets ?? []) {
      if (!asset.file_url) continue
      const isVideo = asset.type === "video"
      const isImage =
        asset.type === "image" ||
        asset.type === "web_page" ||
        /\.(png|jpe?g|webp|gif)(\?|$)/i.test(asset.file_url)
      if (!isVideo && !isImage) continue
      out.push({
        id: asset.id,
        label: asset.title || t("workbench.chip.asset"),
        url: asset.file_url,
        mediaType: isVideo ? "video" : "image",
        asset,
      })
    }
    return out
  }, [workbench?.assets, t])

  const activeItem =
    visualAssets.find((a) => a.id === assetId) ?? visualAssets[0] ?? null

  const mediaRef = useRef<HTMLVideoElement | HTMLImageElement | null>(null)
  const [selecting, setSelecting] = useState(
    () => activeItem?.mediaType !== "video",
  )
  const [region, setRegion] = useState<MediaRegionSelection | null>(null)

  useEffect(() => {
    setRegion(null)
    setSelecting(activeItem?.mediaType !== "video")
  }, [activeItem?.id, activeItem?.mediaType])

  const handleToggleSelect = () => {
    setSelecting((prev) => {
      const next = !prev
      if (
        next &&
        mediaRef.current instanceof HTMLVideoElement &&
        !mediaRef.current.paused
      ) {
        mediaRef.current.pause()
      }
      if (!next) setRegion(null)
      return next
    })
  }

  const handleCite = useCallback(
    (includeRegion: boolean) => {
      if (!activeItem) return
      const ok = citeMention({
        type: "asset",
        id: activeItem.id,
        label: activeItem.label,
        ...(includeRegion && region ? { region } : {}),
      })
      if (ok) {
        toast.success(t("workbench.inspector.regionCited"))
        if (includeRegion) setRegion(null)
      }
    },
    [activeItem, citeMention, region, t],
  )

  if (!activeItem) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          bare
          icon={<ImageIcon className="size-5" />}
          title={t("workbench.inspector.emptyTitle")}
          text={t("workbench.inspector.emptyText")}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4 thin-scroll">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium text-foreground">
            {activeItem.label}
          </div>
          <p className="text-[11px] text-muted-foreground">
            {t("workbench.inspector.dragRegionHint")}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="sm"
            variant={selecting ? "primary" : "secondary"}
            icon={<Crop className="size-3.5" />}
            onClick={handleToggleSelect}
          >
            {t(
              selecting
                ? "workbench.inspector.selectingRegion"
                : "workbench.inspector.selectRegion",
            )}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            icon={<MessageSquarePlus className="size-3.5" />}
            onClick={() => handleCite(Boolean(region))}
          >
            {t(
              region
                ? "workbench.inspector.citeRegionInChat"
                : "workbench.inspector.citeInChat",
            )}
          </Button>
        </div>
      </div>

      <div className="relative flex min-h-[240px] w-full flex-1 items-center justify-center overflow-hidden rounded-lg border border-subtle bg-black/90">
        {activeItem.mediaType === "video" ? (
          <video
            key={activeItem.id}
            ref={(el) => {
              mediaRef.current = el
            }}
            src={activeItem.url}
            controls={!selecting}
            playsInline
            className="max-h-[460px] w-full object-contain"
          />
        ) : (
          <img
            key={activeItem.id}
            ref={(el) => {
              mediaRef.current = el
            }}
            src={activeItem.url}
            alt={activeItem.label}
            draggable={false}
            className="max-h-[460px] w-full select-none object-contain"
          />
        )}
        <MediaRegionSelectionOverlay
          mediaRef={mediaRef}
          control={{
            enabled: selecting,
            value: region,
            onChange: setRegion,
            onReselect: () => setRegion(null),
            onCancel: () => {
              setRegion(null)
              setSelecting(false)
            },
            onDone: () => handleCite(true),
          }}
        />
      </div>

      {visualAssets.length > 1 ? (
        <div className="flex gap-2 overflow-x-auto pb-1 thin-scroll">
          {visualAssets.map((item) => {
            const isSelected = item.id === activeItem.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedAssetId(item.id)}
                className={cn(
                  "group relative flex w-24 shrink-0 flex-col overflow-hidden rounded-lg border bg-muted text-left transition-colors",
                  isSelected
                    ? "border-foreground"
                    : "border-subtle hover:border-foreground/30",
                )}
              >
                <div className="relative aspect-video w-full overflow-hidden bg-muted">
                  {item.mediaType === "image" ? (
                    <img
                      src={item.url}
                      alt={item.label}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="flex h-full w-full items-center justify-center text-muted-foreground">
                      <VideoIcon className="size-4" />
                    </span>
                  )}
                </div>
                <span className="truncate px-1.5 py-1 text-[10px] text-muted-foreground group-hover:text-foreground">
                  {item.label}
                </span>
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

function SkillArtifactView({ skillVersionId }: { skillVersionId: string }) {
  const { t } = useTranslation()
  const { workbench, openArtifact } = useWorkbench()
  const skills = (workbench?.skills ?? []).filter(
    (
      s,
    ): s is typeof s & {
      reference: { kind: "external"; skill_version_id: string }
    } => s.reference.kind === "external" && Boolean(s.reference.skill_version_id),
  )

  if (skills.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          bare
          icon={<Sparkles className="size-5" />}
          title={t("workbench.slots.emptyTitle")}
          text={t("workbench.slots.emptyText")}
        />
      </div>
    )
  }

  const activeSkill =
    skills.find((s) => s.reference.skill_version_id === skillVersionId) ??
    skills[0]

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4 thin-scroll">
      {skills.length > 1 ? (
        <Select
          size="sm"
          aria-label={t("workbench.slots.skillLabel")}
          value={activeSkill.reference.skill_version_id}
          onChange={(val) =>
            openArtifact({
              key: `skill:${val}`,
              kind: "skill",
              skillVersionId: val,
            })
          }
          options={skills.map((s) => ({
            value: s.reference.skill_version_id,
            label: s.name,
            description: s.description,
          }))}
        />
      ) : (
        <div className="flex items-center gap-2 text-xs">
          <Sparkles className="size-3.5 text-muted-foreground" />
          <span className="font-medium text-foreground">{activeSkill.name}</span>
          {activeSkill.blueprint_summary ? (
            <Badge tone="neutral" size="sm">
              {t("skills.slotPreview.durationMeta", {
                duration: activeSkill.blueprint_summary.duration_s,
                count: activeSkill.blueprint_summary.slot_count,
              })}
            </Badge>
          ) : null}
        </div>
      )}
      <Suspense
        fallback={
          <Loading label={t("common.loading")} className="flex flex-col gap-3">
            <div className="aspect-video w-full">
              <Skeleton width="100%" height="100%" radius={10} />
            </div>
            <div className="flex flex-col gap-2 rounded-lg border border-subtle p-3">
              <Skeleton width="36%" height={10} />
              <Skeleton line width="88%" height={10} />
              <Skeleton line width="74%" height={10} />
              <Skeleton line width="80%" height={10} />
            </div>
          </Loading>
        }
      >
        <LazySlotPreviewContent
          skillVersionId={activeSkill.reference.skill_version_id}
          defaultStylePreset={
            activeSkill.blueprint_summary?.style_preset ?? undefined
          }
          active
          embedded
        />
      </Suspense>
    </div>
  )
}

function PresetsArtifactView({
  initialKind = "block",
}: {
  initialKind?: WorkbenchPresetKind
}) {
  const { t } = useTranslation()
  const { openArtifact } = useWorkbench()
  const [kind, setKind] = useState<WorkbenchPresetKind>(initialKind)

  useEffect(() => {
    setKind(initialKind)
  }, [initialKind])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-subtle px-3 py-2">
        <SegmentedControl<WorkbenchPresetKind>
          size="sm"
          variant="underline"
          aria-label={t("workbench.tabs.presets")}
          value={kind}
          onChange={(next) => {
            setKind(next)
            openArtifact({ key: "presets", kind: "presets", presetTab: next })
          }}
          options={[
            { value: "block", label: t("visualGallery.blocks") },
            { value: "text_preset", label: t("visualGallery.text") },
            { value: "music", label: t("visualGallery.music") },
            { value: "voices", label: t("visualGallery.voices") },
            { value: "sounds", label: t("visualGallery.sounds") },
          ]}
        />
      </div>
      <Suspense
        fallback={
          <div className="flex flex-1 items-center justify-center p-6">
            <Spinner size={16} />
          </div>
        }
      >
        {kind === "sounds" ? (
          <SoundLabPanel />
        ) : kind === "music" ? (
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            <MusicLibraryPanel view="grid" />
          </div>
        ) : kind === "voices" ? (
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            <VoiceLibraryPanel view="grid" />
          </div>
        ) : (
          <VisualPresetGalleryPanel key={kind} kind={kind} />
        )}
      </Suspense>
    </div>
  )
}

function artifactTabIcon(artifact: WorkbenchArtifact) {
  switch (artifact.kind) {
    case "output":
      return <Play className="size-3.5 shrink-0" />
    case "version":
      return <Film className="size-3.5 shrink-0" />
    case "storyboard":
    case "markdown":
      return <FileText className="size-3.5 shrink-0" />
    case "asset":
      return <ImageIcon className="size-3.5 shrink-0" />
    case "skill":
      return <Sparkles className="size-3.5 shrink-0" />
    case "presets":
      return <SlidersHorizontal className="size-3.5 shrink-0" />
  }
}

export function WorkbenchPane({
  containerRef,
}: {
  containerRef?: React.RefObject<HTMLElement | null>
}) {
  const { t } = useTranslation()
  const mobile = useIsMobile()
  const prefersReducedMotion = useReducedMotion()
  const {
    isOpen,
    closeWorkbench,
    openArtifacts,
    activeArtifact,
    openArtifact,
    closeArtifact,
    activateArtifact,
    workbench,
  } = useWorkbench()
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  const [resizing, setResizing] = useState(false)

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(WIDTH_STORAGE_KEY)
      if (saved) {
        const parsed = Number.parseInt(saved, 10)
        if (Number.isFinite(parsed) && parsed >= MIN_WIDTH) {
          setWidth(parsed)
        }
      }
    } catch {
      // Ignore storage access errors
    }
  }, [])

  const clampWidth = useCallback(
    (next: number) => {
      const parentWidth =
        containerRef?.current?.clientWidth ?? window.innerWidth
      const maxWidth = Math.max(MIN_WIDTH, Math.floor(parentWidth * 0.56))
      return Math.min(maxWidth, Math.max(MIN_WIDTH, Math.round(next)))
    },
    [containerRef],
  )

  const onResizePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    const startX = event.clientX
    const startWidth = width
    setResizing(true)

    const onMove = (e: PointerEvent) => {
      const delta = startX - e.clientX
      setWidth(clampWidth(startWidth + delta))
    }
    const onUp = (e: PointerEvent) => {
      const delta = startX - e.clientX
      const finalWidth = clampWidth(startWidth + delta)
      setWidth(finalWidth)
      setResizing(false)
      try {
        window.localStorage.setItem(WIDTH_STORAGE_KEY, String(finalWidth))
      } catch {
        // Ignore storage errors
      }
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
    }
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
  }

  const resolveArtifactLabel = useCallback(
    (artifact: WorkbenchArtifact): string => {
      if (artifact.title?.trim()) return artifact.title.trim()
      if (artifact.kind === "output") {
        const out = workbench?.outputs.find((o) => o.id === artifact.outputId)
        const comp = workbench?.compositions.find(
          (c) => c.composition_id === out?.composition_id,
        )
        return comp?.name || t("workbench.player.outputMode")
      }
      if (artifact.kind === "version") {
        for (const comp of workbench?.compositions ?? []) {
          const v = comp.versions.find((ver) => ver.version_id === artifact.versionId)
          if (v) return comp.name ? `${comp.name} · v${v.version}` : `v${v.version}`
        }
        return t("workbench.tabs.player")
      }
      if (artifact.kind === "storyboard") {
        return t("workbench.storyboard.defaultTitle")
      }
      if (artifact.kind === "asset") {
        const asset = workbench?.assets.find((a) => a.id === artifact.assetId)
        return asset?.title || t("workbench.chip.asset")
      }
      if (artifact.kind === "skill") {
        const skill = workbench?.skills.find(
          (s) =>
            s.reference.kind === "external" &&
            s.reference.skill_version_id === artifact.skillVersionId,
        )
        return skill?.name || t("workbench.tabs.slots")
      }
      if (artifact.kind === "presets") {
        return t("workbench.tabs.presets")
      }
      return artifact.title
    },
    [workbench, t],
  )

  const availableItems = useMemo<
    { key: string; label: string; meta?: string; icon: React.ReactNode; artifact: WorkbenchArtifact }[]
  >(() => {
    const items: {
      key: string
      label: string
      meta?: string
      icon: React.ReactNode
      artifact: WorkbenchArtifact
    }[] = []
    const playableOutputs = (workbench?.outputs ?? []).filter((o) =>
      Boolean(resolveOutputVideoUrl(o)),
    )
    for (let i = 0; i < playableOutputs.length; i += 1) {
      const out = playableOutputs[i]
      const comp = workbench?.compositions.find(
        (c) => c.composition_id === out.composition_id,
      )
      const label = comp?.name
        ? playableOutputs.length > 1
          ? `${comp.name} · MP4 #${playableOutputs.length - i}`
          : `${comp.name} · MP4`
        : `${t("workbench.chip.output")} #${playableOutputs.length - i}`
      items.push({
        key: `output:${out.id}`,
        label,
        meta: "MP4",
        icon: <Play className="size-3.5 shrink-0 text-muted-foreground" />,
        artifact: {
          key: `output:${out.id}`,
          kind: "output",
          outputId: out.id,
          title: label,
        },
      })
    }

    for (const comp of workbench?.compositions ?? []) {
      const head =
        comp.versions.find((v) => v.version_id === comp.current_version_id) ??
        comp.versions[0]
      if (!head) continue
      const title = comp.name || t("workbench.tabs.player")
      items.push({
        key: `version:${head.version_id}`,
        label: title,
        meta: `v${head.version} · ${Math.round(head.duration_seconds * 10) / 10}s`,
        icon: <Film className="size-3.5 shrink-0 text-muted-foreground" />,
        artifact: {
          key: `version:${head.version_id}`,
          kind: "version",
          versionId: head.version_id,
          title,
        },
      })
      items.push({
        key: `storyboard:${head.version_id}`,
        label: t("workbench.storyboard.shortTabTitle"),
        meta: `v${head.version}`,
        icon: <FileText className="size-3.5 shrink-0 text-muted-foreground" />,
        artifact: {
          key: `storyboard:${head.version_id}`,
          kind: "storyboard",
          versionId: head.version_id,
          title: t("workbench.storyboard.shortTabTitle"),
        },
      })
    }

    const visualAssets = (workbench?.assets ?? []).filter(
      (a) =>
        a.file_url &&
        (a.type === "image" ||
          a.type === "video" ||
          a.type === "web_page" ||
          /\.(png|jpe?g|webp|gif)(\?|$)/i.test(a.file_url)),
    )
    for (const asset of visualAssets) {
      const label = asset.title || t("workbench.chip.asset")
      items.push({
        key: `asset:${asset.id}`,
        label,
        icon: <ImageIcon className="size-3.5 shrink-0 text-muted-foreground" />,
        artifact: {
          key: `asset:${asset.id}`,
          kind: "asset",
          assetId: asset.id,
          title: label,
        },
      })
    }

    return items
  }, [workbench, t])

  const paneContent = (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* Single Antigravity-style Tab Bar (desktop: shown when tabs open; mobile: always hosts the single close × so there is zero duplicate title row) */}
      {openArtifacts.length > 0 || mobile ? (
        <div className="flex h-11 shrink-0 items-center gap-1.5 border-b border-subtle px-2.5">
          {openArtifacts.length > 0 ? (
            <div
              role="tablist"
              aria-label={t("workbench.title")}
              className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto py-1 no-scrollbar"
            >
              {openArtifacts.map((artifact) => {
                const selected = artifact.key === activeArtifact?.key
                const label = resolveArtifactLabel(artifact)
                return (
                  <div
                    key={artifact.key}
                    className={cn(
                      "group flex h-7 max-w-[196px] shrink-0 items-center gap-1 rounded-md border px-2 text-xs transition-colors",
                      selected
                        ? "border-border/80 bg-card font-medium text-foreground"
                        : "border-transparent text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                    )}
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selected}
                      onClick={() => activateArtifact(artifact.key)}
                      title={label}
                      className="flex min-w-0 items-center gap-1.5 focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      {artifactTabIcon(artifact)}
                      <span className="truncate">{label}</span>
                    </button>
                    <button
                      type="button"
                      aria-label={t("workbench.closeTab", { title: label })}
                      onClick={(e) => {
                        e.stopPropagation()
                        closeArtifact(artifact.key)
                      }}
                      className="ml-0.5 rounded-sm p-0.5 text-muted-foreground opacity-60 transition-opacity hover:bg-accent hover:text-foreground hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                )
              })}
            </div>
          ) : (
            <span className="flex-1 truncate px-1 text-xs font-medium text-foreground">
              {t("workbench.title")}
            </span>
          )}
          {mobile ? (
            <IconButton
              size="sm"
              variant="ghost"
              icon={<X className="size-4" />}
              label={t("workbench.close")}
              onClick={closeWorkbench}
              className="shrink-0"
            />
          ) : null}
        </div>
      ) : null}

      {/* Focused Single-Artifact Stage */}
      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden"
        role="tabpanel"
      >
        {!activeArtifact ? (
          availableItems.length > 0 ? (
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-5 thin-scroll">
              <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
                {t("workbench.projectFilesHeading")}
              </div>
              <div className="flex flex-col gap-1">
                {availableItems.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => openArtifact(item.artifact)}
                    className="flex h-9 items-center justify-between gap-2.5 rounded-lg border border-subtle bg-card px-3 text-left text-xs text-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      {item.icon}
                      <span className="truncate font-medium">{item.label}</span>
                    </span>
                    {item.meta ? (
                      <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
                        {item.meta}
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center p-8">
              <div className="flex w-full max-w-[300px] flex-col items-center gap-5">
                {/* Quiet 16:9 cinema monitor frame — signals a waiting screening stage, not a blank error */}
                <div className="relative flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-subtle bg-card/40">
                  <div className="flex items-center gap-1.5 text-[11px] font-mono tracking-wider text-muted-foreground/60">
                    <span>16:9</span>
                    <span>·</span>
                    <span>READY</span>
                  </div>
                </div>
                <div className="space-y-1.5 text-center">
                  <p className="text-[13px] font-medium text-foreground">
                    {t("workbench.emptyStageTitle")}
                  </p>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {t("workbench.emptyStageText")}
                  </p>
                </div>
              </div>
            </div>
          )
        ) : activeArtifact.kind === "output" ? (
          <OutputArtifactView
            outputId={activeArtifact.outputId}
            initialSelectRegion={activeArtifact.selectRegion}
            seekSeconds={activeArtifact.seekSeconds}
            seekNonce={activeArtifact.seekNonce}
          />
        ) : activeArtifact.kind === "version" ? (
          <VersionArtifactView
            versionId={activeArtifact.versionId}
            initialStartSeconds={activeArtifact.startSeconds}
            initialEndSeconds={activeArtifact.endSeconds}
          />
        ) : activeArtifact.kind === "storyboard" ? (
          <StoryboardMarkdownView versionId={activeArtifact.versionId} />
        ) : activeArtifact.kind === "markdown" ? (
          <MarkdownArtifactView
            title={activeArtifact.title}
            subtitle={activeArtifact.subtitle}
            content={activeArtifact.content}
          />
        ) : activeArtifact.kind === "asset" ? (
          <AssetArtifactView assetId={activeArtifact.assetId} />
        ) : activeArtifact.kind === "skill" ? (
          <SkillArtifactView skillVersionId={activeArtifact.skillVersionId} />
        ) : (
          <PresetsArtifactView initialKind={activeArtifact.presetTab} />
        )}
      </div>
    </div>
  )

  if (mobile) {
    return (
      <Dialog
        open={isOpen}
        onOpenChange={(next) => {
          if (!next) closeWorkbench()
        }}
        title={
          activeArtifact
            ? resolveArtifactLabel(activeArtifact)
            : t("workbench.title")
        }
        closeLabel={t("workbench.close")}
        fullscreen
      >
        <div className="flex h-dvh w-full flex-col overflow-hidden bg-background">
          {paneContent}
        </div>
      </Dialog>
    )
  }

  return (
    <AnimatePresence initial={false}>
      {isOpen ? (
        <motion.aside
          key="studio-workbench-pane"
          data-slot="workbench-pane"
          aria-label={t("workbench.title")}
          initial={
            prefersReducedMotion ? { opacity: 1 } : { width: 0, opacity: 0 }
          }
          animate={
            prefersReducedMotion ? { width, opacity: 1 } : { width, opacity: 1 }
          }
          exit={
            prefersReducedMotion ? { opacity: 0 } : { width: 0, opacity: 0 }
          }
          transition={
            resizing || prefersReducedMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 420, damping: 36 }
          }
          style={{ width }}
          className="ui-as-panel relative flex h-full shrink-0 flex-col overflow-hidden bg-[var(--page)]"
        >
          {/* Left-edge drag-resize handle */}
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label={t("workbench.resizeHandle")}
            onPointerDown={onResizePointerDown}
            className={cn(
              "absolute inset-y-0 left-0 z-20 w-1.5 cursor-col-resize transition-colors",
              resizing ? "bg-foreground/20" : "hover:bg-foreground/15",
            )}
          />
          <div
            className="flex h-full min-h-0 w-full flex-col"
            style={{ minWidth: MIN_WIDTH }}
          >
            {paneContent}
          </div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  )
}
