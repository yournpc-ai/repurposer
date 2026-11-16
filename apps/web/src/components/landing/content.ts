import { RECIPE_ASSETS } from "@/lib/recipes.assets"
import type { BuiltInSkillReference } from "@/lib/skills"

export type LandingGalleryItem = {
  id: "product-promo" | "talking-head" | "text-animation" | "knowledge-explainer"
  skill: BuiltInSkillReference
  videoUrl: string
  posterUrl: string
}

/**
 * Public visual candidates only. Every URL was already published in the demo
 * tree; no pending category-anchor media is copied into the public bundle.
 * Replace individual entries only after that exact category anchor clears its
 * audiovisual and publication gates.
 */
export const LANDING_GALLERY: readonly LandingGalleryItem[] = [
  {
    id: "product-promo",
    skill: { kind: "builtin", skill_id: "promo-video", version: "bdd94be16d60fa8f" },
    videoUrl:
      "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/product-demo-agentveil-in-motion-420b7ffe.mp4",
    posterUrl: "/gallery/product-demo-agentveil-in-motion-420b7ffe.jpg",
  },
  {
    id: "talking-head",
    skill: { kind: "builtin", skill_id: "talking-head-video", version: "1.0.0" },
    videoUrl: RECIPE_ASSETS["highlight-clips-preview.mp4"],
    posterUrl: RECIPE_ASSETS["highlight-clips-poster.jpg"],
  },
  {
    id: "text-animation",
    skill: { kind: "builtin", skill_id: "text-animation", version: "1.0.0" },
    videoUrl:
      "https://repurposer.tos-ap-southeast-1.volces.com/demo/outputs/text-short-genesis-25aa61fa.mp4",
    posterUrl: "/gallery/text-short-genesis-25aa61fa.jpg",
  },
  {
    id: "knowledge-explainer",
    skill: { kind: "builtin", skill_id: "knowledge-explainer", version: "1.0.0" },
    videoUrl: RECIPE_ASSETS["image-video-preview.mp4"],
    posterUrl: RECIPE_ASSETS["image-video-poster.jpg"],
  },
] as const

function publicUrl(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

/** No channel renders until its real public destination is configured. */
export const SOCIAL_CHANNELS = {
  discord: publicUrl(import.meta.env.VITE_DISCORD_URL),
  youtube: publicUrl(import.meta.env.VITE_YOUTUBE_URL),
  x: publicUrl(import.meta.env.VITE_X_URL),
  wechatQr: publicUrl(import.meta.env.VITE_WECHAT_GROUP_QR_URL),
} as const

export const SUPPORT_EMAIL = publicUrl(import.meta.env.VITE_SUPPORT_EMAIL)

export const LEGAL_LINKS = {
  terms: publicUrl(import.meta.env.VITE_TERMS_URL),
  privacy: publicUrl(import.meta.env.VITE_PRIVACY_URL),
  refund: publicUrl(import.meta.env.VITE_REFUND_POLICY_URL),
} as const
