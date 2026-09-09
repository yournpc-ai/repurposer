"use client"

/** OutputInspector (2026-09-06, FLORA node-detail parity) — the canvas's
 * product dossier. A product-node click summons it, anchored to the zoom
 * pill's corner (right-aligned, stacked below — the ADR-056 canvas-chrome
 * slot). Content = the 出生证明 only: producing step → the estimate/actual
 * 对账尺 (ADR-055 credits) → source asset → read-only spec line → model
 * facts, plus the two action doors (download-or-copy / publish). NEVER an
 * editing surface — 修订只经 chat (chat 修订恒胜), parameter forms are
 * FLORA's half we deliberately did not port. */

import { useEffect, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Copy, Download, Send, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn, formatDuration } from "@/lib/utils"
import type { GraphNodeAsset, Output, WorkflowStep } from "@/lib/types"

import type { FlowOutputAction } from "@/components/flow/types"

export interface OutputInspectorProps {
  output: Output
  /** The producing step (workflow_steps row) — null for carried rows. */
  step: WorkflowStep | null
  /** Canvas source assets (the graph's own asset nodes) — source_ref
   * resolves a name through these. */
  assets: GraphNodeAsset[]
  onClose: () => void
  /** The surface's one action channel — same outlet as the card's bar/⋯. */
  onAction: (output: Output, action: FlowOutputAction) => void
  className?: string
}

/** One FLORA-anatomy meta row: muted label left, value right (tabular). */
function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="truncate text-right text-foreground tabular-nums">
        {children}
      </span>
    </div>
  )
}

function elapsedLabel(startedAt: string, finishedAt: string): string {
  const secs = Math.max(
    0,
    Math.round(
      (new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000,
    ),
  )
  return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`
}

export function OutputInspector({
  output,
  step,
  assets,
  onClose,
  onAction,
  className,
}: OutputInspectorProps) {
  const { t, i18n } = useTranslation()

  // Esc closes (pane click is the canvas's; × is the panel's own).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const typeLabel = t(`chat.derivativeTypes.${output.type}`, {
    defaultValue: output.type,
  })
  const title = output.publishing.title || output.payload.hook || typeLabel

  // The same friendly-name chain the canvas step pills use (prohibition #10
  // — never a model name in a node label; the facts section is the model's
  // only legitimate home).
  const stepLabel =
    step == null
      ? null
      : step.summary ||
        (step.stage
          ? t(`results.stepper.${step.stage}`, { defaultValue: "" })
          : "") ||
        t(`chat.stepKinds.${step.kind}`, { defaultValue: step.kind })

  const sourceAsset = output.source_ref?.asset_id
    ? (assets.find((a) => a.id === output.source_ref!.asset_id) ?? null)
    : null
  const start = output.source_ref?.start_seconds
  const end = output.source_ref?.end_seconds

  const locale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US"
  const createdAt = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(output.created_at))

  const modelFacts = output.model_facts ?? []

  return (
    <div
      role="dialog"
      aria-label={title}
      className={cn(
        "overlay-surface max-h-[min(560px,calc(100dvh-160px))] w-[320px] overflow-y-auto rounded-xl p-4 ring-1 ring-foreground/10 thin-scroll",
        className,
      )}
    >
      {/* Header — the product's own name + the quiet close. */}
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm leading-snug font-semibold">{title}</h3>
        <button
          type="button"
          aria-label={t("results.canvas.inspector.close")}
          onClick={onClose}
          className="-mr-1 -mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 出生证明 — FLORA's two-column anatomy, our facts. Rows absent their
          data render not at all (a dossier never shows empty fields). */}
      <div className="mt-3 space-y-2">
        {stepLabel && (
          <MetaRow label={t("results.canvas.inspector.stepLabel")}>
            {stepLabel}
          </MetaRow>
        )}
        {step?.estimate_credits && (
          <MetaRow label={t("results.canvas.inspector.estimateLabel")}>
            {t("credits.range", {
              low: step.estimate_credits[0],
              high: step.estimate_credits[1],
            })}
          </MetaRow>
        )}
        {step?.cost_credits != null && (
          <MetaRow label={t("results.canvas.inspector.spentLabel")}>
            {t("credits.spent", { count: step.cost_credits })}
          </MetaRow>
        )}
        {step?.started_at && step?.finished_at && (
          <MetaRow label={t("results.canvas.inspector.durationLabel")}>
            {elapsedLabel(step.started_at, step.finished_at)}
          </MetaRow>
        )}
        <MetaRow label={t("results.canvas.inspector.createdLabel")}>
          {createdAt}
        </MetaRow>
        <MetaRow label={t("results.canvas.inspector.languageLabel")}>
          {output.language}
        </MetaRow>
        {output.source_ref && (
          <MetaRow label={t("results.canvas.inspector.sourceLabel")}>
            {sourceAsset?.title ??
              (output.source_ref.asset_id
                ? null
                : t("results.canvas.inspector.sourceFull"))}
          </MetaRow>
        )}
        {start != null && end != null && (
          <MetaRow label={t("results.canvas.inspector.rangeLabel")}>
            {`${formatDuration(start)}–${formatDuration(end)}`}
          </MetaRow>
        )}
      </div>

      {/* 任务参数 — the read-only spec line (the hover 框's prefill, honest
          here as a fact). Facts never offer an inline editor. */}
      {output.spec_prompt && (
        <div className="mt-3 space-y-1.5">
          <span className="text-xs text-muted-foreground">
            {t("results.canvas.inspector.specLabel")}
          </span>
          <p className="rounded-md bg-muted px-2.5 py-2 text-xs leading-relaxed">
            {output.spec_prompt}
          </p>
        </div>
      )}

      {/* 模型事实 (ADR-051 H) — the modality registry's display-only home. */}
      {modelFacts.length > 0 && (
        <div className="mt-3 space-y-1.5">
          <span className="text-xs text-muted-foreground">
            {t("results.canvas.inspector.modelsLabel")}
          </span>
          <div className="space-y-2">
            {modelFacts.map((fact) => (
              <MetaRow
                key={`${fact.modality}:${fact.model}`}
                label={t(`composer.modelsRows.${fact.modality}`, {
                  defaultValue: fact.modality,
                })}
              >
                {fact.model}
              </MetaRow>
            ))}
          </div>
        </div>
      )}

      {/* Action doors — the same single channel as the card's bar/⋯ menu
          (no second action home; destructive ops stay in the ⋯ menu). The
          primary speaks the product's verb: copy for text, download for
          media (2026-09-09 走查拍板). */}
      <div className="mt-4 flex gap-2">
        {output.type === "post" || output.type === "article" ? (
          <Button
            variant="outline"
            className="h-9 flex-1"
            onClick={() => onAction(output, "copy")}
          >
            <Copy className="size-4" />
            {t("chat.copy")}
          </Button>
        ) : (
          <Button
            variant="outline"
            className="h-9 flex-1"
            onClick={() => onAction(output, "download")}
          >
            <Download className="size-4" />
            {t("results.canvas.download")}
          </Button>
        )}
        <Button className="h-9 flex-1" onClick={() => onAction(output, "publish")}>
          <Send className="size-4" />
          {t("results.canvas.publish")}
        </Button>
      </div>
    </div>
  )
}
