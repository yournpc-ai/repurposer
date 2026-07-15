import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"

import type { Derivative } from "@/lib/types"

interface PostCardProps {
  derivative: Derivative
  onRegenerate?: () => void
}

export function PostCard({ derivative, onRegenerate }: PostCardProps) {
  const content = derivative.content?.content || ""
  const hashtags = derivative.content?.hashtags || []
  const [chatOpen, setChatOpen] = useState(false)

  const handleDownload = () => {
    if (!content) return
    const text = [content, hashtags.join(" ")].filter(Boolean).join("\n\n")
    const blob = new Blob([text], { type: "text/markdown" })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `post-${derivative.id}.md`
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
    <Card className="p-4 ring-1 ring-border">
      <div className="mb-3 flex items-center justify-between">
        <Badge variant="outline">{derivative.language?.toUpperCase()}</Badge>
        <AssetActionBar
          onDownload={handleDownload}
          onRegenerate={handleRegenerate}
          onChat={() => setChatOpen(true)}
        />
      </div>
      <div className="space-y-3">
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
        {hashtags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {hashtags.map((h: string, i: number) => (
              <Badge key={i} variant="secondary">
                #{h.replace(/^#/, "")}
              </Badge>
            ))}
          </div>
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
