"use client"

/**
 * 多语言字幕 (multilingual-subs) — process schematic.
 *
 * LEFT:  a video frame with a speaker circle and a two-line caption track
 *        (the chosen language caption line grows on hover to convey
 *        "caption translation").
 * RIGHT: a pair of language chips — EN outline / ZH solid — flipping
 *        opacity to advertise the language-fanout.
 */
export function MultilingualSubsCover() {
  return (
    <svg
      className="recipe-cover sc-subs absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <rect
        x="30"
        y="70"
        width="230"
        height="130"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <circle
        cx="145"
        cy="120"
        r="15"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <rect x="70" y="165" width="120" height="12" rx="4" fill="currentColor" fillOpacity="0.4" />
      <rect
        className="cap"
        x="88"
        y="182"
        width="90"
        height="9"
        rx="4"
        fill="currentColor"
      />
      <g className="chip-en">
        <rect
          x="292"
          y="95"
          width="46"
          height="20"
          rx="6"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.85"
          strokeWidth="1.5"
        />
        <text
          x="315"
          y="109"
          fontSize="11"
          fill="currentColor"
          fillOpacity="0.85"
          textAnchor="middle"
          fontFamily="inherit"
        >
          EN
        </text>
      </g>
      <g className="chip-zh">
        <rect x="292" y="135" width="46" height="20" rx="6" fill="currentColor" />
        <text
          x="315"
          y="149"
          fontSize="11"
          fill="currentColor"
          fillOpacity="0"
          textAnchor="middle"
          fontFamily="inherit"
        >
          中
        </text>
      </g>
      <path
        d="M264 135 Q 278 122 288 108"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
        strokeDasharray="3 3"
      />
      <rect x="95" y="222" width="110" height="5" rx="2.5" fill="currentColor" fillOpacity="0.2" />
    </svg>
  )
}
