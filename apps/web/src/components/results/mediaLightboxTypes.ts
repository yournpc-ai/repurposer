import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"

export interface MediaChip {
  Icon: LucideIcon
  label: string
  title?: string
}

export interface MediaLightboxData {
  id?: string
  /** Host-owned card used as the opening / return-flight seat. */
  slotId?: string
  kind: "video" | "image" | "text"
  url?: string
  text?: string
  poster?: string | null
  /** Declared display ratio; the stage never probes media to discover it. */
  aspect?: number | null
  title: string
  versionLabel?: string | null
  createdAt?: string | null
  prompt?: string | null
  chips?: MediaChip[]
  modelFacts?: { modality: string; model: string }[] | null
  downloadName?: string
  /** Existing type-specific reader, e.g. carousel pages or unavailable state. */
  content?: ReactNode
  /** Per-item thumbnail supplied by the Chat's exact-Output adapter. */
  thumbnail?: ReactNode
}
