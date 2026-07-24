import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { PlatformIcon, PLATFORM_LABELS } from "@/components/publish/PlatformIcon"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { apiDelete } from "@/lib/api"
import { connectChannel, PLATFORMS, useChannels } from "@/lib/channels"

import type { ChannelAccount, ChannelPlatform } from "@/lib/types"

export const Route = createFileRoute("/settings")({
  // OAuth callback lands here: /settings?connected=linkedin | ?error=...
  validateSearch: (search: Record<string, unknown>) => ({
    connected: typeof search.connected === "string" ? search.connected : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
  }),
  component: SettingsPage,
})

function SettingsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { connected, error } = Route.useSearch()
  const { refresh, accountFor, isConfigured } = useChannels()

  // Surface the OAuth callback outcome once, then clean the URL.
  useEffect(() => {
    const clean = { connected: undefined, error: undefined }
    if (connected) {
      toast.success(
        t("channels.connectedToast", {
          platform: PLATFORM_LABELS[connected as ChannelPlatform] ?? connected,
        })
      )
      navigate({ to: "/settings", search: clean, replace: true })
      refresh()
    } else if (error) {
      toast.error(t("channels.connectFailed", { platform: error }))
      navigate({ to: "/settings", search: clean, replace: true })
    }
  }, [connected, error, navigate, refresh, t])

  const disconnect = async (account: ChannelAccount) => {
    const res = await apiDelete(`/api/v1/channels/${account.id}`, {
      toast: t("channels.disconnectedToast", {
        platform: PLATFORM_LABELS[account.platform],
      }),
    })
    if (res.ok) refresh()
  }

  return (
    <div className="mx-auto w-full max-w-3xl p-6 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        {t("settings.title")}
      </h1>

      <section className="mt-8 space-y-3">
        <div>
          <h2 className="text-base font-medium">{t("channels.title")}</h2>
          <p className="text-sm text-muted-foreground">
            {t("channels.subtitle")}
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {PLATFORMS.map((platform) => {
            const account = accountFor(platform)
            const configured = isConfigured(platform)
            const expired = account?.status === "expired"
            return (
              <Card key={platform} className="p-4 ring-1 ring-border shadow-xl">
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
      </section>
    </div>
  )
}
