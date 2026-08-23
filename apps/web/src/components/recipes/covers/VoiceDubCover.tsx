"use client"

/**
 * 原声AI配音 (voice-dub) — process schematic.
 *
 * LEFT:  the speaker (a face circle with two outward sound-wave arcs), with
 *        a vertical waveform on its right (the synthesized voice track).
 * RIGHT: the same EN/ZH language-chip pair as the multilingual-subs cover
 *        — the language swap animation conveys "your voice, another
 *        language".
 *
 * 200px test: distinguishable from multilingual-subs because here the
 * LEFT side carries the speaker + waveform (not a frame + dual caption
 * lines). Process schematic, not output promise.
 */
export function VoiceDubCover() {
  return (
    <svg
      className="recipe-cover sc-dub absolute inset-0 h-full w-full"
      viewBox="0 0 400 250"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      <circle
        cx="95"
        cy="115"
        r="34"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <path
        d="M52 190 q 43 -46 86 0"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.85"
        strokeWidth="2"
      />
      <path
        d="M137 100 a 24 24 0 0 1 0 30"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <path
        d="M145 91 a 34 34 0 0 1 0 48"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="2"
      />
      <g className="wb" fill="currentColor" fillOpacity="0.85">
        <rect x="190" y="119" width="6" height="22" rx="3" />
        <rect x="207" y="111" width="6" height="38" rx="3" />
        <rect x="224" y="122" width="6" height="16" rx="3" />
        <rect x="241" y="108" width="6" height="44" rx="3" />
        <rect x="258" y="115" width="6" height="30" rx="3" />
        <rect x="275" y="104" width="6" height="52" rx="3" />
        <rect x="292" y="117" width="6" height="26" rx="3" />
        <rect x="309" y="112" width="6" height="36" rx="3" />
      </g>
      <g className="chip-en">
        <rect
          x="345"
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
          x="368"
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
        <rect x="345" y="135" width="46" height="20" rx="6" fill="currentColor" />
        <text
          x="368"
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
    </svg>
  )
}
