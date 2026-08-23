"use client"

/**
 * 轮播图 (carousel) — process schematic.
 *
 * LEFT:  the source script card (a stack of text rows).
 * RIGHT: three carousel slide frames side-by-side, each with a title line
 *        and two body rows, and a row of pagination dots below. On hover,
 *        the three frames pulse in sequence ("slide carousel past us")
 *        while the dashed arrow flows across to advertise the fanout.
 */
export function CarouselCover() {
  return (
    <svg
      className="recipe-cover sc-carousel absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <defs>
        <marker
          id="car-arr"
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
      <rect x="44" y="130" width="40" height="7" rx="3" fill="currentColor" fillOpacity="0.24" />
      <path
        className="arrp"
        d="M140 115 L 168 115"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
        markerEnd="url(#car-arr)"
      />
      <rect
        className="fr f1"
        x="182"
        y="55"
        width="60"
        height="75"
        rx="5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <rect x="190" y="68" width="30" height="8" rx="3" fill="currentColor" />
      <rect x="190" y="84" width="44" height="5" rx="2.5" fill="currentColor" fillOpacity="0.4" />
      <rect x="190" y="95" width="38" height="5" rx="2.5" fill="currentColor" fillOpacity="0.24" />
      <rect
        className="fr f2"
        x="250"
        y="55"
        width="60"
        height="75"
        rx="5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <rect x="258" y="68" width="30" height="8" rx="3" fill="currentColor" fillOpacity="0.85" />
      <rect x="258" y="84" width="44" height="5" rx="2.5" fill="currentColor" fillOpacity="0.4" />
      <rect x="258" y="95" width="38" height="5" rx="2.5" fill="currentColor" fillOpacity="0.24" />
      <rect
        className="fr f3"
        x="318"
        y="55"
        width="60"
        height="75"
        rx="5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <rect x="326" y="68" width="30" height="8" rx="3" fill="currentColor" fillOpacity="0.85" />
      <rect x="326" y="84" width="44" height="5" rx="2.5" fill="currentColor" fillOpacity="0.4" />
      <rect x="326" y="95" width="38" height="5" rx="2.5" fill="currentColor" fillOpacity="0.24" />
      <circle cx="212" cy="150" r="2.5" fill="currentColor" />
      <circle cx="280" cy="150" r="2.5" fill="currentColor" fillOpacity="0.4" />
      <circle cx="348" cy="150" r="2.5" fill="currentColor" fillOpacity="0.4" />
    </svg>
  )
}
