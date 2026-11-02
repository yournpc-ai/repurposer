/** Detached Run data adapter. The sole presentation implementation lives in
 * RunBlock; this component only owns the historical Run subscription. */

import { useTranslation } from "react-i18next"

import { zeroDeliveryVideoOutputs } from "@/lib/anchorCards"
import type { Output } from "@/lib/types"
import { useRunEvents } from "@/lib/use-run-events"

import { RunBlock } from "./blocks/RunBlock"

interface RunCardProps {
  runId: string
  /** Delivery rows bound the render history needed for an honest Worked span. */
  renderAttemptCount: number
  availableOutputs: Output[]
  hasDelivery: boolean
  onOpen: (outputId: string) => void
}

export function RunCard({
  runId,
  renderAttemptCount,
  availableOutputs,
  hasDelivery,
  onOpen,
}: RunCardProps) {
  const { t } = useTranslation()
  const { steps, status, createdAt, terminal } = useRunEvents(runId)
  // Detached rows are historical hydration: there is no live 60-second review
  // to replay. Any real delivery row keeps ownership on that message instead.
  const outputs = zeroDeliveryVideoOutputs({
    steps,
    outputs: availableOutputs,
    terminal,
    reviewSettled: terminal,
    hasDelivery,
  })

  // A detached stream still connecting must not flash a live-looking row.
  if (steps.length === 0 && !terminal) return null
  return (
    <RunBlock
      steps={steps}
      title=""
      runStartedAt={createdAt}
      terminal={terminal}
      cancelled={status === "cancelled"}
      failed={status === "failed"}
      reviewPending={false}
      workEndedAtMs={null}
      renderAttemptCount={renderAttemptCount}
      narrativeFallback={t("results.stepper.queued")}
      hasUploads={false}
      outputs={outputs}
      onOpen={onOpen}
    />
  )
}
