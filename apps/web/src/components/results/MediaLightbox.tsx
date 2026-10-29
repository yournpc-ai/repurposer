"use client"

/** MediaLightbox — shared media Dialog. Canvas assets use a single item;
 * Chat delivery adds exact-Output navigation and thumbnail browsing without
 * replacing the native media elements or the project sound mutex. */

import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight, Download, FileText, Video, type LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { downloadFile } from "@/lib/api"
import { cn, formatRelativeTime } from "@/lib/utils"
import { useSoundMutexHold } from "@/components/flow/sound-mutex"

export interface MediaChip {
  Icon: LucideIcon
  label: string
  title?: string
}

export interface MediaLightboxData {
  id?: string
  kind: "video" | "image" | "text"
  url?: string
  text?: string
  poster?: string | null
  title: string
  versionLabel?: string | null
  createdAt?: string | null
  prompt?: string | null
  chips?: MediaChip[]
  modelFacts?: { modality: string; model: string }[] | null
  downloadName?: string
  /** Existing type-specific reader, e.g. carousel pages or unavailable state. */
  content?: ReactNode
  /** Per-item thumbnail supplied by the Chat's exact-Output adapter. */
  thumbnail?: ReactNode
}

export function MediaLightbox({
  data,
  onOpenChange,
  navigation,
  gallery,
  actions,
}: {
  data: MediaLightboxData | null
  onOpenChange: (open: boolean) => void
  navigation?: {
    index: number
    total: number
    onPrevious: () => void
    onNext: () => void
  }
  gallery?: {
    items: MediaLightboxData[]
    activeId: string
    onSelect: (outputId: string) => void
  }
  actions?: ReactNode
}) {
  const { t, i18n } = useTranslation()
  useSoundMutexHold(!!data && data.kind === "video", "lightbox")
  return (
    <Dialog open={!!data} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[calc(100%-2rem)] overflow-hidden p-0 sm:max-w-5xl"
        onKeyDown={(event) => {
          if (!navigation || (event.target instanceof Element && event.target.closest("input,textarea,[contenteditable=true],video"))) return
          if (event.key === "ArrowLeft" && navigation.index > 0) {
            event.preventDefault()
            navigation.onPrevious()
          } else if (event.key === "ArrowRight" && navigation.index < navigation.total - 1) {
            event.preventDefault()
            navigation.onNext()
          }
        }}>
        <DialogHeader className="sr-only">
          <DialogTitle>{data?.title}</DialogTitle>
        </DialogHeader>
        {data && (
          <div className="flex min-w-0 max-h-[90vh] flex-col">
            <div className={cn("flex min-h-0 min-w-0 flex-col-reverse md:flex-row", gallery ? "max-h-[72vh]" : "max-h-[85vh]")}>
              <div className="thin-scroll flex w-full shrink-0 flex-col gap-4 overflow-y-auto p-5 md:w-[320px] lg:w-[360px]">
                {navigation ? (
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9"
                        aria-label={t("chat.outputViewer.previous")}
                        title={t("chat.outputViewer.previous")}
                        disabled={navigation.index <= 0}
                        onClick={navigation.onPrevious}
                      >
                        <ChevronLeft className="size-4.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9"
                        aria-label={t("chat.outputViewer.next")}
                        title={t("chat.outputViewer.next")}
                        disabled={navigation.index >= navigation.total - 1}
                        onClick={navigation.onNext}
                      >
                        <ChevronRight className="size-4.5" />
                      </Button>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {t("chat.outputViewer.position", { current: navigation.index + 1, total: navigation.total })}
                    </span>
                  </div>
                ) : null}

                {navigation ? (
                  <div className="flex flex-wrap items-baseline gap-2">
                    <h2 className="text-sm font-medium leading-tight">{data.title}</h2>
                    {data.versionLabel ? (
                      <span className="text-xs text-muted-foreground">{data.versionLabel}</span>
                    ) : null}
                  </div>
                ) : null}

                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {data.createdAt ? formatRelativeTime(data.createdAt, i18n.language) : ""}
                  </span>
                  {data.url ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9"
                      aria-label={t("results.canvas.download")}
                      title={t("results.canvas.download")}
                      onClick={() =>
                        downloadFile(data.url as string, data.downloadName ?? data.title).catch(() => {})
                      }
                    >
                      <Download className="size-4.5" />
                    </Button>
                  ) : null}
                </div>

                {data.prompt ? (
                  <div className="flex flex-col gap-2">
                    <span className="text-meta text-[11px]">{t("results.lightbox.prompt")}</span>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{data.prompt}</p>
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

                {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}

                {data.modelFacts && data.modelFacts.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    <span className="text-meta text-[11px]">{t("composer.models")}</span>
                    <div className="flex flex-col gap-1.5">
                      {data.modelFacts.map((fact) => (
                        <div key={`${fact.modality}:${fact.model}`} className="flex items-baseline justify-between gap-3 text-xs">
                          <span className="text-muted-foreground">
                            {t(`composer.modelsRows.${fact.modality}`, { defaultValue: fact.modality })}
                          </span>
                          <span className="text-right">{fact.model}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="flex min-h-0 min-w-0 flex-1 items-center justify-center p-3">
                {data.content ?? (data.kind === "video" ? (
                  <video
                    key={data.id ?? data.url}
                    src={data.url}
                    poster={data.poster ?? undefined}
                    className={cn("max-w-full rounded-md object-contain", gallery ? "max-h-[45vh] md:max-h-[62vh]" : "max-h-[78vh]")}
                    controls
                    autoPlay
                    playsInline
                    preload="metadata"
                  />
                ) : data.kind === "image" ? (
                  <img
                    key={data.id ?? data.url}
                    src={data.url}
                    alt={data.title}
                    className={cn("max-w-full rounded-md object-contain", gallery ? "max-h-[45vh] md:max-h-[62vh]" : "max-h-[78vh]")}
                  />
                ) : (
                  <div className="thin-scroll max-h-[62vh] w-full max-w-xl overflow-y-auto rounded-md bg-muted p-5">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{data.text}</p>
                  </div>
                ))}
              </div>
            </div>

            {gallery && gallery.items.length > 0 ? (
              <div className="scroll-fade-x flex shrink-0 gap-2 overflow-x-auto px-4 pb-4 pt-1">
                {gallery.items.map((item) => {
                  const id = item.id ?? ""
                  const active = id === gallery.activeId
                  return (
                    <button
                      key={id}
                      type="button"
                      data-viewer-output-id={id}
                      aria-label={t("chat.anchorCards.view", { name: item.title })}
                      aria-current={active ? "true" : undefined}
                      onClick={() => gallery.onSelect(id)}
                      className={cn(
                        "relative h-14 w-24 shrink-0 overflow-hidden rounded-md bg-muted",
                        active ? "ring-2 ring-foreground/60" : "hover:ring-1 hover:ring-foreground/30",
                      )}
                    >
                      {item.thumbnail ?? (item.poster ? (
                        <img src={item.poster} alt="" className="h-full w-full object-contain" />
                      ) : item.kind === "video" ? (
                        <span className="flex h-full items-center justify-center text-muted-foreground"><Video className="h-4 w-4" /></span>
                      ) : (
                        <span className="flex h-full items-center justify-center text-muted-foreground"><FileText className="h-4 w-4" /></span>
                      ))}
                    </button>
                  )
                })}
              </div>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
