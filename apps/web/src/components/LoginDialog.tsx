import { useEffect, useId, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { toast } from "sonner"
import { ArrowLeft, ArrowRight, X } from "@/components/ui/icons"

import { LogoMark } from "@/components/LogoMark"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { OtpInput } from "@/components/ui/otp-input-clean"
import { TextField } from "@/components/ui/text-field-clean"

import { apiPost, errorDetail } from "@/lib/api"
import { setAuth } from "@/lib/auth"

const CODE_LENGTH = 6
const RESEND_COOLDOWN_SECONDS = 60

interface LoginDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

export function LoginDialog({ open, onOpenChange, onSuccess }: LoginDialogProps) {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [step, setStep] = useState<"email" | "code">("email")
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [loading, setLoading] = useState<"send" | "verify" | null>(null)
  const [code, setCode] = useState("")
  const descriptionId = useId()
  const reduceMotion = useReducedMotion()
  const [resendAt, setResendAt] = useState(0)
  const [now, setNow] = useState(0)
  const countdown = Math.max(0, Math.ceil((resendAt - now) / 1000))
  const [attempt, setAttempt] = useState(0)
  const pending = useRef<AbortController | null>(null)
  const sentToThisEmail = sentTo !== null && sentTo === email.trim()

  useEffect(() => () => pending.current?.abort(), [])
  useEffect(() => {
    if (!resendAt) return
    const timer = setInterval(() => {
      const time = Date.now()
      setNow(time)
      if (time >= resendAt) setResendAt(0)
    }, 1000)
    return () => clearInterval(timer)
  }, [resendAt])

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      pending.current?.abort()
      pending.current = null
      setEmail("")
      setStep("email")
      setSentTo(null)
      setCode("")
      setResendAt(0)
      setLoading(null)
    }
    onOpenChange(next)
  }

  const sendCode = async () => {
    const address = email.trim()
    if (!address || pending.current) return
    const request = new AbortController()
    pending.current = request
    setLoading("send")
    try {
      const res = await apiPost(
        "/api/v1/auth/send-code",
        { email: address },
        { toast: false, signal: request.signal },
      )
      if (!res.ok) {
        const message = errorDetail(await res.json().catch(() => null), t("login.sendFailed"))
        if (!request.signal.aborted) toast.error(message)
        return
      }
      if (request.signal.aborted) return
      setSentTo(address)
      setStep("code")
      setCode("")
      setAttempt((n) => n + 1)
      const time = Date.now()
      setNow(time)
      setResendAt(time + RESEND_COOLDOWN_SECONDS * 1000)
    } catch {
      if (!request.signal.aborted) toast.error(t("common.networkError"))
    } finally {
      if (pending.current === request) {
        pending.current = null
        setLoading(null)
      }
    }
  }

  const verify = async (code: string) => {
    if (code.length !== CODE_LENGTH || !sentTo || pending.current) return
    const request = new AbortController()
    pending.current = request
    setLoading("verify")
    try {
      const res = await apiPost(
        "/api/v1/auth/verify-code",
        { email: sentTo, code },
        { toast: false, signal: request.signal },
      )
      if (!res.ok) {
        const message = errorDetail(await res.json().catch(() => null), t("login.verifyFailed"))
        if (!request.signal.aborted) {
          toast.error(message)
          setCode("")
          setAttempt((n) => n + 1)
        }
        return
      }
      const data = await res.json()
      if (request.signal.aborted) return
      setAuth(data.token, data.user)
      handleOpenChange(false)
      onSuccess?.()
    } catch {
      if (!request.signal.aborted) toast.error(t("common.networkError"))
    } finally {
      if (pending.current === request) {
        pending.current = null
        setLoading(null)
      }
    }
  }

  const resend = sentToThisEmail && (
    <p className="text-center text-sm text-muted-foreground">
      {t("login.didntReceive")}{" "}
      {countdown > 0 ? (
        <span className="tabular-nums">{t("login.resendIn", { count: countdown })}</span>
      ) : (
        <button type="button" className="rounded-md font-medium text-foreground" disabled={loading !== null} onClick={sendCode}>
          {t(loading === "send" ? "login.sending" : "login.resendCode")}
        </button>
      )}
    </p>
  )

  const isEmail = step === "email"
  const title = t(isEmail ? "login.title" : "login.codeTitle")
  const complete = code.length === CODE_LENGTH

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
      fullscreen
      className="login-modal"
      title={title}
      aria-describedby={descriptionId}
    >
      <div className="overlay-surface relative max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-sm overflow-y-auto rounded-xl border border-subtle p-4 text-foreground">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={step}
            initial={{ opacity: 0, y: reduceMotion ? 0 : 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: reduceMotion ? 0 : -10 }}
            transition={{ duration: reduceMotion ? 0 : 0.2 }}
            className={isEmail ? "flex flex-col items-start" : "flex flex-col items-center text-center"}
          >
            <LogoMark className="size-10" />
            <h2 className="mt-5 text-xl font-semibold tracking-tight">{title}</h2>
            <p id={descriptionId} className="mt-2 text-sm leading-relaxed wrap-anywhere text-muted-foreground">
              {isEmail ? t("login.subtitle") : (
                <Trans
                  i18nKey="login.codeSubtitle"
                  values={{ email: sentTo }}
                  components={{ b: <span className="font-medium text-foreground" /> }}
                />
              )}
            </p>
            {isEmail ? (
              <form
                className="mt-6 grid w-full gap-4"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (sentToThisEmail) setStep("code")
                  else void sendCode()
                }}
              >
                <TextField
                  label={t("login.emailLabel")}
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  autoFocus
                  data-autofocus
                  placeholder={t("login.emailPlaceholder")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading !== null}
                />
                <Button
                  type="submit"
                  size="lg"
                  loading={loading === "send"}
                  iconRight={sentToThisEmail ? <ArrowRight size={16} /> : undefined}
                  disabled={!email.trim() || loading !== null}
                >
                  {t(loading === "send" ? "login.sending" : sentToThisEmail ? "login.enterCode" : "login.sendCode")}
                </Button>
                {resend}
              </form>
            ) : (
              <>
                <form
                  className="mt-7 grid w-full gap-7"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void verify(code)
                  }}
                >
                  <OtpInput
                    key={attempt}
                    value={code}
                    onChange={setCode}
                    onComplete={verify}
                    length={CODE_LENGTH}
                    inputLabel={t("login.codeLabel")}
                    verifyingLabel={t("login.verifying")}
                    separator
                    align="center"
                    autoFocus
                    resendIn={0}
                    disabled={loading === "send"}
                    status={loading === "verify" ? "verifying" : "idle"}
                  />
                  <Button type="submit" size="lg" loading={loading === "verify"} disabled={!complete || loading !== null}>
                    {t(loading === "verify" ? "login.verifying" : complete ? "login.verifyAndLogin" : "login.enterAllDigits")}
                  </Button>
                </form>
                <div className="mt-5">{resend}</div>
                <div className="mt-8">
                  <Button
                    variant="ghost"
                    icon={<ArrowLeft size={16} />}
                    disabled={loading !== null}
                    onClick={() => {
                      setCode("")
                      setStep("email")
                    }}
                  >
                    {t("login.backToSignIn")}
                  </Button>
                </div>
              </>
            )}
          </motion.div>
        </AnimatePresence>
        <div className="absolute end-2 top-2">
          <IconButton label={t("common.close")} icon={<X size={16} />} onClick={() => handleOpenChange(false)} />
        </div>
      </div>
    </Dialog>
  )
}
