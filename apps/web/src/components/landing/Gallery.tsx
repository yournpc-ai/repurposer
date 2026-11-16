import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import {
  LANDING_GALLERY,
  type LandingGalleryItem,
} from "@/components/landing/content"
import { LANDING_CONTAINER } from "@/components/landing/layout"
import { useReducedMotion } from "@/components/landing/motion"
import { useAuth } from "@/lib/auth-context"
import { stageLandingCreate } from "@/lib/landingCreate"
import { cn } from "@/lib/utils"

const CARD_POSITION: Record<LandingGalleryItem["id"], string> = {
  "product-promo": "lg:col-start-1 lg:col-end-3 lg:row-start-1",
  "talking-head": "lg:col-start-3 lg:row-start-1 lg:row-end-3",
  "text-animation": "lg:col-start-1 lg:row-start-2",
  "knowledge-explainer": "lg:col-start-2 lg:row-start-2",
}

function GalleryCard({
  item,
  onCreate,
  autoPlay,
  className,
}: {
  item: LandingGalleryItem
  onCreate: (item: LandingGalleryItem) => void
  autoPlay: boolean
  className?: string
}): ReactNode {
  const { t } = useTranslation()
  const rootRef = useRef<HTMLElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const root = rootRef.current
    const video = videoRef.current
    if (!root || !video) return
    if (!autoPlay) {
      video.pause()
      return
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          void video.play().catch(() => undefined)
        } else {
          video.pause()
        }
      },
      { threshold: 0.12 },
    )
    observer.observe(root)
    return () => observer.disconnect()
  }, [autoPlay])

  return (
    <article
      ref={rootRef}
      className={cn(
        "group relative min-h-0 overflow-hidden rounded-2xl bg-muted",
        item.id === "talking-head"
          ? "aspect-[3/4] lg:aspect-auto"
          : "aspect-video lg:aspect-auto",
        className,
      )}
    >
      <video
        ref={videoRef}
        src={item.videoUrl}
        poster={item.posterUrl}
        muted
        loop
        playsInline
        preload="metadata"
        className="absolute inset-0 h-full w-full object-cover"
        aria-label={t(`landing.gallery.items.${item.id}.title`)}
      />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[75%] landing-gallery-scrim"
      />

      <button type="button" onClick={() => onCreate(item)} aria-label={`${t("landing.gallery.create")}: ${t(`landing.gallery.items.${item.id}.title`)}`} className="absolute inset-0 rounded-2xl focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-media-foreground" />

      <div className="pointer-events-none absolute inset-x-0 bottom-0 p-5 font-sans text-media-foreground sm:p-6">
        <h3 className="font-sans text-xl leading-tight font-medium sm:text-2xl tracking-[-0.02em]">
          {t(`landing.gallery.items.${item.id}.title`)}
        </h3>
        <p className="mt-2 max-w-md text-sm leading-6 font-normal text-media-foreground/80">
          {t(`landing.gallery.items.${item.id}.description`)}
        </p>
      </div>
    </article>
  )
}

export function Gallery(): ReactNode {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const reduce = useReducedMotion()
  const onCreate = useCallback(
    (item: LandingGalleryItem) => {
      stageLandingCreate({
        skill: item.skill,
        promptKey: `landing.gallery.items.${item.id}.prompt`,
      })
      if (isAuthenticated) void navigate({ to: "/home" })
      else setLoginOpen(true)
    },
    [isAuthenticated, navigate, setLoginOpen],
  )

  const galleryGrid = (
    <div className={cn("grid gap-5 lg:grid-cols-[1fr_1fr_0.96fr] lg:grid-rows-2", reduce ? "lg:h-[min(66svh,680px)]" : "lg:min-h-0 lg:flex-1 lg:max-h-[680px]")}>
      {LANDING_GALLERY.map((item) => (
        <GalleryCard
          key={item.id}
          item={item}
          onCreate={onCreate}
          autoPlay={!reduce}
          className={CARD_POSITION[item.id]}
        />
      ))}
    </div>
  )

  return (
    <section id="gallery" className={cn("scroll-mt-24 py-20 sm:py-24", !reduce && "lg:h-[170svh] lg:py-0")}>
      <div className={cn(LANDING_CONTAINER, !reduce && "lg:sticky lg:top-20 lg:flex lg:h-[calc(100svh-5rem)] lg:flex-col lg:justify-center lg:py-6")}>
        <h2 className="mb-10 lg:mb-6 text-center font-display text-3xl leading-[1.15] font-normal tracking-tight text-balance sm:text-4xl">{t("landing.gallery.heading")}</h2>
        {galleryGrid}
      </div>
    </section>
  )
}
