import { Check } from "lucide-react"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"

interface GenerationStepperProps {
  currentStep: "analyze" | "plan" | "prepare" | string
}

const STEPS = ["analyze", "plan", "prepare"] as const

export function GenerationStepper({ currentStep }: GenerationStepperProps) {
  const { t } = useTranslation()
  const stepIndex = STEPS.indexOf(currentStep as (typeof STEPS)[number])
  const currentIndex = stepIndex >= 0 ? stepIndex : 0

  return (
    <div className="w-full max-w-md">
      <div className="flex items-center justify-between">
        {STEPS.map((step, index) => {
          const isCompleted = index < currentIndex
          const isCurrent = index === currentIndex
          return (
            <div key={step} className="flex flex-1 items-center">
              <div className="flex flex-col items-center gap-2">
                <div
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-medium",
                    isCompleted
                      ? "border-primary bg-primary text-primary-foreground"
                      : isCurrent
                        ? "border-primary text-primary"
                        : "border-muted-foreground/30 text-muted-foreground"
                  )}
                >
                  {isCompleted ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </div>
                <span
                  className={cn(
                    "text-xs",
                    isCurrent ? "text-foreground" : "text-muted-foreground"
                  )}
                >
                  {t(`results.stepper.${step}`)}
                </span>
              </div>
              {index < STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-2 h-0.5 flex-1",
                    index < currentIndex ? "bg-primary" : "bg-muted"
                  )}
                />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
