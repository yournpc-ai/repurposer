import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { PLATFORM_LABELS } from "@/components/publish/PlatformIcon"
import { useChannels } from "@/lib/channels"
import { useSettingsDialog } from "@/components/settings/SettingsDialog"

import type { ChannelPlatform } from "@/lib/types"

/** NOT a page — the shared SettingsDialog is the surface. This shim handles
 * channel OAuth and hosted Checkout returns, opens the matching section, and
 * bounces home. Checkout=success is only a browser return: CreditsSection must
 * still read the server's paid order before announcing a top-up. */
export const Route = createFileRoute("/_app/settings")({
  validateSearch: (search: Record<string, unknown>) => ({
    connected: typeof search.connected === "string" ? search.connected : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
    checkout:
      search.checkout === "success" || search.checkout === "cancelled"
        ? search.checkout
        : undefined,
    order_id: typeof search.order_id === "string" ? search.order_id : undefined,
  }),
  component: SettingsCallbackReturn,
})

function SettingsCallbackReturn() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { connected, error, checkout, order_id: orderId } = Route.useSearch()
  const { refresh } = useChannels()
  const { openSettings } = useSettingsDialog()

  useEffect(() => {
    if (checkout && orderId) {
      openSettings("credits", { orderId, outcome: checkout })
      navigate({ to: "/home", replace: true })
      return
    }
    if (connected) {
      toast.success(
        t("channels.connectedToast", {
          platform: PLATFORM_LABELS[connected as ChannelPlatform] ?? connected,
        }),
      )
      refresh()
    } else if (error) {
      toast.error(t("channels.connectFailed", { platform: error }))
    }
    openSettings("channels")
    navigate({ to: "/home", replace: true })
  }, [checkout, orderId, connected, error, navigate, openSettings, refresh, t])

  return null
}
