import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

/**
 * ProcessingTile — the layered "working" surface for unsettled cards (live
 * project tiles, rendering clips). Detail is the point (Opus reference): a
 * matte base falloff, a light shaft swaying through drifting neutral mist,
 * film grain for tooth, a glass inner edge, and a halo behind the centered
 * content. No hue anywhere — fog, not glow. All layers are CSS-only
 * (styles.css: processing-base / -beam / -surface / -grain / -edge / -halo);
 * motion-reduce stills the two moving layers.
 */
export function ProcessingTile({
  className,
  children,
}: {
  className?: string
  /** Centered content — the BrandLoader plus an optional caption under it. */
  children?: ReactNode
}) {
  return (
    <div className={cn("absolute inset-0 overflow-hidden", className)}>
      {/* Matte panel: soft vertical falloff, never flat. */}
      <div className="processing-base absolute inset-0" />
      {/* Light shaft — a slow diagonal sway, like light through fog. */}
      <div className="processing-beam absolute -inset-y-10 -left-1/3 w-2/3 motion-reduce:animate-none" />
      {/* Drifting neutral mist (the original layer). */}
      <div className="processing-surface absolute -inset-8 motion-reduce:animate-none" />
      {/* Film grain — the matte tooth that keeps the fog from reading as a
          cheap gradient. */}
      <div className="processing-grain absolute inset-0" />
      {/* Glass inner edge: hairline top light, hairline bottom shade. */}
      <div className="processing-edge absolute inset-0 rounded-lg" />
      {/* Centered content on a soft halo. */}
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
        <div className="processing-halo absolute h-28 w-28" />
        {children}
      </div>
    </div>
  )
}
