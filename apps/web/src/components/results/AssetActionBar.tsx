import { Download, MessageSquare, Pencil, RefreshCw, Send } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

interface AssetActionBarProps {
  onEdit?: () => void
  onDownload?: () => void
  onRegenerate?: () => void
  onChat?: () => void
  onPublish?: () => void
  editDisabled?: boolean
  downloadDisabled?: boolean
  regenerateDisabled?: boolean
  chatDisabled?: boolean
  publishDisabled?: boolean
  hideChat?: boolean
}

export function AssetActionBar({
  onEdit,
  onDownload,
  onRegenerate,
  onChat,
  onPublish,
  editDisabled,
  downloadDisabled,
  regenerateDisabled,
  chatDisabled,
  publishDisabled,
  hideChat = false,
}: AssetActionBarProps) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center gap-1">
      {onEdit && (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onEdit}
          disabled={editDisabled}
          title={t("chat.resultActions.edit")}
        >
          <Pencil className="h-4 w-4" />
        </Button>
      )}
      {onDownload && (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onDownload}
          disabled={downloadDisabled}
          title={t("chat.resultActions.export")}
        >
          <Download className="h-4 w-4" />
        </Button>
      )}
      {onRegenerate && (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onRegenerate}
          disabled={regenerateDisabled}
          title={t("chat.resultActions.regenerate")}
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      )}
      {!hideChat && onChat && (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onChat}
          disabled={chatDisabled}
          title={t("chat.quickActions.chat")}
        >
          <MessageSquare className="h-4 w-4" />
        </Button>
      )}
      {onPublish && (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onPublish}
          disabled={publishDisabled}
          title={t("publish.title")}
        >
          <Send className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
