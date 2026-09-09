import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost } from "@/lib/api"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { AssetActionBar } from "./AssetActionBar"
import { outputFullText } from "./outputText"

import type { Output } from "@/lib/types"

interface ArticleCardProps {
  output: Output
  onRegenerate?: () => void
}

export function ArticleCard({ output, onRegenerate }: ArticleCardProps) {
  const { t } = useTranslation()
  const title = output.payload.title || ""
  const content = output.payload.content || ""

  // An article is pasted, not downloaded (2026-09-09 走查拍板 — same
  // ruling as the post's: the clipboard is the text product's verb).
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

    </Card>
  )
}
