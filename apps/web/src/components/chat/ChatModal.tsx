/** ChatModal — the single conversational surface for refining an output (chat-loop-v2).
 *
 * One dialog per asset: history persists server-side (reopen = continue), a
 * run dispatched from a message renders as a RunCard (live via SSE, history
 * via the same snapshot path), and produced outputs inline as the same cards
 * the results page shows. Closing mid-run is safe — the run continues
 * server-side and the results page reflects it.
 */

import { useEffect, useMemo, useRef, useState } from "react"
import { Send, Square } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { LogoMark } from "@/components/LogoMark"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"
import { Bubble, BubbleContent, BubbleGroup } from "@/components/ui/bubble"
import {
  Message,
  MessageContent,
} from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { apiFetch } from "@/lib/api"
import { streamChat } from "@/lib/chat-stream"
import { createTypewriter } from "@/lib/typewriter"
import {
  assetTypeKind,
  outputMentionLabel,
  type ChatMention,
  type MentionContext,
} from "@/lib/mentions"
import type { Output } from "@/lib/types"
import { Streamdown } from "streamdown"

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
  /** Live SSE preview bubble — replaced by the turn.completed envelope. */
  streaming?: boolean
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
  // The docked pending question (ask primitive) — choice questions from the
  // chat loop dock above the input; answered ones archive as QA pairs.
  const [pendingQuestion, setPendingQuestion] = useState<ChatMessage | null>(null)
  const [answering, setAnswering] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const editorRef = useRef<MentionEditorHandle>(null)

  // The mention feeds (registry sources read these live): the project's
  // outputs (reference family — the pinned id resolves the revision target
  // server-side) + its settled assets (context enrichment).
  const [outputs, setOutputs] = useState<Output[]>([])
  const [assets, setAssets] = useState<{ title: string | null; type: string }[]>([])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    Promise.all([
      apiFetch(`/api/v1/projects/${projectId}/results`, { toast: false }),
      apiFetch(`/api/v1/projects/${projectId}/assets`, { toast: false }),
    ])
      .then(async ([resultsRes, assetsRes]) => {
        if (cancelled) return
        if (resultsRes.ok) {
          const data = (await resultsRes.json()) as { outputs?: Output[] }
          setOutputs(data.outputs ?? [])
        }
        if (assetsRes.ok) {
          setAssets((await assetsRes.json()) as { title: string | null; type: string }[])
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [open, projectId])

  const mentionContext = useMemo<MentionContext>(
    () => ({
      assets: assets
        .filter((a) => a.title)
        .map((a) => ({ name: a.title as string, kind: assetTypeKind(a.type) })),
      outputs: outputs.map((o) => ({
        id: o.id,
        label: outputMentionLabel(o, t(`chat.derivativeTypes.${o.type}`)),
        kind: o.type,
      })),
    }),
    [assets, outputs, t],
  )

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
    // Consumed on send (chip law ②) — the editor's clear funnels the emptied
    // {text, mentions} back through onChange, so no separate state resets.
    editorRef.current?.clear()
    setIsSending(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl
    // SSE transport: prose deltas feed a typewriter-paced preview bubble
    // (reasoning models emit short replies in one burst — pacing keeps the
    // "written live" feel); the terminal turn.completed envelope is
    // authoritative and finalizes the preview IN PLACE (same key, no
    // remount — the settled message must not flicker).
    const streamId = crypto.randomUUID()
    let streamedAny = false
    const appendDelta = (delta: string) => {
      streamedAny = true
      setMessages((prev) =>
        prev.some((m) => m.id === streamId)
          ? prev.map((m) =>
              m.id === streamId
                ? { ...m, content: (m.content ?? "") + delta }
                : m
            )
          : [
              ...prev,
              {
                id: streamId,
                role: "assistant" as const,
                content: delta,
                workflow_run_id: null,
                streaming: true,
              },
            ]
      )
    }
    const typewriter = createTypewriter(appendDelta)
    try {
      const data = await streamChat<{
        user_message: ChatMessage
        assistant_message: ChatMessage
        answered_question?: ChatMessage | null
      }>(
        {
          project_id: projectId,
          asset_id: asset.id,
          asset_type: assetType,
          message: instruction,
          mentions: optimisticUser.mentions,
        },
        {
          signal: ctrl.signal,
          onDelta: (delta) => typewriter.push(delta),
        }
      )
      typewriter.flush()
      // Envelope wins — swap the optimistic/preview bubbles for the
      // persisted messages under their EXISTING keys (no remount flicker).
      const assistant = data.assistant_message
      const assistantDocks = !!(assistant.question && !assistant.answer)
      if (data.answered_question) setPendingQuestion(null)
      if (assistantDocks) setPendingQuestion(assistant)
      setMessages((prev) => {
        const out: ChatMessage[] = []
        for (const m of prev) {
          if (m.id === optimisticUser.id) {
            out.push({ ...data.user_message, id: m.id })
            // An autoResumed question archives its QA pair right after the
            // message that answered it.
            if (data.answered_question) out.push(data.answered_question)
            continue
          }
          if (m.id === streamId) {
            // A docked question never enters the flow — drop the preview;
            // anything else settles in place under the preview's key.
            if (!assistantDocks) out.push({ ...assistant, id: m.id, streaming: false })
            continue
          }
          out.push(m)
        }
        if (!streamedAny) {
          if (data.answered_question && !prev.some((m) => m.id === optimisticUser.id)) {
            out.push(data.answered_question)
          }
          if (!assistantDocks) out.push(assistant)
        }
        return out
      })
    } catch (e) {
      typewriter.flush()
      // Stopped by the user: the bubble stays (the server may still finish
      // the turn); the partial preview settles as static text.
      if (e instanceof DOMException && e.name === "AbortError") {
        setMessages((prev) =>
          prev.map((m) => (m.id === streamId ? { ...m, streaming: false } : m))
        )
        return
      }
      // The server commits nothing on a failed turn — roll the optimistic
      // bubble (and any streamed preview) back out and restore the draft
      // (+ mentions) for a retry. The editor is DOM-owned: restore
      // imperatively (chips re-land at the end — positions aren't kept).
      setMessages((prev) =>
        prev.filter((m) => m.id !== optimisticUser.id && m.id !== streamId)
      )
      const editor = editorRef.current
      editor?.insertText(instruction)
      for (const m of optimisticUser.mentions ?? []) editor?.insertMention(m)
      toast.error(e instanceof Error ? e.message : t("chat.failed"))
    } finally {
      if (abortRef.current === ctrl) {
        abortRef.current = null
        setIsSending(false)
      }
    }
  }

  /** Stop the in-flight reply (aborts the fetch; the user's message stays). */
  const handleStop = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsSending(false)
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
                                <BubbleContent className="text-sm">
                                  {/* Assistant prose is markdown (Streamdown
                                      parses incomplete markdown safely
                                      mid-stream); user text stays plain. */}
                                  {isUser ? (
                                    m.content
                                  ) : (
                                    <Streamdown
                                      mode={m.streaming ? "streaming" : "static"}
                                      isAnimating={m.streaming}
                                      className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300"
                                    >
                                      {m.content}
                                    </Streamdown>
                                  )}
                                </BubbleContent>
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
                {/* Working bubble covers send → first delta; the streaming
                    preview bubble then takes over as the progress signal. */}
                {(isLoadingHistory ||
                  (isSending && !messages.some((m) => m.streaming))) && (
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
            {/* Jump-to-latest pill when scrolled up off the bottom. */}
            <MessageScrollerButton direction="end" />
          </MessageScroller>
        </MessageScrollerProvider>

        <div
          className={
            pendingQuestion
              ? "flex flex-col p-4 pt-2"
              : "flex flex-col gap-2 p-4 pt-2"
          }
        >
          {pendingQuestion ? (
            <QuestionDock
              kind="choice"
              joined
              question={pendingQuestion.content ?? ""}
              options={pendingQuestion.question?.options ?? []}
              costHint={pendingQuestion.question?.cost_hint}
              onAnswer={handleChoiceAnswer}
              answering={answering}
            />
          ) : null}
          <div
            className={
              pendingQuestion
                ? "flex items-end gap-2 rounded-b-lg bg-muted p-2"
                : "flex items-end gap-2 rounded-lg bg-muted p-2"
            }
          >
            {/* The composer family's editor: @-chips live inline in the
                sentence (asset = context enrichment; output = the pinned
                revision target), Enter sends, IME composition is guarded
                inside the component. */}
            <MentionEditor
              ref={editorRef}
              placeholder={
                pendingQuestion &&
                (pendingQuestion.question?.options?.length ?? 0) > 0 &&
                pendingQuestion.question?.allow_freeform !== false
                  ? t("chat.choicePlaceholder")
                  : t("chat.assetPlaceholder")
              }
              mentionContext={mentionContext}
              onChange={(text, ms) => {
                setInput(text)
                setMentions(ms)
              }}
              onSubmit={handleSend}
              className="max-h-32 min-h-9 text-sm"
            />
            {isSending ? (
              <Button
                size="icon"
                variant="secondary"
                className="h-9 w-9 shrink-0 rounded-full"
                onClick={handleStop}
                aria-label={t("chat.stop")}
              >
                <Square className="h-3.5 w-3.5 fill-current" />
              </Button>
            ) : (
              <Button
                size="icon"
                className="h-9 w-9 shrink-0 rounded-full"
                disabled={!input.trim()}
                onClick={handleSend}
                aria-label={t("chat.send")}
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
