import { useEffect, useId, useRef, useState } from "react"
import { ArrowUp, ChevronDown, Clapperboard, FileText, LayoutGrid, Plus } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"
import { LANDING_GALLERY, type LandingGalleryItem } from "./content"
import { LogoMark } from "@/components/LogoMark"
import { useReducedMotion } from "./motion"
import { useLandingCreate } from "./useLandingCreate"

const SHOWCASE_TICK_MS = 80

export function DemoVideo({ item, playing, className = "" }: { item: LandingGalleryItem; playing: boolean; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null)
  useEffect(() => {
    const video = ref.current
    if (!video) return
    if (playing) void video.play().catch(() => undefined)
    else video.pause()
    return () => video.pause()
  }, [playing, item.videoUrl])
  return <video ref={ref} src={item.videoUrl} autoPlay={playing} poster={item.posterUrl} muted loop playsInline preload="metadata" className={className} />
}

export function CreationShowcase() {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const create = useLandingCreate()
  const [active, setActive] = useState(0)
  const [progress, setProgress] = useState(0)
  const [docked, setDocked] = useState(false)
  const [visible, setVisible] = useState(false)
  const [background, setBackground] = useState(false)
  const root = useRef<HTMLElement>(null)
  const id = useId()
  const running = visible && !reduce && !background
  const item = LANDING_GALLERY[active]
  const mediaPath = `/gallery/showcase/${item.id}`
  const preview = { ...item, videoUrl: `${mediaPath}.mp4`, posterUrl: `${mediaPath}.webp` }
  useEffect(() => {
    if (!root.current) return
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.15 })
    observer.observe(root.current)
    const onVisibility = () => setBackground(document.hidden)
    onVisibility()
    document.addEventListener("visibilitychange", onVisibility)
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", onVisibility) }
  }, [])
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setProgress((value) => Math.min(100, value + 1)), SHOWCASE_TICK_MS)
    return () => window.clearInterval(timer)
  }, [running])
  useEffect(() => {
    if (progress < 100) return
    setActive((value) => (value + 1) % LANDING_GALLERY.length)
    setProgress(0)
  }, [progress])
  useEffect(() => {
    let frame = 0
    const update = () => {
      const bounds = root.current?.getBoundingClientRect()
      if (bounds) setDocked(bounds.top < window.innerHeight - 180 && bounds.bottom >= window.innerHeight)
    }
    const schedule = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener("scroll", schedule, { passive: true })
    window.addEventListener("resize", schedule)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("scroll", schedule)
      window.removeEventListener("resize", schedule)
    }
  }, [])
  const stepIcons = [FileText, LayoutGrid, Clapperboard]
  const stage = reduce ? 3 : progress > 50 ? 3 : progress > 28 ? 2 : progress > 12 ? 1 : 0
  const previewReady = stage >= 3
  const reply = t(`landing.showcase.replies.${item.id}`)
  const replyProgress = Math.min(1, Math.max(0, (progress - 50) / 32))
  const visibleReply = reduce ? reply : reply.slice(0, Math.ceil(replyProgress * reply.length))
  return (
    <section ref={root} id="showcase" aria-label={t("landing.showcase.label")} className={`landing-showcase scene-${active} relative scroll-mt-24 px-4 pt-8 pb-24 sm:px-8 sm:pt-12 lg:min-h-[160svh] lg:pt-10`}>
      <div aria-hidden className="landing-scene-wash absolute inset-0" />
      <div className="relative mx-auto max-w-[1200px] lg:sticky lg:top-24">
        <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-tab-${active}`} className="grid overflow-hidden rounded-2xl bg-card md:grid-cols-[1fr_3fr] lg:h-[calc(100svh-8rem)] lg:min-h-[520px]">
          <div className="flex min-h-0 flex-col p-4 sm:p-5">
            <div className="flex items-center gap-2 text-sm font-medium"><LogoMark className="size-5" /><span className="flex-1">{t(`landing.gallery.items.${item.id}.title`)}</span><ChevronDown className="size-4" /></div>
            <p key={item.id} className="mt-6 rounded-2xl bg-muted p-4 text-sm leading-6 text-foreground">{t(`landing.showcase.requests.${item.id}`)}</p>
            <div className="mt-7 hidden space-y-3 md:block text-sm text-muted-foreground">
              {["understand", "storyboard", "produce"].map((key, index) => <div key={key} className={`flex items-center gap-2 transition-[opacity,color] ${index < stage ? "text-meta-foreground" : "text-muted-foreground"} ${index > stage ? "opacity-35" : "opacity-100"}`}>
                {(() => { const Icon = stepIcons[index]; return <Icon className="size-4 shrink-0" /> })()}
                <span className={index === stage && stage < 3 ? "shimmer" : undefined}>{t(`landing.showcase.steps.${item.id}.${key}.${index < stage ? "done" : "active"}`)}</span>
              </div>)}
            </div>
            <p className={`mt-7 hidden text-sm md:block leading-6 whitespace-pre-line text-muted-foreground transition-opacity ${previewReady ? "opacity-100" : "opacity-0"}`}>{visibleReply}</p>
            <div className="mt-7 shrink-0 rounded-2xl border border-subtle bg-card p-3 md:mt-auto">
              <textarea readOnly onClick={() => create(item)} aria-label={t("landing.showcase.start")} placeholder={t("landing.showcase.start")} rows={2} className="block w-full resize-none bg-transparent text-sm leading-6 text-foreground outline-none placeholder:text-meta-foreground" />
              <div className="mt-4 flex items-center justify-between">
                <button type="button" onClick={() => create(item)} aria-label={t("landing.showcase.attach")} className="grid size-8 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent"><Plus className="size-5" /></button>
                <button type="button" onClick={() => create(item)} aria-label={t("landing.showcase.send")} className="grid size-8 place-items-center rounded-full bg-foreground text-background transition-opacity hover:opacity-80"><ArrowUp className="size-5" /></button>
              </div>
            </div>
          </div>
          <div className="relative flex min-h-[300px] items-center justify-center overflow-hidden bg-muted p-6 sm:p-10 md:min-h-[480px]">
            <div className={`absolute top-5 left-6 flex items-center gap-2 text-xs text-meta-foreground transition-opacity ${previewReady ? "opacity-100" : "opacity-0"}`}><span className="size-1.5 rounded-full bg-current" />{t("landing.showcase.disclosure")}</div>
            <div aria-hidden={!previewReady} className={`w-full transition-[opacity,transform] duration-500 ease-enter motion-reduce:transform-none motion-reduce:transition-none ${previewReady ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"}`}>
              <DemoVideo key={item.id} item={preview} playing={running && previewReady} className={`max-h-[430px] w-full rounded-lg object-contain ${item.id === "talking-head" ? "mx-auto max-w-[260px]" : "aspect-video"}`} />
            </div>
          </div>
        </div>
      </div>
        <div className={`${docked ? "fixed" : "absolute"} inset-x-0 bottom-6 z-30 flex justify-center px-4 pointer-events-none`}>
          <div role="tablist" aria-label={t("landing.showcase.types")} className="pointer-events-auto flex max-w-full gap-1 overflow-x-auto rounded-full bg-media-control p-1.5 text-media-control-foreground backdrop-blur-xl">
            {LANDING_GALLERY.map((entry, index) => <button key={entry.id} id={`${id}-tab-${index}`} role="tab" aria-selected={active === index} aria-controls={`${id}-panel`} tabIndex={active === index ? 0 : -1}
              onKeyDown={(event) => {
                const next = event.key === "ArrowRight" ? (index + 1) % 4 : event.key === "ArrowLeft" ? (index + 3) % 4 : event.key === "Home" ? 0 : event.key === "End" ? 3 : -1
                if (next < 0) return
                event.preventDefault(); setActive(next); setProgress(0)
                document.getElementById(`${id}-tab-${next}`)?.focus()
              }}
              onClick={() => { setActive(index); setProgress(0) }}
              className={`relative shrink-0 overflow-hidden rounded-full px-3 py-2.5 text-xs transition-colors sm:px-5 sm:text-sm ${active === index ? "bg-card text-foreground" : "text-media-control-foreground hover:bg-media-control-hover"}`}>
              {t(`landing.gallery.items.${entry.id}.title`)}
            </button>)}
          </div>
        </div>
    </section>
  )
}
