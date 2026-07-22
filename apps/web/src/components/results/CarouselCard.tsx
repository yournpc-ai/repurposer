import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"

import type { Output } from "@/lib/types"

interface CarouselCardProps {
  output: Output
  onRegenerate?: () => void
}

export function CarouselCard({ output, onRegenerate }: CarouselCardProps) {
  const { t } = useTranslation()
  const [chatOpen, setChatOpen] = useState(false)
  const slides = output.payload.slides || []

  const handleDownload = () => {
    const text = slides
      .map((s) => [s.title, s.body].filter(Boolean).join("\n"))
      .join("\n\n---\n\n")
    if (!text) return
    const blob = new Blob([text], { type: "text/markdown" })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `carousel-${output.id}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
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
    <Card className="p-4 ring-1 ring-border">
      <div className="mb-3 flex items-center justify-between">
        <Badge variant="outline">{output.language?.toUpperCase()}</Badge>
        <AssetActionBar
          onDownload={handleDownload}
          onRegenerate={handleRegenerate}
          onChat={() => setChatOpen(true)}
        />
      </div>
      <div className="space-y-4">
        {slides.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("results.noSlides")}</p>
        ) : (
          slides.map((slide, i) => (
            <div
              key={i}
              className="rounded-md bg-muted/50 p-3 ring-1 ring-border"
            >
              <p className="font-medium">{slide.title}</p>
              {slide.body && (
                <p className="mt-1 text-sm text-muted-foreground">{slide.body}</p>
              )}
            </div>
          ))
        )}
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
