/** MetaRow — the gray system-layer row (一切入流, the Claude Code anatomy):
 * system facts (step ticks, the run recap, focus events) render IN the
 * message flow as muted meta text — never as separate chrome anywhere.
 * Over-long text clamps (`lines`) and toggles on click (ctrl+o, translated). */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Crosshair, RotateCcw, TriangleAlert } from "@/components/ui/icons"

import { Button } from "@/components/ui/button-clean"
import type { FailureCheckpoint } from "@/components/chat/timeline/types"
import { cn } from "@/lib/utils"

export function MetaRow({
  icon,
  children,
  shimmer = false,
  lines = 2,
}: {
  icon?: React.ReactNode
  children: string
  shimmer?: boolean
  lines?: 1 | 2
}) {
  // Char-length proxy (no DOM measurement): ~90 chars/line at text-xs in the
  // max-w-3xl column — short rows never grow a pointer cursor for nothing.
  const clampable = children.length > lines * 90
  const [expanded, setExpanded] = useState(false)
  const Text = clampable ? "button" : "span"
  return (
    <div className="flex min-w-0 items-start gap-2 text-xs leading-relaxed text-muted-foreground">
      {icon && <span aria-hidden="true" className="shrink-0 [&>svg]:size-4">{icon}</span>}
      <Text
        type={clampable ? "button" : undefined}
        aria-expanded={clampable ? expanded : undefined}
        onClick={clampable ? () => setExpanded((value) => !value) : undefined}
        className={cn("min-w-0 text-start", shimmer && "shimmer",
          clampable && !expanded && (lines === 1 ? "line-clamp-1" : "line-clamp-2"))}
      >
        {children}
      </Text>
    </div>
  )
}

/** A canvas focus event (D8 修订 — 焦点入流): the tail row = the PENDING
 * focus (consumed on send); the same row rides a user message as its
 * persisted prefix. */
export function FocusRow({ label }: { label: string }) {
  const { t } = useTranslation()
  return (
    <MetaRow icon={<Crosshair />}>
      {t("results.dock.focus", { name: label })}
    </MetaRow>
  )
}

/** A failed turn's system fact (turn.failed / transport error — e.g. the
 * provider's balance running out): the gray in-flow row is the ONLY surface,
 * never a toast (the Claude Code inline usage-limit row is the reference
 * anatomy — a turn failure is a fact of the conversation, not chrome). */
export function TurnErrorRow({ text }: { text: string }) {
  return (
    <MetaRow icon={<TriangleAlert />}>
      {text}
    </MetaRow>
  )
}

/** Durable in-flow recovery card for a failed Run (Phase 2 Failure Checkpoint):
 * preserves all upstream progress & committed decisions and offers a one-click
 * resume button without rolling back the conversation. */
export function FailureCheckpointCard({
  text,
  checkpoint,
  recovered = false,
  retrying = false,
  disabled = false,
  onRetry,
}: {
  text: string
  checkpoint?: FailureCheckpoint
  recovered?: boolean
  retrying?: boolean
  disabled?: boolean
  onRetry?: () => void
}) {
  const { t } = useTranslation()
  if (recovered) {
    return (
      <p data-slot="failure-checkpoint-note" className="text-xs text-muted-foreground/70">
        {t("chat.checkpoint.continued")}
      </p>
    )
  }
  const canRetry = Boolean(onRetry && (checkpoint?.retryable ?? true))
  const showPreservedNote = Boolean(
    checkpoint?.decision_committed &&
      !text.includes("安全保留") &&
      !text.toLowerCase().includes("safely preserved"),
  )
  return (
    <div
      data-slot="failure-checkpoint-card"
      className="flex flex-col gap-2.5 rounded-lg border border-subtle bg-card px-3.5 py-3 shadow-resting"
    >
      <div className="flex items-start gap-2.5">
        <TriangleAlert
          aria-hidden="true"
          className="mt-0.5 size-4 shrink-0 text-destructive"
        />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm leading-relaxed text-foreground">{text}</p>
          {showPreservedNote ? (
            <p className="text-xs text-muted-foreground">
              {t("chat.checkpoint.preservedNote")}
            </p>
          ) : null}
        </div>
      </div>
      {canRetry ? (
        <div className="flex items-center justify-end">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            loading={retrying}
            disabled={disabled || retrying}
            icon={<RotateCcw className="size-3.5" />}
            onClick={onRetry}
          >
            {retrying ? t("chat.checkpoint.retrying") : t("chat.checkpoint.retry")}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
