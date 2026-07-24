"use client"

import { useCallback, useEffect, useState } from "react"
import { Bell, ExternalLink } from "lucide-react"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/components/AuthProvider"
import { PlatformIcon, PLATFORM_LABELS } from "@/components/publish/PlatformIcon"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiFetch, apiPost } from "@/lib/api"
import { connectChannel } from "@/lib/channels"

import type { AppNotification, NotificationList } from "@/lib/types"

const POLL_INTERVAL_MS = 30_000

function useRelativeTime() {
  const { t } = useTranslation()
  return (iso: string | null) => {
    if (!iso) return ""
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
    if (seconds < 60) return t("notifications.justNow")
    if (seconds < 3600)
      return t("notifications.minutesAgo", { count: Math.floor(seconds / 60) })
    if (seconds < 86400)
      return t("notifications.hoursAgo", { count: Math.floor(seconds / 3600) })
    return t("notifications.daysAgo", { count: Math.floor(seconds / 86400) })
  }
}

function NotificationRow({
  item,
  relativeTime,
  onAction,
}: {
  item: AppNotification
  relativeTime: (iso: string | null) => string
  onAction: () => void
}) {
  const { t } = useTranslation()
  const platform = item.payload.platform
  const platformLabel = platform ? PLATFORM_LABELS[platform] : ""

  const titleKey =
    item.type === "publish_succeeded"
      ? "notifications.publishSucceeded"
      : item.type === "channel_expired"
        ? "notifications.channelExpired"
        : "notifications.publishFailed"

  const summary =
    item.type === "publish_failed"
      ? item.payload.error || item.payload.title || ""
      : item.payload.title || ""

  return (
    <div className="flex gap-3 px-4 py-3">
      <div className="flex w-4 shrink-0 justify-center pt-1.5">
        {item.read_at === null && (
          <span className="h-2 w-2 rounded-full bg-primary" />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <PlatformIcon platform={platform} className="h-3.5 w-3.5" />
          <span className="truncate">
            {t(titleKey, { platform: platformLabel })}
          </span>
        </div>
        {summary && (
          <p className="line-clamp-2 text-sm text-muted-foreground">{summary}</p>
        )}
        <div className="flex items-center gap-3 pt-0.5">
          {item.type === "publish_succeeded" && item.payload.platform_post_url && (
            <a
              href={item.payload.platform_post_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-sm text-primary hover:underline"
            >
              {t("notifications.openPost")}
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
          {item.type === "publish_failed" && item.payload.publication_id && (
            <button
              type="button"
              className="text-sm text-primary hover:underline"
              onClick={async () => {
                await apiPost(
                  `/api/v1/publications/${item.payload.publication_id}/retry`,
                  {},
                  { toast: t("notifications.retryQueued") }
                )
                onAction()
              }}
            >
              {t("notifications.retry")}
            </button>
          )}
          {item.type === "channel_expired" && platform && (
            <button
              type="button"
              className="text-sm text-primary hover:underline"
              onClick={() => connectChannel(platform)}
            >
              {t("notifications.reconnect")}
            </button>
          )}
          <span className="text-xs text-muted-foreground">
            {relativeTime(item.created_at)}
          </span>
        </div>
      </div>
    </div>
  )
}

export function NotificationBell() {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()
  const [data, setData] = useState<NotificationList | null>(null)
  const [open, setOpen] = useState(false)
  const relativeTime = useRelativeTime()

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await apiFetch("/api/v1/notifications", { toast: false })
      if (res.ok) setData(await res.json())
    } catch {
      // Polling must stay silent — the next tick retries.
    }
  }, [])

  // Poll while authenticated; the panel refetches on open.
  useEffect(() => {
    if (!isAuthenticated) return
    fetchNotifications()
    const id = window.setInterval(fetchNotifications, POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [isAuthenticated, fetchNotifications])

  // Opening the panel marks everything read (bell dot clears): fetch first so
  // the unread dots render, then read-all and refetch the server's truth
  // (real read_at timestamps, plus anything that arrived in between).
  useEffect(() => {
    if (!open || !isAuthenticated) return
    let cancelled = false
    fetchNotifications().then(async () => {
      await apiPost("/api/v1/notifications/read-all", {}, { toast: false })
      if (!cancelled) fetchNotifications()
    })
    return () => {
      cancelled = true
    }
  }, [open, isAuthenticated, fetchNotifications])

  if (!isAuthenticated) return null

  const unread = data?.unread_count ?? 0

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" className="relative">
            <Bell className="h-5 w-5" />
            {unread > 0 && (
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-destructive" />
            )}
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-96 p-0">
        <div className="px-4 pb-2 pt-3 text-sm font-semibold">
          {t("notifications.title")}
        </div>
        <div className="max-h-96 divide-y divide-border overflow-y-auto">
          {!data || data.items.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              {t("notifications.empty")}
            </p>
          ) : (
            data.items.map((item) => (
              <NotificationRow
                key={item.id}
                item={item}
                relativeTime={relativeTime}
                onAction={fetchNotifications}
              />
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
