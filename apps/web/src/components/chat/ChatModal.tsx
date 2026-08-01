/** ChatModal — the single conversational surface for refining an output (chat-loop-v2).
 *
 * One dialog per asset: history persists server-side (reopen = continue), a
 * run dispatched from a message renders as a RunCard (live via SSE, history
 * via the same snapshot path), and produced outputs inline as the same cards
 * the results page shows. Closing mid-run is safe — the run continues
 * server-side and the results page reflects it.
 */

import { useEffect, useState } from "react"
import { Send, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { LogoMark } from "@/components/LogoMark"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { Bubble, BubbleContent, BubbleGroup } from "@/components/ui/bubble"
import {
  Message,
  MessageContent,
} from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { apiFetch } from "@/lib/api"
import type { Output } from "@/lib/types"

import { MentionPicker, type ChatMention } from "./MentionPicker"
import { OpsCard } from "./OpsCard"
import { QaPair, qaAnswerText, type QaAnswer } from "./QaPair"
import { QuestionDock } from "./QuestionDock"
import { RunCard } from "./RunCard"

interface ChatModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  asset: Output | null
  assetType: "clip" | "derivative"
  projectId: string
  onUpdated?: () => void
}

interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string | null
  workflow_run_id: string | null
  mentions?: ChatMention[]
  question?: {
    kind: "task_book" | "choice" | "confirm"
    options?: { id: string; label: string }[]
    allow_freeform?: boolean
    cost_hint?: string | null
  } | null
  answer?: QaAnswer | null
  intent?: {
    type: string
    target_output_id?: string
    ops?: { op: string; params: Record<string, unknown> }[]
    summary?: string
  } | null
}

interface Conversation {
  id: string
  /** The latest unanswered question (dock rebuild source). */
  pending_question?: ChatMessage | null
}

const INTRO_ID = "intro"

export function ChatModal({
  open,
  onOpenChange,
  asset,
  assetType,
  projectId,
  onUpdated,
}: ChatModalProps) {
  const { t } = useTranslation()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const [input, setInput] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [isComposing, setIsComposing] = useState(false)
  // The docked pending question (ask primitive) — choice questions from the
  // chat loop dock above the input; answered ones archive as QA pairs.
  const [pendingQuestion, setPendingQuestion] = useState<ChatMessage | null>(null)
  const [answering, setAnswering] = useState(false)

  useEffect(() => {
    if (!open || !asset) return
    let cancelled = false
    setInput("")
    setIsSending(false)
    setIsLoadingHistory(true)
    setPendingQuestion(null)

    const intro: ChatMessage = {
      id: INTRO_ID,
      role: "assistant",
      content: t("chat.intro"),
      workflow_run_id: null,
    }

    const load = async () => {
      try {
        const params = new URLSearchParams({
          project_id: projectId,
          asset_id: asset.id,
          asset_type: assetType,
        })
        const res = await apiFetch(`/api/v1/chat/conversation?${params}`, {
          toast: false,
        })
        if (!res.ok) {
          if (!cancelled) setMessages([intro])
          return
        }
        const conversation = (await res.json()) as Conversation
        const messagesRes = await apiFetch(
          `/api/v1/chat/conversations/${conversation.id}/messages`,
          { toast: false },
        )
        if (!messagesRes.ok) throw new Error("Failed to load messages")
        const history = ((await messagesRes.json()) as { items: ChatMessage[] }).items
        if (cancelled) return
        setMessages([intro, ...history])
        // The dock rebuilds from the same row query on every open (refresh /
        // cross-device revival is free).
        if (
          conversation.pending_question &&
          conversation.pending_question.question &&
          !conversation.pending_question.answer
        ) {
          setPendingQuestion(conversation.pending_question)
        }
      } catch {
        if (!cancelled) setMessages([intro])
      } finally {
        if (!cancelled) setIsLoadingHistory(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [open, asset?.id, assetType, projectId, t])

  if (!asset) return null

  const assetTitle =
    assetType === "clip"
      ? asset.payload.hook
      : t(`chat.derivativeTypes.${asset.type}`)

  const handleSend = async () => {
    const instruction = input.trim()
    if (!instruction || isSending || !asset) return

    const optimisticUser: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: instruction,
      workflow_run_id: null,
      mentions,
    }
    setMessages((prev) => [...prev, optimisticUser])
    setInput("")
    setMentions([])
    setIsSending(true)

    try {
      const res = await apiFetch("/api/v1/chat", {
        method: "POST",
        body: {
          project_id: projectId,
          asset_id: asset.id,
          asset_type: assetType,
          message: instruction,
          mentions: optimisticUser.mentions,
        },
        toast: false,
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || "Chat failed")
      }
      const data = (await res.json()) as {
        user_message: ChatMessage
        assistant_message: ChatMessage
        answered_question?: ChatMessage | null
      }
      // Replace the optimistic user message with the persisted pair. An
      // autoResumed question archives its QA pair first; a NEW pending
      // question docks instead of entering the flow (prohibited #2).
      const next: ChatMessage[] = [data.user_message]
      if (data.answered_question) {
        setPendingQuestion(null)
        next.push(data.answered_question)
      }
      if (data.assistant_message.question && !data.assistant_message.answer) {
        setPendingQuestion(data.assistant_message)
      } else {
        next.push(data.assistant_message)
      }
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== optimisticUser.id),
        ...next,
      ])
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: e instanceof Error ? e.message : t("chat.failed"),
          workflow_run_id: null,
        },
      ])
    } finally {
      setIsSending(false)
    }
  }

  /** Docked choice question answered by a button click — the endpoint
   * records the answer and continues the conversation (answer = resume). */
  const handleChoiceAnswer = async (optionId: string) => {
    if (!pendingQuestion || answering) return
    setAnswering(true)
    try {
      const res = await apiFetch(
        `/api/v1/chat/messages/${pendingQuestion.id}/answer`,
        { method: "POST", body: { kind: "option", option_id: optionId } },
      )
      if (!res.ok) return // apiFetch already toasted the server's reason
      const data = (await res.json()) as {
        answered_question: ChatMessage
        follow_up: ChatMessage | null
      }
      setPendingQuestion(null)
      const next: ChatMessage[] = [data.answered_question]
      if (data.follow_up) {
        if (data.follow_up.question && !data.follow_up.answer) {
          setPendingQuestion(data.follow_up)
        } else {
          next.push(data.follow_up)
        }
      }
      setMessages((prev) => [...prev, ...next])
    } finally {
      setAnswering(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-2xl">
        <DialogHeader className="px-4 pb-2 pt-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <LogoMark className="h-5 w-5" />
            {t("chat.assetModalTitle", { asset: assetTitle })}
          </DialogTitle>
        </DialogHeader>

        <MessageScrollerProvider>
          <MessageScroller className="min-h-0 flex-1 px-4">
            <MessageScrollerViewport>
              <MessageScrollerContent className="gap-3 pb-2">
                {messages.map((m) => {
                  // Ask primitive: pending questions never render in the
                  // flow (they live in the dock); answered ones archive as
                  // QA pairs.
                  if (m.question && !m.answer) return null
                  if (m.question && m.answer) {
                    const display = qaAnswerText(m.answer, t, !!m.workflow_run_id)
                    return (
                      <MessageScrollerItem key={m.id}>
                        <QaPair
                          question={m.content ?? ""}
                          answer={display.text}
                          muted={display.muted}
                        />
                      </MessageScrollerItem>
                    )
                  }
                  const isUser = m.role === "user"
                  return (
                    <MessageScrollerItem key={m.id}>
                      <Message align={isUser ? "end" : "start"}>
                        <MessageContent className={isUser ? "items-end" : "items-start"}>
                          {m.content ? (
                            <BubbleGroup className={isUser ? "items-end" : "items-start"}>
                              <Bubble
                                variant={isUser ? "default" : "muted"}
                                align={isUser ? "end" : "start"}
                              >
                                <BubbleContent className="text-sm">{m.content}</BubbleContent>
                              </Bubble>
                            </BubbleGroup>
                          ) : null}
                          {isUser && m.mentions && m.mentions.length > 0 ? (
                            <div className="flex flex-wrap justify-end gap-1">
                              {m.mentions.map((mention) => (
                                <span
                                  key={mention.id}
                                  className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                                >
                                  @{mention.label}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          {m.workflow_run_id ? (
                            <RunCard
                              runId={m.workflow_run_id}
                              projectId={projectId}
                              onDone={() => onUpdated?.()}
                            />
                          ) : null}
                          {!isUser &&
                          m.intent?.type === "edit_ops" &&
                          m.intent.target_output_id ? (
                            <OpsCard
                              messageId={m.id}
                              intent={m.intent as never}
                              onDone={() => onUpdated?.()}
                            />
                          ) : null}
                        </MessageContent>
                      </Message>
                    </MessageScrollerItem>
                  )
                })}
                {(isLoadingHistory || isSending) && (
                  <MessageScrollerItem key="working">
                    <Message align="start">
                      <MessageContent className="items-start">
                        <BubbleGroup className="items-start">
                          <Bubble variant="muted" align="start">
                            <BubbleContent className="flex items-center gap-2 text-sm">
                              <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                              {isLoadingHistory ? t("chat.loadingHistory") : t("chat.thinking")}
                            </BubbleContent>
                          </Bubble>
                        </BubbleGroup>
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                )}
              </MessageScrollerContent>
            </MessageScrollerViewport>
          </MessageScroller>
        </MessageScrollerProvider>

        <div className="flex flex-col gap-2 p-4 pt-2">
          {pendingQuestion ? (
            <QuestionDock
              kind="choice"
              question={pendingQuestion.content ?? ""}
              options={pendingQuestion.question?.options ?? []}
              costHint={pendingQuestion.question?.cost_hint}
              onAnswer={handleChoiceAnswer}
              answering={answering}
            />
          ) : null}
          {mentions.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {mentions.map((mention) => (
                <span
                  key={mention.id}
                  className="flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
                >
                  @{mention.label}
                  <button
                    type="button"
                    aria-label={t("chat.mentionRemove")}
                    onClick={() =>
                      setMentions((prev) => prev.filter((m) => m.id !== mention.id))
                    }
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            <MentionPicker
              projectId={projectId}
              excludeIds={mentions.map((m) => m.id)}
              onSelect={(mention) => setMentions((prev) => [...prev, mention])}
            />
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onCompositionStart={() => setIsComposing(true)}
              onCompositionEnd={() => setIsComposing(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !isComposing) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder={
                pendingQuestion &&
                (pendingQuestion.question?.options?.length ?? 0) > 0 &&
                pendingQuestion.question?.allow_freeform !== false
                  ? t("chat.choicePlaceholder")
                  : t("chat.assetPlaceholder")
              }
              rows={1}
              className="max-h-32 min-h-9 flex-1 resize-none"
            />
            <Button
              size="icon"
              className="h-9 w-9 shrink-0 rounded-full"
              disabled={!input.trim() || isSending}
              onClick={handleSend}
              aria-label={t("chat.send")}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
