import { PenLine, Send, Upload, Wand2 } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"

const STEP_ICONS = [Upload, Wand2, PenLine, Send]

interface Step {
  title: string
  desc: string
}

export function LandingWorkflow() {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const steps = t("landing.workflow.steps", { returnObjects: true }) as Step[]

  return (
    <section id="features" className="scroll-mt-16 px-6 py-24">
      <div className="mx-auto w-full max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: reduceMotion ? 0 : 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="mb-14 text-center"
        >
          <h2 className="mb-3 text-3xl font-bold tracking-tight sm:text-4xl">
            {t("landing.workflow.heading")}
          </h2>
          <p className="text-base text-muted-foreground sm:text-lg">
            {t("landing.workflow.subheading")}
          </p>
        </motion.div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step, i) => {
            const Icon = STEP_ICONS[i % STEP_ICONS.length]
            return (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, y: reduceMotion ? 0 : 32 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.5, delay: reduceMotion ? 0 : i * 0.12 }}
                className="rounded-lg bg-card p-6 shadow-lg"
              >
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="h-5 w-5" />
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                </div>
                <h3 className="mb-2 text-lg font-semibold">{step.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {step.desc}
                </p>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
