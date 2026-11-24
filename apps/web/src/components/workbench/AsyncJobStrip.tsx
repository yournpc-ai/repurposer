"use client"

import { ChevronRight } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"

import { formatElapsed, useNow } from "@/components/chat/workTiming"
import { Spinner } from "@/components/ui/spinner-clean"
import type { WorkbenchActiveJob } from "@/lib/workbench"
import { useOptionalWorkbench } from "./WorkbenchContext"

function jobLabel(job: WorkbenchActiveJob, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const key = job.label_key || (
    job.kind === "export"
      ? "workbench.job.export"
      : job.kind === "image"
        ? "workbench.job.image"
        : job.kind === "voice"
          ? "workbench.job.voice"
          : job.kind === "music"
            ? "workbench.job.music"
            : job.kind === "asset_processing"
              ? "workbench.job.assetProcessing"
              : "workbench.job.generic"
  )
  return t(key, { defaultValue: t("workbench.job.generic") })
}

export function AsyncJobStrip({
  jobs: jobsProp,
}: {
  /** Optional explicit list (for isolated tests); defaults to WorkbenchContext. */
  jobs?: WorkbenchActiveJob[]
}) {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const workbenchCtx = useOptionalWorkbench()
  const jobs = jobsProp ?? workbenchCtx?.workbench?.active_jobs ?? []
  const active = jobs.length > 0
  const now = useNow(active)

  const primary = jobs[0]
  const startedMs = primary?.created_at ? Date.parse(primary.created_at) : NaN
  const elapsedText =
    active && now != null && !Number.isNaN(startedMs)
      ? formatElapsed(Math.max(0, now - startedMs))
      : null

  const handleOpen = () => {
    if (!primary || !workbenchCtx) return
    if (primary.kind === "export") {
      workbenchCtx.openWorkbench({
        tab: "player",
        ...(primary.target_version_id ? { versionId: primary.target_version_id } : {}),
      })
    } else {
      workbenchCtx.openWorkbench({ tab: "inspector" })
    }
  }

  return (
    <AnimatePresence initial={false}>
      {active && primary ? (
        <motion.div
          key="async-job-strip"
          data-slot="async-job-strip"
          initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 4 }}
          transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          className="mb-1.5 flex items-center px-1"
        >
          <button
            type="button"
            onClick={handleOpen}
            title={t("workbench.job.openTooltip")}
            className="group inline-flex max-w-full items-center gap-2 rounded-lg px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Spinner size={12} />
            <span className="truncate font-medium text-foreground/85 group-hover:text-foreground">
              {jobLabel(primary, t)}
            </span>
            {primary.status === "queued" ? (
              <span className="shrink-0 text-[11px] text-muted-foreground">
                · {t("workbench.job.queued")}
              </span>
            ) : elapsedText ? (
              <span className="shrink-0 tabular-nums text-muted-foreground">
                · {elapsedText}
              </span>
            ) : null}
            {jobs.length > 1 ? (
              <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {t("workbench.job.moreJobs", { count: jobs.length - 1 })}
              </span>
            ) : null}
            <ChevronRight className="size-3 shrink-0 opacity-50 transition-transform group-hover:translate-x-0.5 group-hover:opacity-90" />
          </button>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
