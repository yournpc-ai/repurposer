"use client"

import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"

import { Card } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiGet, apiPut } from "@/lib/api"
import type { WorkspaceLayout } from "@/lib/canvasVisibility"
import { writeWorkspaceLayoutMirror } from "@/hooks/use-workspace-layout"

/** General section of the shared SettingsDialog: display-class prefs. The
 * workspace layout (ADR-123) is the canvas capability bit's second judgment
 * source — "chat" pins the chat-first workspace on every screen. The server
 * stores it for cross-device sync (nothing server-side consumes it — the
 * effective canvas_available is composed client-side, ADR-118); the
 * localStorage mirror (writeWorkspaceLayoutMirror) keeps the project's
 * first frame + first chat send correct, and this section resyncs the
 * mirror from the server value on mount (server wins). */

export function GeneralSection() {
  const { t } = useTranslation()
  const [layout, setLayout] = useState<WorkspaceLayout | null>(null)
  // Save in flight (2026-10-15 user ruling): the layout flip itself is
  // optimistic (the mirror morphs the workspace immediately), but the
  // control wears the PUT's pending state — spinner + disabled until the
  // server acks, rollback on failure.
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await apiGet("/api/v1/auth/settings", { toast: false })
        if (!res.ok) return
        const data = (await res.json()) as { workspace_layout?: string }
        const value: WorkspaceLayout =
          data.workspace_layout === "chat" ? "chat" : "auto"
        if (cancelled) return
        setLayout(value)
        // Server wins: resync the mirror so other devices' choices reach
        // this one.
        writeWorkspaceLayoutMirror(value)
      } catch {
        /* silent — the select stays disabled until the read lands */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const update = useCallback(
    async (value: WorkspaceLayout) => {
      const prev = layout
      if (prev === null || saving) return
      setLayout(value)
      writeWorkspaceLayoutMirror(value)
      setSaving(true)
      try {
        const res = await apiPut(
          "/api/v1/auth/settings",
          { workspace_layout: value },
          // A bare string is the SUCCESS toast's copy in apiFetch's
          // contract (errors still auto-toast the server detail) — the
          // custom error line rides the `{error}` seat, success stays
          // silent (动作反馈律).
          { toast: { error: t("general.updateFailed") } },
        )
        // Rollback on failure — the global toast already reported it.
        if (!res.ok) {
          setLayout(prev)
          writeWorkspaceLayoutMirror(prev)
        }
      } catch {
        // Network-level failure: apiFetch toasts then rethrows — the
        // optimistic flip rolls back too.
        setLayout(prev)
        writeWorkspaceLayoutMirror(prev)
      } finally {
        setSaving(false)
      }
    },
    [layout, saving, t],
  )

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("general.subtitle")}</p>
      <Card className="gap-0 px-4 py-2">
        <div className="flex items-center gap-3 py-2.5">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-foreground">
              {t("general.workspaceLayout.label")}
            </p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {t("general.workspaceLayout.desc")}
            </p>
          </div>
          <Select
            value={layout ?? "auto"}
            onValueChange={(v) => void update(v as WorkspaceLayout)}
            disabled={layout === null || saving}
          >
            <SelectTrigger
              aria-label={t("general.workspaceLayout.label")}
              className="h-8 flex-none gap-1.5 border-0 bg-muted px-2.5 text-xs hover:bg-accent dark:bg-muted dark:hover:bg-accent"
            >
              {saving && (
                <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
              )}
              <SelectValue />
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false} align="end">
              <SelectItem value="auto">
                {t("general.workspaceLayout.auto")}
              </SelectItem>
              <SelectItem value="chat">
                {t("general.workspaceLayout.chat")}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Card>
    </div>
  )
}
