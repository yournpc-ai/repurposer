import {
  motion,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react"
import {
  Globe,
  Languages,
  Linkedin,
  Mail,
  MessageSquareText,
  Podcast,
  Youtube,
  type LucideIcon,
} from "lucide-react"
import { useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { useReducedMotion } from "@/components/landing/motion"
import { SectionHeading } from "@/components/landing/SectionHeading"

/**
 * Two pill rows scrubbed in opposite directions by section scroll progress.
 * Row A = publish channels, row B = output languages.
 */

const PLATFORMS: { key: string; icon: LucideIcon }[] = [
  { key: "linkedin", icon: Linkedin },
  { key: "newsletter", icon: Mail },
  { key: "website", icon: Globe },
  { key: "youtube", icon: Youtube },
  { key: "x", icon: MessageSquareText },
  { key: "podcast", icon: Podcast },
]

const LANGUAGES: { key: string; icon: LucideIcon }[] = [
  { key: "en", icon: Languages },
  { key: "fr", icon: Languages },
  { key: "de", icon: Languages },
  { key: "es", icon: Languages },
  { key: "it", icon: Languages },
  { key: "nl", icon: Languages },
]

/** Horizontal travel of each row across the section's scroll range, in px. */
const ROW_TRAVEL = 160

function Pill({
  group,
  itemKey,
  icon: Icon,
}: {
  group: "platforms" | "languages"
  itemKey: string
  icon: LucideIcon
}): ReactNode {
  const { t } = useTranslation()
  return (
    <div className="flex shrink-0 items-center gap-2.5 rounded-full border border-border bg-background py-3.5 pr-5 pl-4 whitespace-nowrap">
      <Icon className="size-4 text-foreground" strokeWidth={1.75} aria-hidden="true" />
      <span className="text-sm font-medium text-foreground">
        {t(`landing.channels.${group}.${itemKey}.name`)}
      </span>
      <span className="text-xs text-muted-foreground">
        {t(`landing.channels.${group}.${itemKey}.blurb`)}
      </span>
    </div>
  )
}

function ScrubRow({
  group,
  items,
  x,
}: {
  group: "platforms" | "languages"
  items: { key: string; icon: LucideIcon }[]
  x: MotionValue<number> | undefined
}): ReactNode {
  return (
    <div className="flex justify-center">
      <motion.div {...(x ? { style: { x } } : {})} className="flex w-max gap-3">
        {items.map((item) => (
          <Pill key={item.key} group={group} itemKey={item.key} icon={item.icon} />
        ))}
        <div aria-hidden="true" className="flex gap-3">
          {items.map((item) => (
            <Pill
              key={`copy-${item.key}`}
              group={group}
              itemKey={item.key}
              icon={item.icon}
            />
          ))}
        </div>
      </motion.div>
    </div>
  )
}

export function Channels(): ReactNode {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const sectionRef = useRef<HTMLElement>(null)

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end start"],
  })

  const xA = useTransform(scrollYProgress, [0, 1], [-ROW_TRAVEL, ROW_TRAVEL])
  const xB = useTransform(scrollYProgress, [0, 1], [ROW_TRAVEL, -ROW_TRAVEL])

  return (
    <section
      ref={sectionRef}
      id="channels"
      className="scroll-mt-24 pb-24 sm:pb-32"
    >
      <div className="mx-auto max-w-[1440px] px-5 sm:px-8 lg:px-10">
        <SectionHeading
          align="center"
          title={t("landing.channels.title")}
          description={t("landing.channels.description")}
        />
      </div>

      <div className="mt-14 flex flex-col gap-3">
        <ScrubRow group="platforms" items={PLATFORMS} x={reduce ? undefined : xA} />
        <ScrubRow group="languages" items={LANGUAGES} x={reduce ? undefined : xB} />
      </div>
    </section>
  )
}
