import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"

import type { Output } from "@/lib/types"

interface ArticleCardProps {
  output: Output
  onRegenerate?: () => void
}

export function ArticleCard({ output, onRegenerate }: ArticleCardProps) {
  const [chatOpen, setChatOpen] = useState(false)
  const title = output.payload.title || ""
  const content = output.payload.content || ""

  const handleDownload = () => {
    if (!content) return
    const text = [title, content].filter(Boolean).join("\n\n")
    const blob = new Blob([text], { type: "text/markdown" })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `article-${output.id}.md`
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
      <div className="space-y-3">
        {title && <h3 className="text-lg font-semibold">{title}</h3>}
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <div
            className="whitespace-pre-wrap text-sm leading-relaxed"
            dangerouslySetInnerHTML={{
              __html: content
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;"),
            }}
          />
        </div>
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
