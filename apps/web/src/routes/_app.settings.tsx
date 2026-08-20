import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { PLATFORM_LABELS } from "@/components/publish/PlatformIcon"
import { useChannels } from "@/lib/channels"
import { useSettingsDialog } from "@/components/settings/SettingsDialog"

import type { ChannelPlatform } from "@/lib/types"

/** NOT a page — the settings surface is the shared SettingsDialog (MiniMax
 * pattern, 2026-08-21). This route survives ONLY as the channels OAuth
 * callback landing (`/settings?connected=… | ?error=…`, the redirect URI is
 * registered server-side): it toasts the outcome, opens the dialog to the
 * channels section, and bounces home. A bare visit behaves the same (no
 * toast) — the dialog IS the settings surface now. */
export const Route = createFileRoute("/_app/settings")({
  validateSearch: (search: Record<string, unknown>) => ({
    connected: typeof search.connected === "string" ? search.connected : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
  }),
  component: SettingsOAuthReturn,
})

function SettingsOAuthReturn() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { connected, error } = Route.useSearch()
  const { refresh } = useChannels()
  const { openSettings } = useSettingsDialog()

  useEffect(() => {
    if (connected) {
      toast.success(
        t("channels.connectedToast", {
          platform: PLATFORM_LABELS[connected as ChannelPlatform] ?? connected,
        })
      )
      refresh()
    } else if (error) {
      toast.error(t("channels.connectFailed", { platform: error }))
    }
    openSettings("channels")
    navigate({ to: "/home", replace: true })
  }, [connected, error, navigate, openSettings, refresh, t])

  return null
}
