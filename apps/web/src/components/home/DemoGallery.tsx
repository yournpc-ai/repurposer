import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react"
import { useTranslation } from "react-i18next"

import { ChevronLeft, ChevronRight, Volume2, VolumeX } from "lucide-react"

import { IconButton } from "@/components/ui/icon-button-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"

import { LANDING_GALLERY } from "@/components/landing/content"
import type { SkillReference } from "@/lib/skills"

interface Demo {
  src: string
  poster?: string
  title: string
  prompt: string
  styleLabel?: string
  templateReference?: SkillReference
}

function showcase(id: string): Demo {
  return {
    src: `/gallery/showcase/${id}.mp4`,
    poster: `/gallery/showcase/${id}.webp`,
    title: `landing.gallery.items.${id}.title`,
    prompt: `landing.showcase.requests.${id}`,
  }
}

function archivedDemo(id: string, hash: string): Demo {
  return {
    src: `https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/${id}-${hash}.mp4`,
    title: `recipes.shelf.demos.${id}.title`,
    prompt: `recipes.shelf.demos.${id}.prompt`,
  }
}

const families = [
  {
    id: "product-promo",
    sections: [
      {
        id: "website-product",
        demos: [
          showcase("product-promo"),
          archivedDemo("product-promo-oxvalue-product-evidence", "e1e78348"),
          archivedDemo("product-promo-oxvalue-energy-arc", "6f210db6"),
        ],
      },
    ],
  },
  {
    id: "talking-head",
    sections: [
      { id: "opinion-talking-head", demos: [showcase("talking-head")] },
    ],
  },
  {
    id: "text-animation",
    sections: [
      { id: "opinion-text", demos: [archivedDemo("text-short-clear-rhythm", "2d594025")] },
      { id: "quote-announcement", demos: [showcase("text-animation")] },
    ],
  },
  {
    id: "knowledge-explainer",
    sections: [
      {
        id: "concept-explainer",
        demos: [
          showcase("knowledge-explainer"),
          archivedDemo("knowledge-explainer-clear-expression", "73f4a743"),
        ],
      },
    ],
  },
]

function DemoCard({ demo, onPrefill }: { demo: Demo; onPrefill: (demo: Demo) => void }) {
  const { t } = useTranslation()
  const video = useRef<HTMLVideoElement>(null)

  const [muted, setMuted] = useState(true)

  function previewWithSound() {
    const el = video.current
    if (!el) return
    el.muted = false
    void el.play().catch((error: unknown) => {
      if (!(error instanceof DOMException) || error.name !== "NotAllowedError") return
      el.muted = true
      if (el.isConnected && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
        void el.play().catch(() => {})
      }
    })
  }

  useEffect(() => {
    const el = video.current
    if (!el) return
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)")
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          el.pause()
          el.muted = true
        } else if (!reduced.matches) {
          void el.play().catch(() => {})
        }
      },
      { threshold: 0.25 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <article
      className="demo-preview group relative aspect-video w-[min(82%,26.67rem)] shrink-0 overflow-hidden rounded-lg bg-media-scrim sm:w-[26.67rem]"
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse" && !matchMedia("(prefers-reduced-motion: reduce)").matches)
          previewWithSound()
      }}
      onPointerLeave={() => {
        if (video.current) video.current.muted = true
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget) && video.current) video.current.muted = true
      }}
    >
      <video
        ref={video}
        src={demo.src}
        poster={demo.poster}
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full object-contain"
        playsInline
        muted
        loop
        preload="metadata"
        onVolumeChange={(event) => setMuted(event.currentTarget.muted)}
      />
      <button
        type="button"
        aria-label={`${t("recipes.shelf.usePrompt")} · ${t(demo.title)}`}
        className="absolute inset-0 cursor-pointer rounded-[inherit] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-white"
        onClick={() => {
          if (video.current) video.current.muted = true
          onPrefill(demo)
        }}
      >
        <span className="demo-preview__overlay absolute inset-0 grid place-items-center bg-black/35">
          <span className="rounded-md bg-background px-4 py-2 text-sm font-medium text-foreground">
            {t("recipes.shelf.usePrompt")}
          </span>
        </span>
      </button>
      <div className="demo-preview__audio absolute bottom-2 left-2">
        <IconButton
          label={t(muted ? "recipes.shelf.playSound" : "recipes.shelf.mute")}
          pressed={!muted}
          variant="secondary"
          icon={muted ? <VolumeX /> : <Volume2 />}
          onClick={() => {
            if (video.current?.muted) previewWithSound()
            else if (video.current) video.current.muted = true
          }}
        />
      </div>
    </article>
  )
}

function DemoShelf({ demos, onPrefill }: { demos: Demo[]; onPrefill: (demo: Demo) => void }) {
  const { t } = useTranslation()
  const track = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; left: number } | null>(null)
  const dragged = useRef(false)
  const [edges, setEdges] = useState({ back: false, next: false })

  useEffect(() => {
    const el = track.current
    if (!el) return
    const measure = () => {
      const back = el.scrollLeft > 1
      const next = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
      setEdges((last) => (last.back === back && last.next === next ? last : { back, next }))
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    el.addEventListener("scroll", measure, { passive: true })
    return () => {
      observer.disconnect()
      el.removeEventListener("scroll", measure)
    }
  }, [demos])

  function page(direction: number) {
    const el = track.current
    if (!el) return
    el.scrollBy({
      left: direction * el.clientWidth * 0.85,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    })
  }

  return (
    <div className="relative">
      <div
        ref={track}
        className="no-scrollbar flex select-none gap-3 overflow-x-auto overscroll-x-contain rounded-lg"
        onPointerDown={(event) => {
          dragged.current = false
          if (event.pointerType === "mouse" && event.button === 0 && (edges.back || edges.next)) {
            drag.current = { x: event.clientX, left: event.currentTarget.scrollLeft }
          }
        }}
        onPointerMove={(event) => {
          if (!drag.current || event.buttons !== 1) return
          const delta = event.clientX - drag.current.x
          if (!dragged.current && Math.abs(delta) < 6) return
          dragged.current = true
          event.currentTarget.setPointerCapture(event.pointerId)
          event.currentTarget.scrollLeft = drag.current.left - delta
        }}
        onPointerUp={() => {
          drag.current = null
        }}
        onPointerCancel={() => {
          drag.current = null
        }}
        onClickCapture={(event) => {
          if (dragged.current && event.detail > 0) {
            event.stopPropagation()
            dragged.current = false
          }
        }}
      >
        {demos.map((demo) => (
          <DemoCard key={demo.src} demo={demo} onPrefill={onPrefill} />
        ))}
      </div>
      {edges.back && (
        <div className="absolute left-3 top-1/2 -translate-y-1/2">
          <IconButton
            label={t("recipes.shelf.previousPage")}
            icon={<ChevronLeft />}
            variant="secondary"
            onClick={() => page(-1)}
          />
        </div>
      )}
      {edges.next && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2">
          <IconButton
            label={t("recipes.shelf.nextPage")}
            icon={<ChevronRight />}
            variant="secondary"
            onClick={() => page(1)}
          />
        </div>
      )}
    </div>
  )
}

export function DemoGallery({
  scrollRef,
  onPrefill,
}: {
  scrollRef: RefObject<HTMLDivElement | null>
  onPrefill: (key: string, skill: SkillReference | null) => void
}) {
  const { t } = useTranslation()
  const [family, setFamily] = useState(families[0])
  const showSubnav = family.sections.length > 1
  const [activeSub, setActiveSub] = useState<string | undefined>(family.sections[0]?.id)
  const tabs = useRef<HTMLDivElement>(null)
  const sections = useRef(new Map<string, HTMLElement>())
  const reposition = useRef(false)

  // A family change while the tabs are pinned starts at its first shelf.
  useLayoutEffect(() => {
    if (reposition.current) {
      tabs.current?.parentElement?.scrollIntoView({ block: "start", behavior: "instant" })
      reposition.current = false
    }
  }, [family])

  useEffect(() => {
    const el = scrollRef.current
    const bar = tabs.current
    if (!el || !bar || !showSubnav) return
    const update = () => {
      const edge = bar.getBoundingClientRect().bottom + 8
      let active = family.sections[0].id
      for (const sub of family.sections) {
        const section = sections.current.get(sub.id)
        if (section && section.getBoundingClientRect().top <= edge) active = sub.id
      }
      setActiveSub(active)
    }
    update()
    el.addEventListener("scroll", update, { passive: true })
    const resize = new ResizeObserver(() => {
      // Leave enough room to pin the final section below both rows of tabs.
      bar.parentElement?.style.setProperty("--demo-section-space", `${el.clientHeight - bar.offsetHeight}px`)
      update()
    })
    resize.observe(el)
    resize.observe(bar)
    return () => {
      el.removeEventListener("scroll", update)
      resize.disconnect()
    }
  }, [family, scrollRef, showSubnav])

  function goTo(sub: string) {
    const el = scrollRef.current
    const bar = tabs.current
    const section = sections.current.get(sub)
    if (!el || !bar || !section) return
    const top =
      el.scrollTop + section.getBoundingClientRect().top - el.getBoundingClientRect().top - bar.offsetHeight
    el.scrollTo({
      top,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    })
  }

  return (
    <section
      aria-label={t("landing.showcase.label")}
      className="mx-auto mt-3 w-full max-w-5xl px-4 sm:px-6 md:mt-5"
      onVolumeChangeCapture={(event) => {
        const active = event.target
        if (!(active instanceof HTMLVideoElement) || active.muted) return
        for (const video of event.currentTarget.querySelectorAll("video")) {
          if (video !== active) video.muted = true
        }
      }}
    >
      <div
        ref={tabs}
        className="sticky top-0 z-10 flex min-w-0 flex-col items-center gap-3 bg-background py-3"
      >
        <SegmentedControl
          variant="tray"
          size="lg"
          className="home-gallery-categories"
          value={family.id}
          aria-label={t("landing.showcase.types")}
          options={families.map(({ id }) => ({ value: id, label: t(`landing.gallery.items.${id}.title`) }))}
          onChange={(id) => {
            const next = families.find((f) => f.id === id)
            if (!next || next === family) return
            reposition.current =
              !!scrollRef.current &&
              (tabs.current?.getBoundingClientRect().top ?? Infinity) <=
                scrollRef.current.getBoundingClientRect().top + 1
            setFamily(next)
            setActiveSub(next.sections[0]?.id)
          }}
        />
        {showSubnav && (
          <nav
            aria-label={t(`landing.gallery.items.${family.id}.title`)}
            className="flex max-w-full gap-1 overflow-x-auto"
          >
            {family.sections.map(({ id }) => (
              <button
                key={id}
                type="button"
                aria-current={activeSub === id ? "location" : undefined}
                className="min-h-10 shrink-0 border-b-2 border-transparent px-3 text-[13px] leading-5 text-muted-foreground aria-[current=location]:border-foreground aria-[current=location]:text-foreground"
                onClick={() => goTo(id)}
              >
                {t(`recipes.shelf.subs.${id}`)}
              </button>
            ))}
          </nav>
        )}
      </div>
      {family.sections.map(({ id, demos }) => (
        <section
          key={id}
          ref={(el) => {
            if (el) sections.current.set(id, el)
            else sections.current.delete(id)
          }}
          className={showSubnav ? "pt-6 pb-2 last:min-h-[var(--demo-section-space)]" : "pt-3 pb-2 md:pt-5"}
        >
          {showSubnav && (
            <h2 className="mb-3 text-lg leading-6 font-semibold tracking-tight">
              {t(`recipes.shelf.subs.${id}`)}
            </h2>
          )}
          <DemoShelf
            demos={demos}
            onPrefill={(demo) => {
              const entry = LANDING_GALLERY.find((item) => item.id === family.id)
              onPrefill(demo.prompt, demo.templateReference ?? entry?.skill ?? null)
            }}
          />
        </section>
      ))}
    </section>
  )
}
