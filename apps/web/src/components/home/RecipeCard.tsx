"use client"

import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Mic2, Video } from "lucide-react"

import type { RecipeCard as RecipeCardData } from "@/lib/recipes"

/**
 * One recipe card (RECIPES §7.3): poster (+ hover video preview when
 * harvested), title, one-line promise, output chips. The whole card is a
 * single click target — clicking prefills the composer with the recipe's
 * prompt template and pins its task book (see HomeComposer's recipe prop).
 */
export function RecipeCard({
  card,
  onSelect,
}: {
  card: RecipeCardData
  onSelect: (card: RecipeCardData) => void
}) {
  const { t } = useTranslation()
  const [hover, setHover] = useState(false)

  return (
    <button
      type="button"
      onClick={() => onSelect(card)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="group flex flex-col overflow-hidden rounded-lg bg-card text-left shadow-lg transition-shadow edge-glow hover:shadow-xl dark:shadow-none"
    >
      <div className="relative aspect-video w-full overflow-hidden bg-muted">
        {/* CSS blur-pad: the vertical (9:16) preview sits object-contain over a
            blurred copy of the poster, so no ffmpeg letterboxing step is needed. */}
        <img
          src={card.preview.posterUrl}
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full scale-110 object-cover blur-xl"
        />
        {hover && card.preview.videoUrl ? (
          <video
            src={card.preview.videoUrl}
            poster={card.preview.posterUrl}
            className="relative h-full w-full object-contain"
            autoPlay
            muted
            loop
            playsInline
          />
        ) : (
          <img
            src={card.preview.posterUrl}
            alt={t(`recipes.${card.id}.title`)}
            className="relative h-full w-full object-contain"
            loading="lazy"
          />
        )}
      </div>
      <div className="flex flex-col gap-1.5 p-4">
        <span className="text-sm font-medium">{t(`recipes.${card.id}.title`)}</span>
        <span className="text-sm text-muted-foreground">
          {t(`recipes.${card.id}.promise`)}
        </span>
        <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {card.slotsPrior.map((slot) => (
            <span
              key={slot.type}
              className="flex items-center gap-1 rounded-md bg-muted/60 px-2 py-0.5 text-xs text-muted-foreground"
            >
              <Video className="h-3 w-3" />
              {t(`results.tabs.${slot.type}`)}
            </span>
          ))}
          {card.params?.dubLanguages?.map((lang) => (
            <span
              key={lang}
              className="flex items-center gap-1 rounded-md bg-muted/60 px-2 py-0.5 text-xs text-muted-foreground"
            >
              <Mic2 className="h-3 w-3" />
              {t(`languages.${lang}`, { defaultValue: lang })}
            </span>
          ))}
        </span>
      </div>
    </button>
  )
}
