"use client"

import * as React from "react"
import { ArrowDownIcon } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"
import { IconButton } from "@/components/ui/icon-button-clean"
import { cn } from "@/lib/utils"

type DivProps = React.ComponentProps<"div">

type ThreadScroll = {
  viewport: React.RefObject<HTMLDivElement | null>
  following: React.RefObject<boolean>
  away: boolean
  measure: () => void
  scrollToEnd: (options?: ScrollOptions) => void
}

const ThreadScrollContext = React.createContext<ThreadScroll | null>(null)

export function useMessageScroller() {
  const scroll = React.useContext(ThreadScrollContext)
  if (!scroll) throw new Error("Missing thread scroll provider")
  return scroll
}

export function MessageScrollerProvider({ children }: React.PropsWithChildren) {
  const viewport = React.useRef<HTMLDivElement>(null)
  const following = React.useRef(true)
  const [away, setAway] = React.useState(false)
  const measure = React.useCallback(() => {
    const el = viewport.current
    if (el) setAway(el.scrollHeight - el.clientHeight - el.scrollTop > 8)
  }, [])
  const scrollToEnd = React.useCallback((options: ScrollOptions = {}) => {
    following.current = true
    const el = viewport.current
    if (el) el.scrollTo({ ...options, top: el.scrollHeight })
  }, [])
  return <ThreadScrollContext.Provider value={{ viewport, following, away, measure, scrollToEnd }}>
    {children}
  </ThreadScrollContext.Provider>
}

export function MessageScroller({ className, ...props }: DivProps) {
  return <div data-slot="message-scroller" className={cn("relative flex size-full min-h-0 flex-col overflow-hidden", className)} {...props} />
}

export function MessageScrollerViewport({ className, ...props }: DivProps) {
  const { viewport, following, measure } = useMessageScroller()
  const intentAt = React.useRef(-Infinity)
  const intent = () => { intentAt.current = performance.now() }
  React.useLayoutEffect(() => {
    const el = viewport.current
    if (!el) return
    const resize = () => {
      if (following.current) el.scrollTop = el.scrollHeight
      measure()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(el)
    if (el.firstElementChild) observer.observe(el.firstElementChild)
    resize()
    return () => observer.disconnect()
  }, [following, measure, viewport])

  return <div {...props} ref={viewport} tabIndex={0} data-slot="message-scroller-viewport"
    className={cn("size-full min-h-0 min-w-0 overflow-y-auto overscroll-contain contain-content", className)}
    onWheel={intent} onPointerDown={intent} onTouchMove={intent} onKeyDown={intent}
    onScroll={() => {
      const el = viewport.current
      if (!el) return
      const atEnd = el.scrollHeight - el.clientHeight - el.scrollTop <= 8
      if (atEnd || performance.now() - intentAt.current < 700) following.current = atEnd
      measure()
    }} />
}

export function MessageScrollerContent({ className, ...props }: DivProps) {
  return <div data-slot="message-scroller-content" className={cn("flex h-max min-h-full flex-col gap-6", className)} {...props} />
}

export function MessageScrollerItem({ className, ...props }: DivProps) {
  return <div data-slot="message-scroller-item" className={cn("min-w-0 shrink-0", className)} {...props} />
}

export function MessageScrollerButton() {
  const { t } = useTranslation()
  const { away, scrollToEnd } = useMessageScroller()
  if (!away) return null
  return (
    <IconButton
      data-slot="message-scroller-button"
      label={t("chat.scrollToEnd")}
      icon={<ArrowDownIcon className="size-4" />}
      variant="secondary"
      style={{
        position: "absolute",
        ["--radius" as string]: "9999px",
        ["--size" as string]: "32px",
      }}
      className="inset-s-1/2 bottom-3 z-20 size-8 -translate-x-1/2 rounded-full border border-border bg-background/95 shadow-sm backdrop-blur-sm"
      onClick={() => scrollToEnd()}
    />
  )
}

export function useMessageScrollerViewportAnchor(
  rowRef: React.RefObject<HTMLElement | null>, live: boolean,
) {
  const { viewport, following, measure } = useMessageScroller()
  const pendingRef = React.useRef<{ element: HTMLElement, top: number } | null>(null)
  const record = React.useCallback((element: HTMLElement | null, top?: number) => {
    if (element) pendingRef.current = { element, top: top ?? element.getBoundingClientRect().top }
  }, [])

  const recordReadingEdge = React.useCallback(() => {
    const row = rowRef.current
    if (!row || pendingRef.current) return
    const content = row.closest<HTMLElement>(
      "[data-slot=message-scroller-content]",
    )
    const viewport = row.closest<HTMLElement>(
      "[data-slot=message-scroller-viewport]",
    )
    if (!content || !viewport) return
    const viewportRect = viewport.getBoundingClientRect()
    for (const edge of content.querySelectorAll<HTMLElement>(
      "[data-message-scroller-reading-edge]",
    )) {
      if (!(row.compareDocumentPosition(edge) & Node.DOCUMENT_POSITION_FOLLOWING)) {
        continue
      }
      const rect = edge.getBoundingClientRect()
      if (rect.height === 0) continue
      // A reply/output outside the viewport is not a reading anchor. In
      // particular, never pull a user reading older history back to this turn.
      if (rect.top < viewportRect.top || rect.top > viewportRect.bottom) return
      record(edge, rect.top)
      return
    }
  }, [record, rowRef])

  React.useLayoutEffect(() => {
    if (!live) return
    // Layout cleanup sees the pre-seal DOM; the following layout effect sees
    // the same real edge after React commits live -> Worked.
    return recordReadingEdge
  }, [live, recordReadingEdge])

  const stopTracking = React.useRef<(() => void) | null>(null)
  React.useLayoutEffect(() => () => stopTracking.current?.(), [])

  React.useLayoutEffect(() => {
    const anchor = pendingRef.current
    pendingRef.current = null
    const el = viewport.current
    const row = rowRef.current
    if (!anchor?.element.isConnected || !el || !row) return
    stopTracking.current?.()
    const align = () => {
      if (anchor.element.isConnected) el.scrollTop += anchor.element.getBoundingClientRect().top - anchor.top
    }
    align()
    // A grid disclosure keeps changing height after the React commit.
    // Hold the same edge for that transition, yielding immediately to a gesture.
    const resize = row.getAnimations?.({ subtree: true }).find(animation =>
      "transitionProperty" in animation && animation.transitionProperty === "grid-template-rows")
    const finish = () => {
      following.current = el.scrollHeight - el.clientHeight - el.scrollTop <= 8
      measure()
    }
    if (!resize) {
      finish()
      return
    }
    following.current = false
    const observer = new ResizeObserver(align)
    observer.observe(row)
    const intents = ["wheel", "pointerdown", "touchmove", "keydown"]
    const stop = () => {
      observer.disconnect()
      for (const event of intents) el.removeEventListener(event, stop)
      resize.removeEventListener("finish", settled)
      resize.removeEventListener("cancel", settled)
      stopTracking.current = null
      finish()
    }
    const settled = () => { align(); stop() }
    stopTracking.current = stop
    for (const event of intents) el.addEventListener(event, stop, { passive: true })
    resize.addEventListener("finish", settled)
    resize.addEventListener("cancel", settled)
  })
  return record
}
