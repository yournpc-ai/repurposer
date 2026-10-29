import { FileText, Maximize2, Video } from "lucide-react"
import { useTranslation } from "react-i18next"

import { toAbsoluteUrl } from "@/lib/api"
import { anchorCardOf, anchorLabel } from "@/lib/anchorCards"
import { useOutputPoster } from "@/lib/outputPoster"
import { outputFullText } from "@/components/results/outputText"
import { cn, formatDuration } from "@/lib/utils"
import type { Output } from "@/lib/types"

function outputAspect(output: Output): number {
  const spec = output.render_spec as { aspect?: string; width?: number; height?: number } | null
  const declared = output.aspect ?? spec?.aspect
  const match = declared?.match(/^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/)
  if (match) return Number(match[1]) / Number(match[2])
  if (spec?.width && spec.height) return spec.width / spec.height
  return output.type === "clip" || output.type === "film" || output.type === "video" ? 16 / 9 : 4 / 3
}

export function OutputPosterImage({
  output,
  className,
}: {
  output: Output
  className?: string
}) {
  const poster = useOutputPoster(output)
  if (poster) {
    return <img src={poster} alt="" className={cn("h-full w-full object-contain", className)} />
  }
  return (
    <span className={cn("flex h-full w-full items-center justify-center bg-muted text-muted-foreground", className)}>
      {output.files.video ? <Video className="h-6 w-6" /> : <FileText className="h-6 w-6" />}
    </span>
  )
}

/** Cover-first delivery entrance; the player lives only in the shared viewer. */
export function OutputDeliveryCard({
  output,
  onOpen,
}: {
  output: Output
  onOpen: (outputId: string) => void
}) {
  const { t } = useTranslation()
  const card = anchorCardOf(output)
  const typeWord = t(`chat.anchorCards.types.${output.type}`, { defaultValue: output.type })
  const label = anchorLabel(card, typeWord, null)
  const aspect = outputAspect(output)
  const portrait = aspect < 1
  const imageUrl = card.kind === "image" ? toAbsoluteUrl(card.imageUrl) : null
  const text = card.kind === "text"
    ? output.type === "carousel"
      ? (output.payload.slides ?? []).map((slide) => [slide.title, slide.body].filter(Boolean).join("\n")).join("\n\n")
      : outputFullText(output)
    : ""

  return (
    <div className="w-fit max-w-full">
      <button
        type="button"
        data-output-id={output.id}
        aria-label={t("chat.anchorCards.view", { name: label })}
        onClick={() => onOpen(output.id)}
        className={cn(
          "group relative block max-w-full overflow-hidden rounded-lg bg-muted text-left",
          "hover:ring-1 hover:ring-foreground/30 focus-visible:ring-1 focus-visible:ring-foreground/30",
          portrait ? "h-72" : "w-[340px]",
        )}
        style={portrait ? { aspectRatio: aspect } : { aspectRatio: aspect }}
      >
        {imageUrl ? (
          <img src={imageUrl} alt="" className="h-full w-full object-contain" />
        ) : card.kind === "text" ? (
          <span className="flex h-full w-full flex-col gap-2 p-4">
            <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
            <span className="line-clamp-5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
              {text || typeWord}
            </span>
          </span>
        ) : (
          <OutputPosterImage output={output} />
        )}
        <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md bg-background text-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100 motion-reduce:transition-none max-md:opacity-100">
          <Maximize2 className="h-4 w-4" />
        </span>
        {card.durationSec != null ? (
          <span className="absolute bottom-2 right-2 rounded-md bg-background px-1.5 py-0.5 font-mono text-[11px] leading-4 text-foreground">
            {formatDuration(card.durationSec)}
          </span>
        ) : null}
      </button>
      <div className="mt-2 flex max-w-[340px] items-baseline gap-2">
        <span className="min-w-0 truncate text-sm font-medium text-foreground">{label}</span>
        {output.composition_version_number != null ? (
          <span className="shrink-0 text-xs text-muted-foreground">
            {t("chat.outputCard.version", { number: output.composition_version_number })}
          </span>
        ) : null}
      </div>
    </div>
  )
}
