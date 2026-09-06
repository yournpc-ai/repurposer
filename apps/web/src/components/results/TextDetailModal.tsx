"use client"

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Copy } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

import type { Output } from "@/lib/types"

/** The text product's reader (2026-09-06 — post / article nodes had NO
 * reading surface: clicking the card entered the inline EDIT textarea, so
 * the only way to read a long-form post was inside an edit surface that
 * saves on blur). This is the ClipDetailModal parallel for text products:
 * full text at a readable measure, one Copy action, zero editing (editing
 * stays on the card's inline textarea; this modal is read-only on
 * purpose). Field extraction mirrors runFlow's textContentFromOutput so
 * the card preview and the reader never disagree about what the product
 * says. */
export function TextDetailModal({
  output,
  open,
  onOpenChange,
}: {
  output: Output
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const [textState, setTextState] = useState<Output>(output)
  const [copied, setCopied] = useState(false)

  // Keep modal state in sync when the parent re-renders with updated data
  // (e.g. a chat revision lands while the reader is open).
  useEffect(() => {
    setTextState(output)
  }, [output])

  const title = textState.publishing.title ?? textState.payload.title ?? null
  const body = textState.payload.content ?? ""
  const hashtags =
    textState.publishing.hashtags ?? textState.payload.hashtags ?? []

  const fullText = [
    title,
    body,
    hashtags.length > 0 ? hashtags.map((h) => `#${h}`).join(" ") : null,
  ]
    .filter(Boolean)
    .join("\n\n")

  const handleCopy = () => {
    navigator.clipboard.writeText(fullText).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const typeLabel = t(`results.tabs.${textState.type}`, {
    defaultValue: textState.type,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[calc(100%-2rem)] overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="sr-only">
          <DialogTitle>{title ?? typeLabel}</DialogTitle>
        </DialogHeader>

        <div className="flex max-h-[85vh] flex-col gap-4 p-5">
          {/* Meta header — same caption grammar as the canvas card. */}
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">
              {typeLabel}
              {textState.language
                ? ` · ${t(`languages.${textState.language}`, { defaultValue: textState.language })}`
                : null}
            </span>
            {title ? (
              <h2 className="text-lg font-medium leading-tight">{title}</h2>
            ) : null}
          </div>

          {/* The full text — the reading surface the card only previews
              (the canvas card clamps at 12 lines by design). thin-scroll =
              the shared FLORA-parity 6px thumb (a default browser track
              reads as foreign chrome inside the glass dialog). */}
          <div className="min-h-0 flex-1 overflow-y-auto pr-1 thin-scroll">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {body}
            </p>
            {hashtags.length > 0 ? (
              <p className="mt-3 text-xs text-muted-foreground">
                {hashtags.map((h) => `#${h}`).join(" ")}
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-9" onClick={handleCopy}>
              <Copy className="mr-2 h-4 w-4" />
              {copied ? t("chat.copied") : t("chat.copy")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
