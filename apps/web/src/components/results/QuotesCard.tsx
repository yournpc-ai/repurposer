import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost, toAbsoluteUrl } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"

import type { Output } from "@/lib/types"

interface QuotesCardProps {
  output: Output
  onRegenerate?: () => void
}

export function QuotesCard({ output, onRegenerate }: QuotesCardProps) {
  const { t } = useTranslation()

  const quotes = output.payload.quotes || []
  const firstQuote = quotes[0]
  const imageUrl = output.files.image ?? null

  // Server-declared aspect drives the frame (产物展示统一 P1, 2026-08-27):
  // the stacked card bakes 9:16 — a hardcoded square cropped it. Products
  // are never cropped: object-contain inside the declared frame.
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
    a.download = `quotes-${output.id}.png`
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  const handleRegenerate = async () => {
    try {
      await apiPost(`/api/v1/outputs/${output.id}/regenerate`, {
        target_language: output.language || "en",
      })
      onRegenerate?.()
    } catch (e) {
      console.error("Regenerate failed", e)
    }
  }

  return (
    <Card className="overflow-hidden">
      {imageUrl ? (
        <div className={`relative ${frameAspect} bg-muted`}>
          <img
            src={toAbsoluteUrl(imageUrl) || undefined}
            alt={firstQuote?.quote || "Quote card"}
            className="h-full w-full object-contain"
          />
        </div>
      ) : (
        <div className={`flex ${frameAspect} flex-col justify-between bg-muted p-6`}>
          {firstQuote ? (
            <>
              <p className="text-xl font-medium leading-snug text-foreground">
                “{firstQuote.quote}”
              </p>
              <div>
                <div className="mb-2 h-0.5 w-8 bg-primary" />
                <p className="text-sm text-muted-foreground">
                  {firstQuote.attribution}
                </p>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t("results.noQuote")}
            </p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between p-3">
        <Badge variant="outline">{output.language?.toUpperCase()}</Badge>
        <AssetActionBar
          onDownload={imageUrl ? handleDownload : undefined}
          onRegenerate={handleRegenerate}
        />
      </div>

    </Card>
  )
}
