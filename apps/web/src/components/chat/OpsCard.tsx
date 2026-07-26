/** OpsCard — edit ops applied from a chat message (chat-loop-v2 §2.1).
 *
 * Reads the operation journal rows carrying this message's id (lineage),
 * renders the applied op list + the current output card, and offers a
 * stack-honest "undo last edit" button. Renders nothing when the journal
 * holds no rows for the message (e.g. the apply was rejected).
 */

import { useCallback, useEffect, useState } from "react"
import { Undo2 } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { Check } from "lucide-react"
import { apiFetch } from "@/lib/api"
import type { Output } from "@/lib/types"

import { OutputChatCard } from "./OutputChatCard"

interface EditOpsIntent {
  type: "edit_ops"
  target_output_id: string
  ops: { op: string; params: Record<string, unknown> }[]
  summary: string
}

interface OperationRow {
  id: string
  op: string
  params: Record<string, unknown>
  message_id: string | null
  undone_at: string | null
}

interface OpsCardProps {
  messageId: string
  intent: EditOpsIntent
  onDone?: () => void
}

function opLabel(
  op: string,
  params: Record<string, unknown>,
  t: (k: string, o?: { defaultValue: string }) => string,
): string {
  const base = t(`chat.ops.${op}`, { defaultValue: op })
  if ((op === "remove_range" || op === "set_trim") && typeof params.start === "number") {
    return `${base} · ${(params.start as number).toFixed(1)}s–${(params.end as number).toFixed(1)}s`
  }
  if (op === "set_title" && typeof params.text === "string" && params.text) {
    return `${base} · “${params.text.length > 24 ? `${params.text.slice(0, 24)}…` : params.text}”`
  }
  return base
}

export function OpsCard({ messageId, intent, onDone }: OpsCardProps) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<OperationRow[] | null>(null)
  const [output, setOutput] = useState<Output | null>(null)
  const [undoing, setUndoing] = useState(false)
  const onDoneRef = useCallback(() => onDone?.(), [onDone])

  const load = useCallback(async () => {
    const [opsRes, outRes] = await Promise.all([
      apiFetch(`/api/v1/outputs/${intent.target_output_id}/operations`, { toast: false }),
      apiFetch(`/api/v1/outputs/${intent.target_output_id}`, { toast: false }),
    ])
    if (opsRes.ok) {
      const all = (await opsRes.json()) as OperationRow[]
      setRows(all.filter((r) => r.message_id === messageId))
    }
    if (outRes.ok) setOutput((await outRes.json()) as Output)
  }, [intent.target_output_id, messageId])

  useEffect(() => {
    load()
  }, [load])

  const undo = async () => {
    setUndoing(true)
    try {
      const res = await apiFetch(`/api/v1/outputs/${intent.target_output_id}/operations/undo`, {
        method: "POST",
        toast: false,
      })
      if (res.ok) {
        await load()
        onDoneRef()
      }
    } finally {
      setUndoing(false)
    }
  }

  // Nothing journaled for this message (apply was rejected) → no card.
  if (rows === null || rows.length === 0) return null

  const active = rows.filter((r) => !r.undone_at)

  return (
    <div className="flex w-full flex-col gap-1.5">
      {rows.map((row) => (
        <Marker key={row.id} className={row.undone_at ? "opacity-50 line-through" : undefined}>
          <MarkerIcon>
            <Check className="text-green-600 dark:text-green-400" />
          </MarkerIcon>
          <MarkerContent>{opLabel(row.op, row.params, t)}</MarkerContent>
        </Marker>
      ))}

      {output && (
        <div className="w-40 pt-1.5">
          <OutputChatCard output={output} />
        </div>
      )}

      {active.length > 0 && (
        <div className="pt-1">
          <Button variant="outline" size="sm" className="h-8 gap-1.5" disabled={undoing} onClick={undo}>
            <Undo2 className="h-3.5 w-3.5" />
            {t("chat.undoLastEdit")}
          </Button>
        </div>
      )}
    </div>
  )
}
