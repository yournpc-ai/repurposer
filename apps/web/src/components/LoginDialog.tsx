import { useEffect, useState } from "react"
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

const RESEND_COOLDOWN_SECONDS = 60

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
  const [countdown, setCountdown] = useState(0)

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setInterval(() => setCountdown((c) => c - 1), 1000)
    return () => clearInterval(timer)
  }, [countdown > 0])

  const reset = () => {
    setEmail("")
    setCode("")
    setStep("email")
    setError(null)
    setCountdown(0)
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
      setCountdown(RESEND_COOLDOWN_SECONDS)
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

  const resendDisabled = loading || countdown > 0 || !email.trim()
  const sendLabel =
    step === "email"
      ? t("login.sendCode")
      : countdown > 0
        ? t("login.resendIn", { count: countdown })
        : t("login.resendCode")

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
                onKeyDown={(e) => {
                  if (e.key === "Enter" && step === "email" && email.trim()) sendCode()
                }}
                disabled={loading || step === "code"}
              />
              <Button
                type="button"
                variant="outline"
                onClick={sendCode}
                disabled={resendDisabled}
              >
                {sendLabel}
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
                onKeyDown={(e) => {
                  if (e.key === "Enter" && code.length === 6) verifyCode()
                }}
                disabled={loading}
                autoFocus
              />
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        {step === "code" && (
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setStep("email")
                setCode("")
                setError(null)
              }}
              disabled={loading}
            >
              {t("login.back")}
            </Button>
            <Button
              type="button"
              onClick={verifyCode}
              disabled={loading || code.length !== 6}
            >
              {loading ? t("login.loading") : t("login.verifyAndLogin")}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
