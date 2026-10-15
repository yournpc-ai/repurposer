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

/** Assistant section of the shared SettingsDialog (ADR-117 §1): the two
 * confirmation prefs — execution (wait for a confirm beat before starting
 * paid work) and credits (one priced confirmation before a paid plan
 * starts), both defaulting to auto. The section is the prefs' ONLY UI seat
 * (composer / dock control strips never carry them); the server reads them
 * fresh per turn, so a change takes effect in the same session with no
 * client broadcast. The internal guardrail is an ops parameter — the
 * footnote's honesty line is its only user-facing mention. */

type ConfirmMode = "auto" | "ask"
type ConfirmKey = "confirm_execution" | "confirm_credits"

interface ConfirmationPrefs {
  confirm_execution: ConfirmMode
  confirm_credits: ConfirmMode
}

export function AssistantSection() {
  const { t } = useTranslation()
  const [prefs, setPrefs] = useState<ConfirmationPrefs | null>(null)
  // Save in flight, per row (2026-10-15 user ruling — GeneralSection 同款
  // 体感): the flip is optimistic, but the control wears the PUT's pending
  // state — spinner + disabled until the server acks, rollback on failure.
  const [saving, setSaving] = useState<ConfirmKey | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await apiGet("/api/v1/auth/settings", { toast: false })
        if (!res.ok) return
        if (!cancelled) setPrefs((await res.json()) as ConfirmationPrefs)
      } catch {
        /* silent — the selects stay disabled until the read lands */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const update = useCallback(
    async (key: ConfirmKey, value: ConfirmMode) => {
      const prev = prefs
      if (prev === null || saving !== null) return
      setPrefs({ ...prev, [key]: value })
      setSaving(key)
      try {
        const res = await apiPut(
          "/api/v1/auth/settings",
          { [key]: value },
          // A bare string is the SUCCESS toast's copy in apiFetch's
          // contract (errors still auto-toast the server detail) — the
          // custom error line rides the `{error}` seat, success stays
          // silent (动作反馈律).
          { toast: { error: t("assistant.updateFailed") } },
        )
        // Rollback on failure — the global toast already reported it.
        if (!res.ok) setPrefs(prev)
      } catch {
        // Network-level failure: apiFetch toasts then rethrows — the
        // optimistic flip rolls back too.
        setPrefs(prev)
      } finally {
        setSaving(null)
      }
    },
    [prefs, saving, t],
  )

  const prefRow = (
    key: ConfirmKey,
    labelKey: string,
    descKey: string,
    last: boolean,
  ) => (
    <div
      className={
        "flex items-center gap-3 py-2.5" +
        (last ? "" : " border-b border-foreground/5")
      }
    >
      <div className="min-w-0 flex-1">
        <p className="text-xs text-foreground">{t(labelKey)}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {t(descKey)}
        </p>
      </div>
      <Select
        value={prefs?.[key] ?? "auto"}
        onValueChange={(v) => void update(key, v as ConfirmMode)}
        disabled={prefs === null || saving !== null}
      >
        <SelectTrigger
          aria-label={t(labelKey)}
          className="h-8 flex-none gap-1.5 border-0 bg-muted px-2.5 text-xs hover:bg-accent dark:bg-muted dark:hover:bg-accent"
        >
          {saving === key && (
            <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
          )}
          <SelectValue />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false} align="end">
          <SelectItem value="auto">{t("assistant.mode.auto")}</SelectItem>
          <SelectItem value="ask">{t("assistant.mode.ask")}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("assistant.subtitle")}</p>
      <Card className="gap-0 px-4 py-2">
        <p className="pb-1 pt-2 text-[11px] text-meta">
          {t("assistant.permissions")}
        </p>
        {prefRow("confirm_execution", "assistant.execution.label", "assistant.execution.desc", false)}
        {prefRow("confirm_credits", "assistant.spending.label", "assistant.spending.desc", true)}
        <p className="border-t border-foreground/5 py-2.5 text-[11px] leading-relaxed text-meta">
          {t("assistant.footnote")}
        </p>
      </Card>
    </div>
  )
}
