import { cn } from "@/lib/utils"

import { LOGO_GLYPH_PATH } from "./LogoMark"

/**
 * BrandLoader — the project's loading indicator for card-level surfaces
 * (rendering clips, active project tiles, generation placeholders).
 *
 * The delta glyph fills left → right: one stream flowing in, fanning out
 * into many — the "being generated" metaphor, instead of a generic spinning
 * ring. A dim base copy keeps the full silhouette readable while the solid
 * copy sweeps across via an animated clip-path (see `brand-loader-fill` in
 * styles.css; reduced-motion parks it at a static partial fill).
 *
 * Bare glyph, no tile — it sits on card surfaces (`processing-surface`,
 * muted tiles) rather than reading as a logo lockup. Decorative: every
 * usage carries an adjacent text label, so it's aria-hidden.
 *
 * NOT for inline 12–16px spots (busy buttons etc.) — at that size the
 * glyph's narrow waist smears; the plain border-spinner stays there.
 */
export function BrandLoader({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block h-7 w-7 shrink-0 text-primary", className)}
    >
      <svg viewBox="0 0 24 24" className="h-full w-full">
        {/* Dim base — the full silhouette the fill sweeps over. */}
        <path
          d={LOGO_GLYPH_PATH}
          fill="currentColor"
          stroke="currentColor"
          strokeWidth="0.9"
          strokeLinejoin="round"
          opacity={0.18}
        />
        <path
          d={LOGO_GLYPH_PATH}
          fill="currentColor"
          stroke="currentColor"
          strokeWidth="0.9"
          strokeLinejoin="round"
          className="brand-loader-fill"
        />
      </svg>
    </span>
  )
}
