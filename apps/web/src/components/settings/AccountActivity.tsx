import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiDelete, apiGet } from "@/lib/api"
import { Button } from "@/components/ui/button-clean"
import { Switch } from "@/components/ui/switch-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { useAccountSettings } from "./account-settings-context"

export function NotificationsSection() {
  const { t } = useTranslation()
  const { data, busy, save } = useAccountSettings()
  if (!data) return null
  if (!data.email_available) return <p className="settings-note">{t("settings.inboxOnly")}</p>
  return (
    <div className="settings-card settings-switch">
      <Switch
        placement="end"
        label={t("settings.emailAlerts")}
        description={t("settings.emailDetails")}
        checked={data.publish_alerts}
        disabled={busy}
        onChange={(e) => void save({ publish_alerts: e.target.checked })}
      />
    </div>
  )
}

type Session = { id: string; user_agent: string; last_seen_at: string; current: boolean }

function deviceName(agent: string) {
  const browser = [/Edg\//, /Firefox\//, /Chrome\//, /Safari\//].findIndex((pattern) =>
    pattern.test(agent),
  )
  const platform = [/iPhone/, /iPad/, /Android/, /Windows/, /Macintosh/, /Linux/].find((pattern) =>
    pattern.test(agent),
  )?.source
  return [
    ["Edge", "Firefox", "Chrome", "Safari"][browser],
    platform === "Macintosh" ? "macOS" : platform,
  ]
    .filter(Boolean)
    .join(" · ")
}

export function SessionsSection() {
  const { t, i18n } = useTranslation()
  const [sessions, setSessions] = useState<Session[]>([])
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading")
  const [revision, setRevision] = useState(0)
  const [pending, setPending] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    setStatus("loading")
    void (async () => {
      try {
        const res = await apiGet("/api/v1/auth/sessions", { toast: false })
        if (!res.ok) throw new Error()
        const rows: Session[] = await res.json()
        if (active) {
          setSessions(rows)
          setStatus("ready")
        }
      } catch {
        if (active) setStatus("error")
      }
    })()
    return () => {
      active = false
    }
  }, [revision])
  async function revoke(id: string) {
    setPending(id)
    try {
      const res = await apiDelete("/api/v1/auth/sessions/" + id)
      if (res.ok) setSessions((rows) => rows.filter((row) => row.id !== id))
    } catch {
      /* API client reports failures. */
    } finally {
      setPending(null)
    }
  }
  if (status === "loading") return <Spinner label={t("common.loading")} />
  if (status === "error")
    return (
      <Button size="sm" onClick={() => setRevision((n) => n + 1)}>
        {t("credits.retry")}
      </Button>
    )
  return (
    <ul className="settings-card">
      {sessions.map((s) => (
        <li key={s.id} className="settings-row">
          <div>
            <p>{deviceName(s.user_agent) || t("settings.device")}</p>
            <time className="text-xs text-muted-foreground" dateTime={s.last_seen_at}>
              {new Date(s.last_seen_at).toLocaleString(i18n.language)}
            </time>
          </div>
          {s.current ? (
            <span className="text-xs text-muted-foreground">{t("settings.currentDevice")}</span>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              disabled={pending !== null}
              onClick={() => void revoke(s.id)}
            >
              {t("common.logout")}
            </Button>
          )}
        </li>
      ))}
    </ul>
  )
}
