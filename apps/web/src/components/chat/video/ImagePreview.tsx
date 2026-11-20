import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { MediaLightbox } from "@/components/results/MediaLightbox"
import { apiGet } from "@/lib/api"
import type { ImagePreviewBlock } from "../timeline/types"

export function ImagePreview({ block }: { block: ImagePreviewBlock }) {
  const { t } = useTranslation()
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    let active = true
    setOpen(false)
    setSrc(null)
    setFailed(false)
    async function load() {
      const response = await apiGet(
        `/api/v1/projects/${block.project_id}/image/${block.snapshot_id}/preview`, { toast: false },
      )
      if (!response.ok) throw new Error("Image unavailable")
      const data = await response.json()
      if (data.snapshot_id !== block.snapshot_id || data.digest !== block.digest || typeof data.url !== "string") {
        throw new Error("Image source changed")
      }
      if (active) setSrc(data.url)
    }
    void load().catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [block.project_id, block.snapshot_id, block.digest])
  if (failed) return <p>{t("chat.activity.imageUnavailable")}</p>
  if (!src) return null
  return (
    <>
      <button ref={trigger} type="button" onClick={() => setOpen(true)}
        aria-label={t("chat.anchorCards.view", { name: block.description })}>
        <img className="max-h-96 rounded-lg object-contain" src={src} alt={block.description}
          onError={() => setFailed(true)} />
      </button>
      <MediaLightbox data={open ? {
        id: block.snapshot_id, slotId: block.snapshot_id, kind: "image", url: src, title: block.description,
      } : null} onOpenChange={setOpen} getSlot={() => trigger.current} />
    </>
  )
}
