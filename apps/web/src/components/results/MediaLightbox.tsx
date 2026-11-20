"use client"

/** Shared exact-media viewer. The host owns the single persisted reference;
 * this surface supplies the full-screen stage, gestures and return flight. */

import { useEffect, useRef } from "react"
import type { ReactNode } from "react"
import { motion, useMotionValue } from "motion/react"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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
    finalFocusRef.current = data?.slotId ? getSlot?.(data.slotId) ?? null : null
    onOpenChange(false)
  }

  return (
    <Dialog
      open={!!data}
      onOpenChange={(open) => {
        if (!open) requestCloseRef.current?.()
      }}
    >
      <DialogContent
        variant="lightbox"
        showCloseButton={false}
        finalFocus={getSlot ? () => finalFocusRef.current : undefined}
        overlayClassName="z-[70] bg-background duration-0 backdrop-blur-none data-open:animate-none data-closed:animate-none dark:bg-background supports-backdrop-filter:backdrop-blur-none"
        overlayRender={<motion.div style={{ opacity: veil }} />}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{data?.title}</DialogTitle>
        </DialogHeader>
        {data ? (
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
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
