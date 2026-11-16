import { useEffect, useRef, useState, type ReactNode } from "react"
import { motion, useMotionValueEvent, useScroll } from "motion/react"
import { ArrowDown, ArrowUp, FileText, Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import {
  Attachment,
  AttachmentContent,
  AttachmentMedia,
  AttachmentTitle,
} from "@/components/ui/attachment"
import { LANDING_GALLERY } from "./content"
import { DemoVideo } from "./CreationShowcase"
import { LogoMark } from "@/components/LogoMark"
import { LANDING_CONTAINER } from "./layout"
import { useReducedMotion } from "./motion"

function revealText(text: string, start: number, end: number, progress: number) {
  if (progress <= start) return ""
  if (progress >= end) return text
  return text.slice(0, Math.ceil(((progress - start) / (end - start)) * text.length))
}

function StoryNote({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex items-start gap-3 ${className}`}><LogoMark className="mt-1 size-5 shrink-0" /><p className="text-sm leading-6 text-muted-foreground">{children}</p></div>
}

type StoryStep = { active: string; done: string; start: number; end: number }

function StoryWorkStep({ step, progress }: { step: StoryStep; progress: number }) {
  if (progress < step.start) return null
  const complete = progress >= step.end
  return <div className={`mt-5 pl-8 text-left text-sm leading-6 transition-colors ${complete ? "text-meta-foreground" : "text-muted-foreground"}`}>
    <span className={complete ? undefined : "shimmer"}>{complete ? step.done : step.active}</span>
  </div>
}

function StoryAttachments({ className = "" }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <div role="group" aria-label={t("landing.story.attachments.label")} className={`flex min-w-0 flex-wrap gap-2 ${className}`}>
      <Attachment size="xs">
        <AttachmentMedia variant="image">
          <img src={LANDING_GALLERY[0].posterUrl} alt="" />
        </AttachmentMedia>
        <AttachmentContent>
          <AttachmentTitle className="font-normal">{t("landing.story.attachments.image")}</AttachmentTitle>
        </AttachmentContent>
      </Attachment>
      <Attachment size="xs">
        <AttachmentMedia><FileText /></AttachmentMedia>
        <AttachmentContent>
          <AttachmentTitle className="font-normal">{t("landing.story.attachments.document")}</AttachmentTitle>
        </AttachmentContent>
      </Attachment>
    </div>
  )
}

export function CreationStory() {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const root = useRef<HTMLElement>(null)
  const transcript = useRef<HTMLDivElement>(null)
  const messages = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)
  const [visible, setVisible] = useState(false)
  const [background, setBackground] = useState(false)
  const { scrollYProgress } = useScroll({ target: root, offset: ["start start", "end end"] })
  useMotionValueEvent(scrollYProgress, "change", setProgress)
  useEffect(() => {
    if (!root.current) return
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting))
    observer.observe(root.current)
    const update = () => setBackground(document.hidden)
    update()
    document.addEventListener("visibilitychange", update)
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", update) }
  }, [])
  const p = reduce ? 1 : progress
  const sent = p >= 0.1
  const delivered = p >= 0.32
  const revising = p >= 0.44
  const revised = p >= 0.53
  const request = t("landing.story.request")
  const feedback = t("landing.story.feedback")
  const suggested = p >= 0.6
  const confirming = p >= 0.67
  const confirmed = p >= 0.76
  const redelivered = p >= 0.94
  const confirmation = t("landing.story.confirmation")
  const initialSteps = [
    { active: t("landing.story.workSteps.understand.active"), done: t("landing.story.workSteps.understand.done"), start: 0.13, end: 0.16 },
    { active: t("landing.story.workSteps.storyboard.active"), done: t("landing.story.workSteps.storyboard.done"), start: 0.19, end: 0.22 },
    { active: t("landing.story.workSteps.produce.active"), done: t("landing.story.workSteps.produce.done"), start: 0.26, end: 0.29 },
  ]
  const revisionSteps = [
    { active: t("landing.story.revisionSteps.locate.active"), done: t("landing.story.revisionSteps.locate.done"), start: 0.79, end: 0.82 },
    { active: t("landing.story.revisionSteps.revise.active"), done: t("landing.story.revisionSteps.revise.done"), start: 0.84, end: 0.87 },
    { active: t("landing.story.revisionSteps.check.active"), done: t("landing.story.revisionSteps.check.done"), start: 0.9, end: 0.92 },
  ]
  useEffect(() => {
    const viewport = transcript.current
    const content = messages.current
    if (!viewport || !content) return
    const follow = () => { viewport.scrollTop = viewport.scrollHeight }
    const observer = new ResizeObserver(follow)
    observer.observe(content)
    follow()
    return () => observer.disconnect()
  }, [sent, delivered, revised, suggested, confirmed, redelivered])
  const typing = confirming && !confirmed
    ? confirmation.slice(0, Math.ceil(Math.min(1, (p - 0.67) / 0.09) * confirmation.length))
    : revising && !revised
      ? feedback.slice(0, Math.ceil(Math.min(1, (p - 0.44) / 0.09) * feedback.length))
      : !sent ? request.slice(0, Math.ceil(Math.min(1, p / 0.1) * request.length)) : ""
  const transition = { duration: reduce ? 0 : 0.45, ease: "easeInOut" as const }
  return (
    <section ref={root} id="how-it-works" aria-label={t("landing.story.demoLabel")} className={`scroll-mt-20 ${reduce ? "py-20" : "h-[520svh]"}`}>
      <div className={reduce ? "relative" : "sticky top-20 flex h-[calc(100svh-5rem)] items-center overflow-hidden pb-14"}>
        <div className={LANDING_CONTAINER}>
          <div className="mx-auto w-full max-w-3xl">
            <h2 className="mb-7 text-center font-display text-2xl leading-[1.2] font-normal tracking-tight text-balance sm:mb-10 sm:text-4xl">
              {t(redelivered ? "landing.story.redeliveryTitle" : revising ? "landing.story.refineTitle" : delivered ? "landing.story.deliveryTitle" : "landing.story.idea.title")}
            </h2>
            <motion.div transition={transition} className="overflow-hidden rounded-3xl border border-subtle bg-card p-4 sm:p-6">
              <motion.div ref={transcript} initial={false} animate={{ height: sent ? reduce ? "auto" : "min(43svh, 420px)" : 0, opacity: sent ? 1 : 0 }} transition={transition} className={reduce ? "overflow-visible" : "overflow-hidden"}>
                <div ref={messages}>
                <div className="ml-auto w-fit max-w-[85%]">
                  <StoryAttachments className="mb-2 justify-end" />
                  <p className="rounded-2xl bg-muted px-4 py-3 text-sm leading-6">{request}</p>
                </div>
                <StoryNote className="mt-4">{revealText(t("landing.story.opening"), 0.1, 0.13, p)}</StoryNote>
                <StoryWorkStep step={initialSteps[0]} progress={p} />
                <StoryWorkStep step={initialSteps[1]} progress={p} />
                <motion.div initial={false} animate={{ height: p >= 0.22 ? "auto" : 0, opacity: p >= 0.22 ? 1 : 0 }} transition={transition} className="overflow-hidden">
                  <StoryNote className="mt-5">{revealText(t("landing.story.storyboardSummary"), 0.22, 0.26, p)}</StoryNote>
                </motion.div>
                <StoryWorkStep step={initialSteps[2]} progress={p} />
                <motion.div initial={false} animate={{ height: p >= 0.29 ? "auto" : 0, opacity: p >= 0.29 ? 1 : 0 }} transition={transition} className="overflow-hidden">
                  <div className="mt-5 flex items-start gap-3">
                    <LogoMark className="mt-1 size-5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm leading-6 text-muted-foreground">{revealText(t("landing.story.delivery"), 0.29, 0.32, p)}</p>
                      <motion.div initial={false} animate={{ height: delivered ? "auto" : 0, opacity: delivered ? 1 : 0 }} transition={transition} className="overflow-hidden">
                        <DemoVideo item={LANDING_GALLERY[0]} playing={visible && delivered && !revised && !reduce && !background} className="mt-3 aspect-video max-h-[26svh] w-full rounded-xl bg-muted object-contain" />
                      </motion.div>
                    </div>
                  </div>
                </motion.div>
                <motion.div initial={false} animate={{ height: revised ? "auto" : 0, opacity: revised ? 1 : 0 }} transition={transition} className="overflow-hidden">
                  <p className="mt-4 ml-auto w-fit max-w-[85%] rounded-2xl bg-muted px-4 py-3 text-sm leading-6">{feedback}</p>
                </motion.div>
                <motion.div initial={false} animate={{ height: suggested ? "auto" : 0, opacity: suggested ? 1 : 0 }} transition={transition} className="overflow-hidden">
                  <StoryNote className="mt-4">{revealText(t("landing.story.suggestion"), 0.6, 0.67, p)}</StoryNote>
                </motion.div>
                <motion.div initial={false} animate={{ height: confirmed ? "auto" : 0, opacity: confirmed ? 1 : 0 }} transition={transition} className="overflow-hidden">
                  <p className="mt-4 ml-auto w-fit max-w-[85%] rounded-2xl bg-muted px-4 py-3 text-sm leading-6">{confirmation}</p>
                  <StoryNote className="mt-4">{revealText(t("landing.story.revisionOpening"), 0.76, 0.79, p)}</StoryNote>
                  <StoryWorkStep step={revisionSteps[0]} progress={p} />
                  <motion.div initial={false} animate={{ height: p >= 0.82 ? "auto" : 0, opacity: p >= 0.82 ? 1 : 0 }} transition={transition} className="overflow-hidden">
                    <StoryNote className="mt-5">{revealText(t("landing.story.revisionLocation"), 0.82, 0.84, p)}</StoryNote>
                  </motion.div>
                  <StoryWorkStep step={revisionSteps[1]} progress={p} />
                  <motion.div initial={false} animate={{ height: p >= 0.87 ? "auto" : 0, opacity: p >= 0.87 ? 1 : 0 }} transition={transition} className="overflow-hidden">
                    <StoryNote className="mt-5">{revealText(t("landing.story.revisionSummary"), 0.87, 0.9, p)}</StoryNote>
                  </motion.div>
                  <StoryWorkStep step={revisionSteps[2]} progress={p} />
                  <motion.div initial={false} animate={{ height: p >= 0.92 ? "auto" : 0, opacity: p >= 0.92 ? 1 : 0 }} transition={transition} className="overflow-hidden">
                    <div className="mt-5 flex items-start gap-3"><LogoMark className="mt-1 size-5 shrink-0" /><div className="min-w-0 flex-1">
                      <p className="text-sm leading-6 text-muted-foreground">{revealText(t("landing.story.redelivery"), 0.92, 0.94, p)}</p>
                      <motion.div initial={false} animate={{ height: redelivered ? "auto" : 0, opacity: redelivered ? 1 : 0 }} transition={transition} className="overflow-hidden">
                        <DemoVideo item={LANDING_GALLERY[0]} playing={visible && redelivered && !reduce && !background} className="mt-3 aspect-video max-h-[26svh] w-full rounded-xl bg-muted object-contain" />
                      </motion.div>
                    </div></div>
                  </motion.div>
                </motion.div>
                </div>
              </motion.div>
              <motion.div transition={transition} className={`${sent ? "mt-5" : ""} rounded-2xl border border-subtle bg-card p-3 sm:p-4`}>
                {!sent && <StoryAttachments className="mb-3" />}
                <p className={`${sent ? "min-h-6 text-sm leading-6" : "min-h-16 text-base leading-7 sm:text-xl sm:leading-8"} text-foreground`}>
                  {!typing ? <span className="text-meta-foreground">{t("landing.story.followup")}</span> : <>{typing}<span aria-hidden className="ml-0.5 inline-block h-[1em] w-px translate-y-0.5 bg-foreground" /></>}
                </p>
                <div aria-hidden className="mt-4 flex items-center justify-between text-muted-foreground">
                  <Plus className="size-5" />
                  <span className="grid size-9 place-items-center rounded-full bg-foreground text-background"><ArrowUp className="size-5" /></span>
                </div>
              </motion.div>
            </motion.div>
          </div>
        </div>
        {!reduce && <span className="absolute inset-x-0 bottom-6 flex items-center justify-center gap-2 text-xs text-meta-foreground">{t("landing.story.scroll")}<ArrowDown className="size-3.5" /></span>}
      </div>
    </section>
  )
}
