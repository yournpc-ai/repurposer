"use client"

import { useEffect, useRef, useState, type DragEvent as ReactDragEvent } from "react"

/**
 * useFileDrop — the shared drag-drop upload gesture (2026-09-24, user
 * ruling — MiniMax/Lovart parity). One gesture, two surfaces: the home
 * composer shell and the chat dock's input container both are drop
 * targets; dropping is just another entry into each surface's existing
 * staging pipeline (composer: useStagingUploads.addFiles; dock:
 * handleFilesPicked) — the chips lifecycle rides unchanged.
 *
 * `depth` counts nested dragenter/leave pairs so crossing child elements
 * never flickers the affordance; only FILE drags arm it (a text/link drag
 * must not). Also arms the browser-default guard: a file dropped OUTSIDE
 * any target would otherwise navigate the tab to the file (two hook
 * instances both adding it is harmless — preventDefault is idempotent).
 *
 * Returns `dragging` (drive the dashed dropzone + floating pill) and
 * `dropProps` to spread on the drop-target container.
 */
export function useFileDrop(
  onFiles: (files: File[]) => void,
  disabled = false,
) {
  const [dragging, setDragging] = useState(false)
  const depth = useRef(0)

  const hasFiles = (e: ReactDragEvent) =>
    Array.from(e.dataTransfer.types).includes("Files")

  const onDragEnter = (e: ReactDragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault()
    depth.current += 1
    if (!disabled) setDragging(true)
  }
  const onDragOver = (e: ReactDragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault() // required — otherwise the drop event never fires
  }
  const onDragLeave = (e: ReactDragEvent) => {
    if (!hasFiles(e)) return
    depth.current = Math.max(0, depth.current - 1)
    if (depth.current === 0) setDragging(false)
  }
  const onDrop = (e: ReactDragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault()
    depth.current = 0
    setDragging(false)
    if (disabled) return
    onFiles(Array.from(e.dataTransfer.files))
  }

  useEffect(() => {
    const prevent = (e: globalThis.DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) e.preventDefault()
    }
    window.addEventListener("dragover", prevent)
    window.addEventListener("drop", prevent)
    return () => {
      window.removeEventListener("dragover", prevent)
      window.removeEventListener("drop", prevent)
    }
  }, [])

  return { dragging, dropProps: { onDragEnter, onDragOver, onDragLeave, onDrop } }
}
