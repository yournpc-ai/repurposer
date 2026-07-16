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

export interface OutputStatusEntry {
  status: "pending" | "running" | "completed" | "failed"
  progress?: number | null
  error?: string | null
  stage?: string | null
}

export interface ResultsAssetStatus {
  id: string
  type: string
  processing_status: "pending" | "processing" | "completed" | "failed"
  processing_error?: string | null
}

interface GenerationStepperProps {
  open: boolean
  runStatus?: "pending" | "running" | "completed" | "failed" | null
  currentStep?: string | null
  progress?: number
  assets?: ResultsAssetStatus[]
  outputs?: string[]
  outputStatus?: Record<string, OutputStatusEntry>
}

const PLANNING_STEPS = ["analyze", "plan", "prepare"] as const
const OUTPUT_STEPS = ["clips", "post", "quotes", "carousel", "article"] as const

export function GenerationStepper({
  open,
  runStatus,
  currentStep,
  progress,
  assets = [],
  outputs = [],
  outputStatus = {},
}: GenerationStepperProps) {
  const { t } = useTranslation()

  // 1. Assets still transcribing/parsing — the run is queued behind them.
  const busyAssets = assets.filter(
    (a) => a.processing_status === "pending" || a.processing_status === "processing"
  )
  const busyTypes = new Set(busyAssets.map((a) => a.type))

  // 2. Currently running output (drives the sub-stage label).
  const activeOutput = outputs.find((o) => outputStatus[o]?.status === "running")
  const activeStage = activeOutput ? outputStatus[activeOutput]?.stage : null

  let labelKey: string
  let percent: number

  const planningIndex = PLANNING_STEPS.indexOf(
    currentStep as (typeof PLANNING_STEPS)[number]
  )
  const isOutputStep = OUTPUT_STEPS.includes(
    currentStep as (typeof OUTPUT_STEPS)[number]
  )

  if (busyAssets.length > 0) {
    labelKey = busyTypes.has("video")
      ? "transcribing_video"
      : busyTypes.has("audio")
        ? "transcribing_audio"
        : "parsing"
    percent = 8
  } else if (runStatus === "pending") {
    labelKey = "queued"
    percent = 15
  } else if (planningIndex >= 0) {
    // Planning phases occupy 20%–30% of the bar.
    labelKey = PLANNING_STEPS[planningIndex]
    percent = 20 + planningIndex * 5
  } else if (currentStep === "done") {
    labelKey = "done"
    percent = 100
  } else if (isOutputStep) {
    // Map backend 0–100 (mean of per-output progress) onto 30%–100%.
    const backendProgress = Math.max(0, Math.min(100, progress ?? 0))
    percent = 30 + Math.round((backendProgress / 100) * 70)
    if (activeStage === "writing_copy" && activeOutput) {
      labelKey = `stage.writing_copy.${activeOutput}`
    } else if (activeStage) {
      labelKey = `stage.${activeStage}`
    } else {
      labelKey = currentStep ?? "clips"
    }
  } else {
    // Unknown/fallback step: keep at the end of planning.
    labelKey = "prepare"
    percent = 30
  }

  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false} className="sm:max-w-md">
        <Progress value={percent} className="w-full space-y-2">
          <div className="flex items-center justify-between gap-1">
            <ProgressLabel className="shimmer text-sm font-medium">
              {t(`results.stepper.${labelKey}`)}
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
