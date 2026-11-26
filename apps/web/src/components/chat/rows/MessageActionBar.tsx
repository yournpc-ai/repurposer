"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Check, Copy, ThumbsDown, ThumbsUp } from "@/components/ui/icons"
import { motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Button } from "@/components/ui/button-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Popover } from "@/components/ui/popover-clean"
import { TextField } from "@/components/ui/text-field-clean"
import {
  FEEDBACK_TAGS,
  formatRelativeTime,
  submitMessageFeedback,
  type MessageFeedbackRating,
  type MessageFeedbackSummary,
} from "@/lib/workbench"
import { cn } from "@/lib/utils"

export interface MessageActionBarProps {
  messageId?: string
  text: string
  createdAt?: string
  feedback?: MessageFeedbackSummary | null
  onFeedbackChange?: (messageId: string, next: MessageFeedbackSummary | null) => void
  /** Hover-reveal mode (for substantive pre-QA checkpoint summaries): silent at rest,
   * surfaces on parent group hover / keyboard focus-visible, or while rated/open. */
  revealOnHover?: boolean
  /** Omit the trailing relative timestamp (e.g. "刚刚") on intermediate framing rows. */
  hideTimestamp?: boolean
  className?: string
}

export function MessageActionBar({
  messageId,
  text,
  createdAt,
  feedback: initialFeedback = null,
  onFeedbackChange,
  revealOnHover = false,
  hideTimestamp = false,
  className,
}: MessageActionBarProps) {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const [copied, setCopied] = useState(false)
  const copyTimerRef = useRef<number | null>(null)
  const [feedback, setFeedback] = useState<MessageFeedbackSummary | null>(initialFeedback)
  const [badPopoverOpen, setBadPopoverOpen] = useState(false)
  const [selectedTags, setSelectedTags] = useState<string[]>(initialFeedback?.tags ?? [])
  const [reason, setReason] = useState<string>(initialFeedback?.reason ?? "")
  const [submitting, setSubmitting] = useState(false)
  const [nowMs, setNowMs] = useState<number | null>(null)
  const badAnchorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setFeedback(initialFeedback)
    setSelectedTags(initialFeedback?.tags ?? [])
    setReason(initialFeedback?.reason ?? "")
  }, [initialFeedback])

  useEffect(() => {
    if (!createdAt) return
    setNowMs(Date.now())
    const timer = window.setInterval(() => {
      setNowMs(Date.now())
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [createdAt])

  useEffect(() => {
    return () => {
      if (copyTimerRef.current != null) window.clearTimeout(copyTimerRef.current)
    }
  }, [])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success(t("chat.feedback.copied"))
      if (copyTimerRef.current != null) window.clearTimeout(copyTimerRef.current)
      copyTimerRef.current = window.setTimeout(() => setCopied(false), 1800)
    } catch {
      toast.error(t("common.requestFailed"))
    }
  }, [text, t])

  const commitFeedback = useCallback(
    async (
      nextRating: MessageFeedbackRating | null,
      nextTags: string[] = [],
      nextReason: string | null = null,
      showSavedToast = false,
    ) => {
      if (!messageId) return
      const previous = feedback
      const optimistic: MessageFeedbackSummary | null = nextRating
        ? {
            rating: nextRating,
            tags: nextTags,
            reason: nextReason,
            updated_at: new Date().toISOString(),
          }
        : null
      setFeedback(optimistic)
      onFeedbackChange?.(messageId, optimistic)
      setSubmitting(true)
      try {
        const res = await submitMessageFeedback(messageId, {
          rating: nextRating,
          tags: nextRating ? nextTags : [],
          reason: nextRating ? nextReason : null,
        })
        setFeedback(res.feedback)
        onFeedbackChange?.(messageId, res.feedback)
        if (showSavedToast) {
          toast.success(t(nextRating ? "chat.feedback.saved" : "chat.feedback.cleared"))
        }
      } catch {
        setFeedback(previous)
        onFeedbackChange?.(messageId, previous)
        toast.error(t("chat.feedback.failed"))
      } finally {
        setSubmitting(false)
      }
    },
    [feedback, messageId, onFeedbackChange, t],
  )

  const handleGoodClick = useCallback(() => {
    setBadPopoverOpen(false)
    const nextRating: MessageFeedbackRating | null =
      feedback?.rating === "good" ? null : "good"
    setSelectedTags([])
    setReason("")
    void commitFeedback(nextRating, [], null, true)
  }, [commitFeedback, feedback?.rating])

  const handleBadClick = useCallback(() => {
    if (feedback?.rating === "bad") {
      setBadPopoverOpen(false)
      setSelectedTags([])
      setReason("")
      void commitFeedback(null, [], null, true)
      return
    }
    setSelectedTags([])
    setReason("")
    setBadPopoverOpen(true)
    void commitFeedback("bad", [], null, false)
  }, [commitFeedback, feedback?.rating])

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    )
  }

  const handleSubmitBadDetails = useCallback(() => {
    setBadPopoverOpen(false)
    void commitFeedback("bad", selectedTags, reason.trim() || null, true)
  }, [commitFeedback, reason, selectedTags])

  const relativeTime =
    !hideTimestamp && createdAt && nowMs != null ? formatRelativeTime(createdAt, t, nowMs) : ""
  const exactTime = createdAt ? (() => {
    const parsed = Date.parse(createdAt)
    return Number.isNaN(parsed) ? undefined : new Date(parsed).toLocaleString()
  })() : undefined
  const stayVisible = !revealOnHover || Boolean(feedback) || badPopoverOpen || copied

  const content = (
    <>
      <IconButton
        size="sm"
        variant="ghost"
        icon={copied ? <Check className="size-3.5 text-foreground" /> : <Copy className="size-3.5" />}
        label={copied ? t("chat.feedback.copied") : t("chat.feedback.copy")}
        onClick={() => { void handleCopy() }}
      />
      {messageId ? (
        <>
          <IconButton
            size="sm"
            variant="ghost"
            pressed={feedback?.rating === "good"}
            disabled={submitting}
            icon={<ThumbsUp className={cn("size-3.5", feedback?.rating === "good" && "text-foreground")} />}
            label={t("chat.feedback.good")}
            onClick={handleGoodClick}
          />
          <div ref={badAnchorRef} className="relative inline-flex">
            <IconButton
              size="sm"
              variant="ghost"
              pressed={feedback?.rating === "bad"}
              disabled={submitting}
              icon={<ThumbsDown className={cn("size-3.5", feedback?.rating === "bad" && "text-destructive")} />}
              label={t("chat.feedback.bad")}
              onClick={handleBadClick}
            />
            <Popover
              open={badPopoverOpen}
              onClose={() => setBadPopoverOpen(false)}
              anchor={badAnchorRef}
              side="top"
              align="start"
              width={300}
              title={t("chat.feedback.badTitle")}
              description={t("chat.feedback.badDescription")}
            >
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-1.5">
                  {FEEDBACK_TAGS.map((tag) => {
                    const active = selectedTags.includes(tag)
                    return (
                      <Button
                        key={tag}
                        size="sm"
                        variant={active ? "primary" : "secondary"}
                        onClick={() => toggleTag(tag)}
                      >
                        {t(`chat.feedback.tags.${tag}`)}
                      </Button>
                    )
                  })}
                </div>
                <TextField
                  size="sm"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={t("chat.feedback.reasonPlaceholder")}
                  aria-label={t("chat.feedback.reasonPlaceholder")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                      e.preventDefault()
                      handleSubmitBadDetails()
                    }
                  }}
                />
                <div className="flex items-center justify-end gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setBadPopoverOpen(false)}
                  >
                    {t("common.close")}
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    loading={submitting}
                    onClick={handleSubmitBadDetails}
                  >
                    {t("chat.feedback.submit")}
                  </Button>
                </div>
              </div>
            </Popover>
          </div>
        </>
      ) : null}
      {relativeTime ? (
        <span
          className="ml-1.5 select-none text-[11px] tabular-nums text-muted-foreground/75"
          title={exactTime}
        >
          {relativeTime}
        </span>
      ) : null}
    </>
  )

  // Never put motion `animate={{ opacity: 1 }}` on the same node as `opacity-0`
  // hover classes — Framer Motion writes inline `style="opacity: 1"` which
  // overrides Tailwind's `opacity-0` utility.
  if (revealOnHover) {
    return (
      <div
        data-slot="message-action-bar"
        data-reveal-mode="hover"
        className={cn(
          "mt-1.5 flex items-center gap-0.5 text-muted-foreground transition-opacity duration-150",
          !stayVisible &&
            "opacity-0 group-hover/msg:opacity-100 group-has-[:focus-visible]/msg:opacity-100",
          className,
        )}
      >
        {content}
      </div>
    )
  }

  return (
    <motion.div
      data-slot="message-action-bar"
      data-reveal-mode="always"
      initial={prefersReducedMotion ? false : { opacity: 0, y: 2 }}
      animate={{ opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "mt-1.5 flex items-center gap-0.5 text-muted-foreground",
        className,
      )}
    >
      {content}
    </motion.div>
  )
}
