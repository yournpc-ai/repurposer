import Lenis from "lenis"
import { useEffect, type ReactNode } from "react"

import { useReducedMotion } from "@/components/landing/motion"

const LENIS_OPTIONS = {
  duration: 1.6,
  easing: (t: number): number => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
  orientation: "vertical" as const,
  gestureOrientation: "vertical" as const,
  smoothWheel: true,
  wheelMultiplier: 1,
  touchMultiplier: 2,
}

const ANCHOR_OFFSET = -80

/**
 * Lenis smooth scrolling for the landing page only. Mounted by the landing
 * route; the workbench keeps native scrolling. Disabled under reduced motion.
 * Anchor clicks (`a[href^="#"]`) are intercepted and routed through Lenis so
 * in-page navigation stays on the smooth scroller.
 */
export function SmoothScroll({ children }: { children: ReactNode }): ReactNode {
  const prefersReducedMotion = useReducedMotion()

  useEffect(() => {
    if (prefersReducedMotion) return

    const lenis = new Lenis(LENIS_OPTIONS)

    let frame = 0
    function raf(time: number): void {
      lenis.raf(time)
      frame = requestAnimationFrame(raf)
    }
    frame = requestAnimationFrame(raf)

    function handleAnchorClick(event: MouseEvent): void {
      const target = event.target
      if (!(target instanceof Element)) return
      const anchor = target.closest('a[href^="#"]')
      if (!anchor) return
      const href = anchor.getAttribute("href")
      if (!href || href === "#") return
      const element = document.querySelector(href)
      if (!(element instanceof HTMLElement)) return
      event.preventDefault()
      lenis.scrollTo(element, { offset: ANCHOR_OFFSET })
    }

    document.addEventListener("click", handleAnchorClick)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener("click", handleAnchorClick)
      lenis.destroy()
    }
  }, [prefersReducedMotion])

  return <>{children}</>
}
