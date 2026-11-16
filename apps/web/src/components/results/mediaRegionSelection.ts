import type { MediaRegionSelection } from "@/lib/mediaRegionSelection"

export {
  formatMediaTimeMs,
  makeMediaRegionSelection,
  videoContentRect,
} from "@/lib/mediaRegionSelection"
export type {
  PixelRect,
  PixelSize,
  MediaRegionSelection,
} from "@/lib/mediaRegionSelection"

export interface MediaRegionSelectionControl {
  enabled: boolean
  value: MediaRegionSelection | null
  onChange: (value: MediaRegionSelection) => void
  onReselect: () => void
  onCancel: () => void
  onDone: () => void
}
