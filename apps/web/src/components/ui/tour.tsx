"use client"

import * as React from "react"
import { createPortal } from "react-dom"
import { Popover as PopoverPrimitive } from "@base-ui/react/popover"
import { ChevronLeft, ChevronRight, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * Tour — spotlight step-by-step guide (see docs/tasks/tour-component.md).
 *
 * Pure mechanism, zero behavior lock-in: `open` is controlled, persistence
 * (seen flags) and analytics belong to the caller via `onComplete`/`onSkip`.
 * Steps whose target selector matches nothing are skipped automatically.
 */

export interface TourStep {
  /** CSS selector of the element to highlight, e.g. "[data-tour='composer']". */
  target: string
  title: string
  description: string
  side?: "top" | "bottom" | "left" | "right"
  align?: "start" | "center" | "end"
}

export interface TourProps {
  steps: TourStep[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onComplete?: () => void
  onSkip?: () => void
}

const HIGHLIGHT_PADDING = 8

export function Tour({
  steps,
  open,
  onOpenChange,
  onComplete,
  onSkip,
}: TourProps) {
  const { t } = useTranslation()
  const [mounted, setMounted] = React.useState(false)
  const [index, setIndex] = React.useState(0)
  const [targetEl, setTargetEl] = React.useState<Element | null>(null)
  const [rect, setRect] = React.useState<DOMRect | null>(null)
  const [reducedMotion, setReducedMotion] = React.useState(false)
  const popupRef = React.useRef<HTMLDivElement>(null)

  // Read steps through a ref so effect behavior never depends on the caller
  // memoizing the array.
  const stepsRef = React.useRef(steps)
  stepsRef.current = steps

  React.useEffect(() => {
    setMounted(true)
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)")
    setReducedMotion(mq.matches)
    const onChange = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  const finish = React.useCallback(
    (kind: "complete" | "skip") => {
      setIndex(0)
      setTargetEl(null)
      setRect(null)
      if (kind === "complete") onComplete?.()
      else onSkip?.()
      onOpenChange(false)
    },
    [onComplete, onSkip, onOpenChange]
  )

  const goNext = React.useCallback(() => {
    if (index >= stepsRef.current.length - 1) finish("complete")
    else setIndex((i) => i + 1)
  }, [index, finish])

  const goPrev = React.useCallback(() => {
    setIndex((i) => Math.max(0, i - 1))
  }, [])

  // Resolve the current step's target; auto-skip steps with no matching
  // element. If nothing is showable, close silently (no complete/skip fired).
  React.useEffect(() => {
    if (!open) return
    const list = stepsRef.current
    let i = index
    while (i < list.length && !document.querySelector(list[i].target)) i++
    if (i >= list.length) {
      setIndex(0)
      setTargetEl(null)
      onOpenChange(false)
      return
    }
    if (i !== index) {
      setIndex(i)
      return
    }
    const el = document.querySelector(list[i].target)
    setTargetEl(el)
    el?.scrollIntoView({
      block: "center",
      behavior: reducedMotion ? "auto" : "smooth",
    })
  }, [open, index, reducedMotion, onOpenChange])

  // Track the highlight rect: scroll, resize, target size changes, and target
  // removal (advance when the element leaves the DOM mid-tour).
  React.useEffect(() => {
    if (!open || !targetEl) return
    const update = () => {
      if (!targetEl.isConnected) {
        setTargetEl(null)
        setRect(null)
        setIndex((i) => i + 1)
        return
      }
      setRect(targetEl.getBoundingClientRect())
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(targetEl)
    window.addEventListener("resize", update)
    window.addEventListener("scroll", update, { capture: true, passive: true })
    return () => {
      ro.disconnect()
      window.removeEventListener("resize", update)
      window.removeEventListener("scroll", update, { capture: true })
    }
  }, [open, targetEl])

  // Keyboard: Esc = skip, arrows = navigate.
  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        finish("skip")
      } else if (e.key === "ArrowRight") {
        e.preventDefault()
        goNext()
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        goPrev()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, finish, goNext, goPrev])

  // Focus the popup on every step so Tab/Esc land predictably.
  React.useEffect(() => {
    if (!open || !targetEl) return
    const id = requestAnimationFrame(() =>
      popupRef.current?.focus({ preventScroll: true })
    )
    return () => cancelAnimationFrame(id)
  }, [open, index, targetEl])

  if (!mounted || !open || steps.length === 0) return null

  const step = steps[Math.min(index, steps.length - 1)]
  const isLast = index >= steps.length - 1

  // Keep Tab cycling inside the popup.
  const trapTab = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab") return
    const root = popupRef.current
    if (!root) return
    const focusables = root.querySelectorAll<HTMLElement>(
      "button, a[href], [tabindex]:not([tabindex='-1'])"
    )
    if (focusables.length === 0) {
      e.preventDefault()
      return
    }
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const active = document.activeElement
    if (e.shiftKey && (active === first || active === root)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <>
      {rect &&
        createPortal(
          <>
            {/* Click blocker: background stays visible but non-interactive. */}
            <div
              aria-hidden
              className="fixed inset-0 z-[95]"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
              }}
            />
            {/* Spotlight ring + scrim in one element: the box-shadow is the
                scrim, and it animates with the ring's position/size. */}
            <div
              aria-hidden
              className={cn(
                "pointer-events-none fixed z-[96] rounded-md ring-2 ring-white/90",
                reducedMotion ? "" : "transition-all duration-300 ease-out"
              )}
              style={{
                top: rect.top - HIGHLIGHT_PADDING,
                left: rect.left - HIGHLIGHT_PADDING,
                width: rect.width + HIGHLIGHT_PADDING * 2,
                height: rect.height + HIGHLIGHT_PADDING * 2,
                boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.55)",
              }}
            />
          </>,
          document.body
        )}

      <PopoverPrimitive.Root
        open={!!targetEl}
        // Controlled: ignore close requests (outside press etc.) — the tour
        // closes only via its buttons/keys. Esc is handled globally above.
        onOpenChange={() => {}}
      >
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Positioner
            anchor={targetEl}
            side={step.side ?? "bottom"}
            align={step.align ?? "center"}
            sideOffset={12}
            collisionPadding={16}
            className="isolate z-[100]"
          >
            <PopoverPrimitive.Popup
              ref={popupRef}
              tabIndex={-1}
              onKeyDown={trapTab}
              className={cn(
                "flex w-80 flex-col gap-3 rounded-lg bg-popover p-4 text-popover-foreground shadow-xl ring-1 ring-border outline-hidden duration-150",
                "data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-1">
                  <PopoverPrimitive.Title className="text-sm font-medium">
                    {step.title}
                  </PopoverPrimitive.Title>
                  <PopoverPrimitive.Description className="text-xs leading-relaxed text-muted-foreground">
                    {step.description}
                  </PopoverPrimitive.Description>
                </div>
                <button
                  type="button"
                  aria-label={t("tour.skip")}
                  onClick={() => finish("skip")}
                  className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5" aria-hidden>
                  {steps.map((_, i) => (
                    <span
                      key={i}
                      className={cn(
                        "h-1.5 w-1.5 rounded-full transition-colors",
                        i === index ? "bg-foreground" : "bg-muted-foreground/30"
                      )}
                    />
                  ))}
                </div>
                <span className="sr-only">
                  {t("tour.stepOf", { current: index + 1, total: steps.length })}
                </span>
                <div className="flex items-center gap-2">
                  {index > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9"
                      onClick={goPrev}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      {t("tour.prev")}
                    </Button>
                  )}
                  {index === 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-9"
                      onClick={() => finish("skip")}
                    >
                      {t("tour.skip")}
                    </Button>
                  )}
                  <Button size="sm" className="h-9" onClick={goNext}>
                    {isLast ? t("tour.done") : t("tour.next")}
                    {!isLast && <ChevronRight className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            </PopoverPrimitive.Popup>
          </PopoverPrimitive.Positioner>
        </PopoverPrimitive.Portal>
      </PopoverPrimitive.Root>
    </>
  )
}
