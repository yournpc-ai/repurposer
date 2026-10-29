import { useEffect, useState } from "react"

import { apiPost, toAbsoluteUrl } from "@/lib/api"
import type { Output } from "@/lib/types"

const posterRequests = new Map<string, Promise<string | null>>()

function requestPoster(outputId: string): Promise<string | null> {
  const existing = posterRequests.get(outputId)
  if (existing) return existing
  const request = apiPost(`/api/v1/outputs/${outputId}/poster`, {}, { toast: false })
    .then(async (response) => {
      if (!response.ok) return null
      const data = (await response.json()) as { poster_url?: string }
      return data.poster_url ?? null
    })
    .catch(() => null)
  posterRequests.set(outputId, request)
  return request
}

/** The exact Output's real frame; no latest-version or first-frame substitute. */
export function useOutputPoster(output: Output | null): string | null {
  const existing = output?.publishing.cover_image_url ?? output?.files.image ?? null
  const needsPoster = Boolean(
    output &&
    !existing &&
    (output.type === "clip" || output.type === "film" || output.type === "video") &&
    output.render_status === "completed" &&
    output.files.video,
  )
  const [poster, setPoster] = useState<string | null>(existing)

  useEffect(() => {
    let active = true
    setPoster(existing)
    if (output && needsPoster) {
      void requestPoster(output.id).then((url) => {
        if (active && url) setPoster(url)
      })
    }
    return () => {
      active = false
    }
  }, [output?.id, existing, needsPoster])

  return toAbsoluteUrl(poster) ?? null
}
