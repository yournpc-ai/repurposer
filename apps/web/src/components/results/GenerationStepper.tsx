import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog"
import {
  Progress,
  ProgressLabel,
  ProgressTrack,
  ProgressValue,
} from "@/components/animate-ui/components/base/progress"

/** Stepper position computed by the backend (`ui_step` on /results). The
 * pipeline owns the step list; this component only renders it. */
export interface UiStep {
  key: string
  index: number
  total: number
}

interface GenerationStepperProps {
  open: boolean
  uiStep?: UiStep | null
}

/**
 * Eases the displayed percent toward the polled target so the bar animates
 * between 2.5s polls instead of jumping. Never regresses within an open
 * dialog; resets to 0 when the dialog closes.
 */
function useSmoothedPercent(target: number, active: boolean): number {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!active) {
      setValue(0)
      return
    }
    // Clamp down only when the target itself regresses (new run / retry).
    setValue((v) => (target < v ? target : v))
    const id = window.setInterval(() => {
      setValue((v) => {
        if (v >= target) return v
        return Math.min(target, v + Math.max(0.4, (target - v) * 0.12))
      })
    }, 100)
    return () => window.clearInterval(id)
  }, [target, active])

  return Math.round(value)
}

export function GenerationStepper({ open, uiStep }: GenerationStepperProps) {
  const { t } = useTranslation()

  // Equal increments: each pipeline step is worth the same 1/total of the
  // bar; the final step (ready_to_render) lands on 100%.
  const percent = uiStep ? Math.round(((uiStep.index + 1) / uiStep.total) * 100) : 0
  const displayPercent = useSmoothedPercent(percent, open)

  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false} className="sm:max-w-md">
        <Progress value={displayPercent} className="w-full space-y-2">
          <div className="flex items-center justify-between gap-1">
            <ProgressLabel className="shimmer text-muted-foreground text-sm font-medium">
              {t(`results.stepper.${uiStep?.key ?? "queued"}`)}
            </ProgressLabel>
            <span className="text-sm">
              <ProgressValue /> %
            </span>
          </div>
          <ProgressTrack />
        </Progress>
      </DialogContent>
    </Dialog>
  )
}
