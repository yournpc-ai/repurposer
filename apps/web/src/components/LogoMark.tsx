import { cn } from "@/lib/utils"

/**
 * Repurposer brand mark — a solid "delta": one stream fanning out into many
 * (a talk becomes clips / posts / articles). This is the one sanctioned
 * hand-written SVG in the app (CLAUDE.md icon rule): a brand mark has no
 * lucide alternative by definition. Functional icons still come from lucide.
 *
 * Theme-aware: tile = bg-primary, glyph = text-primary-foreground, so it
 * inverts with the theme like every other control. Keep the geometry in sync
 * with public/favicon.svg (the static, baked-color version of this mark).
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grid h-7 w-7 shrink-0 place-items-center rounded-[22%] bg-primary text-primary-foreground",
        className
      )}
    >
      <svg viewBox="0 0 24 24" className="h-[86%] w-[86%]" aria-hidden="true">
        <path
          d="M4.5 9.9 C8.5 9.9 9.4 6.7 18.8 5.9 L15.4 12 L18.8 18.1 C9.4 17.3 8.5 14.1 4.5 14.1 Z"
          fill="currentColor"
          stroke="currentColor"
          strokeWidth="0.9"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  )
}
