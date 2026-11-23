/** Shared channel (OAuth account) plumbing for the publish dialog, the
 * settings channels section, and the notification bell's Reconnect CTA. */

import { useCallback, useEffect, useState } from "react"

import { apiFetch } from "@/lib/api"

import type {
  ChannelAccount,
  ChannelPlatform,
  PlatformAvailability,
} from "@/lib/types"

export const PLATFORMS: ChannelPlatform[] = ["linkedin", "tiktok"]

/** Kick off the OAuth connect flow: fetch the platform's authorize URL and
 * full-page redirect to it. Errors surface via apiFetch's global toast. */
export async function connectChannel(platform: ChannelPlatform): Promise<void> {
  const res = await apiFetch(`/api/v1/channels/${platform}/oauth-url`)
  if (res.ok) {
    const { url } = await res.json()
    window.location.href = url
  }
}

/** Connected accounts + per-platform availability, with presence-gating
 * helpers. Pass `enabled = false` to defer fetching (e.g. a closed dialog) —
 * flipping it true triggers the fetch. */
export function useChannels(enabled = true) {
  const [channels, setChannels] = useState<ChannelAccount[]>([])
  const [availability, setAvailability] = useState<PlatformAvailability[]>([])

  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading")
  const refresh = useCallback(async () => {
    setStatus("loading")
    try {
      const [accounts, platforms] = await Promise.all(
        ["/api/v1/channels", "/api/v1/channels/platforms"].map(async path => {
          const res = await apiFetch(path, { toast: false })
          if (!res.ok) throw new Error("Channels unavailable")
          return res.json()
        })
      )
      setChannels(accounts)
      setAvailability(platforms)
      setStatus("ready")
    } catch {
      setStatus("error")
    }
  }, [])

  useEffect(() => {
    if (enabled) refresh()
  }, [enabled, refresh])

  /** The account for a platform in any status (active or expired). */
  const accountFor = useCallback(
    (platform: ChannelPlatform) =>
      channels.find((a) => a.platform === platform),
    [channels]
  )
  /** Only publishable accounts count — expired ones need reconnect first. */
  const activeAccountFor = useCallback(
    (platform: ChannelPlatform) =>
      channels.find((a) => a.platform === platform && a.status === "active"),
    [channels]
  )
  /** Presence-gating (§4.1): unconfigured platforms render "coming soon". */
  const isConfigured = useCallback(
    (platform: ChannelPlatform) =>
      availability.find((a) => a.platform === platform)?.configured ?? false,
    [availability]
  )

  return { channels, availability, status, refresh, accountFor, activeAccountFor, isConfigured }
}
