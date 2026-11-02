import { Maximize2, Video } from "lucide-react"
import { useTranslation } from "react-i18next"

import { anchorCardOf, anchorLabel, isChatVideoOutput } from "@/lib/anchorCards"
import { useOutputPoster } from "@/lib/outputPoster"
import { outputAspect } from "@/lib/outputAspect"
import { cn, formatDuration } from "@/lib/utils"
import type { Output } from "@/lib/types"

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
      <Video className="h-6 w-6" />
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
  if (!isChatVideoOutput(output)) return null
  const card = anchorCardOf(output)
  const typeWord = t(`chat.anchorCards.types.${output.type}`, { defaultValue: output.type })
  const label = anchorLabel(card, typeWord, null)
  const aspect = outputAspect(output)
  const portrait = aspect < 1

  return (
    <div className="w-fit max-w-full">
      <button
        type="button"
        data-output-id={output.id}
        aria-label={t("chat.anchorCards.view", { name: label })}
        onClick={() => onOpen(output.id)}
        className={cn(
          "group relative block max-w-full overflow-hidden rounded-lg bg-muted text-left",
          "focus-visible:outline-2 focus-visible:outline-ring/30",
          portrait ? "h-72" : "w-[340px]",
        )}
        style={{ aspectRatio: aspect }}
      >
        <OutputPosterImage output={output} />
        <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md bg-background text-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100 motion-reduce:transition-none max-md:opacity-100">
          <Maximize2 className="h-4 w-4" />
        </span>
        <span className="absolute right-2 bottom-2 left-2 flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-baseline gap-2 rounded-md bg-background px-2 py-1.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100 motion-reduce:transition-none [@media(hover:none)]:opacity-100">
            <span className="truncate text-sm font-medium text-foreground">{label}</span>
          </span>
          {card.durationSec != null ? (
            <span className="shrink-0 rounded-md bg-background px-1.5 py-0.5 font-mono text-[11px] leading-4 text-foreground">
              {formatDuration(card.durationSec)}
            </span>
          ) : null}
        </span>
      </button>
    </div>
  )
}
