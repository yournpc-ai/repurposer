"use client"

/**
 * 社媒帖 (social-post) — process schematic.
 *
 * A vertical feed-post card: avatar + identity header, four body lines
 * (the last one highlighted as the "hook"), and three icon rows for
 * engagement (likes / comments / share). On hover, the four body lines
 * grow horizontally in sequence, conveying "the post being written".
 */
export function SocialPostCover() {
  return (
    <svg
      className="recipe-cover sc-post absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <rect
        x="85"
        y="35"
        width="230"
        height="185"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <circle
        cx="113"
        cy="66"
        r="13"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <rect x="134" y="57" width="70" height="8" rx="3" fill="currentColor" fillOpacity="0.85" />
      <rect x="134" y="71" width="48" height="6" rx="3" fill="currentColor" fillOpacity="0.24" />
      <rect className="tl tl1" x="105" y="102" width="190" height="7" rx="3" fill="currentColor" fillOpacity="0.4" />
      <rect className="tl tl2" x="105" y="120" width="190" height="7" rx="3" fill="currentColor" fillOpacity="0.4" />
      <rect className="tl tl3" x="105" y="138" width="140" height="7" rx="3" fill="currentColor" fillOpacity="0.4" />
      <rect className="tl tl4" x="105" y="162" width="110" height="7" rx="3" fill="currentColor" />
      <rect
        x="105"
        y="192"
        width="8"
        height="8"
        rx="2"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
      />
      <rect x="119" y="195" width="28" height="3" rx="1.5" fill="currentColor" fillOpacity="0.24" />
      <rect
        x="165"
        y="192"
        width="8"
        height="8"
        rx="2"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
      />
      <rect x="179" y="195" width="28" height="3" rx="1.5" fill="currentColor" fillOpacity="0.24" />
      <rect
        x="225"
        y="192"
        width="8"
        height="8"
        rx="2"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
      />
      <rect x="239" y="195" width="28" height="3" rx="1.5" fill="currentColor" fillOpacity="0.24" />
    </svg>
  )
}
