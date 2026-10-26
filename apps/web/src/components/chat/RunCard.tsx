/** RunCard — the DAG's linear projection inside a chat message (chat-loop-v2).
 *
 * The run's work segment renders through the shared RunTaskList (SSE via
 * useRunEvents — snapshot first, so historical messages rehydrate through
 * the exact same path): the live checklist collapses into the one Worked
 * receipt row, expandable back to the step details. Replay has no delivery
 * seal, so the segment honestly settles on the run's observable step span
 * (runWorkElapsedMs fallback). Terminal also inlines the produced outputs
 * as the same cards the results page uses. Never renders the graph itself
 * ("用户不见图").
 */

import { useEffect, useRef, useState } from "react"
import { Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { apiFetch } from "@/lib/api"
import { isDeliveredOutput } from "@/lib/anchorCards"
import { useRunEvents } from "@/lib/use-run-events"
import type { Output } from "@/lib/types"

import { OutputChatCard } from "./OutputChatCard"
import { RunTaskList } from "./RunTaskList"

interface RunCardProps {
  runId: string
  projectId: string
  /** Fired once when the run reaches a terminal state (outputs loaded). */
  onDone?: () => void
}

export function RunCard({ runId, onDone }: RunCardProps) {
  const { t } = useTranslation()
  const [outputs, setOutputs] = useState<Output[] | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const { steps, status, createdAt, terminal } = useRunEvents(runId)

  // Terminal → inline the produced outputs (from steps' output_refs). Fires
  // once; `outputs !== null` guards the loaded state (empty list included).
  useEffect(() => {
    if (!terminal || outputs !== null) return
    const refs = [...new Set(steps.flatMap((s) => s.output_refs ?? []))]
    const load = async () => {
      if (refs.length === 0) {
        setOutputs([])
        onDoneRef.current?.()
        return
      }
      const fetched = await Promise.all(
        refs.map(async (id) => {
          const res = await apiFetch(`/api/v1/outputs/${id}`, { toast: false })
          return res.ok ? ((await res.json()) as Output) : null
        }),
      )
      setOutputs(fetched.filter((o): o is Output => o !== null))
      onDoneRef.current?.()
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terminal])

  const failed = status === "failed"
  const deliveredOutputs = outputs?.filter(isDeliveredOutput) ?? null

  return (
    <div className="flex w-full flex-col gap-1.5">
      {/* Quiet until the first snapshot lands — a stream still connecting
          must not flash a live-looking row on every historical run. */}
      {(steps.length > 0 || terminal) && (
        <RunTaskList
          steps={steps}
          title=""
          runStartedAt={createdAt}
          terminal={terminal}
          failed={failed}
          reviewPending={false}
          workEndedAtMs={null}
          narrativeFallback={t("results.stepper.queued")}
          hasUploads={false}
        />
      )}

      {terminal && outputs === null && (
        <Marker>
          <MarkerIcon>
            <Loader2 className="animate-spin text-primary" />
          </MarkerIcon>
          <MarkerContent>…</MarkerContent>
        </Marker>
      )}

      {deliveredOutputs && deliveredOutputs.length > 0 && (
        <div className="flex flex-wrap gap-3 pt-1.5">
          {deliveredOutputs.map((output) => (
            <div key={output.id} className="w-40">
              <OutputChatCard output={output} />
            </div>
          ))}
        </div>
      )}

      {failed && (
        <Marker variant="border" className="pt-1.5 text-destructive">
          <MarkerContent>{t("chat.runFailed")}</MarkerContent>
        </Marker>
      )}
    </div>
  )
}
