"use client"

/** Shared exact-media viewer. The host owns the single persisted reference;
 * this surface supplies the full-screen stage, gestures and return flight. */

import { useEffect, useRef } from "react"
import type { ReactNode } from "react"
import { motion, useMotionValue } from "motion/react"

import { Dialog } from "@/components/ui/dialog-clean"
import { MediaLightboxStage } from "./MediaLightboxStage"
import type { MediaLightboxData } from "./mediaLightboxTypes"
import type { MediaRegionSelectionControl } from "./mediaRegionSelection"

export type { MediaChip, MediaLightboxData } from "./mediaLightboxTypes"

export function MediaLightbox({
  data,
  onOpenChange,
  actions,
  getSlot,
  regionSelection,
}: {
  data: MediaLightboxData | null
  onOpenChange: (open: boolean) => void
  actions?: ReactNode
  getSlot?: (slotId: string) => HTMLElement | null
  regionSelection?: MediaRegionSelectionControl
}) {
  const requestCloseRef = useRef<(() => void) | null>(null)
  const finalFocusRef = useRef<HTMLElement | null>(null)
  const veil = useMotionValue(0)
  const dataId = data?.id
  useEffect(() => {
    if (dataId) finalFocusRef.current = null
  }, [dataId])
  useEffect(() => {
    if (!data) veil.jump(0)
  }, [data, veil])

  const closeAndRestoreFocus = () => {
    finalFocusRef.current = data?.slotId ? (getSlot?.(data.slotId) ?? null) : null
    onOpenChange(false)
  }

  if (!data) return null
  return (
    <Dialog
      fullscreen
      open
      title={data.title}
      closeButton={false}
      returnFocus={finalFocusRef}
      onOpenChange={(open) => {
        if (open) return
        if (regionSelection?.enabled) regionSelection.onCancel()
        else requestCloseRef.current?.()
      }}
    >
      <motion.div aria-hidden className="absolute inset-0 bg-background" style={{ opacity: veil }} />
      <MediaLightboxStage
        items={[data]}
        activeId={data.id}
        start={0}
        actions={actions}
        getSlot={getSlot}
        regionSelection={regionSelection}
        onNavigate={() => {}}
        onClosed={closeAndRestoreFocus}
        requestCloseRef={requestCloseRef}
        veil={veil}
      />
    </Dialog>
  )
}
