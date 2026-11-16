/** One stable Run adapter in both modes. Attached data comes from ChatDock's
 * existing subscription; detached mode alone opens the historical read. */

import { useRef, type ComponentProps, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { zeroDeliveryVideoOutputs } from "@/lib/anchorCards"
import type { Output } from "@/lib/types"
import { useRunEvents } from "@/lib/use-run-events"

import { RunBlock } from "./blocks/RunBlock"

interface RunCardProps {
  attached?: Omit<ComponentProps<typeof RunBlock>, "opening" | "children">
  opening?: ReactNode
  children?: ReactNode
  runId: string
  /** Delivery rows bound the render history needed for an honest Worked span. */
  renderAttemptCount: number
  availableOutputs: Output[]
  hasDelivery: boolean
  onOpen: (outputId: string) => void
}

export function RunCard({
  attached,
  opening,
  children,
  runId,
  renderAttemptCount,
  availableOutputs,
  hasDelivery,
  onOpen,
}: RunCardProps) {
  const { t } = useTranslation()
  const { steps, status, createdAt, terminal } = useRunEvents(attached ? null : runId)
  // Keep the last exact attached read while the detached snapshot connects.
  // Otherwise changing data owners would briefly unmount the shared work row.
  const lastAttached = useRef<{ runId: string; props: NonNullable<RunCardProps["attached"]> } | null>(null)
  if (attached) lastAttached.current = { runId, props: attached }
  const pendingSnapshot = steps.length === 0 && !terminal
  const presentation = attached ?? (pendingSnapshot && lastAttached.current?.runId === runId
    ? lastAttached.current.props : undefined)
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
  return (
    <RunBlock
      {...(presentation ?? {
        pendingSnapshot,
        steps,
        title: "",
        runStartedAt: createdAt,
        terminal,
        cancelled: status === "cancelled",
        failed: status === "failed",
        reviewPending: false,
        workEndedAtMs: null,
        renderAttemptCount,
        narrativeFallback: t("results.stepper.queued"),
        hasUploads: false,
        outputs,
        onOpen,
      })}
      opening={opening}    >
      {children}
    </RunBlock>
  )
}
