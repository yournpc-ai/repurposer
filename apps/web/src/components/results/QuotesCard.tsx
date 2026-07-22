import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost, toAbsoluteUrl } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"

import type { Output } from "@/lib/types"

interface QuotesCardProps {
  output: Output
  onRegenerate?: () => void
}

export function QuotesCard({ output, onRegenerate }: QuotesCardProps) {
  const { t } = useTranslation()
  const [chatOpen, setChatOpen] = useState(false)

  const quotes = output.payload.quotes || []
  const firstQuote = quotes[0]
  const imageUrl = output.files.image ?? null

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
    <Card className="overflow-hidden ring-1 ring-border">
      {imageUrl ? (
        <div className="relative aspect-square bg-muted">
          <img
            src={toAbsoluteUrl(imageUrl) || undefined}
            alt={firstQuote?.quote || "Quote card"}
            className="h-full w-full object-cover"
          />
        </div>
      ) : (
        <div className="flex aspect-square flex-col justify-between bg-muted p-6">
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
          onChat={() => setChatOpen(true)}
        />
      </div>

      <AssetChatModal
        open={chatOpen}
        onOpenChange={setChatOpen}
        asset={output}
        assetType="derivative"
        projectId={output.project_id}
        onUpdated={onRegenerate}
      />
    </Card>
  )
}
