import { cn } from "@/lib/utils"

/**
 * Rookie brand mark — a fluid geometric "R" formed by a folded film ribbon
 * cleanly separated by a single diagonal edit cut ("Explore the art of the
 * cut"). This is the one sanctioned hand-written SVG in the app (CLAUDE.md icon
 * rule): a brand mark has no lucide alternative by definition. Functional icons
 * still come from lucide.
 *
 * Theme-aware: tile = bg-primary, glyph = text-primary-foreground, so it
 * inverts with the theme like every other control. Keep the geometry in sync
 * with public/favicon.svg (the static, baked-color version of this mark).
 */

/** The Rookie "R" glyph path — the single source of truth for the mark's
 * geometry. Shared by LogoMark (tiled lockups) and BrandLoader (the fill
 * animation); public/favicon.svg carries a static baked copy of the same path. */
export const LOGO_GLYPH_PATH =
  "M5.30 20.15 V6.00 C5.30 4.45 6.20 3.55 7.75 3.55 H12.60 C16.35 3.55 18.40 5.95 18.40 8.95 C18.40 11.45 17.15 13.10 14.85 13.85 L9.78 15.43 V13.65 C9.78 12.15 10.65 11.45 12.15 11.08 C13.95 10.65 14.85 10.05 14.85 8.90 C14.85 7.65 13.95 7.05 12.40 7.05 H8.80 V20.15 Z M10.85 16.32 L14.40 15.21 L18.65 19.65 C17.30 20.55 15.25 20.60 13.95 19.60 Z"

export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grid h-7 w-7 shrink-0 place-items-center rounded-[22%] bg-primary text-primary-foreground",
        className
      )}
    >
      <svg viewBox="0 0 24 24" className="h-[86%] w-[86%]" aria-hidden="true">
        <path d={LOGO_GLYPH_PATH} fill="currentColor" fillRule="evenodd" />
      </svg>
    </span>
  )
}
