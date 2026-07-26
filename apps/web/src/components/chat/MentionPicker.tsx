/** MentionPicker — @ an output into the message (chat-loop-v2 §4.2).
 *
 * Precise addressing for the intent agent: the pinned output id lands in
 * ChatRequest.mentions and resolves target_output_id deterministically.
 */

import { useEffect, useState } from "react"
import { AtSign, Clapperboard, FileText } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiFetch } from "@/lib/api"
import type { Output } from "@/lib/types"

export interface ChatMention {
  type: "output"
  id: string
  label: string
}

interface MentionPickerProps {
  projectId: string
  /** Ids already mentioned — hidden from the list. */
  excludeIds?: string[]
  onSelect: (mention: ChatMention) => void
}

function labelOf(output: Output, fallback: string): string {
  const hook = (output.payload as { hook?: string }).hook
  if (hook) return hook.length > 40 ? `${hook.slice(0, 40)}…` : hook
  return fallback
}

export function MentionPicker({ projectId, excludeIds = [], onSelect }: MentionPickerProps) {
  const { t } = useTranslation()
  const [outputs, setOutputs] = useState<Output[]>([])

  useEffect(() => {
    apiFetch(`/api/v1/projects/${projectId}/results`, { toast: false })
      .then((r) => (r.ok ? r.json() : { outputs: [] }))
      .then((data: { outputs?: Output[] }) => setOutputs(data.outputs ?? []))
      .catch(() => setOutputs([]))
  }, [projectId])

  const candidates = outputs.filter((o) => !excludeIds.includes(o.id))

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 shrink-0"
            aria-label={t("chat.mentionAdd")}
            disabled={candidates.length === 0}
          />
        }
      >
        <AtSign className="h-4 w-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-64">
        {candidates.map((o) => (
          <DropdownMenuItem
            key={o.id}
            onClick={() =>
              onSelect({ type: "output", id: o.id, label: labelOf(o, t(`chat.derivativeTypes.${o.type}`)) })
            }
          >
            {o.type === "clip" ? (
              <Clapperboard className="h-4 w-4 text-muted-foreground" />
            ) : (
              <FileText className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="truncate">{labelOf(o, t(`chat.derivativeTypes.${o.type}`))}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
