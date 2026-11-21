import { useEffect, useRef, useState, type ReactNode } from "react"
import { motion, useMotionValueEvent, useScroll } from "motion/react"
import { ArrowDown, ArrowUp, FileText, Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge-clean"
import { LANDING_GALLERY } from "./content"
import { DemoVideo } from "./CreationShowcase"
import { LogoMark } from "@/components/LogoMark"
import { LANDING_CONTAINER } from "./layout"
import { useReducedMotion } from "./motion"

const sample = LANDING_GALLERY[0]
const sampleClassName = "mt-2 aspect-video max-h-[26svh] w-full rounded-xl bg-muted object-contain"

function revealText(text: string, start: number, end: number, progress: number) {
  if (progress <= start) return ""
  if (progress >= end) return text
  return text.slice(0, Math.ceil(((progress - start) / (end - start)) * text.length))
}

function StoryNote({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex items-start gap-3 ${className}`}><LogoMark className="mt-1 size-5 shrink-0" /><p className="text-sm leading-6 text-muted-foreground">{children}</p></div>
}

function StoryAttachments({ className = "" }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <div role="group" aria-label={t("landing.story.attachments.label")} className={`flex min-w-0 flex-wrap gap-2 ${className}`}>
      <Badge size="md" icon={<img src={sample.posterUrl} alt="" className="size-4 rounded-sm object-cover" />}>
        {t("landing.story.attachments.image")}
      </Badge>
      <Badge size="md" icon={<FileText />}>{t("landing.story.attachments.document")}</Badge>
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
  const sent = p >= 0.15
  const outlineReady = p >= 0.22
  const delivered = p >= 0.44
  const revising = p >= 0.66
  const revisionSent = p >= 0.8
  const revisionAnswered = p >= 0.87
  const request = t("landing.story.request")
  const feedback = t("landing.story.feedback")
  const draft = sent
    ? revisionSent ? "" : revealText(feedback, 0.66, 0.8, p)
    : revealText(request, 0, 0.15, p)
  const transition = { duration: reduce ? 0 : 0.35, ease: "easeInOut" as const }

  useEffect(() => {
    const viewport = transcript.current
    const content = messages.current
    if (!viewport || !content) return
    const follow = () => { viewport.scrollTop = viewport.scrollHeight }
    const observer = new ResizeObserver(follow)
    observer.observe(content)
    follow()
    return () => observer.disconnect()
  }, [])
  return (
    <section ref={root} id="how-it-works" aria-label={t("landing.story.demoLabel")} className={`scroll-mt-20 ${reduce ? "py-20" : "h-[240svh] lg:h-[280svh]"}`}>
      <div className={reduce ? "relative" : "sticky top-20 flex h-[calc(100svh-5rem)] items-center overflow-hidden pb-14"}>
        <div className={LANDING_CONTAINER}>
          <div className="mx-auto w-full max-w-3xl">
            <h2 className="mb-7 text-center font-display text-2xl leading-[1.2] font-normal tracking-tight text-balance sm:mb-10 sm:text-4xl">
              {t(revising ? "landing.story.refineTitle" : delivered ? "landing.story.deliveryTitle" : "landing.story.idea.title")}
            </h2>
            <motion.div transition={transition} className="overflow-hidden rounded-3xl border border-subtle bg-card p-4 sm:p-6">
              <motion.div ref={transcript} initial={false} animate={{ height: sent ? reduce ? "auto" : "min(43svh, 420px)" : 0, opacity: sent ? 1 : 0 }} transition={transition} className={reduce ? "overflow-visible" : "overflow-hidden"}>
                <div ref={messages}>
                  <div className="ml-auto w-fit max-w-[85%]">
                    <StoryAttachments className="mb-2 justify-end" />
                    <p className="rounded-2xl bg-muted px-4 py-3 text-sm leading-6">{request}</p>
                  </div>
                  {outlineReady && (
                    <StoryNote className="mt-4">{t("landing.story.storyboardSummary")}</StoryNote>
                  )}
                  {outlineReady && !delivered && (
                    <p className="mt-3 pl-8 text-sm leading-6 text-muted-foreground">
                      <span className="shimmer">{t("landing.story.rendering")}</span>
                    </p>
                  )}
                  {delivered && (
                    <motion.div initial={{ opacity: reduce ? 1 : 0 }} animate={{ opacity: 1 }} transition={transition} className="mt-4 flex items-start gap-3">
                      <LogoMark className="mt-1 size-5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm leading-6 text-muted-foreground">{t("landing.story.delivery")}</p>
                        {reduce || revisionSent ? (
                          <img src={sample.posterUrl} alt={t("landing.story.posterAlt")} className={sampleClassName} />
                        ) : (
                          <DemoVideo item={sample} playing={visible && !background} className={sampleClassName} />
                        )}
                      </div>
                    </motion.div>
                  )}
                  {revisionSent && (
                    <p className="mt-4 ml-auto w-fit max-w-[85%] rounded-2xl bg-muted px-4 py-3 text-sm leading-6">{feedback}</p>
                  )}
                  {revisionAnswered && (
                    <StoryNote className="mt-4">{t("landing.story.revisionOpening")}</StoryNote>
                  )}
                </div>
              </motion.div>
              <motion.div transition={transition} className={`${sent ? "mt-5" : ""} rounded-2xl border border-subtle bg-card p-3 sm:p-4`}>
                {!sent && <StoryAttachments className="mb-3" />}
                <p className={`${sent ? "min-h-6 text-sm leading-6" : "min-h-16 text-base leading-7 sm:text-xl sm:leading-8"} text-foreground`}>
                  {!draft ? <span className="text-meta-foreground">{t("landing.story.followup")}</span> : <>{draft}<span aria-hidden className="ml-0.5 inline-block h-[1em] w-px translate-y-0.5 bg-foreground" /></>}
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
