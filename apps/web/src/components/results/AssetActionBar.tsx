import { Copy, Download, MessageSquare, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

interface AssetActionBarProps {
  onCopy?: () => void
  onDownload?: () => void
  onRegenerate?: () => void
  onChat?: () => void
  copyDisabled?: boolean
  downloadDisabled?: boolean
  regenerateDisabled?: boolean
  chatDisabled?: boolean
  hideChat?: boolean
}

export function AssetActionBar({
  onCopy,
  onDownload,
  onRegenerate,
  onChat,
  copyDisabled,
  downloadDisabled,
  regenerateDisabled,
  chatDisabled,
  hideChat = false,
}: AssetActionBarProps) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center gap-1">
      {onCopy && (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onCopy}
          disabled={copyDisabled}
          title={t("chat.resultActions.copy")}
        >
          <Copy className="h-4 w-4" />
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
    </div>
  )
}
