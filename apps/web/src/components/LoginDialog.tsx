import { useEffect, useRef, useState } from "react"
import type {
  ChangeEvent,
  ClipboardEvent,
  KeyboardEvent,
} from "react"
import { Trans, useTranslation } from "react-i18next"
import { ArrowLeft, ArrowRight } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import type { Variants } from "motion/react"

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
import { LogoMark } from "@/components/LogoMark"
import { apiPost, errorDetail } from "@/lib/api"
import { setAuth } from "@/lib/auth"
import { cn } from "@/lib/utils"

const RESEND_COOLDOWN_SECONDS = 60
const CODE_LENGTH = 6
const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1]

interface LoginDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

/** Two-step passwordless login inside one dialog: email → 6-digit code.
 * Steps swap via AnimatePresence; the code step auto-submits on the 6th
 * digit and clears itself on a failed verify. */
export function LoginDialog({ open, onOpenChange, onSuccess }: LoginDialogProps) {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(""))
  const [step, setStep] = useState<"email" | "code">("email")
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [loading, setLoading] = useState<"send" | "verify" | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [countdown, setCountdown] = useState(0)
  const inputsRef = useRef<Array<HTMLInputElement | null>>([])
  const reduce = useReducedMotion()

  const isComplete = digits.every(Boolean)
  // A code is "in flight" for the address currently in the input. Editing the
  // email reverts the page to the fresh "Email me a code" state on its own.
  const sentToThisEmail = sentTo !== null && sentTo === email.trim()

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setInterval(() => setCountdown((c) => c - 1), 1000)
    return () => clearInterval(timer)
  }, [countdown > 0])

  const reset = () => {
    setEmail("")
    setDigits(Array(CODE_LENGTH).fill(""))
    setStep("email")
    setSentTo(null)
    setError(null)
    setCountdown(0)
    setLoading(null)
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  const focusInput = (index: number) => {
    inputsRef.current[index]?.focus()
  }

  const sendCode = async () => {
    if (!email.trim() || loading) return
    setLoading("send")
    setError(null)
    try {
      const res = await apiPost(
        "/api/v1/auth/send-code",
        { email: email.trim() },
        // Errors render inline inside the dialog; suppress the global toast.
        { toast: false }
      )
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(errorDetail(body, t("login.sendFailed")))
      }
      setDigits(Array(CODE_LENGTH).fill(""))
      setSentTo(email.trim())
      setStep("code")
      setCountdown(RESEND_COOLDOWN_SECONDS)
    } catch (e) {
      setError(e instanceof Error ? e.message : t("login.sendFailed"))
    } finally {
      setLoading(null)
    }
  }

  const verify = async (value: string) => {
    if (value.length !== CODE_LENGTH || loading) return
    setLoading("verify")
    setError(null)
    try {
      const res = await apiPost(
        "/api/v1/auth/verify-code",
        { email: email.trim(), code: value },
        { toast: false }
      )
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
      // Wrong code: start over on digit 1. The focus is deferred a tick so
      // the input has been re-enabled (loading cleared in finally) first.
      setDigits(Array(CODE_LENGTH).fill(""))
      setTimeout(() => focusInput(0), 0)
    } finally {
      setLoading(null)
    }
  }

  const handleDigitChange = (index: number, event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value.replace(/\D/g, "").slice(-1)
    const next = [...digits]
    next[index] = value
    setDigits(next)
    if (value && index < CODE_LENGTH - 1) focusInput(index + 1)
    if (next.every(Boolean)) verify(next.join(""))
  }

  const handleDigitKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      focusInput(index - 1)
    }
    if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault()
      focusInput(index - 1)
    }
    if (event.key === "ArrowRight" && index < CODE_LENGTH - 1) {
      event.preventDefault()
      focusInput(index + 1)
    }
  }

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault()
    const pasted = event.clipboardData
      .getData("text")
      .replace(/\D/g, "")
      .slice(0, CODE_LENGTH)
    if (!pasted) return
    const next = Array(CODE_LENGTH)
      .fill("")
      .map((_, index) => pasted[index] ?? "")
    setDigits(next)
    if (next.every(Boolean)) verify(next.join(""))
    else focusInput(Math.min(pasted.length, CODE_LENGTH - 1))
  }

  const handleResend = async () => {
    await sendCode()
    focusInput(0)
  }

  const goBackToEmail = () => {
    setStep("email")
    setDigits(Array(CODE_LENGTH).fill(""))
    setError(null)
  }

  const swap: Variants = {
    initial: { opacity: 0, y: reduce ? 0 : 10 },
    animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE } },
    exit: { opacity: 0, y: reduce ? 0 : -10, transition: { duration: 0.2, ease: EASE } },
  }

  const digitContainer: Variants = {
    animate: { transition: { staggerChildren: 0.05, delayChildren: 0.15 } },
  }

  const digitItem: Variants = {
    initial: { opacity: 0, y: reduce ? 0 : 8 },
    animate: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE } },
  }

  const renderDigit = (index: number) => (
    <motion.div key={index} variants={digitItem}>
      <input
        ref={(el) => {
          inputsRef.current[index] = el
        }}
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={1}
        autoComplete={index === 0 ? "one-time-code" : "off"}
        autoFocus={index === 0}
        value={digits[index]}
        onChange={(e) => handleDigitChange(index, e)}
        onKeyDown={(e) => handleDigitKeyDown(index, e)}
        onPaste={handlePaste}
        onFocus={(e) => e.target.select()}
        disabled={loading !== null}
        aria-label={t("login.digitLabel", { index: index + 1, total: CODE_LENGTH })}
        className={cn(
          "h-12 w-10 rounded-md border bg-background text-center text-lg font-semibold tabular-nums text-foreground outline-none transition-colors focus:border-foreground focus:ring-4 focus:ring-foreground/10 sm:w-11",
          digits[index]
            ? "border-foreground"
            : "border-input hover:border-muted-foreground/50"
        )}
      />
    </motion.div>
  )

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader className="sr-only">
          <DialogTitle>{t("login.title")}</DialogTitle>
          <DialogDescription>{t("login.subtitle")}</DialogDescription>
        </DialogHeader>

        <AnimatePresence mode="wait" initial={false}>
          {step === "email" ? (
            <motion.div
              key="email"
              variants={swap}
              initial="initial"
              animate="animate"
              exit="exit"
              className="flex flex-col justify-center"
            >
              <LogoMark className="h-10 w-10" />
              <h2 className="mt-5 text-xl font-semibold tracking-tight">
                {t("login.title")}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {t("login.subtitle")}
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (sentToThisEmail) setStep("code")
                  else sendCode()
                }}
                className="mt-6"
              >
                <Label htmlFor="login-email" className="mb-1.5 block">
                  {t("login.emailLabel")}
                </Label>
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  autoFocus
                  placeholder={t("login.emailPlaceholder")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading !== null}
                />
                <Button
                  type="submit"
                  className="mt-4 h-11 w-full"
                  disabled={!email.trim() || loading !== null}
                >
                  {loading === "send" ? (
                    t("login.sending")
                  ) : sentToThisEmail ? (
                    <>
                      {t("login.enterCode")}
                      <ArrowRight className="h-4 w-4" />
                    </>
                  ) : (
                    t("login.sendCode")
                  )}
                </Button>
                {sentToThisEmail && (
                  <p
                    className="mt-4 text-center text-sm text-muted-foreground"
                    aria-live="polite"
                  >
                    {t("login.didntReceive")}{" "}
                    {countdown > 0 ? (
                      <span className="tabular-nums">
                        {t("login.resendIn", { count: countdown })}
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={handleResend}
                        className="rounded-md font-medium text-foreground transition-colors hover:text-muted-foreground"
                      >
                        {t("login.resendCode")}
                      </button>
                    )}
                  </p>
                )}
              </form>
              {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
            </motion.div>
          ) : (
            <motion.div
              key="code"
              variants={swap}
              initial="initial"
              animate="animate"
              exit="exit"
              className="flex flex-col items-center justify-center text-center"
            >
              <LogoMark className="h-10 w-10" />
              <h2 className="mt-5 text-xl font-semibold tracking-tight">
                {t("login.codeTitle")}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                <Trans
                  i18nKey="login.codeSubtitle"
                  values={{ email }}
                  components={{
                    b: <span className="font-medium text-foreground" />,
                  }}
                />
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  verify(digits.join(""))
                }}
                className="mt-7 w-full"
              >
                <motion.div
                  variants={digitContainer}
                  className="flex items-center justify-center gap-1.5 sm:gap-2"
                >
                  {[0, 1, 2].map(renderDigit)}
                  <span className="h-px w-3 shrink-0 bg-border" aria-hidden="true" />
                  {[3, 4, 5].map(renderDigit)}
                </motion.div>
                <Button
                  type="submit"
                  className="mt-7 h-11 w-full"
                  disabled={!isComplete || loading !== null}
                >
                  {loading === "verify"
                    ? t("login.verifying")
                    : isComplete
                      ? t("login.verifyAndLogin")
                      : t("login.enterAllDigits")}
                </Button>
              </form>
              {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
              <p className="mt-5 text-sm text-muted-foreground" aria-live="polite">
                {t("login.didntReceive")}{" "}
                {countdown > 0 ? (
                  <span className="tabular-nums">
                    {t("login.resendIn", { count: countdown })}
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={handleResend}
                    className="rounded-md font-medium text-foreground transition-colors hover:text-muted-foreground"
                  >
                    {t("login.resendCode")}
                  </button>
                )}
              </p>
              <button
                type="button"
                onClick={goBackToEmail}
                className="mt-8 inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                <ArrowLeft className="h-4 w-4" />
                {t("login.backToSignIn")}
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  )
}
