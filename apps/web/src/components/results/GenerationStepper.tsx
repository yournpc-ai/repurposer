import { useTranslation } from "react-i18next"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Progress,
  ProgressLabel,
  ProgressTrack,
} from "@/components/animate-ui/components/base/progress"
import { cn } from "@/lib/utils"

interface GenerationStepperProps {
  currentStep: string
  progress?: number
  open: boolean
}

const PLANNING_STEPS = ["analyze", "plan", "prepare"] as const
const OUTPUT_STEPS = ["clips", "post", "quotes", "carousel", "article"] as const

export function GenerationStepper({
  currentStep,
  progress,
  open,
}: GenerationStepperProps) {
  const { t } = useTranslation()

  const planningIndex = PLANNING_STEPS.indexOf(
    currentStep as (typeof PLANNING_STEPS)[number]
  )
  const isPlanning = planningIndex >= 0

  let labelKey = currentStep
  let normalizedProgress = progress ?? 0

  if (isPlanning) {
    normalizedProgress = Math.min(
      ((planningIndex + 1) / PLANNING_STEPS.length) * 45,
      45
    )
  } else if (currentStep === "done") {
    normalizedProgress = 100
    labelKey = "done"
  } else if (!OUTPUT_STEPS.includes(currentStep as (typeof OUTPUT_STEPS)[number])) {
    labelKey = "prepare"
    normalizedProgress = 45
  }

  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("results.generatingTitle")}</DialogTitle>
        </DialogHeader>
        <div className="w-full space-y-3 py-2">
          <Progress value={normalizedProgress}>
            <div className="flex items-center justify-between">
              <ProgressLabel>{t(`results.stepper.${labelKey}`)}</ProgressLabel>
            </div>
            <ProgressTrack
              className={cn("h-2 w-full overflow-hidden rounded-full bg-muted")}
            >
              <div
                className="h-full w-full origin-left rounded-full bg-primary transition-transform duration-500"
                style={{ transform: `scaleX(${normalizedProgress / 100})` }}
              />
            </ProgressTrack>
          </Progress>
        </div>
      </DialogContent>
    </Dialog>
  )
}
