import { useEffect, useState } from "react"
import { AtSign, ChevronLeft, ChevronRight, Download, FileWarning, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { MediaLightbox, type MediaLightboxData } from "@/components/results/MediaLightbox"
import { downloadOutput } from "@/components/results/downloadOutput"
import { outputFullText } from "@/components/results/outputText"
import { apiFetch, toAbsoluteUrl } from "@/lib/api"
import { anchorCardOf, anchorLabel } from "@/lib/anchorCards"
import { useOutputPoster } from "@/lib/outputPoster"
import { outputAspect } from "@/lib/outputAspect"
import { outputViewerItems } from "@/lib/outputViewer"
import type { ChatOutputEntry, Output } from "@/lib/types"
import { OutputPosterImage } from "./OutputDeliveryCard"

function getOutputSlot(slotId: string) {
  return document.querySelector<HTMLElement>(`[data-output-id="${CSS.escape(slotId)}"]`)
}

function CarouselReader({ output }: { output: Output }) {
  const { t } = useTranslation()
  const slides = output.payload.slides ?? []
  const [index, setIndex] = useState(0)
  useEffect(() => setIndex(0), [output.id])
  const slide = slides[Math.min(index, Math.max(0, slides.length - 1))]
  return (
    <div className="flex max-h-[62vh] w-full max-w-xl flex-col gap-4 overflow-y-auto rounded-md bg-muted p-5 thin-scroll">
      {slide ? (
        <div>
          <p className="font-medium">{slide.title}</p>
          {slide.body ? <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{slide.body}</p> : null}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t("results.noSlides")}</p>
      )}
      {slides.length > 1 ? (
        <div className="mt-auto flex items-center justify-between gap-2">
          <Button variant="ghost" size="icon" className="h-9 w-9" disabled={index <= 0} onClick={() => setIndex((value) => value - 1)} aria-label={t("chat.outputViewer.previousSlide")}>
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-xs text-muted-foreground">
            {t("chat.outputViewer.slidePosition", { current: index + 1, total: slides.length })}
          </span>
          <Button variant="ghost" size="icon" className="h-9 w-9" disabled={index >= slides.length - 1} onClick={() => setIndex((value) => value + 1)} aria-label={t("chat.outputViewer.nextSlide")}>
            <ChevronRight className="size-4" />
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export function ChatOutputViewer({
  outputId,
  entries,
  onNavigate,
  onOpenChange,
  onMention,
}: {
  outputId: string | null
  entries: ChatOutputEntry[] | null
  onNavigate: (outputId: string) => void
  onOpenChange: (open: boolean) => void
  onMention: (output: Output) => void
}) {
  const { t } = useTranslation()
  const selectedEntry = outputId ? entries?.find((entry) => entry.output_id === outputId) : undefined
  const hasPersistedEntry = selectedEntry !== undefined
  const [fallback, setFallback] = useState<Output | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    setFallback(null)
    setFailed(false)
    if (!outputId || hasPersistedEntry) return () => { active = false }
    void apiFetch(`/api/v1/outputs/${outputId}`, { toast: false })
      .then(async (response) => {
        if (!active) return
        if (!response.ok) setFailed(true)
        else setFallback((await response.json()) as Output)
      })
      .catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [outputId, hasPersistedEntry])

  const selectedOutput = selectedEntry ? selectedEntry.output : fallback
  const items = outputId ? outputViewerItems(entries, outputId, selectedOutput) : []
  const index = Math.max(0, items.findIndex((entry) => entry.output_id === outputId))
  const poster = useOutputPoster(selectedOutput)
  const unavailable = failed || selectedEntry?.output === null

  const itemData = (entry: ChatOutputEntry): MediaLightboxData => {
    const output = entry.output
    if (!output) {
      return { id: entry.output_id, kind: "text", title: t("chat.outputViewer.unavailable") }
    }
    const card = anchorCardOf(output)
    const title = anchorLabel(card, t(`chat.anchorCards.types.${output.type}`, { defaultValue: output.type }), null)
    return {
      id: output.id,
      slotId: output.id,
      kind: card.kind,
      url: toAbsoluteUrl(output.files.video ?? output.files.image) ?? undefined,
      poster: toAbsoluteUrl(output.publishing.cover_image_url ?? output.files.image) ?? undefined,
      aspect: outputAspect(output),
      title,
      thumbnail: card.kind === "text" ? undefined : <OutputPosterImage output={output} />,
    }
  }
  const galleryItems = items.map(itemData)
  const gallery = outputId && galleryItems.length > 0 ? {
    items: galleryItems,
    activeId: outputId,
    onSelect: onNavigate,
  } : undefined
  const navigation = outputId && items.length > 0 ? {
    index,
    total: items.length,
    onPrevious: () => { if (index > 0) onNavigate(items[index - 1].output_id) },
    onNext: () => { if (index < items.length - 1) onNavigate(items[index + 1].output_id) },
  } : undefined

  let data: MediaLightboxData | null = null
  if (outputId && selectedOutput) {
    const card = anchorCardOf(selectedOutput)
    const typeWord = t(`chat.anchorCards.types.${selectedOutput.type}`, { defaultValue: selectedOutput.type })
    const title = anchorLabel(card, typeWord, null)
    const url = toAbsoluteUrl(selectedOutput.files.video ?? selectedOutput.files.image) ?? undefined
    data = {
      id: selectedOutput.id,
      slotId: selectedOutput.id,
      kind: card.kind,
      url,
      poster,
      aspect: outputAspect(selectedOutput),
      title,
      versionLabel: selectedOutput.composition_version_number != null
        ? t("chat.outputCard.version", { number: selectedOutput.composition_version_number })
        : null,
      createdAt: selectedOutput.created_at,
      text: card.kind === "text" ? outputFullText(selectedOutput) : undefined,
      content: selectedOutput.type === "carousel" ? <CarouselReader output={selectedOutput} /> : undefined,
      downloadName: selectedOutput.files.video ? `${title}.mp4` : undefined,
    }
  } else if (outputId) {
    data = {
      id: outputId,
      kind: "text",
      title: unavailable ? t("chat.outputViewer.unavailable") : t("chat.outputViewer.title"),
      content: unavailable ? (
        <div className="flex min-h-48 flex-col items-center justify-center gap-3 p-8 text-muted-foreground">
          <FileWarning className="h-7 w-7" />
          <p className="text-sm">{t("chat.outputViewer.unavailableDetail")}</p>
        </div>
      ) : (
        <div className="flex min-h-48 items-center justify-center p-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-label={t("common.loading")} />
        </div>
      ),
    }
  }

  return (
    <MediaLightbox
      data={data}
      onOpenChange={onOpenChange}
      navigation={navigation}
      gallery={gallery}
      getSlot={getOutputSlot}
      actions={selectedOutput ? (
        <>
          {!selectedOutput.files.video && !selectedOutput.files.image ? (
            <Button variant="outline" size="sm" className="h-9" onClick={() => downloadOutput(selectedOutput)}>
              <Download className="size-4" />{t("results.clipDetail.download")}
            </Button>
          ) : null}
          <Button variant="outline" size="sm" className="h-9" onClick={() => onMention(selectedOutput)}>
            <AtSign className="size-4" />{t("chat.outputViewer.mention")}
          </Button>
        </>
      ) : null}
    />
  )
}
