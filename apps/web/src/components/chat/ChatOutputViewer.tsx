import { useEffect, useState } from "react"
import { AtSign, FileWarning, Scan } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Spinner } from "@/components/ui/spinner-clean"
import { Button } from "@/components/ui/button-clean"
import { MediaLightbox, type MediaLightboxData } from "@/components/results/MediaLightbox"
import type { MediaRegionSelection } from "@/lib/mediaRegionSelection"
import { apiFetch, toAbsoluteUrl } from "@/lib/api"
import { anchorCardOf, anchorLabel, isChatVideoOutput } from "@/lib/anchorCards"
import { useOutputPoster } from "@/lib/outputPoster"
import { outputAspect } from "@/lib/outputAspect"
import type { ChatOutputEntry, Output } from "@/lib/types"

function getOutputSlot(slotId: string) {
  return document.querySelector<HTMLElement>(`[data-output-id="${CSS.escape(slotId)}"]`)
}

export function ChatOutputViewer({
  outputId,
  entries,
  onOpenChange,
  onMention,
}: {
  outputId: string | null
  entries: ChatOutputEntry[] | null
  onOpenChange: (open: boolean) => void
  onMention: (output: Output, region?: MediaRegionSelection) => void
}) {
  const { t } = useTranslation()
  const selectedEntry = outputId ? entries?.find((entry) => entry.output_id === outputId) : undefined
  const hasPersistedEntry = selectedEntry !== undefined
  const [fallback, setFallback] = useState<Output | null>(null)
  const [failed, setFailed] = useState(false)
  const [regionSelecting, setRegionSelecting] = useState(false)
  const [regionSelection, setRegionSelection] = useState<MediaRegionSelection | null>(null)

  useEffect(() => {
    setRegionSelecting(false)
    setRegionSelection(null)
  }, [outputId])

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

  const candidateOutput = selectedEntry ? selectedEntry.output : fallback
  const selectedOutput = candidateOutput && isChatVideoOutput(candidateOutput) ? candidateOutput : null
  const poster = useOutputPoster(selectedOutput)
  const unavailable = failed || selectedEntry?.output === null || Boolean(candidateOutput && !selectedOutput)

  let data: MediaLightboxData | null = null
  if (outputId && selectedOutput) {
    const card = anchorCardOf(selectedOutput)
    const typeWord = t(`chat.anchorCards.types.${selectedOutput.type}`, { defaultValue: selectedOutput.type })
    const title = anchorLabel(card, typeWord, null)
    data = {
      id: selectedOutput.id,
      slotId: selectedOutput.id,
      kind: "video",
      url: toAbsoluteUrl(selectedOutput.files.video) ?? undefined,
      poster,
      aspect: outputAspect(selectedOutput),
      title,
      createdAt: selectedOutput.created_at,
      downloadName: `${title}.mp4`,
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
          <Spinner size={24} label={t("common.loading")} />
        </div>
      ),
    }
  }

  return (
    <MediaLightbox
      data={data}
      onOpenChange={(open) => {
        if (!open && selectedOutput) onMention(selectedOutput)
        else onOpenChange(open)
      }}
      getSlot={getOutputSlot}
      actions={selectedOutput ? (
        <>
          <Button
            variant={regionSelecting ? "primary" : "secondary"}
            size="sm"
            className="h-9 max-sm:w-9 max-sm:px-0"
            aria-label={t("chat.outputViewer.selectRegion")}
            title={t("chat.outputViewer.selectRegion")}
            aria-pressed={regionSelecting}
            disabled={!selectedOutput.files.video}
            onClick={() => setRegionSelecting((current) => !current)}
          >
            <Scan className="size-4" /><span className="max-sm:hidden">{t("chat.outputViewer.selectRegion")}</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            className="h-9 max-sm:w-9 max-sm:px-0"
            aria-label={t("chat.outputViewer.referenceAsset")}
            title={t("chat.outputViewer.referenceAsset")}
            onClick={() => onMention(selectedOutput)}
          >
            <AtSign className="size-4" /><span className="max-sm:hidden">{t("chat.outputViewer.referenceAsset")}</span>
          </Button>
        </>
      ) : null}
      regionSelection={selectedOutput?.files.video ? {
        enabled: regionSelecting,
        value: regionSelection,
        onChange: setRegionSelection,
        onReselect: () => setRegionSelection(null),
        onCancel: () => {
          setRegionSelection(null)
          setRegionSelecting(false)
        },
        onDone: () => {
          if (regionSelection) onMention(selectedOutput, regionSelection)
          setRegionSelecting(false)
        },
      } : undefined}
    />
  )
}
