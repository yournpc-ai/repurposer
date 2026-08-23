"use client"

import { HighlightClipsCover } from "./HighlightClipsCover"
import { MultilingualSubsCover } from "./MultilingualSubsCover"
import { VoiceDubCover } from "./VoiceDubCover"
import { ReframeCover } from "./ReframeCover"
import { ImageVideoCover } from "./ImageVideoCover"
import { SocialPostCover } from "./SocialPostCover"
import { QuoteCardsCover } from "./QuoteCardsCover"
import { CarouselCover } from "./CarouselCover"

/** Cover registry — recipe id → process-schematic component (ADR-048).
 *
 * The geometry is sourced from `docs/tasks/recipe-gallery-v2-covers.html`;
 * the React components translate the inline SVG to JSX using currentColor +
 * three opacity tiers only — no hex, no fourth gray.
 *
 * The cover id IS the recipe id (no separate identifier) so the registry
 * stays a literal lookup. Unknown ids resolve to undefined and the host
 * RecipeCard renders nothing in the tile (still SSR-safe).
 */
export const recipeCovers: Record<string, () => React.JSX.Element> = {
  "highlight-clips": () => <HighlightClipsCover />,
  "multilingual-subs": () => <MultilingualSubsCover />,
  "voice-dub": () => <VoiceDubCover />,
  reframe: () => <ReframeCover />,
  "image-video": () => <ImageVideoCover />,
  "social-post": () => <SocialPostCover />,
  "quote-cards": () => <QuoteCardsCover />,
  carousel: () => <CarouselCover />,
}
