import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"

import type { Derivative } from "@/lib/types"

interface SummaryCardProps {
  derivative: Derivative
  onRegenerate?: () => void
}

export function SummaryCard({ derivative, onRegenerate }: SummaryCardProps) {
  const content = derivative.content || {}
  const tldr = content.tldr || ""
  const keyPoints = content.key_points || []
  const [chatOpen, setChatOpen] = useState(false)

  const handleDownload = () => {
    const text = [tldr, ...keyPoints].filter(Boolean).join("\n\n")
    const blob = new Blob([text], { type: "text/markdown" })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `summary-${derivative.id}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  }

  const handleRegenerate = async () => {
    try {
      await apiPost(`/api/v1/derivatives/${derivative.id}/regenerate`, {
        target_language: derivative.language || "en",
      })
      onRegenerate?.()
    } catch (e) {
      console.error("Regenerate failed", e)
    }
  }

  return (
    <Card className="p-4 ring-1 ring-border shadow-xl">
      <div className="mb-3 flex items-center justify-between">
        <Badge variant="outline">{derivative.language?.toUpperCase()}</Badge>
        <AssetActionBar
          onDownload={handleDownload}
          onRegenerate={handleRegenerate}
          onChat={() => setChatOpen(true)}
        />
      </div>
      <div className="space-y-3">
        {tldr && (
          <p className="font-medium leading-relaxed">{tldr}</p>
        )}
        {keyPoints.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {keyPoints.map((p: string, i: number) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
      </div>

      <AssetChatModal
        open={chatOpen}
        onOpenChange={setChatOpen}
        asset={derivative}
        assetType="derivative"
        projectId={derivative.project_id}
        onUpdated={onRegenerate}
      />
    </Card>
  )
}
