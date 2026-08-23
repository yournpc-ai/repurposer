"use client"

/**
 * 高光切片 (highlight-clips) — process schematic.
 *
 * LEFT:  a horizontal video frame carrying an audio waveform, with three
 *        vertical highlight brackets marking the chosen moments.
 * RIGHT: the three resulting vertical clips, each with a baseline (the
 *        caption track).
 *
 * Color law: three grayscale tiers via `currentColor` + `opacity`. The host
 * RecipeCard sets the parent class to `text-foreground/*` so the inversion
 * between light and dark themes is free — never hardcode hex.
 */
export function HighlightClipsCover() {
  return (
    <svg
      className="recipe-cover sc-highlight absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <rect
        x="24"
        y="70"
        width="150"
        height="110"
        rx="6"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <polyline
        points="36,128 50,112 64,140 78,104 92,134 106,116 120,130 134,108 148,136 162,120 166,124"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
      />
      <rect
        className="br"
        x="52"
        y="79"
        width="22"
        height="92"
        rx="3"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <rect
        className="br br2"
        x="92"
        y="79"
        width="22"
        height="92"
        rx="3"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <rect
        className="br br3"
        x="132"
        y="79"
        width="22"
        height="92"
        rx="3"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <rect
        x="196"
        y="77"
        width="54"
        height="96"
        rx="5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <rect
        x="262"
        y="77"
        width="54"
        height="96"
        rx="5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <rect
        x="328"
        y="77"
        width="54"
        height="96"
        rx="5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <rect x="203" y="150" width="40" height="6" rx="3" fill="currentColor" />
      <rect x="269" y="150" width="40" height="6" rx="3" fill="currentColor" />
      <rect x="335" y="150" width="40" height="6" rx="3" fill="currentColor" />
    </svg>
  )
}
