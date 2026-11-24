"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { PointerEvent as ReactPointerEvent, RefObject } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button-clean"
import {
  formatMediaTimeMs,
  makeMediaRegionSelection,
  videoContentRect,
  type MediaRegionSelectionControl,
  type MediaRegionSelection,
  type PixelRect,
} from "./mediaRegionSelection"

const MIN_DRAG_PX = 3

export function MediaRegionSelectionOverlay({
  videoRef,
  mediaRef,
  control,
}: {
  videoRef?: RefObject<HTMLVideoElement | null>
  mediaRef?: RefObject<HTMLVideoElement | HTMLImageElement | null>
  control: MediaRegionSelectionControl
}) {
  const { t } = useTranslation()
  const overlayRef = useRef<HTMLDivElement>(null)
  const pointerIdRef = useRef<number | null>(null)
  const originRef = useRef<{ x: number; y: number } | null>(null)
  const mediaTimeRef = useRef(0)
  const [content, setContent] = useState<PixelRect>({ x: 0, y: 0, width: 0, height: 0 })
  const [draft, setDraft] = useState<PixelRect | null>(null)
  const [draftSelection, setDraftSelection] = useState<MediaRegionSelection | null>(null)

  const getMediaElement = useCallback(
    () => mediaRef?.current ?? videoRef?.current ?? null,
    [mediaRef, videoRef],
  )

  const getSourceSize = useCallback((el: HTMLVideoElement | HTMLImageElement | null) => {
    if (!el) return { width: 0, height: 0 }
    if ("videoWidth" in el) {
      return { width: el.videoWidth, height: el.videoHeight }
    }
    return { width: el.naturalWidth, height: el.naturalHeight }
  }, [])

  const measure = useCallback(() => {
    const overlay = overlayRef.current
    const media = getMediaElement()
    if (!overlay || !media) return
    const bounds = overlay.getBoundingClientRect()
    setContent(videoContentRect(
      { width: bounds.width, height: bounds.height },
      getSourceSize(media),
    ))
  }, [getMediaElement, getSourceSize])

  useEffect(() => {
    const media = getMediaElement()
    measure()
    if (control.enabled && media && "pause" in media) media.pause()
    window.addEventListener("resize", measure)
    media?.addEventListener("loadedmetadata", measure)
    media?.addEventListener("load", measure)
    media?.addEventListener("resize", measure)
    const ro = typeof ResizeObserver !== "undefined" && overlayRef.current
      ? new ResizeObserver(measure)
      : null
    if (overlayRef.current) ro?.observe(overlayRef.current)
    return () => {
      window.removeEventListener("resize", measure)
      media?.removeEventListener("loadedmetadata", measure)
      media?.removeEventListener("load", measure)
      media?.removeEventListener("resize", measure)
      ro?.disconnect()
    }
  }, [control.enabled, getMediaElement, measure])

  const pointInContent = (event: ReactPointerEvent<HTMLDivElement>) => {
    const overlay = overlayRef.current
    if (!overlay || content.width <= 0 || content.height <= 0) return null
    const bounds = overlay.getBoundingClientRect()
    return {
      x: Math.min(content.width, Math.max(0, event.clientX - bounds.left - content.x)),
      y: Math.min(content.height, Math.max(0, event.clientY - bounds.top - content.y)),
    }
  }

  const clearDrag = () => {
    pointerIdRef.current = null
    originRef.current = null
    setDraft(null)
    setDraftSelection(null)
  }

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!control.enabled || (event.pointerType === "mouse" && event.button !== 0)) return
    const point = pointInContent(event)
    if (!point) return
    const overlay = overlayRef.current
    const media = getMediaElement()
    const sourceSize = getSourceSize(media)
    if (!overlay || !media || sourceSize.width <= 0 || sourceSize.height <= 0) return
    event.preventDefault()
    event.stopPropagation()
    if ("pause" in media) media.pause()
    mediaTimeRef.current = "currentTime" in media ? media.currentTime : 0
    pointerIdRef.current = event.pointerId
    originRef.current = point
    setDraft({ x: point.x, y: point.y, width: 0, height: 0 })
    setDraftSelection(null)
    overlay.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (pointerIdRef.current !== event.pointerId || !originRef.current) return
    const point = pointInContent(event)
    if (!point) return
    event.preventDefault()
    event.stopPropagation()
    const origin = originRef.current
    const next = {
      x: Math.min(origin.x, point.x),
      y: Math.min(origin.y, point.y),
      width: Math.abs(point.x - origin.x),
      height: Math.abs(point.y - origin.y),
    }
    setDraft(next)
    setDraftSelection(next.width >= MIN_DRAG_PX && next.height >= MIN_DRAG_PX
      ? makeMediaRegionSelection({
          viewportRect: next,
          viewportSize: { width: content.width, height: content.height },
          sourceSize: getSourceSize(getMediaElement()),
          mediaTimeSeconds: mediaTimeRef.current,
        })
      : null)
  }

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (pointerIdRef.current !== event.pointerId) return
    event.preventDefault()
    event.stopPropagation()
    if (draftSelection && draftSelection.sourceRect.width > 0 && draftSelection.sourceRect.height > 0) {
      control.onChange(draftSelection)
    }
    if (overlayRef.current?.hasPointerCapture(event.pointerId)) {
      overlayRef.current.releasePointerCapture(event.pointerId)
    }
    clearDrag()
  }

  const selectedRect = control.value && content.width > 0 && content.height > 0 ? {
    x: control.value.normalizedRect.x * content.width,
    y: control.value.normalizedRect.y * content.height,
    width: control.value.normalizedRect.width * content.width,
    height: control.value.normalizedRect.height * content.height,
  } : null
  const visibleRect = draft ?? selectedRect
  const value = control.value
  const summaryValue = draftSelection ?? value
  const summary = summaryValue ? t("chat.outputViewer.regionSummary", {
    time: formatMediaTimeMs(summaryValue.mediaTimeMs),
    sourceWidth: summaryValue.sourceSize.width,
    sourceHeight: summaryValue.sourceSize.height,
    x: summaryValue.sourceRect.x,
    y: summaryValue.sourceRect.y,
    width: summaryValue.sourceRect.width,
    height: summaryValue.sourceRect.height,
  }) : null
  const maskRect = visibleRect && visibleRect.width > 0 && visibleRect.height > 0 ? visibleRect : null
  const maskPanels = maskRect ? [
    { x: 0, y: 0, width: content.width, height: maskRect.y },
    { x: 0, y: maskRect.y + maskRect.height, width: content.width, height: content.height - maskRect.y - maskRect.height },
    { x: 0, y: maskRect.y, width: maskRect.x, height: maskRect.height },
    { x: maskRect.x + maskRect.width, y: maskRect.y, width: content.width - maskRect.x - maskRect.width, height: maskRect.height },
  ] : []

  return (
    <div
      ref={overlayRef}
      className={`absolute inset-0 z-10 ${control.enabled ? "cursor-crosshair touch-none" : "pointer-events-none"}`}
      data-no-viewer-gesture
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={(event) => {
        if (pointerIdRef.current !== event.pointerId) return
        event.stopPropagation()
        clearDrag()
      }}
    >
      {maskPanels.map((panel, index) => panel.width > 0 && panel.height > 0 ? (
        <div
          key={index}
          className="pointer-events-none absolute backdrop-brightness-50"
          style={{
            left: content.x + panel.x,
            top: content.y + panel.y,
            width: panel.width,
            height: panel.height,
          }}
        />
      ) : null)}
      {maskRect ? (
        <div
          className="pointer-events-none absolute outline-2 outline-foreground"
          style={{
            left: content.x + maskRect.x,
            top: content.y + maskRect.y,
            width: maskRect.width,
            height: maskRect.height,
          }}
        >
          {[
            "-left-1 -top-1",
            "-right-1 -top-1",
            "-left-1 -bottom-1",
            "-right-1 -bottom-1",
          ].map((position) => (
            <span key={position} className={`absolute size-2 bg-foreground ${position}`} />
          ))}
        </div>
      ) : null}
      {control.enabled ? (
        <div
          className="overlay-surface absolute bottom-3 left-1/2 flex max-w-[calc(100%-1.5rem)] -translate-x-1/2 flex-wrap items-center justify-center gap-x-3 gap-y-2 rounded-lg px-3 py-2 text-center text-[11px] text-foreground"
          onPointerDown={(event) => event.stopPropagation()}
          onPointerMove={(event) => event.stopPropagation()}
          onPointerUp={(event) => event.stopPropagation()}
        >
          <span className="min-w-0" aria-live="polite">
            {summary ?? t(content.width > 0
              ? "chat.outputViewer.regionHint"
              : "chat.outputViewer.regionLoading")}
          </span>
          <div className="flex shrink-0 items-center gap-1">
            {value ? (
              <>
                <Button variant="ghost" size="sm" onClick={control.onReselect}>
                  {t("chat.outputViewer.reselectRegion")}
                </Button>
                <Button variant="ghost" size="sm" onClick={control.onDone}>
                  {t("chat.outputViewer.referenceRegion")}
                </Button>
              </>
            ) : null}
            <Button variant="ghost" size="sm" onClick={control.onCancel}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
