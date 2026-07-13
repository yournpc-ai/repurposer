"use client"

// Draggable card stack, adapted from https://reactbits.dev/components/stack
// (ported to TypeScript/Tailwind; trimmed to the drag-to-cycle interaction
// this project actually uses — no autoplay/mobile variants).

import { type ReactNode, useEffect, useState } from "react"
import { motion, useMotionValue, useTransform, type PanInfo } from "motion/react"

import { cn } from "@/lib/utils"

export interface StackCardData {
  id: string | number
  content: ReactNode
}

interface CardRotateProps {
  children: ReactNode
  onSendToBack: () => void
  sensitivity: number
}

function CardRotate({ children, onSendToBack, sensitivity }: CardRotateProps) {
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const rotateX = useTransform(y, [-100, 100], [40, -40])
  const rotateY = useTransform(x, [-100, 100], [-40, 40])

  const handleDragEnd = (_: unknown, info: PanInfo) => {
    if (Math.abs(info.offset.x) > sensitivity || Math.abs(info.offset.y) > sensitivity) {
      onSendToBack()
    } else {
      x.set(0)
      y.set(0)
    }
  }

  return (
    <motion.div
      className="absolute inset-0 cursor-grab"
      style={{ x, y, rotateX, rotateY }}
      drag
      dragConstraints={{ top: 0, right: 0, bottom: 0, left: 0 }}
      dragElastic={0.6}
      whileTap={{ cursor: "grabbing" }}
      onDragEnd={handleDragEnd}
    >
      {children}
    </motion.div>
  )
}

interface StackProps {
  cards: StackCardData[]
  className?: string
  randomRotation?: boolean
  sensitivity?: number
  sendToBackOnClick?: boolean
}

export function Stack({
  cards,
  className,
  randomRotation = false,
  sensitivity = 200,
  sendToBackOnClick = false,
}: StackProps) {
  const [order, setOrder] = useState<Array<string | number>>(() => cards.map((c) => c.id))

  // Keep drag-cycle position stable across card list changes (e.g. adding or
  // removing a file) instead of snapping back to the original order.
  useEffect(() => {
    setOrder((prev) => {
      const ids = cards.map((c) => c.id)
      const kept = prev.filter((id) => ids.includes(id))
      const added = ids.filter((id) => !kept.includes(id))
      return [...kept, ...added]
    })
  }, [cards])

  const sendToBack = (id: string | number) => {
    setOrder((prev) => {
      const index = prev.indexOf(id)
      if (index === -1) return prev
      const next = [...prev]
      const [item] = next.splice(index, 1)
      next.unshift(item)
      return next
    })
  }

  const byId = new Map(cards.map((c) => [c.id, c]))
  const stack = order.map((id) => byId.get(id)).filter((c): c is StackCardData => c != null)

  return (
    <div className={cn("relative", className)} style={{ perspective: 600 }}>
      {stack.map((card, index) => {
        // How many positions back from the front (top) card this one sits.
        const depth = stack.length - index - 1
        const randomRotate = randomRotation ? Math.random() * 10 - 5 : 0
        return (
          <CardRotate key={card.id} onSendToBack={() => sendToBack(card.id)} sensitivity={sensitivity}>
            <motion.div
              className="absolute inset-0"
              onClick={() => sendToBackOnClick && sendToBack(card.id)}
              animate={{
                // Fan cards toward the top-left as they go back — rotation
                // alone doesn't move a centered label far enough to keep it
                // from overlapping the card in front at this card size.
                x: depth * -5,
                y: depth * -5,
                rotateZ: depth * 4 + randomRotate,
                scale: 1 + index * 0.06 - stack.length * 0.06,
                transformOrigin: "90% 90%",
              }}
              initial={false}
              transition={{ type: "spring", stiffness: 260, damping: 20 }}
            >
              {card.content}
            </motion.div>
          </CardRotate>
        )
      })}
    </div>
  )
}
