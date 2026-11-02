"use client"

import * as React from "react"
import {
  MessageScroller as MessageScrollerPrimitive,
  useMessageScroller,
  useMessageScrollerScrollable,
  useMessageScrollerVisibility,
} from "@shadcn/react/message-scroller"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ArrowDownIcon } from "lucide-react"

type ViewportAnchor = {
  element: HTMLElement
  viewport: HTMLElement
  content: HTMLElement
  top: number
  contentHeight: number
  suppressionId: number | null
}

type ViewportAnchorBridge = {
  begin: (content: HTMLElement) => number
  finish: (id: number, waitForResize: boolean) => void
}

const ViewportAnchorContext =
  React.createContext<ViewportAnchorBridge | null>(null)

function MessageScrollerProvider({
  autoScroll = false,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Provider>) {
  const [autoScrollSuppressed, setAutoScrollSuppressed] = React.useState(false)
  const autoScrollRef = React.useRef(autoScroll)
  const suppressionRef = React.useRef(0)
  const observerRef = React.useRef<ResizeObserver | null>(null)
  const releaseFrameRef = React.useRef<number | null>(null)
  autoScrollRef.current = autoScroll

  const clearRelease = React.useCallback(() => {
    if (releaseFrameRef.current !== null) {
      cancelAnimationFrame(releaseFrameRef.current)
      releaseFrameRef.current = null
    }
    observerRef.current?.disconnect()
    observerRef.current = null
  }, [])

  const scheduleRelease = React.useCallback(
    (id: number) => {
      if (
        suppressionRef.current !== id ||
        releaseFrameRef.current !== null
      ) {
        return
      }
      // The primitive's resize handler queues its state sync before this
      // one-shot bridge queues re-arming. Restoring autoScroll earlier could
      // immediately undo the layout-effect compensation.
      releaseFrameRef.current = requestAnimationFrame(() => {
        releaseFrameRef.current = null
        if (suppressionRef.current !== id) return
        clearRelease()
        setAutoScrollSuppressed(false)
      })
    },
    [clearRelease],
  )

  const bridge = React.useMemo<ViewportAnchorBridge>(
    () => ({
      begin(content) {
        clearRelease()
        const id = ++suppressionRef.current
        if (!autoScrollRef.current) return id
        setAutoScrollSuppressed(true)
        // This observer does not measure or move geometry. It only holds the
        // primitive's autoScroll through this gesture's resize delivery.
        if (typeof ResizeObserver !== "undefined") {
          const observer = new ResizeObserver(() => scheduleRelease(id))
          observer.observe(content)
          observerRef.current = observer
        }
        return id
      },
      finish(id, waitForResize) {
        if (suppressionRef.current !== id) return
        if (waitForResize && observerRef.current) return
        scheduleRelease(id)
      },
    }),
    [clearRelease, scheduleRelease],
  )

  React.useEffect(
    () => () => {
      clearRelease()
    },
    [clearRelease],
  )

  return (
    <ViewportAnchorContext.Provider value={bridge}>
      <MessageScrollerPrimitive.Provider
        {...props}
        autoScroll={autoScroll && !autoScrollSuppressed}
      />
    </ViewportAnchorContext.Provider>
  )
}

/** Keep a real row or the following visible reply/output at its pre-commit
 * viewport position. The primitive remains the only scrollport and owner of
 * following; this hook adds no observer, timer or follow-state override. */
function useMessageScrollerViewportAnchor(
  rowRef: React.RefObject<HTMLElement | null>,
  live: boolean,
) {
  const bridge = React.useContext(ViewportAnchorContext)
  const pendingRef = React.useRef<ViewportAnchor | null>(null)

  const finish = React.useCallback(
    (anchor: ViewportAnchor, waitForResize: boolean) => {
      if (anchor.suppressionId !== null) {
        bridge?.finish(anchor.suppressionId, waitForResize)
      }
    },
    [bridge],
  )

  const record = React.useCallback(
    (element: HTMLElement | null, top?: number) => {
      if (!element) return
      const viewport = element.closest<HTMLElement>(
        "[data-slot=message-scroller-viewport]",
      )
      const content = element.closest<HTMLElement>(
        "[data-slot=message-scroller-content]",
      )
      if (!viewport || !content) return
      if (pendingRef.current) finish(pendingRef.current, false)
      pendingRef.current = {
        element,
        viewport,
        content,
        top: top ?? element.getBoundingClientRect().top,
        contentHeight: content.getBoundingClientRect().height,
        suppressionId: bridge?.begin(content) ?? null,
      }
    },
    [bridge, finish],
  )

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

  React.useLayoutEffect(() => {
    const anchor = pendingRef.current
    if (!anchor) return
    pendingRef.current = null
    if (!anchor.element.isConnected || !anchor.viewport.isConnected) {
      finish(anchor, false)
      return
    }
    const delta = anchor.element.getBoundingClientRect().top - anchor.top
    if (Math.abs(delta) > 0.5) anchor.viewport.scrollTop += delta
    finish(
      anchor,
      anchor.content.isConnected &&
        anchor.content.getBoundingClientRect().height !== anchor.contentHeight,
    )
  })

  React.useLayoutEffect(
    () => () => {
      // On unmount the live capture above runs first; cancel its unused anchor
      // rather than leaving autoScroll suppressed.
      const anchor = pendingRef.current
      pendingRef.current = null
      if (anchor) finish(anchor, false)
    },
    [finish],
  )

  return record
}

function MessageScroller({
  className,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Root>) {
  return (
    <MessageScrollerPrimitive.Root
      data-slot="message-scroller"
      className={cn(
        "group/message-scroller relative flex size-full min-h-0 flex-col overflow-hidden",
        className
      )}
      {...props}
    />
  )
}

function MessageScrollerViewport({
  className,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Viewport>) {
  return (
    <MessageScrollerPrimitive.Viewport
      data-slot="message-scroller-viewport"
      className={cn(
        // No scrollbar-gutter-stable: it reserves a permanent track on the
        // right even when content fits (a stray always-on scrollbar rail).
        // Overlay-style auto-hiding is the chat-surface norm (2026-08-04).
        "size-full min-h-0 min-w-0 scrollbar-thin overflow-y-auto overscroll-contain contain-content data-autoscrolling:scrollbar-thumb-transparent data-autoscrolling:scrollbar-track-transparent",
        className
      )}
      {...props}
    />
  )
}

function MessageScrollerContent({
  className,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Content>) {
  return (
    <MessageScrollerPrimitive.Content
      data-slot="message-scroller-content"
      className={cn("flex h-max min-h-full flex-col gap-6", className)}
      {...props}
    />
  )
}

function MessageScrollerItem({
  className,
  scrollAnchor = false,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Item>) {
  return (
    <MessageScrollerPrimitive.Item
      data-slot="message-scroller-item"
      scrollAnchor={scrollAnchor}
      className={cn(
        "min-w-0 shrink-0 [contain-intrinsic-size:auto_10rem] [content-visibility:auto]",
        className
      )}
      {...props}
    />
  )
}

function MessageScrollerButton({
  direction = "end",
  className,
  children,
  render,
  variant = "ghost",
  size = "icon-lg",
  ...props
}: Omit<React.ComponentProps<typeof MessageScrollerPrimitive.Button>, "render"> &
  Pick<React.ComponentProps<typeof Button>, "variant" | "size" | "render">) {
  // Visibility is computed from LIVE viewport geometry (scroll listener +
  // ResizeObserver on both viewport and content), not the primitive's
  // commit-based snapshot: the snapshot only updates on the library's own
  // commit triggers, and when one is missed the pill sticks at its last
  // state — visible forever no matter how the user scrolls.
  const { scrollToEnd, scrollToStart } = useMessageScroller()
  const [active, setActive] = React.useState(false)
  const ref = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    const root = ref.current?.closest("[data-slot=message-scroller]")
    const viewport = root?.querySelector<HTMLElement>(
      "[data-slot=message-scroller-viewport]"
    )
    if (!viewport) return
    let raf = 0
    const compute = () => {
      raf = 0
      const remaining =
        direction === "end"
          ? viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
          : viewport.scrollTop
      setActive(remaining > 8)
    }
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(compute)
    }
    schedule()
    viewport.addEventListener("scroll", schedule, { passive: true })
    const observer = new ResizeObserver(schedule)
    observer.observe(viewport)
    if (viewport.firstElementChild) observer.observe(viewport.firstElementChild)
    return () => {
      viewport.removeEventListener("scroll", schedule)
      observer.disconnect()
      if (raf) cancelAnimationFrame(raf)
    }
  }, [direction])

  return (
    <Button
      data-slot="message-scroller-button"
      data-direction={direction}
      data-variant={variant}
      data-size={size}
      data-active={active ? "true" : "false"}
      inert={!active}
      variant={variant}
      size={size}
      ref={ref}
      onClick={() =>
        direction === "end"
          ? scrollToEnd({ behavior: "smooth" })
          : scrollToStart({ behavior: "smooth" })
      }
      className={cn(
        "dock-surface absolute inset-s-1/2 -translate-x-1/2 rounded-full text-foreground transition-[translate,scale,opacity] duration-200 hover:bg-accent hover:text-foreground data-[active=false]:pointer-events-none data-[active=false]:scale-95 data-[active=false]:opacity-0 data-[active=false]:duration-400 data-[active=false]:ease-[cubic-bezier(0.7,0,0.84,0)] data-[active=true]:translate-y-0 data-[active=true]:scale-100 data-[active=true]:opacity-100 data-[active=true]:ease-[cubic-bezier(0.23,1,0.32,1)] data-[direction=end]:bottom-4 data-[direction=end]:data-[active=false]:translate-y-full data-[direction=start]:top-4 data-[direction=start]:data-[active=false]:-translate-y-full rtl:translate-x-1/2 data-[direction=start]:[&_svg]:rotate-180",
        className
      )}
      render={render ?? <button type="button" />}
      {...props}
    >
      {children ?? (
        <>
          <ArrowDownIcon
          />
          <span className="sr-only">
            {direction === "end" ? "Scroll to end" : "Scroll to start"}
          </span>
        </>
      )}
    </Button>
  )
}

export {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
  useMessageScroller,
  useMessageScrollerViewportAnchor,
  useMessageScrollerScrollable,
  useMessageScrollerVisibility,
}
