import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { toAbsoluteUrl } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"

import type { Output } from "@/lib/types"

interface QuoteFrameCardProps {
  output: Output
}

/** quote_frame (quote-cards §2.2, 2026-08-28): a single baked PNG — the
 * per-entry frame card or the chain composite (source_ref.quote_chain).
 * Image products: download + lightbox only (publish stays a clip affair;
 * regeneration targets the parent quotes row, never the frame card). */
export function QuoteFrameCard({ output }: QuoteFrameCardProps) {
  const { t } = useTranslation()

  const imageUrl = output.files.image ?? null
  const quote = output.payload.quote || ""
  const attribution = output.payload.attribution || ""

  // Server-declared aspect drives the frame (产物展示统一 P1): the cards
  // bake 9:16; products are never cropped — object-contain inside the
  // declared frame.
  const frameAspect =
    output.aspect === "9:16"
      ? "aspect-[9/16]"
      : output.aspect === "16:9"
        ? "aspect-video"
        : "aspect-square"

  const handleDownload = () => {
    const url = toAbsoluteUrl(imageUrl)
    if (!url) return
    const a = document.createElement("a")
    a.href = url
    a.download = `quote-frame-${output.id}.png`
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return (
    <Card className="overflow-hidden">
      {imageUrl ? (
        <div className={`relative ${frameAspect} bg-muted`}>
          <img
            src={toAbsoluteUrl(imageUrl) || undefined}
            alt={quote || t("results.tabs.quoteFrame")}
            className="h-full w-full object-contain"
          />
        </div>
      ) : (
        <div className={`flex ${frameAspect} flex-col justify-between bg-muted p-6`}>
          <p className="text-xl font-medium leading-snug text-foreground">
            “{quote}”
          </p>
          {attribution ? (
            <p className="text-sm text-muted-foreground">{attribution}</p>
          ) : null}
        </div>
      )}

      <div className="flex items-center justify-between p-3">
        <Badge variant="outline">{output.language?.toUpperCase()}</Badge>
        <AssetActionBar onDownload={imageUrl ? handleDownload : undefined} />
      </div>
    </Card>
  )
}
