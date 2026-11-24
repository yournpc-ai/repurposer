"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Player } from "@remotion/player"
import { Video } from "@repurposer/video-remotion"
import type { VideoSpec } from "@repurposer/video-spec"
import { Check, Copy, Download, Film, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge-clean"
import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import {
  exportSlotPreviewMp4,
  fetchSlotPreview,
  type SlotManifestItem,
  type SlotPreviewResponse,
  type StylePresetId,
} from "@/lib/skills"

const STYLE_PRESETS: readonly StylePresetId[] = [
  "institutional_dark",
  "swiss_paper",
  "vox_editorial",
  "kinetic_anime",
]

function isStylePresetId(value: string | null | undefined): value is StylePresetId {
  return Boolean(value && (STYLE_PRESETS as readonly string[]).includes(value))
}

function SlotPreviewComposition({ spec }: { spec: VideoSpec }) {
  return <Video key={spec.provenance.content_digest} spec={spec} />
}

export interface SlotPreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  skillVersionId: string | null
  skillName?: string
  defaultStylePreset?: string | null
}

export function SlotPreviewDialog({
  open,
  onOpenChange,
  skillVersionId,
  skillName,
  defaultStylePreset,
}: SlotPreviewDialogProps) {
  const { t, i18n } = useTranslation()
  const [mounted, setMounted] = useState(false)
  const [stylePreset, setStylePreset] = useState<StylePresetId>(
    isStylePresetId(defaultStylePreset) ? defaultStylePreset : "vox_editorial",
  )
  const [locale, setLocale] = useState<"zh" | "en">("zh")
  const [data, setData] = useState<SlotPreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadNonce, setReloadNonce] = useState(0)
  const [copied, setCopied] = useState(false)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  // Sync initial locale & style when opening a different template
  useEffect(() => {
    if (!open) return
    setLocale(i18n.language?.toLowerCase().startsWith("en") ? "en" : "zh")
    if (isStylePresetId(defaultStylePreset)) {
      setStylePreset(defaultStylePreset)
    }
  }, [open, skillVersionId, defaultStylePreset, i18n.language])

  useEffect(() => {
    if (!open || !skillVersionId) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    fetchSlotPreview(
      skillVersionId,
      { stylePreset, locale },
      controller.signal,
    )
      .then((response) => {
        setData(response)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return
        setError(err instanceof Error ? err.message : t("skills.slotPreview.loadError"))
        setLoading(false)
      })
    return () => controller.abort()
  }, [open, skillVersionId, stylePreset, locale, reloadNonce, t])

  const groupedByAct = useMemo(() => {
    const groups = new Map<number, { actIndex: number; blockId: string; items: SlotManifestItem[] }>()
    for (const item of data?.slots ?? []) {
      const existing = groups.get(item.act_index)
      if (existing) {
        existing.items.push(item)
      } else {
        groups.set(item.act_index, {
          actIndex: item.act_index,
          blockId: item.block_id,
          items: [item],
        })
      }
    }
    return Array.from(groups.values()).sort((a, b) => a.actIndex - b.actIndex)
  }, [data])

  const handleCopyChecklist = useCallback(async () => {
    if (!data?.copyable_checklist) return
    try {
      await navigator.clipboard.writeText(data.copyable_checklist)
      setCopied(true)
      toast.success(t("skills.slotPreview.copiedChecklist"))
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      toast.error(t("common.requestFailed"))
    }
  }, [data, t])

  const handleExport = useCallback(async () => {
    if (!skillVersionId || exporting) return
    setExporting(true)
    try {
      const { blob, filename } = await exportSlotPreviewMp4(skillVersionId, {
        style_preset: stylePreset,
        locale,
        include_sfx: true,
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 5000)
      toast.success(t("skills.slotPreview.exportSuccess"))
    } catch {
      // apiFetch already displayed the structured server toast
    } finally {
      setExporting(false)
    }
  }, [skillVersionId, stylePreset, locale, exporting, t])

  const spec = data?.video_spec ?? null
  const displayName = data?.name || skillName || t("skills.slotPreview.title")

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      width={1060}
      closeLabel={t("common.close")}
      title={
        <span className="inline-flex items-center gap-2">
          <Film className="size-4 text-muted-foreground" />
          <span>{t("skills.slotPreview.title")}</span>
          <Badge tone="neutral" size="sm">
            {displayName}
          </Badge>
        </span>
      }
      description={t("skills.slotPreview.description")}
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          <div className="text-xs text-muted-foreground">
            {data
              ? t("skills.slotPreview.durationMeta", {
                  duration: data.duration_s,
                  count: data.slots.length,
                })
              : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="md"
              disabled={!data || loading}
              icon={copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
              onClick={handleCopyChecklist}
            >
              {t("skills.slotPreview.copyChecklist")}
            </Button>
            <Button
              variant="primary"
              size="md"
              disabled={!data || loading}
              loading={exporting}
              icon={<Download className="size-3.5" />}
              onClick={handleExport}
            >
              {exporting
                ? t("skills.slotPreview.exportingMp4")
                : t("skills.slotPreview.exportMp4")}
            </Button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {/* Controls Bar: 4-Style switcher + ZH/EN toggle */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SegmentedControl<StylePresetId>
            variant="tray"
            size="sm"
            aria-label={t("skills.slotPreview.styleLabel")}
            value={stylePreset}
            onChange={(next) => setStylePreset(next)}
            options={STYLE_PRESETS.map((preset) => ({
              value: preset,
              label: t(`skills.picker.styles.${preset}`),
            }))}
          />
          <SegmentedControl<"zh" | "en">
            variant="tray"
            size="sm"
            aria-label={t("skills.slotPreview.localeLabel")}
            value={locale}
            onChange={(next) => setLocale(next)}
            options={[
              { value: "zh", label: "中文" },
              { value: "en", label: "EN" },
            ]}
          />
        </div>

        {/* Main Split: 16:9 Live Remotion Player + Numbered Slot Checklist */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="relative overflow-hidden rounded-lg border border-border bg-muted/40">
            <div className="aspect-video w-full">
              {error ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
                  <p className="text-sm text-muted-foreground">{error}</p>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<RefreshCw className="size-3.5" />}
                    onClick={() => setReloadNonce((n) => n + 1)}
                  >
                    {t("skills.slotPreview.retry")}
                  </Button>
                </div>
              ) : mounted && spec ? (
                <Player
                  key={`${spec.provenance.content_digest}-${stylePreset}-${locale}`}
                  component={SlotPreviewComposition}
                  inputProps={{ spec }}
                  durationInFrames={spec.duration_frames}
                  fps={spec.fps.num / spec.fps.den}
                  initialFrame={Math.min(
                    Math.round((spec.fps.num / spec.fps.den) * 1.5),
                    Math.max(0, spec.duration_frames - 1),
                  )}
                  compositionWidth={spec.width}
                  compositionHeight={spec.height}
                  style={{ width: "100%", height: "100%" }}
                  className="h-full w-full"
                  controls
                  loop
                  numberOfSharedAudioTags={0}
                />
              ) : (
                <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
                  <Spinner size={16} />
                  <span>{t("common.loading")}</span>
                </div>
              )}
            </div>
            {loading && spec ? (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/45 backdrop-blur-[1px]">
                <Spinner size={18} />
              </div>
            ) : null}
          </div>

          {/* Right Panel: [01]..[N] Slot Checklist */}
          <div className="flex max-h-[380px] flex-col rounded-lg border border-border bg-muted/20">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <span className="text-xs font-medium text-foreground">
                {t("skills.slotPreview.checklistTitle", {
                  count: data?.slots.length ?? 0,
                })}
              </span>
              {data ? (
                <Badge tone="info" size="sm">
                  {t(`skills.picker.styles.${data.style_preset}`)}
                </Badge>
              ) : null}
            </div>
            <div className="thin-scroll flex-1 space-y-3 overflow-y-auto p-3">
              {groupedByAct.map((group) => (
                <div key={group.actIndex} className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    <span>{`ACT ${String(group.actIndex + 1).padStart(2, "0")}`}</span>
                    <span className="font-mono text-[10px] opacity-75">{group.blockId}</span>
                  </div>
                  <div className="space-y-1">
                    {group.items.map((slot) => (
                      <div
                        key={slot.code}
                        className="flex items-start gap-2 rounded-md border border-border/60 bg-background/80 px-2 py-1.5"
                      >
                        <span className="mt-0.5 shrink-0 rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] font-semibold text-foreground">
                          {slot.code}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate text-xs font-medium text-foreground">
                              {locale === "zh" ? slot.label_zh : slot.label_en}
                            </span>
                            {slot.aspect_ratio ? (
                              <Badge tone="neutral" size="sm">
                                {slot.aspect_ratio}
                              </Badge>
                            ) : null}
                          </div>
                          <p className="truncate text-[11px] text-muted-foreground">
                            {slot.example_value}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {!loading && groupedByAct.length === 0 && !error ? (
                <p className="py-6 text-center text-xs text-muted-foreground">
                  {t("mentions.pickerEmpty")}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </Dialog>
  )
}
