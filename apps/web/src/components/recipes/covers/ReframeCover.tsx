"use client"

/**
 * 访谈分镜 (reframe) — process schematic.
 *
 * A horizontal frame containing two seated speakers (left/right pair).
 * A dashed viewport box marks the framing target; a solid viewport
 * (the actual vertical crop window) tracks between them — on hover the
 * tracking viewport slides from the left speaker to the right speaker.
 */
export function ReframeCover() {
  return (
    <svg
      className="recipe-cover sc-reframe absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <rect
        x="40"
        y="65"
        width="320"
        height="120"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <circle
        cx="125"
        cy="103"
        r="15"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <path
        d="M102 152 q 23 -24 46 0"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <circle
        cx="275"
        cy="103"
        r="15"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <path
        d="M252 152 q 23 -24 46 0"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <rect
        x="238"
        y="55"
        width="76"
        height="140"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
        strokeDasharray="4 4"
      />
      <rect
        className="vp"
        x="88"
        y="55"
        width="76"
        height="140"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
      />
    </svg>
  )
}
