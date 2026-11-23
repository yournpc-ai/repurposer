import { useState } from "react"
import { useTranslation } from "react-i18next"
import { PlatformIcon, PLATFORM_LABELS } from "@/components/publish/PlatformIcon"
import { Button } from "@/components/ui/button-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { apiDelete } from "@/lib/api"
import { connectChannel, PLATFORMS, useChannels } from "@/lib/channels"
import type { ChannelPlatform } from "@/lib/types"

export function ChannelsSection() {
  const { t } = useTranslation()
  const { refresh, accountFor, isConfigured, status } = useChannels()
  const [pending, setPending] = useState<ChannelPlatform | null>(null)
  if (status === "loading") return <Spinner label={t("common.loading")} />
  if (status === "error")
    return (
      <Button size="sm" variant="secondary" className="self-start" onClick={refresh}>
        {t("credits.retry")}
      </Button>
    )
  const visible = PLATFORMS.filter((platform) => isConfigured(platform) || accountFor(platform))
  if (!visible.length)
    return <p className="settings-note">{t("settings.channelsUnavailable")}</p>
  async function act(platform: ChannelPlatform, disconnectId?: string) {
    setPending(platform)
    try {
      if (disconnectId) {
        const res = await apiDelete("/api/v1/channels/" + disconnectId, {
          toast: t("channels.disconnectedToast", { platform: PLATFORM_LABELS[platform] }),
        })
        if (res.ok) await refresh()
      } else await connectChannel(platform)
    } catch {
      /* The API client reports action failures. */
    } finally {
      setPending(null)
    }
  }
  return (
    <ul className="settings-card">
      {visible.map((platform) => {
        const account = accountFor(platform)
        const expired = account?.status === "expired"
        const disconnect = account && (!expired || !isConfigured(platform))
        return (
          <li key={platform} className="settings-row">
            <div className="flex min-w-0 items-center gap-3">
              <PlatformIcon platform={platform} />
              <div className="min-w-0">
                <p>{PLATFORM_LABELS[platform]}</p>
                {account && (
                  <p className="truncate text-xs text-muted-foreground">
                    {account.display_name} ·{" "}
                    {t(expired ? "channels.expired" : "channels.connected")}
                  </p>
                )}
              </div>
            </div>
            <Button
              size="sm"
              variant="secondary"
              disabled={pending !== null}
              onClick={() => void act(platform, disconnect ? account.id : undefined)}
            >
              {t(
                disconnect
                  ? "channels.disconnect"
                  : expired
                    ? "channels.reconnect"
                    : "channels.connect",
              )}
            </Button>
          </li>
        )
      })}
    </ul>
  )
}
