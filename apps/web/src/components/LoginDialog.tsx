import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiPost, errorDetail } from "@/lib/api"
import { setAuth } from "@/lib/auth"

interface LoginDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

export function LoginDialog({ open, onOpenChange, onSuccess }: LoginDialogProps) {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [step, setStep] = useState<"email" | "code">("email")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setEmail("")
    setCode("")
    setStep("email")
    setError(null)
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  const sendCode = async () => {
    if (!email.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await apiPost("/api/v1/auth/send-code", { email: email.trim() })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(errorDetail(body, t("login.sendFailed")))
      }
      setStep("code")
    } catch (e) {
      setError(e instanceof Error ? e.message : t("login.sendFailed"))
    } finally {
      setLoading(false)
    }
  }

  const verifyCode = async () => {
    if (!code.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await apiPost("/api/v1/auth/verify-code", {
        email: email.trim(),
        code: code.trim(),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(errorDetail(body, t("login.verifyFailed")))
      }
      const data = await res.json()
      setAuth(data.token, data.user)
      handleOpenChange(false)
      onSuccess?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : t("login.verifyFailed"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("login.title")}</DialogTitle>
          <DialogDescription>{t("login.subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="login-email">{t("login.emailLabel")}</Label>
            <div className="flex gap-2">
              <Input
                id="login-email"
                type="email"
                placeholder={t("login.emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading || step === "code"}
              />
              <Button
                type="button"
                variant="outline"
                onClick={sendCode}
                disabled={loading || step === "code" || !email.trim()}
              >
                {step === "code" ? t("login.codeSent") : t("login.sendCode")}
              </Button>
            </div>
          </div>

          {step === "code" && (
            <div className="space-y-2">
              <Label htmlFor="login-code">{t("login.codeLabel")}</Label>
              <Input
                id="login-code"
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder={t("login.codePlaceholder")}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                disabled={loading}
              />
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-2">
          {step === "code" && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => setStep("email")}
              disabled={loading}
            >
              {t("login.back")}
            </Button>
          )}
          <Button
            type="button"
            onClick={step === "email" ? sendCode : verifyCode}
            disabled={loading || (step === "email" ? !email.trim() : code.length !== 6)}
          >
            {loading
              ? t("login.loading")
              : step === "email"
                ? t("login.sendCode")
                : t("login.verifyAndLogin")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
