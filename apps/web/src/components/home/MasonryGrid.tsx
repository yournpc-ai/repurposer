"use client"

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"

import { cn } from "@/lib/utils"

/** Data-driven masonry (ADR-046 D4): CSS grid + dense flow + row-span
 * measurement. Each item's rendered height (media ratio from registry w/h +
 * its caption, which varies by language) is measured and expressed as a
 * span of the 8px auto-row; a ResizeObserver re-spans on load / relayout.
 * Read-only topology — no drag, no reorder, span comes from the registry. */

const ROW_PX = 8
const GAP_PX = 16 // matches gap-4 on the grid container

// SSR has no layout to measure — effects only; the first client pass runs in
// a layout effect so the corrected span lands before paint (no flash).
const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect

export function MasonryGrid({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn("grid [grid-auto-flow:dense] [grid-auto-rows:8px]", className)}
    >
      {children}
    </div>
  )
}

export function MasonryItem({
  children,
  className,
  span,
  ...rest
}: {
  children: ReactNode
  className?: string
  /** Column span (featured cards = 2). Row span is measured, never set. */
  span?: 2
} & React.HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null)
  const [rowSpan, setRowSpan] = useState<number | null>(null)

  useIsoLayoutEffect(() => {
    const el = ref.current
    const content = el?.firstElementChild as HTMLElement | null
    if (!el || !content) return undefined
    const measure = () => {
      const h = content.getBoundingClientRect().height
      if (h > 0) setRowSpan(Math.ceil((h + GAP_PX) / (ROW_PX + GAP_PX)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(content)
    return () => ro.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={cn(span === 2 && "sm:col-span-2", className)}
      style={{
        gridRowEnd: rowSpan !== null ? `span ${rowSpan}` : "span 24",
        // Reserve the estimated slot but don't paint a mis-measured tile.
        visibility: rowSpan !== null ? "visible" : "hidden",
      }}
      {...rest}
    >
      {children}
    </div>
  )
}
