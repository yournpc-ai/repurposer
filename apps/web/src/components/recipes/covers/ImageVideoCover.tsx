"use client"

/**
 * 图文视频 (image-video) — process schematic.
 *
 * LEFT:  a script/article card (text rows) — the user's long-form material.
 * MID:   two image tiles (the photos or slide extracts).
 * RIGHT: the output video frame; an arrow with a dashed flow line crosses
 *        the boundary. A caption overlay fades over the output frame on
 *        hover to advertise the burned-in subtitles.
 */
export function ImageVideoCover() {
  return (
    <svg
      className="recipe-cover sc-imageVideo absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <defs>
        <marker
          id="im-arr"
          markerWidth="8"
          markerHeight="8"
          refX="6"
          refY="4"
          orient="auto"
        >
          <path d="M0 0 L8 4 L0 8" fill="none" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.5" />
        </marker>
      </defs>
      <rect
        x="30"
        y="60"
        width="90"
        height="110"
        rx="6"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <rect x="44" y="82" width="60" height="7" rx="3" fill="currentColor" fillOpacity="0.4" />
      <rect x="44" y="98" width="48" height="7" rx="3" fill="currentColor" fillOpacity="0.24" />
      <rect x="44" y="114" width="54" height="7" rx="3" fill="currentColor" fillOpacity="0.24" />
      <rect
        x="132"
        y="60"
        width="64"
        height="50"
        rx="6"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <path
        d="M138 102 L150 86 L160 96 L167 89 L190 102"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
      />
      <rect
        x="132"
        y="120"
        width="64"
        height="50"
        rx="6"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <circle
        cx="152"
        cy="138"
        r="7"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
      />
      <path
        className="arrp"
        d="M210 115 L 240 115"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
        markerEnd="url(#im-arr)"
      />
      <rect
        x="252"
        y="66"
        width="132"
        height="94"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <rect
        x="252"
        y="66"
        width="132"
        height="94"
        rx="8"
        fill="currentColor"
        fillOpacity="0.04"
      />
      <rect
        className="cap2"
        x="268"
        y="136"
        width="92"
        height="10"
        rx="4"
        fill="currentColor"
      />
    </svg>
  )
}
