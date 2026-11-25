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
  Crop,
  Download,
  Film,
  Image as ImageIcon,
  MessageSquarePlus,
  Play,
  RefreshCw,
  Sparkles,
  Video as VideoIcon,
  X,
} from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { MediaRegionSelectionOverlay } from "@/components/results/MediaRegionSelectionOverlay"
import { Badge } from "@/components/ui/badge-clean"
import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { EmptyState } from "@/components/ui/empty-state-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { Select } from "@/components/ui/select-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { useIsMobile } from "@/hooks/use-mobile"
import { apiFetch } from "@/lib/api"
import type { MediaRegionSelection } from "@/lib/mediaRegionSelection"
import { cn } from "@/lib/utils"
import type { WorkbenchAsset, WorkbenchOutput } from "@/lib/workbench"
import { useWorkbench, type WorkbenchTab } from "./WorkbenchContext"

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
const SoundLabPanel = lazy(() => import("./SoundLabPanel"))

const WIDTH_STORAGE_KEY = "repurposer-workbench-width"
const DEFAULT_WIDTH = 460
const MIN_WIDTH = 360

interface StoryboardSceneSummary {
  scene_id?: string
  label?: string
  duration_seconds?: number
  start_seconds?: number
  end_seconds?: number
  description?: string
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
    scenes?: StoryboardSceneSummary[]
  }
  scenes?: StoryboardSceneSummary[]
}

function resolveOutputVideoUrl(output: WorkbenchOutput | undefined): string | null {
  if (!output?.files) return null
  for (const key of ["video", "mp4", "stream", "url", "final"]) {
    const val = output.files[key]
    if (typeof val === "string" && val.trim()) return val
  }
  const firstVideo = Object.values(output.files).find(
    (v): v is string => typeof v === "string" && /\.(mp4|webm|mov)(\?|$)/i.test(v),
  )
  return firstVideo ?? null
}

function resolveOutputPosterUrl(output: WorkbenchOutput | undefined): string | null {
  if (!output?.files) return null
  for (const key of ["poster", "thumbnail", "cover", "image"]) {
    const val = output.files[key]
    if (typeof val === "string" && val.trim()) return val
  }
  return null
}

function PlayerTabContent() {
  const { t } = useTranslation()
  const {
    workbench,
    selectedVersionId,
    setSelectedVersionId,
    selectedOutputId,
    setSelectedOutputId,
  } = useWorkbench()

  const allVersions = useMemo(() => {
    const list: {
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
          compositionName: comp.name || t("workbench.tabs.player"),
          ...ver,
        })
      }
    }
    return list
  }, [workbench?.compositions, t])

  const videoOutputs = useMemo(
    () => (workbench?.outputs ?? []).filter((o) => Boolean(resolveOutputVideoUrl(o))),
    [workbench?.outputs],
  )

  const [mode, setMode] = useState<"draft" | "output">(() =>
    allVersions.length > 0 ? "draft" : videoOutputs.length > 0 ? "output" : "draft",
  )

  useEffect(() => {
    if (selectedOutputId && !selectedVersionId && videoOutputs.some((o) => o.id === selectedOutputId)) {
      setMode("output")
    } else if (selectedVersionId && allVersions.some((v) => v.version_id === selectedVersionId)) {
      setMode("draft")
    } else if (allVersions.length === 0 && videoOutputs.length > 0) {
      setMode("output")
    }
  }, [selectedOutputId, selectedVersionId, allVersions, videoOutputs])

  const activeVersion =
    allVersions.find((v) => v.version_id === selectedVersionId) ?? allVersions[0] ?? null
  const activeOutput =
    videoOutputs.find((o) => o.id === selectedOutputId) ?? videoOutputs[0] ?? null

  const [storyboard, setStoryboard] = useState<StoryboardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadNonce, setReloadNonce] = useState(0)

  useEffect(() => {
    if (mode !== "draft" || !activeVersion) {
      setStoryboard(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    const rangeEnd = Math.min(12, Math.max(1, Number(activeVersion.duration_seconds) || 12))
    const scrubParam = encodeURIComponent(
      JSON.stringify({ kind: "range", start_seconds: 0, end_seconds: rangeEnd }),
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
          setLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("workbench.player.loadError"))
          setLoading(false)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [mode, activeVersion, reloadNonce, t])

  if (allVersions.length === 0 && videoOutputs.length === 0) {
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

  const scenes = storyboard?.storyboard?.scenes ?? storyboard?.scenes ?? []
  const previewSpec =
    storyboard?.video_preview?.status === "ready"
      ? storyboard.video_preview.video_spec
      : null
  const outputVideoUrl = resolveOutputVideoUrl(activeOutput ?? undefined)

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4 thin-scroll">
      {/* Mode switcher (Draft vs Rendered MP4) + Version selector */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        {allVersions.length > 0 && videoOutputs.length > 0 ? (
          <SegmentedControl<"draft" | "output">
            variant="tray"
            size="sm"
            value={mode}
            onChange={setMode}
            options={[
              { value: "draft", label: t("workbench.player.draftMode") },
              { value: "output", label: t("workbench.player.outputMode") },
            ]}
          />
        ) : null}

        {mode === "draft" && allVersions.length > 0 ? (
          <div className="flex min-w-[170px] flex-1 items-center justify-end gap-2">
            <Select
              size="sm"
              aria-label={t("workbench.player.versionLabel")}
              value={activeVersion?.version_id ?? null}
              onChange={(val) => setSelectedVersionId(val)}
              options={allVersions.map((v) => ({
                value: v.version_id,
                label: t("workbench.player.versionOption", {
                  version: v.version,
                  duration: Math.round(v.duration_seconds * 10) / 10,
                }),
                description: v.style_preset
                  ? t(`skills.picker.styles.${v.style_preset}`, { defaultValue: v.style_preset })
                  : undefined,
              }))}
            />
          </div>
        ) : null}

        {mode === "output" && videoOutputs.length > 1 ? (
          <div className="flex min-w-[170px] flex-1 items-center justify-end gap-2">
            <Select
              size="sm"
              aria-label={t("workbench.player.outputMode")}
              value={activeOutput?.id ?? null}
              onChange={(val) => setSelectedOutputId(val)}
              options={videoOutputs.map((o, idx) => ({
                value: o.id,
                label: `${t("workbench.chip.output")} #${videoOutputs.length - idx}`,
              }))}
            />
          </div>
        ) : null}
      </div>

      {/* Main Stage */}
      {mode === "output" ? (
        outputVideoUrl ? (
          <div className="flex flex-col gap-3">
            <div className="overflow-hidden rounded-lg border border-border bg-black">
              <video
                key={activeOutput?.id}
                src={outputVideoUrl}
                poster={resolveOutputPosterUrl(activeOutput ?? undefined) ?? undefined}
                controls
                playsInline
                className="aspect-video w-full object-contain"
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge tone="success" size="sm">
                  MP4
                </Badge>
                {activeOutput?.created_at ? (
                  <span>{new Date(activeOutput.created_at).toLocaleString()}</span>
                ) : null}
              </div>
              <a
                href={outputVideoUrl}
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
          </div>
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">
            {t("workbench.player.noOutputs")}
          </p>
        )
      ) : (
        <div className="flex flex-col gap-3">
          {/* Draft header metadata */}
          {activeVersion ? (
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">
                {activeVersion.compositionName}
              </span>
              <Badge tone="info" size="sm">
                {`v${activeVersion.version}`}
              </Badge>
              {activeVersion.is_head ? (
                <Badge tone="success" size="sm">
                  {t("workbench.player.latestBadge")}
                </Badge>
              ) : null}
              {activeVersion.style_preset ? (
                <Badge tone="neutral" size="sm">
                  {t(`skills.picker.styles.${activeVersion.style_preset}`, {
                    defaultValue: activeVersion.style_preset,
                  })}
                </Badge>
              ) : null}
              <span className="ml-auto tabular-nums">
                {`${Math.round(activeVersion.duration_seconds * 10) / 10}s`}
              </span>
            </div>
          ) : null}

          {loading ? (
            <div className="flex aspect-video w-full items-center justify-center gap-2 rounded-lg border border-border bg-muted/40 text-xs text-muted-foreground">
              <Spinner size={16} />
              <span>{t("common.loading")}</span>
            </div>
          ) : error ? (
            <div className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-lg border border-border bg-muted/30 p-4 text-center">
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
                <div className="flex aspect-video w-full items-center justify-center gap-2 rounded-lg border border-border bg-muted/40 text-xs text-muted-foreground">
                  <Spinner size={16} />
                  <span>{t("common.loading")}</span>
                </div>
              }
            >
              <LazyWorkbenchDraftPlayer rawSpec={previewSpec} />
            </Suspense>
          ) : (
            <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 p-4 text-center text-xs text-muted-foreground">
              <Play className="size-5 opacity-60" />
              <span>{activeVersion ? `${activeVersion.compositionName} · v${activeVersion.version}` : ""}</span>
            </div>
          )}

          {/* Scene breakdown list below player */}
          {scenes.length > 0 ? (
            <div className="flex flex-col gap-1.5 pt-1">
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {t("workbench.player.scenesHeading")} ({scenes.length})
              </div>
              <div className="flex flex-col gap-1.5">
                {scenes.map((scene, idx) => (
                  <div
                    key={scene.scene_id ?? idx}
                    className="flex items-start justify-between gap-2 rounded-lg border border-border/70 bg-muted/20 px-2.5 py-2 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium text-foreground">
                        {scene.label || `Scene ${idx + 1}`}
                      </div>
                      {scene.description ? (
                        <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                          {scene.description}
                        </p>
                      ) : null}
                    </div>
                    {typeof scene.duration_seconds === "number" ? (
                      <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
                        {`${Math.round(scene.duration_seconds * 10) / 10}s`}
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

type InspectorItem =
  | { kind: "asset"; id: string; label: string; url: string; mediaType: "image" | "video"; asset: WorkbenchAsset }
  | { kind: "output"; id: string; label: string; url: string; poster?: string | null; mediaType: "video"; output: WorkbenchOutput }

function InspectorTabContent() {
  const { t } = useTranslation()
  const {
    workbench,
    selectedAssetId,
    setSelectedAssetId,
    selectedOutputId,
    setSelectedOutputId,
    citeMention,
  } = useWorkbench()

  const items = useMemo<InspectorItem[]>(() => {
    const out: InspectorItem[] = []
    for (const asset of workbench?.assets ?? []) {
      if (!asset.file_url) continue
      const isVideo = asset.type === "video"
      const isImage = asset.type === "image" || asset.type === "web_page" || /\.(png|jpe?g|webp|gif)(\?|$)/i.test(asset.file_url)
      if (!isVideo && !isImage) continue
      out.push({
        kind: "asset",
        id: asset.id,
        label: asset.title || t("workbench.chip.asset"),
        url: asset.file_url,
        mediaType: isVideo ? "video" : "image",
        asset,
      })
    }
    for (const output of workbench?.outputs ?? []) {
      const videoUrl = resolveOutputVideoUrl(output)
      if (!videoUrl) continue
      out.push({
        kind: "output",
        id: output.id,
        label: `${t("workbench.chip.output")} · ${output.type}`,
        url: videoUrl,
        poster: resolveOutputPosterUrl(output),
        mediaType: "video",
        output,
      })
    }
    return out
  }, [workbench?.assets, workbench?.outputs, t])

  const activeItem = useMemo<InspectorItem | null>(() => {
    if (selectedAssetId) {
      const hit = items.find((i) => i.kind === "asset" && i.id === selectedAssetId)
      if (hit) return hit
    }
    if (selectedOutputId) {
      const hit = items.find((i) => i.kind === "output" && i.id === selectedOutputId)
      if (hit) return hit
    }
    return items[0] ?? null
  }, [items, selectedAssetId, selectedOutputId])

  const mediaRef = useRef<HTMLVideoElement | HTMLImageElement | null>(null)
  const [selecting, setSelecting] = useState(true)
  const [region, setRegion] = useState<MediaRegionSelection | null>(null)

  useEffect(() => {
    setRegion(null)
  }, [activeItem?.id, activeItem?.kind])

  const handleCite = useCallback(
    (includeRegion: boolean) => {
      if (!activeItem) return
      const ok = citeMention({
        type: activeItem.kind,
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

  if (items.length === 0 || !activeItem) {
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
      {/* Toolbar */}
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
            onClick={() => {
              setSelecting((prev) => !prev)
              if (selecting) setRegion(null)
            }}
          >
            {t(selecting ? "workbench.inspector.selectingRegion" : "workbench.inspector.selectRegion")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            icon={<MessageSquarePlus className="size-3.5" />}
            onClick={() => handleCite(Boolean(region))}
          >
            {t(region ? "workbench.inspector.citeRegionInChat" : "workbench.inspector.citeInChat")}
          </Button>
        </div>
      </div>

      {/* Main Inspector Stage with Inline MediaRegionSelectionOverlay */}
      <div className="relative flex min-h-[240px] w-full flex-1 items-center justify-center overflow-hidden rounded-lg border border-border bg-black/90">
        {activeItem.mediaType === "video" ? (
          <video
            key={activeItem.id}
            ref={(el) => { mediaRef.current = el }}
            src={activeItem.url}
            poster={activeItem.kind === "output" ? activeItem.poster ?? undefined : undefined}
            controls={!selecting}
            playsInline
            className="max-h-[420px] w-full object-contain"
          />
        ) : (
          <img
            key={activeItem.id}
            ref={(el) => { mediaRef.current = el }}
            src={activeItem.url}
            alt={activeItem.label}
            draggable={false}
            className="max-h-[420px] w-full select-none object-contain"
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

      {/* Thumbnail Strip */}
      <div className="flex gap-2 overflow-x-auto pb-1 thin-scroll">
        {items.map((item) => {
          const isSelected = item.kind === activeItem.kind && item.id === activeItem.id
          return (
            <button
              key={`${item.kind}:${item.id}`}
              type="button"
              onClick={() => {
                if (item.kind === "asset") {
                  setSelectedAssetId(item.id)
                  setSelectedOutputId(null)
                } else {
                  setSelectedOutputId(item.id)
                  setSelectedAssetId(null)
                }
              }}
              className={cn(
                "group relative flex w-24 shrink-0 flex-col overflow-hidden rounded-lg border bg-muted/30 text-left transition-colors",
                isSelected
                  ? "border-foreground ring-1 ring-foreground/25"
                  : "border-border/70 hover:border-border",
              )}
            >
              <div className="relative aspect-video w-full overflow-hidden bg-muted">
                {item.mediaType === "image" ? (
                  <img
                    src={item.url}
                    alt={item.label}
                    className="h-full w-full object-cover"
                  />
                ) : item.kind === "output" && item.poster ? (
                  <img
                    src={item.poster}
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
    </div>
  )
}

function SlotsTabContent() {
  const { t } = useTranslation()
  const { workbench, selectedSkillVersionId, setSelectedSkillVersionId } = useWorkbench()
  const skills = (workbench?.skills ?? []).filter(
    (s): s is typeof s & { reference: { kind: "external"; skill_version_id: string } } =>
      s.reference.kind === "external" && Boolean(s.reference.skill_version_id),
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
    skills.find((s) => s.reference.skill_version_id === selectedSkillVersionId) ?? skills[0]

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4 thin-scroll">
      {skills.length > 1 ? (
        <Select
          size="sm"
          aria-label={t("workbench.slots.skillLabel")}
          value={activeSkill.reference.skill_version_id}
          onChange={(val) => setSelectedSkillVersionId(val)}
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
          <div className="flex h-48 items-center justify-center gap-2 text-xs text-muted-foreground">
            <Spinner size={16} />
            <span>{t("common.loading")}</span>
          </div>
        }
      >
        <LazySlotPreviewContent
          skillVersionId={activeSkill.reference.skill_version_id}
          defaultStylePreset={activeSkill.blueprint_summary?.style_preset ?? undefined}
          active
          embedded
        />
      </Suspense>
    </div>
  )
}

export function WorkbenchPane({
  containerRef,
}: {
  containerRef?: React.RefObject<HTMLElement | null>
}) {
  const { t } = useTranslation()
  const mobile = useIsMobile()
  const prefersReducedMotion = useReducedMotion()
  const { isOpen, closeWorkbench, activeTab, setActiveTab, workbench } = useWorkbench()
  const [visualKind, setVisualKind] = useState<"block" | "text_preset">("block")
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
      const parentWidth = containerRef?.current?.clientWidth ?? window.innerWidth
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

  const slotsCount = workbench?.skills.length ?? 0
  const assetsCount = (workbench?.assets.filter((a) => Boolean(a.file_url)).length ?? 0) + (workbench?.outputs.length ?? 0)
  const versionsCount = workbench?.compositions.reduce((n, c) => n + c.versions.length, 0) ?? 0

  const paneContent = (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* Workbench tabs and close control */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-3 py-2">
        <SegmentedControl<WorkbenchTab>
          kind="tabs"
          variant="tray"
          size="sm"
          aria-label={t("workbench.title")}
          className="min-w-0"
          value={activeTab === "sounds" ? "presets" : activeTab}
          onChange={setActiveTab}
          options={[
            {
              value: "player",
              label: t("workbench.tabs.player"),
              count: versionsCount > 0 ? versionsCount : undefined,
            },
            {
              value: "inspector",
              label: t("workbench.tabs.inspector"),
              count: assetsCount > 0 ? assetsCount : undefined,
            },
            {
              value: "slots",
              label: t("workbench.tabs.slots"),
              count: slotsCount > 0 ? slotsCount : undefined,
            },
            { value: "presets", label: t("workbench.tabs.presets") },
          ]}
        />
        <IconButton
          size="sm"
          variant="ghost"
          icon={<X className="size-4" />}
          label={t("workbench.close")}
          onClick={closeWorkbench}
        />
      </div>

      {/* Active Tab Panel */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden" role="tabpanel">
        {activeTab === "player" ? <PlayerTabContent /> : null}
        {activeTab === "inspector" ? <InspectorTabContent /> : null}
        {activeTab === "slots" ? <SlotsTabContent /> : null}
        {(activeTab === "presets" || activeTab === "sounds") && <>
          <div className="shrink-0 border-b border-subtle px-3 py-2">
            <SegmentedControl<"block" | "text_preset" | "sounds">
              size="sm" variant="underline" aria-label={t("workbench.tabs.presets")}
              value={activeTab === "sounds" ? "sounds" : visualKind}
              onChange={kind => {
                if (kind !== "sounds") setVisualKind(kind)
                setActiveTab(kind === "sounds" ? "sounds" : "presets")
              }}
              options={[
                { value: "block", label: t("visualGallery.blocks") },
                { value: "text_preset", label: t("visualGallery.text") },
                { value: "sounds", label: t("visualGallery.sounds") },
              ]}
            />
          </div>
          <Suspense fallback={<Spinner />}>
            {activeTab === "sounds" ? <SoundLabPanel /> : <VisualPresetGalleryPanel key={visualKind} kind={visualKind} />}
          </Suspense>
        </>}
      </div>
    </div>
  )

  if (mobile) {
    return (
      <Dialog
        open={isOpen}
        onOpenChange={(next) => { if (!next) closeWorkbench() }}
        title={t("workbench.title")}
        closeLabel={t("workbench.close")}
        width={680}
      >
        <div className="h-[72dvh] min-h-0 overflow-hidden">{paneContent}</div>
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
          initial={prefersReducedMotion ? { opacity: 1 } : { width: 0, opacity: 0 }}
          animate={prefersReducedMotion ? { width, opacity: 1 } : { width, opacity: 1 }}
          exit={prefersReducedMotion ? { opacity: 0 } : { width: 0, opacity: 0 }}
          transition={
            resizing || prefersReducedMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 420, damping: 36 }
          }
          style={{ width }}
          className="relative flex h-full shrink-0 flex-col overflow-hidden border-l border-border bg-background"
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
          <div className="flex h-full min-h-0 w-full flex-col" style={{ minWidth: MIN_WIDTH }}>
            {paneContent}
          </div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  )
}
