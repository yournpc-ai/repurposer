// @vitest-environment jsdom
import type { ComponentProps, ReactNode } from "react"
import { act, cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ChatConversation } from "./ChatConversation"
import { buildConversationUnits } from "./timeline/project"
import { foldActivityUnits } from "./timeline/activity"
import type { OverlayMessage } from "./timeline/types"

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("@/components/settings/settings-dialog-context", () => ({ useSettingsDialog: () => ({ openCreditTopup: vi.fn() }) }))
vi.mock("./AnchorCards", () => ({ AnchorCards: () => null }))
vi.mock("./rows/AssistantText", () => ({ AssistantText: ({ text }: { text: string }) => <p>{text}</p> }))
vi.mock("./rows/UserMessage", () => ({ UserBubble: ({ text }: { text: string }) => <p>{text}</p> }))
vi.mock("./blocks/ComponentSlot", () => ({
  ComponentSlot: ({ slot }: { slot: { kind: string; block?: { text: string } } }) => (
    <div>{slot.kind === "systemNotice" ? slot.block?.text : "Delivered video"}</div>
  ),
}))
vi.mock("@/components/chat/MessageScroller", () => {
  const Container = ({ children, className }: { children?: ReactNode; className?: string }) => <div className={className}>{children}</div>
  const Item = ({ children, className }: { children?: ReactNode; className?: string }) => (
    <div data-slot="message-scroller-item" className={className}>{children}</div>
  )
  return {
    MessageScroller: Container, MessageScrollerProvider: Container,
    MessageScrollerContent: Container, MessageScrollerItem: Item, MessageScrollerViewport: Container,
    MessageScrollerButton: () => null,
    useMessageScroller: () => ({ scrollToEnd: vi.fn() }),
    useMessageScrollerViewportAnchor: () => vi.fn(),
  }
})

afterEach(() => { cleanup(); vi.useRealTimers() })
function props(rows: OverlayMessage[], extra: Partial<ComponentProps<typeof ChatConversation>> = {}): ComponentProps<typeof ChatConversation> {
  return {
    conversationUnits: foldActivityUnits(buildConversationUnits(rows)),
    chatOutputs: [], skillOptions: [],
    openOutputViewer: vi.fn(), chatBusy: false,
    onSuggestionClick: vi.fn(), onStructureVisible: vi.fn(),
    presentationRecovery: null,
    currentActivityRowKeysRef: { current: new Set() }, liveWorkFoldKey: null,
    nowRow: null, bottomNowRow: null, activeTurnId: null,
    scrollerSendRef: { current: null }, ...extra,
  }
}
const user: OverlayMessage = { id: "user", role: "user", content: "Make a video", turnId: "turn" }
const opening: OverlayMessage = { id: "opening", role: "assistant", content: "Starting", turnId: "turn" }

it("keeps user outside one assistant container with prose and work inside", () => {
  const rows: OverlayMessage[] = [user, opening, {
    id: "activity", role: "assistant", content: "", turnId: "turn",
    activity: { activity_id: "a1", kind: "read", status: "completed", key: "chat.activity.uploadDone" },
  }, { id: "result", role: "assistant", content: "Done", turnId: "turn" }]
  render(<ChatConversation {...props(rows)} />)
  const response = screen.getByText("Starting").closest('[data-slot="assistant-response"]')!
  expect(response.contains(screen.getByRole("button", { name: "chat.activityFold.workedWithoutTime" }))).toBe(true)
  expect(response.contains(screen.getByText("Done"))).toBe(true)
  expect(response.contains(screen.getByText("Make a video"))).toBe(false)
})

it("does not give an empty streaming speech row its own flex gap", () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] })
  const rows: OverlayMessage[] = [user, opening, {
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
  expect(items).toHaveLength(4)
  expect(items[0].textContent).toBe("Make a video")
  expect(items[1].textContent).toBe("Starting")
  expect(within(items[2] as HTMLElement).getByRole("button", { name: "chat.failed" })).toBeTruthy()
  expect(items[3].textContent).toBe("chat.thinking")
})

it("keeps thinking below a submitted questionnaire when the continuation reuses the turn id", () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] })
  const rows: OverlayMessage[] = [user, opening, {
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

it("keeps native receipts in declaration order and scopes job outcomes to the original opening and call", () => {
  const member = (id: string, index: number, callState: string): OverlayMessage => ({
    id: "member-" + id, turnId: "opening", role: "assistant", content: "",
    activity: { activity_id: id, call_id: id, group_id: "batch", call_index: index,
      tool_name: "export_video", kind: "read", status: "completed", call_state: callState, key: null },
  })
  const rows: OverlayMessage[] = [
    member("second", 1, "not_executed"), member("first", 0, "completed"),
    { id: "stopped", turnId: "opening", role: "assistant", content: "",
      activity: { activity_id: "stopped", call_id: "stopped", tool_name: "generate_voice",
        kind: "read", status: "cancelled", key: null } },
    { id: "uncertain", turnId: "opening", role: "assistant", content: "Reservation held",
      jobReceipt: { callId: "first", status: "provider_unknown", reservedCredits: 10 } },
    { id: "other", turnId: "another-opening", role: "assistant", content: "",
      jobReceipt: { callId: "first", role: "export", outputId: "fixed-output", status: "available" } },
  ]
  const open = vi.fn()
  render(<ChatConversation {...props(rows, { openOutputViewer: open })} />)
  const [before, after] = screen.getAllByRole("button")
  expect(before.textContent).toContain("agentReceipt.unknown")
  expect(screen.getByText("Reservation held")).toBeDefined()
  expect(screen.queryByRole("listitem")).toBeNull()
  act(() => before.click())
  const steps = screen.getAllByRole("listitem")
  expect(steps).toHaveLength(3)
  expect(steps[0].textContent).toContain("agentReceipt.unknown")
  expect(steps[0].textContent).toContain("agentReceipt.reservedCredits")
  expect(steps[1].textContent).toContain("agentReceipt.notExecuted")
  expect(steps[2].textContent).toContain("agentReceipt.cancelled")
  expect(screen.queryByRole("button", { name: "common.preview" })).toBeNull()
  act(() => after.click())
  act(() => screen.getByRole("button", { name: "common.preview" }).click())
  expect(open).toHaveBeenCalledWith("fixed-output")
})
