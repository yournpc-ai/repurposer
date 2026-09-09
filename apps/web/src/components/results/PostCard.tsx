import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost } from "@/lib/api"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { AssetActionBar } from "./AssetActionBar"
import { outputFullText } from "./outputText"

import type { Output } from "@/lib/types"

interface PostCardProps {
  output: Output
  onRegenerate?: () => void
}

export function PostCard({ output, onRegenerate }: PostCardProps) {
  const { t } = useTranslation()
  const content = output.payload.content || ""
  const hashtags = output.payload.hashtags || []

  // A post is pasted, not downloaded (2026-09-09 走查拍板 — the .md
  // download retired everywhere; the clipboard is the product's verb).
  const handleCopy = () => {
    navigator.clipboard
      .writeText(outputFullText(output))
      .then(() => toast.success(t("chat.copied")))
      .catch(() => toast.error(t("common.requestFailed")))
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
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <Badge variant="outline" className="rounded-md">{output.language?.toUpperCase()}</Badge>
        <AssetActionBar
          onCopy={handleCopy}
          onRegenerate={handleRegenerate}
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

    </Card>
  )
}
