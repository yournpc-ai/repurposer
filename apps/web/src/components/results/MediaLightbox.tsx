"use client"

/** MediaLightbox — the canvas media nodes' expand target (2026-08-15, the
 * reference canvas's viewer anatomy): ONE frosted dialog — a scrollable
 * info column on the left (timestamp + download, the full prompt, the
 * derived-attribute chip grid, the model-facts section), the media itself
 * on the right. Serves both product media (clip video / quote & carousel
 * images — chips carry the derived attributes: type / language / duration /
 * aspect / score / source range) and source assets (video / image — file
 * meta chips). Model/provider names live ONLY here (ADR-051 H — this is
 * the detail surface where 事实陈列 is allowed): a quiet facts section,
 * never a selector (禁令2); the canvas caption stays model-free (#12). */

import { useTranslation } from "react-i18next"
import { Download, type LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { downloadFile } from "@/lib/api"
import { formatRelativeTime } from "@/lib/utils"

export interface MediaChip {
  Icon: LucideIcon
  label: string
  title?: string
}

export interface MediaLightboxData {
  kind: "video" | "image"
  /** Absolute media URL (the surface resolves it through toAbsoluteUrl). */
  url: string
  poster?: string | null
  title: string
  createdAt?: string | null
  /** The run's prompt, in full (products only — assets carry no prompt). */
  prompt?: string | null
  /** Derived-attribute chips (type / language / duration / aspect / …). */
  chips?: MediaChip[]
  /** Model/provider facts (ADR-051 H — 事实陈列 on the detail surface only):
   * server-projected per product; the section renders when non-empty. */
  modelFacts?: { modality: string; model: string }[] | null
  downloadName?: string
}

export function MediaLightbox({
  data,
  onOpenChange,
}: {
  data: MediaLightboxData | null
  onOpenChange: (open: boolean) => void
}) {
  const { t, i18n } = useTranslation()
  return (
    <Dialog open={!!data} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[calc(100%-2rem)] overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="sr-only">
          <DialogTitle>{data?.title}</DialogTitle>
        </DialogHeader>
        {data && (
          <div className="flex max-h-[85vh] flex-col-reverse md:flex-row">
            {/* Info column — scrollable; the media column stays put. */}
            <div className="flex w-full shrink-0 flex-col gap-4 overflow-y-auto p-5 md:w-[320px] lg:w-[360px]">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {data.createdAt
                    ? formatRelativeTime(data.createdAt, i18n.language)
                    : ""}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9"
                  aria-label={t("results.canvas.download")}
                  title={t("results.canvas.download")}
                  onClick={() =>
                    downloadFile(data.url, data.downloadName ?? data.title).catch(
                      () => {},
                    )
                  }
                >
                  <Download className="h-4.5 w-4.5" />
                </Button>
              </div>

              {data.prompt ? (
                <div className="flex flex-col gap-2">
                  <span className="text-meta text-[11px]">
                    {t("results.lightbox.prompt")}
                  </span>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {data.prompt}
                  </p>
                </div>
              ) : null}

              {data.chips && data.chips.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {data.chips.map(({ Icon, label, title }) => (
                    <span
                      key={label}
                      title={title}
                      className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground"
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {label}
                    </span>
                  ))}
                </div>
              ) : null}

              {/* Model facts (ADR-051 H — 详情面模型事实): quiet rows in the
                  prompt-section anatomy (meta label + fact lines) — 事实陈列,
                  never a selector. Modality labels ride the composer models
                  panel's keys; model names are server-stamped DATA. */}
              {data.modelFacts && data.modelFacts.length > 0 ? (
                <div className="flex flex-col gap-2">
                  <span className="text-meta text-[11px]">
                    {t("composer.models")}
                  </span>
                  <div className="flex flex-col gap-1.5">
                    {data.modelFacts.map((fact) => (
                      <div
                        key={`${fact.modality}:${fact.model}`}
                        className="flex items-baseline justify-between gap-3 text-xs"
                      >
                        <span className="text-muted-foreground">
                          {t(`composer.modelsRows.${fact.modality}`, {
                            defaultValue: fact.modality,
                          })}
                        </span>
                        <span className="text-right">{fact.model}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            {/* Media — no fill: the letterbox shows the modal's glass (the
                ClipDetailModal rule). */}
            <div className="flex min-h-0 flex-1 items-center justify-center p-3">
              {data.kind === "video" ? (
                <video
                  src={data.url}
                  poster={data.poster ?? undefined}
                  className="max-h-[78vh] max-w-full rounded-md object-contain"
                  controls
                  autoPlay
                  playsInline
                  preload="metadata"
                />
              ) : (
                <img
                  src={data.url}
                  alt={data.title}
                  className="max-h-[78vh] max-w-full rounded-md object-contain"
                />
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
