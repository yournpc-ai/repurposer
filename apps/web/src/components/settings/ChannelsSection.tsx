"use client"

import { useTranslation } from "react-i18next"

import { PlatformIcon, PLATFORM_LABELS } from "@/components/publish/PlatformIcon"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { apiDelete } from "@/lib/api"
import { connectChannel, PLATFORMS, useChannels } from "@/lib/channels"

import type { ChannelAccount } from "@/lib/types"

/** Channels section of the shared SettingsDialog (ported from the retired
 * /settings page, 2026-08-21): platform connection cards — connect /
 * disconnect / reconnect-expired. The OAuth callback outcome (toast +
 * refresh) is handled by the /settings shim route, not here. */
export function ChannelsSection() {
  const { t } = useTranslation()
  const { refresh, accountFor, isConfigured } = useChannels()

  const disconnect = async (account: ChannelAccount) => {
    const res = await apiDelete(`/api/v1/channels/${account.id}`, {
      toast: t("channels.disconnectedToast", {
        platform: PLATFORM_LABELS[account.platform],
      }),
    })
    if (res.ok) refresh()
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("channels.subtitle")}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        {PLATFORMS.map((platform) => {
          const account = accountFor(platform)
          const configured = isConfigured(platform)
          const expired = account?.status === "expired"
          return (
            <Card key={platform} className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <PlatformIcon platform={platform} />
                  {PLATFORM_LABELS[platform]}
                </div>
                {account && !expired && (
                  <Badge className="rounded-md" variant="secondary">
                    {t("channels.connected")}
                  </Badge>
                )}
                {expired && (
                  <Badge className="rounded-md" variant="destructive">
                    {t("channels.expired")}
                  </Badge>
                )}
              </div>
              <div className="mt-4 flex items-center justify-between">
                {!configured ? (
                  <span className="text-sm text-muted-foreground">
                    {t("channels.comingSoon")}
                  </span>
                ) : account ? (
                  <>
                    <div className="flex items-center gap-2">
                      <Avatar className="h-7 w-7">
                        {account.avatar_url && (
                          <AvatarImage src={account.avatar_url} />
                        )}
                        <AvatarFallback>
                          {account.display_name.slice(0, 1).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <span className="truncate text-sm">
                        {account.display_name}
                      </span>
                    </div>
                    {expired ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-9"
                        onClick={() => connectChannel(platform)}
                      >
                        {t("channels.reconnect")}
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-9"
                        onClick={() => disconnect(account)}
                      >
                        {t("channels.disconnect")}
                      </Button>
                    )}
                  </>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9"
                    onClick={() => connectChannel(platform)}
                  >
                    {t("channels.connect")}
                  </Button>
                )}
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
