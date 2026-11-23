import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/lib/auth-context"
import type { AuthUser } from "@/lib/auth"
import { apiGet, apiPut } from "@/lib/api"
import { Button } from "@/components/ui/button-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { Avatar } from "@/components/ui/avatar-clean"
import { Info } from "lucide-react"

export function ProfileSection() {
  const { t } = useTranslation()
  const { user, updateUser } = useAuth()
  const [draft, setDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const latest = useRef(updateUser)
  latest.current = updateUser
  const edits = useRef(0)
  useEffect(() => {
    let active = true
    const version = edits.current
    void apiGet("/api/v1/auth/profile", { toast: false })
      .then(async (res) => {
        if (!res.ok) return
        const profile: AuthUser = await res.json()
        if (active && version === edits.current) latest.current(profile)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [user?.id])
  const name = draft ?? user?.name ?? ""
  async function saveName() {
    if (!name.trim() || saving) return
    edits.current++
    setSaving(true)
    try {
      const res = await apiPut("/api/v1/auth/profile", { name: name.trim() })
      if (res.ok) {
        updateUser(await res.json())
        setDraft(null)
      }
    } catch {
      /* apiPut reports the error and the draft stays editable. */
    } finally {
      setSaving(false)
    }
  }
  return (
    <>
      <p className="settings-note">
        <Info size={15} aria-hidden />
        {t("settings.profileNote")}
      </p>
      <div className="settings-card">
        <div className="settings-row">
          <span>{t("settings.avatar")}</span>
          <Avatar size={40} name={user?.name || user?.email} />
        </div>
        <form
          className="settings-row"
          onSubmit={(e) => {
            e.preventDefault()
            void saveName()
          }}
        >
          <label htmlFor="settings-name">{t("settings.name")}</label>
          <div className="flex min-w-0 items-center gap-2">
            <TextField
              id="settings-name"
              autoComplete="nickname"
              maxLength={80}
              size="sm"
              className="settings-field"
              value={name}
              disabled={saving}
              onChange={(e) => setDraft(e.target.value)}
            />
            {draft !== null && name.trim() !== user?.name && (
              <Button type="submit" size="sm" disabled={!name.trim() || saving}>
                {t(saving ? "common.saving" : "common.save")}
              </Button>
            )}
          </div>
        </form>
        <div className="settings-row">
          <span>{t("settings.email")}</span>
          <TextField
            aria-label={t("settings.email")}
            className="settings-field"
            size="sm"
            value={user?.email ?? ""}
            readOnly
          />
        </div>
      </div>
    </>
  )
}
