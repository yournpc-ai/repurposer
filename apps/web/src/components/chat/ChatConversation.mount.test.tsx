// @vitest-environment jsdom
import type { ComponentProps, ReactNode } from "react"
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ChatConversation } from "./ChatConversation"
import { buildConversationUnits } from "./timeline/project"
import { foldActivityUnits } from "./timeline/activity"
import type { OverlayMessage } from "./timeline/types"

const state = vi.hoisted(() => ({ mounts: 0, reads: [] as (string | null)[], snapshot: {
  steps: [], status: null as string | null, createdAt: null, terminal: false,
} }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("@/components/settings/settings-dialog-context", () => ({ useSettingsDialog: () => ({ openCreditTopup: vi.fn() }) }))
vi.mock("@/lib/use-run-events", () => ({ useRunEvents: (id: string | null) => {
  state.reads.push(id)
  return state.snapshot
} }))
vi.mock("./RunTaskList", async () => {
  const { useState } = await import("react")
  return { RunTaskList: ({ terminal }: { terminal: boolean }) => {
    const [instance] = useState(() => ++state.mounts)
    return <div data-testid="run-work" data-instance={instance}>{terminal ? "Worked" : "Rendering"}</div>
  } }
})
vi.mock("./AnchorCards", () => ({ AnchorCards: () => null }))
vi.mock("./rows/AssistantText", () => ({ AssistantText: ({ text }: { text: string }) => <p>{text}</p> }))
vi.mock("./rows/UserMessage", () => ({ UserBubble: ({ text }: { text: string }) => <p>{text}</p> }))
vi.mock("./ActivityStream", async (importOriginal) => ({
  ...await importOriginal<typeof import("./ActivityStream")>(),
  WorkSegmentRow: ({ liveLabel }: { liveLabel?: ReactNode }) => <div>{liveLabel ?? "Chat work"}</div>,
  ActivityRow: () => <div>Activity</div>,
}))
vi.mock("./blocks/ComponentSlot", () => ({
  ComponentSlot: ({ slot }: { slot: { kind: string; block?: { text: string } } }) => (
    <div>{slot.kind === "systemNotice" ? slot.block?.text : "Delivered video"}</div>
  ),
}))
vi.mock("@/components/ui/message-scroller", () => {
  const Container = ({ children, className }: { children?: ReactNode; className?: string }) => <div className={className}>{children}</div>
  const Item = ({ children, className }: { children?: ReactNode; className?: string }) => (
    <div data-slot="message-scroller-item" className={className}>{children}</div>
  )
  return {
    MessageScroller: Container, MessageScrollerProvider: Container,
    MessageScrollerContent: Container, MessageScrollerItem: Item, MessageScrollerViewport: Container,
    MessageScrollerButton: () => null,
    useMessageScroller: () => ({ scrollToEnd: vi.fn() }),
  }
})

afterEach(() => { cleanup(); vi.useRealTimers(); state.mounts = 0; state.reads = []; state.snapshot = { steps: [], status: null, createdAt: null, terminal: false } })
function props(rows: OverlayMessage[], extra: Partial<ComponentProps<typeof ChatConversation>> = {}): ComponentProps<typeof ChatConversation> {
  return {
    messages: rows, conversationUnits: foldActivityUnits(buildConversationUnits(rows)),
    planVersions: [], renderPlanVersion: () => null, chatOutputs: [], skillOptions: [],
    openOutputViewer: vi.fn(), runId: null, chatBusy: false,
    onSuggestionClick: vi.fn(), onRunStarted: vi.fn(), onStructureVisible: vi.fn(),
    pendingPlanMessageId: null, presentationRecovery: null,
    currentActivityRowKeysRef: { current: new Set() }, liveWorkFoldKey: null,
    nowRow: null, bottomNowRow: null, activeTurnId: null,
    steps: [], runTitle: "Video", runCreatedAt: null, terminal: false, status: null,
    reviewPending: false, runWorkEndedAtMs: null, runFallbackOutputs: [],
    hasUploads: false, assets: [], panel: false, scrollerSendRef: { current: null }, ...extra,
  }
}
const user: OverlayMessage = { id: "user", role: "user", content: "Make a video", turnId: "turn" }
const opening: OverlayMessage = { id: "opening", role: "assistant", content: "Starting", turnId: "turn", runId: "run" }
const delivery: OverlayMessage = { id: "delivery", role: "assistant", content: "Delivered", runId: "run", runDelivery: true, outputRefs: ["video"] }

it("keeps user outside one assistant container with prose and work inside", () => {
  const rows: OverlayMessage[] = [user, { ...opening, runId: null }, {
    id: "activity", role: "assistant", content: "", turnId: "turn",
    activity: { activity_id: "a1", kind: "read", status: "completed", key: "chat.activity.uploadDone" },
  }, { id: "result", role: "assistant", content: "Done", turnId: "turn" }]
  render(<ChatConversation {...props(rows)} />)
  const response = screen.getByText("Starting").closest('[data-slot="assistant-response"]')!
  expect(response.contains(screen.getByText("Chat work"))).toBe(true)
  expect(response.contains(screen.getByText("Done"))).toBe(true)
  expect(response.contains(screen.getByText("Make a video"))).toBe(false)
})

it("does not give an empty streaming speech row its own flex gap", () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] })
  const rows: OverlayMessage[] = [user, { ...opening, runId: null }, {
    id: "completed-capture", role: "assistant", content: "", turnId: "turn",
    activity: { activity_id: "a1", kind: "read", status: "completed", key: "chat.activity.videoCapturePlanDone" },
  }, {
    id: "failed-capture", role: "assistant", content: "", turnId: "turn",
    activity: { activity_id: "a2", kind: "read", status: "failed", key: "chat.activity.videoCapturePlan" },
  }, {
    id: "empty-partial", role: "assistant", content: "", turnId: "turn", streaming: true,
  }]
  const thinking = { activity_id: "__now__", seq: 0, kind: "think" as const, status: "active" as const, key: null }
  render(<ChatConversation {...props(rows, {
    chatBusy: true, activeTurnId: "turn", nowRow: thinking, bottomNowRow: thinking,
  })} />)
  act(() => vi.advanceTimersByTime(1000))
  const items = Array.from(document.querySelectorAll('[data-slot="message-scroller-item"]'))
  expect(items.map((item) => item.textContent)).toEqual([
    "Make a video", "Starting", "Chat work", "chat.thinking",
  ])
})

it("keeps thinking below a submitted questionnaire when the continuation reuses the turn id", () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] })
  const rows: OverlayMessage[] = [user, { ...opening, runId: null }, {
    id: "answers", role: "assistant", content: "", turnId: "turn", independentKind: "qa",
    qa: { question: "Brief", answer: "Demo", muted: false, items: [{ question: "Purpose?", answer: "Demo" }] },
  }]
  const thinking = { activity_id: "__now__", kind: "think" as const, status: "active" as const, key: null }
  const busy = { chatBusy: true, activeTurnId: "turn", nowRow: thinking, bottomNowRow: thinking }
  const view = render(<ChatConversation {...props(rows, busy)} />)
  act(() => vi.advanceTimersByTime(1000))
  const before = (first: string, second: string) =>
    expect(screen.getByText(first).compareDocumentPosition(screen.getByText(second)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  before("Demo", "chat.thinking")

  view.rerender(<ChatConversation {...props([...rows, {
    id: "reply", role: "assistant", content: "Building the storyboard", turnId: "turn",
  }], busy)} />)
  before("Demo", "Building the storyboard")
  before("Building the storyboard", "chat.thinking")
})

it("skips brief standalone waits and shows only the latest status after a second", () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] })
  const renderStatus = (key: string | null) => {
    const activity = key === null ? null : {
      activity_id: "__now__", kind: "think" as const, status: "active" as const, key,
    }
    return <ChatConversation {...props([user], {
      chatBusy: true, activeTurnId: "turn", nowRow: activity, bottomNowRow: activity,
    })} />
  }
  const view = render(renderStatus("chat.thinking"))
  act(() => vi.advanceTimersByTime(999))
  expect(screen.queryByText("chat.thinking")).toBeNull()
  view.rerender(renderStatus(null))
  act(() => vi.advanceTimersByTime(1000))
  expect(screen.queryByText("chat.thinking")).toBeNull()

  view.rerender(renderStatus("chat.thinking"))
  act(() => vi.advanceTimersByTime(1000))
  expect(screen.getByText("chat.thinking")).toBeTruthy()
  view.rerender(renderStatus("chat.activity.read"))
  act(() => vi.advanceTimersByTime(500))
  view.rerender(renderStatus("chat.activity.write"))
  act(() => vi.advanceTimersByTime(499))
  expect(screen.getByText("chat.thinking")).toBeTruthy()
  act(() => vi.advanceTimersByTime(1))
  expect(screen.getByText("chat.activity.write")).toBeTruthy()
  expect(screen.queryByText("chat.activity.read")).toBeNull()
  view.rerender(renderStatus(null))
  expect(screen.queryByText("chat.activity.write")).toBeNull()
})

it("preserves the Run work instance while delivery grows inside the same response", () => {
  const view = render(<ChatConversation {...props([user, opening], { runId: "run", status: "running" })} />)
  const work = screen.getByTestId("run-work")
  const response = work.closest('[data-slot="run-response"]')!
  expect(response.contains(screen.getByText("Starting"))).toBe(true)
  view.rerender(<ChatConversation {...props([user, opening, delivery], { runId: "run", terminal: true, status: "completed" })} />)
  expect(screen.getByTestId("run-work")).toBe(work)
  expect(response.contains(screen.getByText("Delivered"))).toBe(true)
  expect(response.contains(screen.getByText("Delivered video"))).toBe(true)
  expect(state.mounts).toBe(1)
  expect(state.reads.every((id) => id === null)).toBe(true)

  // A new current Run must not replace the historical work's component while
  // its detached read is still connecting.
  view.rerender(<ChatConversation {...props([user, opening, delivery], { terminal: true })} />)
  expect(screen.getByTestId("run-work")).toBe(work)
  expect(state.reads).toContain("run")
  expect(state.mounts).toBe(1)
  state.snapshot = { ...state.snapshot, terminal: true, status: "completed" }
  view.rerender(<ChatConversation {...props([user, opening, delivery], { terminal: true })} />)
  expect(screen.getByTestId("run-work")).toBe(work)
  expect(state.mounts).toBe(1)
})

it("independent upload remains in its current reply, outside the failed Run", () => {
  const retryUser: OverlayMessage = { id: "retry", role: "user", content: "Retry upload", turnId: "retry" }
  const uploaded: OverlayMessage = { id: "uploaded", role: "assistant", content: "Uploaded", turnId: "retry", outputRefs: ["video"] }
  state.snapshot = { ...state.snapshot, status: "failed", terminal: true }
  render(<ChatConversation {...props([user, opening, { ...delivery, content: "Upload failed", outputRefs: [] }, retryUser, uploaded])} />)
  const response = screen.getByText("Uploaded").closest('[data-slot="assistant-response"]')!
  expect(response.closest('[data-slot="run-response"]')).toBeNull()
  expect(response.contains(screen.getByText("Delivered video"))).toBe(true)
  expect(screen.getAllByTestId("run-work")).toHaveLength(1)
})

it("renders system notices after assistant prose through the shared component slot", () => {
  const reply: OverlayMessage = {
    id: "reply",
    role: "assistant",
    content: "Here is the answer.",
    turnId: "turn",
    proseDrainedAtMs: 1,
    blocks: [{ kind: "system_notice", text: "Still waiting for your answer." }],
  }
  render(<ChatConversation {...props([user, reply])} />)
  const response = screen.getByText("Here is the answer.").closest('[data-slot="assistant-response"]')!
  expect(response.contains(screen.getByText("Still waiting for your answer."))).toBe(true)
  expect(screen.getByText("Here is the answer.").textContent).not.toContain("Still waiting")
})
