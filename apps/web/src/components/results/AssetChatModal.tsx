import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Send, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Bubble,
  BubbleContent,
  BubbleGroup,
} from "@/components/ui/bubble"
import { Marker, MarkerContent } from "@/components/ui/marker"
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

import type { Clip, Derivative } from "@/lib/types"

type Asset = Clip | Derivative

interface AssetChatModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  asset: Asset | null
  assetType: "clip" | "derivative"
  projectId: string
  onUpdated?: () => void
}

interface ChatTurn {
  id: string
  role: "user" | "assistant" | "marker"
  content: string
  status?: "pending" | "running" | "completed" | "failed"
}

interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string | null
}

interface ChatSession {
  id: string
  project_id: string
  asset_id: string | null
  asset_type: string | null
  title: string | null
}

interface ChatResponse {
  session_id: string
  user_message: ChatMessage
  assistant_message: ChatMessage
  job_id: string | null
}

const pollJob = async (projectId: string, jobId: string) => {
  for (let i = 0; i < 60; i++) {
    const res = await apiFetch(`/api/v1/projects/${projectId}/jobs/${jobId}`)
    if (!res.ok) continue
    const job = await res.json()
    if (job.status === "completed") return true
    if (job.status === "failed") return false
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return false
}

export function AssetChatModal({
  open,
  onOpenChange,
  asset,
  assetType,
  projectId,
  onUpdated,
}: AssetChatModalProps) {
  const { t } = useTranslation()
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState("")
  const [isWorking, setIsWorking] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const scrollerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const viewport = scrollerRef.current
    if (!viewport) return
    viewport.scrollTop = viewport.scrollHeight
  }, [turns])

  useEffect(() => {
    if (!open || !asset) return

    let cancelled = false
    setInput("")
    setIsWorking(false)
    setIsLoadingHistory(true)

    const loadHistory = async () => {
      try {
        const params = new URLSearchParams({
          project_id: projectId,
          asset_id: asset.id,
          asset_type: assetType,
        })
        const sessionRes = await apiFetch(`/api/v1/chat/session?${params.toString()}`)
        if (!sessionRes.ok) {
          if (sessionRes.status === 404) {
            if (!cancelled) {
                            setTurns([
                {
                  id: "intro",
                  role: "assistant",
                  content: t("assetChat.intro"),
                },
              ])
            }
            return
          }
          throw new Error("Failed to load chat session")
        }

        const session = (await sessionRes.json()) as ChatSession
        const messagesRes = await apiFetch(
          `/api/v1/chat/sessions/${session.id}/messages`
        )
        if (!messagesRes.ok) throw new Error("Failed to load messages")
        const messages = (await messagesRes.json()) as { items: ChatMessage[] }

        if (cancelled) return
                setTurns([
          {
            id: "intro",
            role: "assistant",
            content: t("assetChat.intro"),
          },
          ...messages.items.map((m) => ({
            id: m.id,
            role: m.role === "system" ? "assistant" : m.role,
            content: m.content ?? "",
          })),
        ])
      } catch {
        if (!cancelled) {
                    setTurns([
            {
              id: "intro",
              role: "assistant",
              content: t("assetChat.intro"),
            },
          ])
        }
      } finally {
        if (!cancelled) setIsLoadingHistory(false)
      }
    }

    loadHistory()
    return () => {
      cancelled = true
    }
  }, [open, asset?.id, assetType, projectId, t])

  if (!asset) return null

  const assetTitle =
    assetType === "clip"
      ? (asset as Clip).hook
      : t(`assetChat.derivativeTypes.${(asset as Derivative).type}`)

  const handleSend = async () => {
    if (!input.trim() || isWorking || !asset) return
    const instruction = input.trim()

    const userTurn: ChatTurn = {
      id: crypto.randomUUID(),
      role: "user",
      content: instruction,
    }
    const assistantTurn: ChatTurn = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: t("assetChat.working"),
      status: "running",
    }

    setTurns((prev) => [...prev, userTurn, assistantTurn])
    setInput("")
    setIsWorking(true)

    try {
      const res = await apiFetch("/api/v1/chat", {
        method: "POST",
        body: {
          project_id: projectId,
          asset_id: asset.id,
          asset_type: assetType,
          message: instruction,
        },
      })
      if (!res.ok) throw new Error("Chat failed")

      const data = (await res.json()) as ChatResponse
      const { job_id } = data

      if (job_id) {
        const ok = await pollJob(projectId, job_id)
        const finalContent = ok ? t("assetChat.done") : t("assetChat.failed")
        setTurns((prev) =>
          prev.map((turn) =>
            turn.id === assistantTurn.id
              ? { ...turn, content: finalContent, status: ok ? "completed" : "failed" }
              : turn
          )
        )
        if (ok) onUpdated?.()
      } else {
        setTurns((prev) =>
          prev.map((turn) =>
            turn.id === assistantTurn.id
              ? { ...turn, content: t("assetChat.done"), status: "completed" }
              : turn
          )
        )
        onUpdated?.()
      }
    } catch (e) {
      const errorContent =
        e instanceof Error ? e.message : t("assetChat.failed")
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === assistantTurn.id
            ? { ...turn, content: errorContent, status: "failed" }
            : turn
        )
      )
    } finally {
      setIsWorking(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-lg">
        <DialogHeader className="px-4 pt-4 pb-2">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-primary" />
            {t("assetChat.title", { asset: assetTitle })}
          </DialogTitle>
        </DialogHeader>

        <MessageScrollerProvider autoScroll={false}>
          <MessageScroller className="min-h-0 flex-1 px-4">
            <MessageScrollerViewport ref={scrollerRef}>
              <MessageScrollerContent className="gap-3 pb-2">
                {turns.map((turn) => {
                  if (turn.role === "marker") {
                    return (
                      <MessageScrollerItem key={turn.id}>
                        <Marker variant="separator" className="py-2">
                          <MarkerContent>{turn.content}</MarkerContent>
                        </Marker>
                      </MessageScrollerItem>
                    )
                  }

                  const isUser = turn.role === "user"
                  return (
                    <MessageScrollerItem key={turn.id}>
                      <Message align={isUser ? "end" : "start"}>
                        <MessageContent className={isUser ? "items-end" : "items-start"}>
                          <BubbleGroup className={isUser ? "items-end" : "items-start"}>
                            <Bubble
                              variant={isUser ? "default" : "muted"}
                              align={isUser ? "end" : "start"}
                            >
                              <BubbleContent className="text-sm">
                                {turn.content}
                                {turn.status === "running" && (
                                  <span className="ml-2 inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                                )}
                              </BubbleContent>
                            </Bubble>
                          </BubbleGroup>
                        </MessageContent>
                      </Message>
                    </MessageScrollerItem>
                  )
                })}
                {isLoadingHistory && (
                  <MessageScrollerItem key="loading">
                    <Message align="start">
                      <MessageContent className="items-start">
                        <BubbleGroup className="items-start">
                          <Bubble variant="muted" align="start">
                            <BubbleContent className="text-sm">
                              {t("assetChat.loadingHistory")}
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

        <div className="flex items-center gap-2 border-t p-4">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={t("assetChat.placeholder")}
            className="h-10 flex-1"
            disabled={isWorking || isLoadingHistory}
          />
          <Button
            size="icon"
            className="h-10 w-10 rounded-full"
            disabled={!input.trim() || isWorking || isLoadingHistory}
            onClick={handleSend}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
