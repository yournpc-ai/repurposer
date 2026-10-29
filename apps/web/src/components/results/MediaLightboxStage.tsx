"use client"

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  Ref,
  RefObject,
} from "react"
import {
  AnimatePresence,
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
} from "motion/react"
import type { MotionValue, Transition } from "motion/react"
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Info,
  Video,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { downloadFile } from "@/lib/api"
import { formatRelativeTime } from "@/lib/utils"
import type { MediaLightboxData } from "./mediaLightboxTypes"

const DURATION = { fast: 0.12, standard: 0.2, exit: 0.18 }
const ENTER_EASE = [0.22, 1, 0.36, 1] as [number, number, number, number]
const STANDARD_EASE = [0.4, 0, 0.2, 1] as [number, number, number, number]

/** Restate a visual-duration spring as stiffness and damping so retargeting
 * keeps the current velocity instead of restarting the movement. */
const physical = ({ visualDuration, bounce }: { visualDuration: number; bounce: number }): Transition => {
  const root = 2 * Math.PI / (visualDuration * 1.2)
  return { type: "spring", stiffness: root * root, damping: 2 * (1 - bounce) * root, mass: 1 }
}
const openSpring = physical({ visualDuration: 0.44, bounce: 0 })
const closeSpring = physical({ visualDuration: 0.4, bounce: 0 })
const slideSpring = physical({ visualDuration: 0.36, bounce: 0 })
const settle = physical({ visualDuration: 0.24, bounce: 0 })

const RADIUS = 12
const MAX_ZOOM = 4
const PINCH_CLOSE = 0.86
const WHEEL_PAGE = 70

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))
const project = (velocity: number, rate = 0.995) => velocity / 1000 * rate / (1 - rate)
const rubber = (overshoot: number, dimension: number, constant = 0.55) =>
  overshoot * dimension * constant / (dimension + constant * Math.abs(overshoot))
const wheelPx = (delta: number, mode: number, page: number) =>
  mode === 1 ? delta * 16 : mode === 2 ? delta * page : delta

type Viewport = { w: number; h: number }
type Rect = { left: number; top: number; width: number; height: number }
type Sample = { x: number; y: number; t: number }

function aspectOf(item: MediaLightboxData) {
  return item.aspect && Number.isFinite(item.aspect) && item.aspect > 0
    ? item.aspect
    : item.kind === "video" ? 16 / 9 : 4 / 3
}

const MAX_STAGE_WIDTH = 1200
const MAX_STAGE_HEIGHT = 720

function chromeOf(vp: Viewport) {
  const compact = vp.w < 640
  const top = compact ? 56 : 64
  const bottom = compact ? 168 : 148
  const pad = compact ? 12 : 72
  return { top, bottom, pad, stage: Math.max(120, vp.h - top - bottom) }
}

/** Fit the declared frame without cropping or reading intrinsic media size. */
function fit(item: MediaLightboxData, vp: Viewport): Rect {
  const c = chromeOf(vp)
  const availableWidth = Math.max(1, Math.min(vp.w - c.pad * 2, MAX_STAGE_WIDTH))
  const availableHeight = Math.max(1, Math.min(c.stage - 16, MAX_STAGE_HEIGHT))
  const aspect = aspectOf(item)
  const width = Math.min(availableWidth, availableHeight * aspect)
  const height = width / aspect
  return {
    width,
    height,
    left: (vp.w - width) / 2,
    top: c.top + (c.stage - height) / 2,
  }
}

function panBounds(frame: Rect, zoom: number, vp: Viewport) {
  const hw = frame.width * zoom / 2
  const hh = frame.height * zoom / 2
  const cx = frame.left + frame.width / 2
  const cy = frame.top + frame.height / 2
  const x = [vp.w - cx - hw, hw - cx]
  const y = [vp.h - cy - hh, hh - cy]
  return {
    minX: x[0] > x[1] ? 0 : x[0],
    maxX: x[0] > x[1] ? 0 : x[1],
    minY: y[0] > y[1] ? 0 : y[0],
    maxY: y[0] > y[1] ? 0 : y[1],
  }
}

function velocityOf(history: Sample[]) {
  const last = history[history.length - 1]
  if (!last || performance.now() - last.t > 60) return { x: 0, y: 0 }
  let first = last
  for (let i = history.length - 1; i >= 0 && last.t - history[i].t <= 80; i--) first = history[i]
  const dt = (last.t - first.t) / 1000
  return dt > 0
    ? { x: (last.x - first.x) / dt, y: (last.y - first.y) / dt }
    : { x: 0, y: 0 }
}

type Gesture =
  | { mode: "idle" }
  | {
      mode: "pending" | "swipe" | "dismiss" | "pan"
      id: number
      x: number
      y: number
      baseStrip: number
      basePanX: number
      basePanY: number
      grabX: number
      grabY: number
      onMedia: boolean
      history: Sample[]
    }
  | {
      mode: "pinch"
      distance: number
      zoom: number
      midX: number
      midY: number
      panX: number
      panY: number
    }

type HeroValues = { x: MotionValue<number>; y: MotionValue<number>; scale: MotionValue<number>; opacity: MotionValue<number> }
type ZoomValues = { scale: MotionValue<number>; x: MotionValue<number>; y: MotionValue<number>; radius: MotionValue<string> }

export function MediaLightboxStage({
  items,
  activeId,
  start,
  actions,
  getSlot,
  onNavigate,
  onClosed,
  requestCloseRef,
  veil,
}: {
  items: MediaLightboxData[]
  activeId?: string
  start: number
  actions?: ReactNode
  getSlot?: (slotId: string) => HTMLElement | null
  onNavigate: (outputId: string) => void
  onClosed: () => void
  requestCloseRef: RefObject<(() => void) | null>
  veil: MotionValue<number>
}) {
  const { t, i18n } = useTranslation()
  const reduced = !!useReducedMotion()
  const initial = clamp(start, 0, Math.max(0, items.length - 1))
  const [vp, setVp] = useState<Viewport>({ w: 0, h: 0 })
  const [index, setIndexState] = useState(initial)
  const [zoomed, setZoomed] = useState(false)
  const [closing, setClosing] = useState(false)
  const indexRef = useRef(initial)
  const vpRef = useRef(vp)
  const closingRef = useRef(false)
  const canZoomRef = useRef(false)
  const overlayRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const mediaRef = useRef<HTMLDivElement>(null)
  const stripRef = useRef<HTMLDivElement>(null)
  const gesture = useRef<Gesture>({ mode: "idle" })
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const lastTap = useRef<Sample | null>(null)

  const stripX = useMotionValue(-initial * vp.w)
  const heroX = useMotionValue(0)
  const heroY = useMotionValue(0)
  const heroS = useMotionValue(1)
  const heroO = useMotionValue(1)
  const zoomS = useMotionValue(1)
  const panX = useMotionValue(0)
  const panY = useMotionValue(0)
  const chrome = useTransform(veil, [0.6, 1], [0, 1])
  const radius = useTransform(() => `${RADIUS / Math.max(0.05, heroS.get() * zoomS.get())}px`)
  useMotionValueEvent(zoomS, "change", (value) => setZoomed(value > 1.01))

  const current = items[index] ?? items[initial]
  canZoomRef.current = current?.kind === "image" && !!current.url

  const frameOf = useCallback(
    (i: number) => fit(items[i], vpRef.current),
    [items],
  )

  // The viewer mounts after a user gesture. Measure before paint so no
  // browser global is read during SSR and the opening flight starts on-frame.
  useLayoutEffect(() => {
    const next = { w: window.innerWidth, h: window.innerHeight }
    vpRef.current = next
    stripX.jump(-indexRef.current * next.w)
    setVp(next)
  }, [stripX])

  useLayoutEffect(() => {
    const item = items[initial]
    const frame = fit(item, vpRef.current)
    const slot = item.slotId ? getSlot?.(item.slotId) : null
    const rect = slot?.getBoundingClientRect()
    if (reduced || !rect || rect.width <= 0) {
      heroO.jump(0)
      animate(heroO, 1, { duration: DURATION.standard, ease: ENTER_EASE })
    } else {
      heroX.jump(rect.left - frame.left)
      heroY.jump(rect.top - frame.top)
      heroS.jump(rect.width / frame.width)
      animate(heroX, 0, openSpring)
      animate(heroY, 0, openSpring)
      animate(heroS, 1, openSpring)
    }
    animate(veil, 1, { duration: reduced ? DURATION.standard : 0.34, ease: ENTER_EASE })
    closeRef.current?.focus({ preventScroll: true })
    // The opening flight runs once from the seat measured on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const onResize = () => {
      const next = { w: window.innerWidth, h: window.innerHeight }
      vpRef.current = next
      stripX.jump(-indexRef.current * next.w)
      zoomS.jump(1)
      panX.jump(0)
      panY.jump(0)
      setVp(next)
    }
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [stripX, zoomS, panX, panY])

  // Output id is the business truth. This only aligns the visual strip after
  // a host-side selection or a refreshed transcript projection.
  useEffect(() => {
    if (!activeId) return
    const next = items.findIndex((item) => item.id === activeId)
    if (next < 0 || next === indexRef.current) return
    indexRef.current = next
    setIndexState(next)
    zoomS.jump(1)
    panX.jump(0)
    panY.jump(0)
    stripX.jump(-next * vpRef.current.w)
  }, [activeId, items, panX, panY, stripX, zoomS])

  const stopZoom = useCallback(() => {
    zoomS.stop()
    panX.stop()
    panY.stop()
  }, [zoomS, panX, panY])

  const coast = useCallback((velocity: { x: number; y: number }) => {
    const bounds = panBounds(frameOf(indexRef.current), zoomS.get(), vpRef.current)
    if (reduced) {
      animate(panX, clamp(panX.get(), bounds.minX, bounds.maxX), { duration: DURATION.fast, ease: STANDARD_EASE })
      animate(panY, clamp(panY.get(), bounds.minY, bounds.maxY), { duration: DURATION.fast, ease: STANDARD_EASE })
      return
    }
    const glide = { type: "inertia", power: 0.7, timeConstant: 300, bounceStiffness: 320, bounceDamping: 36, restDelta: 0.5 } as const
    animate(panX, panX.get(), { ...glide, velocity: velocity.x, min: bounds.minX, max: bounds.maxX })
    animate(panY, panY.get(), { ...glide, velocity: velocity.y, min: bounds.minY, max: bounds.maxY })
  }, [frameOf, panX, panY, reduced, zoomS])

  const resetZoom = useCallback((smooth: boolean) => {
    if (!smooth || reduced) {
      zoomS.jump(1)
      panX.jump(0)
      panY.jump(0)
      return
    }
    animate(zoomS, 1, settle)
    animate(panX, 0, settle)
    animate(panY, 0, settle)
  }, [reduced, zoomS, panX, panY])

  const goTo = useCallback((target: number, velocity = 0) => {
    if (closingRef.current || items.length === 0) return
    const w = vpRef.current.w
    const previous = indexRef.current
    const next = clamp(target, 0, items.length - 1)
    if (next !== previous) {
      resetZoom(false)
      if (Math.abs(next - previous) > 1) {
        stripX.jump(-(next - Math.sign(next - previous)) * w + (stripX.get() + previous * w))
      }
      indexRef.current = next
      setIndexState(next)
      const id = items[next].id
      if (id) onNavigate(id)
    }
    if (reduced) stripX.jump(-next * w)
    else animate(stripX, -next * w, { ...slideSpring, velocity })
  }, [items, onNavigate, reduced, resetZoom, stripX])

  const close = useCallback((release?: { x: number; y: number }) => {
    if (closingRef.current) return
    const velocity = release ?? { x: heroX.getVelocity(), y: heroY.getVelocity() }
    closingRef.current = true
    setClosing(true)
    const i = indexRef.current
    const viewport = vpRef.current
    const item = items[i]
    const frame = fit(item, viewport)
    // Never scroll the Chat to chase another message's card. An offscreen or
    // unmounted destination simply takes the honest fade-out path.
    const slot = item.slotId ? getSlot?.(item.slotId) : null
    const rect = slot?.getBoundingClientRect()
    const visible = !!rect && rect.width > 0 && rect.bottom > 0 && rect.top < viewport.h && rect.right > 0 && rect.left < viewport.w
    const finish = () => onClosed()
    animate(veil, 0, { duration: reduced ? DURATION.standard : 0.3, ease: STANDARD_EASE })
    if (reduced || !visible || !rect) {
      resetZoom(false)
      stripX.jump(-i * viewport.w)
      animate(heroO, 0, { duration: DURATION.exit, ease: STANDARD_EASE }).then(finish)
      return
    }
    resetZoom(true)
    animate(stripX, -i * viewport.w, closeSpring)
    animate(heroX, rect.left - frame.left, { ...closeSpring, velocity: velocity.x })
    animate(heroY, rect.top - frame.top, { ...closeSpring, velocity: velocity.y })
    animate(heroS, rect.width / frame.width, { ...closeSpring, velocity: heroS.getVelocity() }).then(finish)
  }, [getSlot, heroO, heroS, heroX, heroY, items, onClosed, reduced, resetZoom, stripX, veil])

  useLayoutEffect(() => {
    requestCloseRef.current = close
    return () => {
      if (requestCloseRef.current === close) requestCloseRef.current = null
    }
  }, [close, requestCloseRef])

  const zoomAround = useCallback((px: number, py: number, target: number, smooth: boolean) => {
    if (!canZoomRef.current) return
    const frame = frameOf(indexRef.current)
    const z0 = zoomS.get()
    const cx = frame.left + frame.width / 2
    const cy = frame.top + frame.height / 2
    const z = clamp(target, 1, MAX_ZOOM)
    const bounds = panBounds(frame, z, vpRef.current)
    const nx = clamp(px - cx - (px - cx - panX.get()) * (z / z0), bounds.minX, bounds.maxX)
    const ny = clamp(py - cy - (py - cy - panY.get()) * (z / z0), bounds.minY, bounds.maxY)
    if (smooth && !reduced) {
      animate(zoomS, z, settle)
      animate(panX, nx, settle)
      animate(panY, ny, settle)
    } else {
      zoomS.jump(z)
      panX.jump(nx)
      panY.jump(ny)
    }
  }, [frameOf, panX, panY, reduced, zoomS])

  const toggleZoom = useCallback((px?: number, py?: number) => {
    if (!canZoomRef.current) return
    const frame = frameOf(indexRef.current)
    if (zoomS.get() > 1.01) {
      resetZoom(true)
      return
    }
    const viewport = vpRef.current
    const fill = Math.max(viewport.w / frame.width, viewport.h / frame.height)
    zoomAround(
      px ?? frame.left + frame.width / 2,
      py ?? frame.top + frame.height / 2,
      clamp(fill, 2, MAX_ZOOM),
      true,
    )
  }, [frameOf, resetZoom, zoomAround, zoomS])

  useEffect(() => {
    const node = overlayRef.current
    if (!node) return
    const paging = { travel: 0, locked: false, timer: 0 }
    const onWheel = (event: WheelEvent) => {
      if (event.target instanceof Element && event.target.closest("video,button,input,textarea,[data-no-viewer-gesture]")) return
      if (!canZoomRef.current || closingRef.current) return
      event.preventDefault()
      const viewport = vpRef.current
      const dx = wheelPx(event.deltaX, event.deltaMode, viewport.w)
      const dy = wheelPx(event.deltaY, event.deltaMode, viewport.h)
      if (event.ctrlKey) {
        stopZoom()
        zoomAround(event.clientX, event.clientY, zoomS.get() * Math.exp(-clamp(dy, -50, 50) * 0.012), false)
        return
      }
      if (zoomS.get() <= 1.01) {
        window.clearTimeout(paging.timer)
        paging.timer = window.setTimeout(() => {
          paging.travel = 0
          paging.locked = false
        }, 160)
        if (paging.locked || Math.abs(dx) <= Math.abs(dy)) return
        paging.travel += dx
        if (Math.abs(paging.travel) < WHEEL_PAGE) return
        paging.locked = true
        goTo(indexRef.current + Math.sign(paging.travel))
        return
      }
      stopZoom()
      const bounds = panBounds(frameOf(indexRef.current), zoomS.get(), viewport)
      panX.jump(clamp(panX.get() - dx, bounds.minX, bounds.maxX))
      panY.jump(clamp(panY.get() - dy, bounds.minY, bounds.maxY))
    }
    type SafariGesture = Event & { scale: number; clientX: number; clientY: number }
    let base = 1
    const onGestureStart = (event: Event) => {
      if (!canZoomRef.current) return
      event.preventDefault()
      stopZoom()
      base = zoomS.get()
    }
    const onGestureChange = (event: Event) => {
      if (!canZoomRef.current || closingRef.current) return
      event.preventDefault()
      const value = event as SafariGesture
      zoomAround(value.clientX, value.clientY, base * value.scale, false)
    }
    const onGestureEnd = (event: Event) => {
      if (canZoomRef.current) event.preventDefault()
    }
    node.addEventListener("wheel", onWheel, { passive: false })
    node.addEventListener("gesturestart", onGestureStart)
    node.addEventListener("gesturechange", onGestureChange)
    node.addEventListener("gestureend", onGestureEnd)
    return () => {
      window.clearTimeout(paging.timer)
      node.removeEventListener("wheel", onWheel)
      node.removeEventListener("gesturestart", onGestureStart)
      node.removeEventListener("gesturechange", onGestureChange)
      node.removeEventListener("gestureend", onGestureEnd)
    }
  }, [frameOf, goTo, panX, panY, stopZoom, zoomAround, zoomS])

  const isOnMedia = (x: number, y: number) => {
    const rect = mediaRef.current?.getBoundingClientRect()
    return !!rect && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
  }

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.target instanceof Element && event.target.closest("video,button,input,textarea,[data-no-viewer-gesture]")) return
    if (closingRef.current || (event.pointerType === "mouse" && event.button !== 0)) return
    event.currentTarget.setPointerCapture(event.pointerId)
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    if (pointers.current.size === 2) {
      if (!canZoomRef.current) {
        gesture.current = { mode: "idle" }
        return
      }
      const [a, b] = [...pointers.current.values()]
      animate(stripX, -indexRef.current * vpRef.current.w, settle)
      animate(heroX, 0, settle)
      animate(heroY, 0, settle)
      animate(heroS, 1, settle)
      animate(veil, 1, { duration: DURATION.fast })
      stopZoom()
      gesture.current = {
        mode: "pinch",
        distance: Math.hypot(a.x - b.x, a.y - b.y) || 1,
        zoom: zoomS.get(),
        midX: (a.x + b.x) / 2,
        midY: (a.y + b.y) / 2,
        panX: panX.get(),
        panY: panY.get(),
      }
      return
    }
    if (pointers.current.size > 2) return
    stripX.stop()
    panX.stop()
    panY.stop()
    if (zoomS.get() > 1.01) zoomS.stop()
    const frame = frameOf(indexRef.current)
    gesture.current = {
      mode: "pending",
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      baseStrip: stripX.get(),
      basePanX: panX.get(),
      basePanY: panY.get(),
      grabX: clamp((event.clientX - frame.left) / frame.width, 0, 1),
      grabY: clamp((event.clientY - frame.top) / frame.height, 0, 1),
      onMedia: isOnMedia(event.clientX, event.clientY),
      history: [{ x: event.clientX, y: event.clientY, t: performance.now() }],
    }
  }

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!pointers.current.has(event.pointerId)) return
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    const currentGesture = gesture.current
    const viewport = vpRef.current
    if (currentGesture.mode === "pinch") {
      if (pointers.current.size < 2) return
      const [a, b] = [...pointers.current.values()]
      const midX = (a.x + b.x) / 2
      const midY = (a.y + b.y) / 2
      const raw = currentGesture.zoom * Math.hypot(a.x - b.x, a.y - b.y) / currentGesture.distance
      const z = raw < 1
        ? 1 - rubber(1 - raw, 1, 0.4)
        : raw > MAX_ZOOM ? MAX_ZOOM + rubber(raw - MAX_ZOOM, MAX_ZOOM, 0.4) : raw
      const frame = frameOf(indexRef.current)
      const cx = frame.left + frame.width / 2
      const cy = frame.top + frame.height / 2
      zoomS.set(z)
      veil.set(z < 1 ? clamp(1 - (1 - z) * 4, 0.25, 1) : 1)
      panX.set(currentGesture.midX - cx - (currentGesture.midX - cx - currentGesture.panX) * (z / currentGesture.zoom) + (midX - currentGesture.midX))
      panY.set(currentGesture.midY - cy - (currentGesture.midY - cy - currentGesture.panY) * (z / currentGesture.zoom) + (midY - currentGesture.midY))
      return
    }
    if (currentGesture.mode === "idle" || event.pointerId !== currentGesture.id) return
    currentGesture.history.push({ x: event.clientX, y: event.clientY, t: performance.now() })
    if (currentGesture.history.length > 12) currentGesture.history.shift()
    const dx = event.clientX - currentGesture.x
    const dy = event.clientY - currentGesture.y
    if (currentGesture.mode === "pending") {
      if (Math.hypot(dx, dy) < 6) return
      currentGesture.mode = zoomS.get() > 1.01
        ? "pan"
        : Math.abs(dx) > Math.abs(dy) ? "swipe" : "dismiss"
      if (currentGesture.mode === "pan") overlayRef.current?.setAttribute("data-panning", "")
    }
    if (currentGesture.mode === "swipe") {
      const min = -(items.length - 1) * viewport.w
      const raw = currentGesture.baseStrip + dx
      stripX.set(raw > 0
        ? rubber(raw, viewport.w)
        : raw < min ? min + rubber(raw - min, viewport.w) : raw)
    } else if (currentGesture.mode === "dismiss") {
      const down = Math.max(0, dy)
      const progress = clamp(down / (viewport.h * 0.6), 0, 1)
      const scale = 1 - progress * 0.4
      const frame = frameOf(indexRef.current)
      heroS.set(scale)
      heroX.set(dx + (1 - scale) * frame.width * currentGesture.grabX)
      heroY.set((dy < 0 ? -rubber(-dy, viewport.h, 0.35) : dy) + (1 - scale) * frame.height * currentGesture.grabY)
      veil.set(1 - progress * 0.85)
    } else if (currentGesture.mode === "pan") {
      const bounds = panBounds(frameOf(indexRef.current), zoomS.get(), viewport)
      const band = (value: number, lo: number, hi: number, size: number) =>
        value < lo ? lo - rubber(lo - value, size) : value > hi ? hi + rubber(value - hi, size) : value
      panX.set(band(currentGesture.basePanX + dx, bounds.minX, bounds.maxX, viewport.w))
      panY.set(band(currentGesture.basePanY + dy, bounds.minY, bounds.maxY, viewport.h))
    }
  }

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!pointers.current.has(event.pointerId)) return
    pointers.current.delete(event.pointerId)
    if (!pointers.current.size) overlayRef.current?.removeAttribute("data-panning")
    const currentGesture = gesture.current
    const viewport = vpRef.current
    if (currentGesture.mode === "pinch") {
      const z = zoomS.get()
      if (z < PINCH_CLOSE && event.type !== "pointercancel") {
        pointers.current.clear()
        gesture.current = { mode: "idle" }
        close()
        return
      }
      if (z < 1) animate(veil, 1, { duration: DURATION.fast, ease: ENTER_EASE })
      const frame = frameOf(indexRef.current)
      const remaining = [...pointers.current.entries()][0]
      if (remaining && z > 1.01) {
        const [id, point] = remaining
        gesture.current = {
          mode: "pan",
          id,
          x: point.x,
          y: point.y,
          baseStrip: stripX.get(),
          basePanX: panX.get(),
          basePanY: panY.get(),
          grabX: 0.5,
          grabY: 0.5,
          onMedia: true,
          history: [{ ...point, t: performance.now() }],
        }
      } else {
        gesture.current = { mode: "idle" }
      }
      if (remaining && z > 1.01 && z <= MAX_ZOOM) return
      if (z <= 1.02) {
        resetZoom(true)
        return
      }
      const target = clamp(z, 1, MAX_ZOOM)
      const bounds = panBounds(frame, target, viewport)
      animate(zoomS, target, settle)
      animate(panX, clamp(panX.get(), bounds.minX, bounds.maxX), settle)
      animate(panY, clamp(panY.get(), bounds.minY, bounds.maxY), settle)
      return
    }
    if (currentGesture.mode === "idle" || event.pointerId !== currentGesture.id) return
    gesture.current = { mode: "idle" }
    const velocity = velocityOf(currentGesture.history)
    const dx = event.clientX - currentGesture.x
    const dy = event.clientY - currentGesture.y
    if (currentGesture.mode === "pending") {
      if (event.type === "pointercancel") return
      if (!currentGesture.onMedia) {
        close()
        return
      }
      if (event.pointerType === "mouse" || !canZoomRef.current) return
      const now = performance.now()
      const tap = lastTap.current
      if (tap && now - tap.t < 300 && Math.hypot(tap.x - event.clientX, tap.y - event.clientY) < 30) {
        lastTap.current = null
        toggleZoom(event.clientX, event.clientY)
      } else {
        lastTap.current = { x: event.clientX, y: event.clientY, t: now }
      }
      return
    }
    if (currentGesture.mode === "swipe") {
      const travelled = dx + project(velocity.x)
      const flick = Math.abs(velocity.x) > 450 && Math.sign(velocity.x) === Math.sign(dx)
        ? -Math.sign(velocity.x)
        : 0
      const step = travelled < -viewport.w * 0.3 ? 1 : travelled > viewport.w * 0.3 ? -1 : flick
      goTo(indexRef.current + step, velocity.x)
      return
    }
    if (currentGesture.mode === "dismiss") {
      if (dy > 0 && (velocity.y > 500 || (dy > 110 && velocity.y > -150))) {
        close(velocity)
        return
      }
      const back = reduced ? { duration: DURATION.fast, ease: STANDARD_EASE } : null
      animate(heroX, 0, back ?? { ...settle, velocity: velocity.x })
      animate(heroY, 0, back ?? { ...settle, velocity: velocity.y })
      animate(heroS, 1, back ?? settle)
      animate(veil, 1, { duration: DURATION.standard, ease: ENTER_EASE })
      return
    }
    if (currentGesture.mode === "pan") coast(velocity)
  }

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault()
      close()
      return
    }
    if (event.target instanceof Element && event.target.closest("input,textarea,video,[contenteditable=true],[data-no-viewer-gesture]")) return
    if (event.key === "ArrowRight") {
      event.preventDefault()
      goTo(indexRef.current + 1)
      return
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault()
      goTo(indexRef.current - 1)
      return
    }
    if (!canZoomRef.current) return
    if (event.key === "+" || event.key === "=") {
      event.preventDefault()
      const frame = frameOf(indexRef.current)
      zoomAround(frame.left + frame.width / 2, frame.top + frame.height / 2, zoomS.get() * 1.5, true)
    } else if (event.key === "-") {
      event.preventDefault()
      const frame = frameOf(indexRef.current)
      zoomAround(frame.left + frame.width / 2, frame.top + frame.height / 2, zoomS.get() / 1.5, true)
    } else if (event.key === "0") {
      event.preventDefault()
      resetZoom(true)
    }
  }

  useEffect(() => {
    const strip = stripRef.current
    const node = strip?.querySelector<HTMLElement>(`[data-index="${index}"]`)
    if (!strip || !node) return
    const width = clamp(48 * aspectOf(items[index]), 36, 72)
    strip.scrollTo({
      left: node.offsetLeft + width / 2 - strip.clientWidth / 2,
      behavior: reduced ? "auto" : "smooth",
    })
  }, [items, index, reduced])

  const c = chromeOf(vp)
  const range = [index - 1, index, index + 1].filter((i) => i >= 0 && i < items.length)
  const hasDetails = !!(current.prompt || current.chips?.length || current.modelFacts?.length)

  return (
    <div
      ref={overlayRef}
      className="relative h-full w-full overflow-hidden text-foreground"
      onKeyDown={onKeyDown}
      data-closing={closing || undefined}
      data-zoomed={zoomed || undefined}
    >
      <div
        className="absolute inset-0 select-none"
        style={{ touchAction: current.kind === "image" ? "none" : "auto" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={(event) => {
          if (!closingRef.current && canZoomRef.current && isOnMedia(event.clientX, event.clientY)) {
            toggleZoom(event.clientX, event.clientY)
          }
        }}
      >
        <motion.div className="absolute inset-0" style={{ x: stripX }}>
          {range.map((i) => {
            const item = items[i]
            const frame = fit(item, vp)
            const active = i === index
            return (
              <div
                key={item.id ?? item.url ?? i}
                className="absolute top-0"
                style={{ left: i * vp.w, width: vp.w, height: vp.h }}
                aria-hidden={active ? undefined : true}
              >
                <MediaFrame
                  item={item}
                  frame={frame}
                  active={active}
                  mediaRef={active ? mediaRef : undefined}
                  hero={active ? { x: heroX, y: heroY, scale: heroS, opacity: heroO } : null}
                  zoom={active && item.kind === "image" ? { scale: zoomS, x: panX, y: panY, radius } : null}
                />
              </div>
            )
          })}
        </motion.div>
      </div>

      <motion.div
        className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-center justify-between px-3 sm:px-5"
        style={{ opacity: chrome, height: c.top }}
      >
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {t("chat.outputViewer.position", { current: index + 1, total: items.length })}
        </p>
        {actions ? (
          <div className="pointer-events-auto absolute top-1/2 left-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center gap-2">
            {actions}
          </div>
        ) : null}
        <div className="pointer-events-auto flex items-center gap-1">
          {hasDetails ? (
            <Popover>
              <PopoverTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-9 rounded-full"
                    aria-label={t("chat.outputViewer.details")}
                    title={t("chat.outputViewer.details")}
                  />
                }
              >
                <Info className="size-4.5" />
              </PopoverTrigger>
              <PopoverContent align="end" positionerClassName="z-[80]" className="thin-scroll max-h-[70vh] w-[min(22rem,calc(100vw-2rem))] gap-4 overflow-y-auto p-4">
                {current.prompt ? (
                  <div className="flex flex-col gap-2">
                    <span className="text-meta text-[11px]">{t("results.lightbox.prompt")}</span>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{current.prompt}</p>
                  </div>
                ) : null}
                {current.chips?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {current.chips.map(({ Icon, label, title }) => (
                      <span key={label} title={title} className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                        <Icon className="size-3.5" />
                        {label}
                      </span>
                    ))}
                  </div>
                ) : null}
                {current.modelFacts?.length ? (
                  <div className="flex flex-col gap-2">
                    <span className="text-meta text-[11px]">{t("composer.models")}</span>
                    <div className="flex flex-col gap-1.5">
                      {current.modelFacts.map((fact) => (
                        <div key={`${fact.modality}:${fact.model}`} className="flex items-baseline justify-between gap-3 text-xs">
                          <span className="text-muted-foreground">
                            {t(`composer.modelsRows.${fact.modality}`, { defaultValue: fact.modality })}
                          </span>
                          <span className="text-right">{fact.model}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </PopoverContent>
            </Popover>
          ) : null}
          {current.url ? (
            <Button
              variant="ghost"
              size="icon"
              className="size-9 rounded-full"
              aria-label={t("results.canvas.download")}
              title={t("results.canvas.download")}
              onClick={() => downloadFile(current.url as string, current.downloadName ?? current.title).catch(() => {})}
            >
              <Download className="size-4.5" />
            </Button>
          ) : null}
          {current.kind === "image" && current.url ? (
            <Button
              variant="ghost"
              size="icon"
              className="size-9 rounded-full"
              aria-label={zoomed ? t("chat.outputViewer.zoomOut") : t("chat.outputViewer.zoomIn")}
              title={zoomed ? t("chat.outputViewer.zoomOut") : t("chat.outputViewer.zoomIn")}
              aria-pressed={zoomed}
              onClick={() => toggleZoom()}
            >
              {zoomed ? <ZoomOut className="size-4.5" /> : <ZoomIn className="size-4.5" />}
            </Button>
          ) : null}
          <Button
            ref={closeRef}
            variant="ghost"
            size="icon"
            className="size-9 rounded-full"
            aria-label={t("common.close")}
            title={t("common.close")}
            onClick={() => close()}
          >
            <X className="size-4.5" />
          </Button>
        </div>
      </motion.div>

      <motion.div className="pointer-events-none absolute inset-0 z-20" style={{ opacity: chrome }}>
        <Button
          variant="ghost"
          size="icon"
          className="pointer-events-auto absolute top-1/2 left-5 size-10 -translate-y-1/2 rounded-full max-sm:hidden"
          onClick={() => goTo(index - 1)}
          disabled={index === 0}
          aria-label={t("chat.outputViewer.previous")}
          title={t("chat.outputViewer.previous")}
        >
          <ChevronLeft className="size-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="pointer-events-auto absolute top-1/2 right-5 size-10 -translate-y-1/2 rounded-full max-sm:hidden"
          onClick={() => goTo(index + 1)}
          disabled={index === items.length - 1}
          aria-label={t("chat.outputViewer.next")}
          title={t("chat.outputViewer.next")}
        >
          <ChevronRight className="size-5" />
        </Button>
      </motion.div>

      <motion.div
        className="absolute inset-x-0 bottom-0 z-20 flex flex-col justify-end gap-2 px-3 pb-3 sm:px-5"
        style={{ opacity: chrome, height: c.bottom }}
      >
        <div className="min-w-0 text-center">
          <AnimatePresence initial={false} mode="wait">
            <motion.div
              key={current.id ?? index}
              initial={reduced ? { opacity: 0 } : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, transition: { duration: DURATION.fast } }}
              transition={reduced ? { duration: DURATION.fast } : { duration: DURATION.standard, ease: ENTER_EASE, delay: 0.04 }}
              className="min-w-0"
            >
              <p className="truncate text-sm font-medium">{current.title}</p>
              {current.versionLabel || current.createdAt ? (
                <div className="mt-0.5 flex items-center justify-center gap-2 text-xs text-muted-foreground">
                  {current.versionLabel ? <span>{current.versionLabel}</span> : null}
                  {current.createdAt ? <span>{formatRelativeTime(current.createdAt, i18n.language)}</span> : null}
                </div>
              ) : null}
            </motion.div>
          </AnimatePresence>
        </div>

        <div
          ref={stripRef}
          className="thin-scroll relative mx-auto flex h-12 max-w-full items-center gap-1 self-center overflow-x-auto"
          role="group"
          aria-label={t("chat.outputViewer.allOutputs")}
        >
          {items.map((item, i) => {
            const width = clamp(48 * aspectOf(item), 36, 72)
            const active = i === index
            return (
              <button
                key={item.id ?? item.url ?? i}
                type="button"
                data-index={i}
                className="relative h-12 shrink-0 overflow-hidden rounded-md bg-muted transition-[width] motion-reduce:transition-none data-active:ring-2 data-active:ring-foreground/60"
                data-active={active || undefined}
                style={{ width: active ? width : 36 }}
                onClick={() => goTo(i)}
                aria-label={t("chat.anchorCards.view", { name: item.title })}
                aria-current={active ? "true" : undefined}
              >
                <MediaThumbnail item={item} />
              </button>
            )
          })}
        </div>
      </motion.div>
    </div>
  )
}

function MediaThumbnail({ item }: { item: MediaLightboxData }) {
  if (item.thumbnail) return item.thumbnail
  const src = item.poster ?? (item.kind === "image" ? item.url : null)
  if (src) return <img src={src} alt="" className="h-full w-full object-contain" draggable={false} />
  return (
    <span className="flex h-full w-full items-center justify-center text-muted-foreground">
      {item.kind === "video" ? <Video className="size-4" /> : <FileText className="size-4" />}
    </span>
  )
}

function MediaFrame({
  item,
  frame,
  active,
  hero,
  zoom,
  mediaRef,
}: {
  item: MediaLightboxData
  frame: Rect
  active: boolean
  hero: HeroValues | null
  zoom: ZoomValues | null
  mediaRef?: Ref<HTMLDivElement>
}) {
  return (
    <motion.div
      className="absolute origin-top-left"
      style={{ left: frame.left, top: frame.top, width: frame.width, height: frame.height, ...(hero ?? {}) }}
    >
      <motion.div
        ref={mediaRef}
        className="absolute inset-0 overflow-hidden bg-muted"
        style={zoom ? { scale: zoom.scale, x: zoom.x, y: zoom.y, borderRadius: zoom.radius } : { borderRadius: RADIUS }}
        data-no-viewer-gesture={item.kind === "text" ? "" : undefined}
      >
        {item.kind === "video" ? (
          <>
            <div className="absolute inset-0"><MediaThumbnail item={item} /></div>
            {active && item.url ? (
              <video
                key={item.id ?? item.url}
                src={item.url}
                poster={item.poster ?? undefined}
                className="absolute inset-0 h-full w-full object-contain"
                controls
                autoPlay
                playsInline
                preload="metadata"
              />
            ) : null}
          </>
        ) : item.kind === "image" && item.url ? (
          <img
            src={item.url}
            alt={active ? item.title : ""}
            className="absolute inset-0 h-full w-full object-contain"
            draggable={false}
            loading={active ? "eager" : "lazy"}
          />
        ) : active ? (
          <div className="thin-scroll h-full w-full overflow-y-auto select-text" data-no-viewer-gesture>
            {item.content ?? (
              <div className="min-h-full w-full bg-muted p-5">
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{item.text}</p>
              </div>
            )}
          </div>
        ) : (
          <MediaThumbnail item={item} />
        )}
      </motion.div>
    </motion.div>
  )
}
