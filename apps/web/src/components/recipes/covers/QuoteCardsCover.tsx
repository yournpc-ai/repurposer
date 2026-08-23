"use client"

/**
 * 金句卡 (quote-cards) — process schematic.
 *
 * A single shareable card carrying a large "open-quote" glyph, two body
 * lines, and a meta row (author handle + source). On hover the open-quote
 * glyph pulses softly to convey "this is the line we picked".
 */
export function QuoteCardsCover() {
  return (
    <svg
      className="recipe-cover sc-quote absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <rect
        x="75"
        y="40"
        width="250"
        height="170"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <text
        className="qm"
        x="95"
        y="105"
        fontSize="54"
        fill="currentColor"
        fontFamily="Georgia, serif"
      >
        &ldquo;
      </text>
      <rect x="100" y="128" width="170" height="13" rx="4" fill="currentColor" fillOpacity="0.85" />
      <rect x="100" y="152" width="130" height="13" rx="4" fill="currentColor" fillOpacity="0.85" />
      <rect x="100" y="186" width="40" height="5" rx="2.5" fill="currentColor" fillOpacity="0.4" />
      <rect x="146" y="186" width="56" height="5" rx="2.5" fill="currentColor" fillOpacity="0.2" />
    </svg>
  )
}
