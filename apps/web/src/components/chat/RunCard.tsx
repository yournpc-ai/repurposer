/** RunCard — the DAG's linear projection inside a chat message (chat-loop-v2).
 *
 * Renders a run's step checklist live (SSE via useRunEvents — snapshot first,
 * so historical messages rehydrate through the exact same path), then the
 * produced outputs as the same cards the results page uses, plus the terminal
 * aggregate line. Never renders the graph itself ("用户不见图").
 */

import { useEffect, useRef, useState } from "react"
import { Check, CircleHelp, Loader2, Minus, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { apiFetch } from "@/lib/api"
import { useRunEvents } from "@/lib/use-run-events"
import type { Output, WorkflowStep } from "@/lib/types"

import { OutputChatCard } from "./OutputChatCard"

interface RunCardProps {
  runId: string
  projectId: string
  /** Fired once when the run reaches a terminal state (outputs loaded). */
  onDone?: () => void
}

function StepRow({ step }: { step: WorkflowStep }) {
  const { t } = useTranslation()
  const icon =
    step.status === "running" ? (
      <Loader2 className="animate-spin text-primary" />
    ) : step.status === "done" ? (
      <Check className="text-green-600 dark:text-green-400" />
    ) : step.status === "failed" ? (
      <X className="text-destructive" />
    ) : step.status === "waiting" ? (
      // Checkpoint parked for a human answer (期 4) — same glyph as the
      // generation overlay's StepMarker.
      <CircleHelp className="text-primary" />
    ) : (
      <Minus className="text-muted-foreground/50" />
    )
  const label =
    step.summary ||
    (step.stage ? t(`results.stepper.${step.stage}`, { defaultValue: "" }) : "") ||
    t(`chat.stepKinds.${step.kind}`, { defaultValue: step.kind })
  return (
    <Marker>
      <MarkerIcon>{icon}</MarkerIcon>
      <MarkerContent className={step.status === "running" ? "shimmer" : undefined}>
        {label}
        {step.status === "failed" && step.error ? ` — ${step.error}` : ""}
      </MarkerContent>
    </Marker>
  )
}

export function RunCard({ runId, onDone }: RunCardProps) {
  const { t } = useTranslation()
  const [outputs, setOutputs] = useState<Output[] | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const { steps, status, summary, terminal } = useRunEvents(runId)

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

  return (
    <div className="flex w-full flex-col gap-1.5">
      {steps.map((step) => (
        <StepRow key={step.id} step={step} />
      ))}

      {terminal && outputs === null && (
        <Marker>
          <MarkerIcon>
            <Loader2 className="animate-spin text-primary" />
          </MarkerIcon>
          <MarkerContent>…</MarkerContent>
        </Marker>
      )}

      {outputs && outputs.length > 0 && (
        <div className="flex flex-wrap gap-3 pt-1.5">
          {outputs.map((output) => (
            <div key={output.id} className="w-40">
              <OutputChatCard output={output} />
            </div>
          ))}
        </div>
      )}

      {summary && (
        <Marker variant="border" className="pt-1.5 text-foreground">
          <MarkerContent>{summary}</MarkerContent>
        </Marker>
      )}
      {failed && !summary && (
        <Marker variant="border" className="pt-1.5 text-destructive">
          <MarkerContent>{t("chat.runFailed")}</MarkerContent>
        </Marker>
      )}
    </div>
  )
}
