"use client"

/** MediaLightbox — the shared exact-Output viewer. The host owns selection;
 * this surface supplies the full-screen stage, gestures and return flight. */

import { useEffect, useMemo, useRef } from "react"
import type { ReactNode } from "react"
import { motion, useMotionValue } from "motion/react"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useSoundMutexHold } from "@/components/flow/sound-mutex"
import { MediaLightboxStage } from "./MediaLightboxStage"
import type { MediaLightboxData } from "./mediaLightboxTypes"

export type { MediaChip, MediaLightboxData } from "./mediaLightboxTypes"

export function MediaLightbox({
  data,
  onOpenChange,
  navigation,
  gallery,
  actions,
  getSlot,
}: {
  data: MediaLightboxData | null
  onOpenChange: (open: boolean) => void
  navigation?: {
    index: number
    total: number
    onPrevious: () => void
    onNext: () => void
  }
  gallery?: {
    items: MediaLightboxData[]
    activeId: string
    onSelect: (outputId: string) => void
  }
  actions?: ReactNode
  getSlot?: (slotId: string) => HTMLElement | null
}) {
  useSoundMutexHold(!!data && data.kind === "video", "lightbox")
  const requestCloseRef = useRef<(() => void) | null>(null)
  const veil = useMotionValue(0)
  useEffect(() => {
    // Mention / revise intentionally bypasses the return flight and focuses
    // the composer. Reset the shared backdrop for the next opening.
    if (!data) veil.jump(0)
  }, [data, veil])

  const items = useMemo(() => {
    const source = gallery?.items.length ? gallery.items : data ? [data] : []
    if (!data) return source
    return source.map((item) => item.id && item.id === data.id
      ? { ...item, ...data, thumbnail: data.thumbnail ?? item.thumbnail }
      : item)
  }, [data, gallery?.items])

  const activeId = gallery?.activeId ?? data?.id
  const start = items.findIndex((item) => item.id === activeId)
  const resolvedStart = start >= 0 ? start : navigation?.index ?? 0

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
        overlayClassName="z-[70] bg-background duration-0 backdrop-blur-none data-open:animate-none data-closed:animate-none dark:bg-background supports-backdrop-filter:backdrop-blur-none"
        overlayRender={<motion.div style={{ opacity: veil }} />}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{data?.title}</DialogTitle>
        </DialogHeader>
        {data && items.length > 0 ? (
          <MediaLightboxStage
            items={items}
            activeId={activeId}
            start={resolvedStart}
            actions={actions}
            getSlot={getSlot}
            onNavigate={(id) => gallery?.onSelect(id)}
            onClosed={() => onOpenChange(false)}
            requestCloseRef={requestCloseRef}
            veil={veil}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
