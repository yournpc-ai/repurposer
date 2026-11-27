// @vitest-environment jsdom
import type { ComponentProps, ReactNode } from "react"
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ChatConversation } from "./ChatConversation"
import { buildConversationUnits } from "./timeline/project"
import { foldActivityUnits } from "./timeline/activity"
import type { OverlayMessage } from "./timeline/types"

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("@/components/settings/settings-dialog-context", () => ({ useSettingsDialog: () => ({ openCreditTopup: vi.fn() }) }))
vi.mock("./AnchorCards", () => ({ AnchorCards: () => null }))
vi.mock("./rows/AssistantText", () => ({
  AssistantText: ({ text, stageNote }: { text: string; stageNote?: boolean }) => (
    <p data-stage-note={stageNote ? "true" : undefined}>{text}</p>
  ),
}))
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
  expect(items[3].textContent).toMatch(/^chat\.thinking\d+s$/)
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

it("keeps interim prose visible in the main narrative flow between tool folds (zero retroactive swallowing) and never shows ActionBar on stage notes", () => {
  const rows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "给 oxvalue 制作一条宣传片", turnId: "u1" },
    {
      id: "a1",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "prepare_video_materials",
        kind: "read",
        status: "completed",
        key: "chat.activity.videoMaterialsDone",
        at: "2026-11-26T11:17:00Z",
        duration_ms: 15000,
      },
    },
    {
      id: "ip1",
      serverMessageId: "ip1",
      role: "assistant",
      content: "官网已采集完成，事实齐备。接下来直接推进 30 秒成片。",
      turnId: "u1",
      runId: "run-1",
      interim: true,
      displayRole: "stage_note",
      streaming: false,
      at: "2026-11-26T11:17:51Z",
    },
    {
      id: "a2",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-1",
      activity: {
        activity_id: "c2",
        call_id: "c2",
        tool_name: "analyze_brand",
        kind: "read",
        status: "active",
        key: "chat.activity.brandAnalyze",
      },
    },
  ]
  const liveUnits = foldActivityUnits(buildConversationUnits(rows), undefined, "u1")
  const liveFolds = liveUnits.filter((u) => u.kind === "activityFold")
  // Option A single-rail: mid-run interim note after tools started folds into the ONE work fold
  expect(liveFolds).toHaveLength(1)
  expect(liveUnits.some((u) => u.kind === "message" && u.message.id === "ip1")).toBe(false)
  expect(liveFolds[0].kind === "activityFold" && liveFolds[0].openTail).toBe(true)
  expect(
    liveFolds[0].kind === "activityFold" &&
      liveFolds[0].trail.some((entry) => entry.kind === "note" && entry.text.includes("官网已采集完成")),
  ).toBe(true)

  const { container, rerender } = render(
    <ChatConversation
      conversationUnits={liveUnits}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set(["a1", "a2"]) }}
      liveWorkFoldKey="a1"
      liveFocus={null}
      nowRow={{
        activity_id: "c2",
        seq: 2,
        kind: "read",
        status: "active",
        tool_name: "analyze_brand",
        key: "chat.activity.brandAnalyze",
      }}
      bottomNowRow={null}
      activeTurnId="u1"
      activeRunId="run-1"
      scrollerSendRef={{ current: null }}
    />,
  )
  // Live state: mid-run note stays inside the single collapsed fold; no ActionBar
  expect(container.querySelector("[data-slot='message-action-bar']")).toBeNull()

  // Settled state: still ONE single work fold, final reply gets ActionBar
  const settledRows: OverlayMessage[] = [
    ...rows.slice(0, 3),
    {
      ...rows[3],
      activity: {
        ...rows[3].activity!,
        status: "completed",
        at: "2026-11-26T11:18:00Z",
        duration_ms: 8000,
      },
    },
    { id: "final1", serverMessageId: "final1", role: "assistant", content: "成片已交付。", turnId: "u1", runId: "run-1" },
  ]
  const settledUnits = foldActivityUnits(buildConversationUnits(settledRows), undefined, null)
  expect(settledUnits.filter((u) => u.kind === "activityFold")).toHaveLength(1)
  rerender(
    <ChatConversation
      conversationUnits={settledUnits}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy={false}
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set() }}
      liveWorkFoldKey={null}
      liveFocus={null}
      nowRow={null}
      bottomNowRow={null}
      activeTurnId={null}
      activeRunId={null}
      scrollerSendRef={{ current: null }}
    />,
  )
  expect(screen.getByText("成片已交付。")).toBeTruthy()
  expect(screen.getByText("成片已交付。")).toBeTruthy()
  expect(container.querySelectorAll("[data-slot='message-action-bar']")).toHaveLength(1)
})

it("renders standalone StepsPlanCard above collapsed ThinkingState live and survives mid-turn + settled refresh", () => {
  const liveSteps = [
    { title: "准备素材与配音配乐", status: "done" as const },
    { title: "编排分镜与字幕动效", status: "in_progress" as const },
    { title: "渲染成片并逐帧审片", status: "pending" as const },
  ]
  const rows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "开工", turnId: "u1", steps: liveSteps },
    {
      id: "act1",
      role: "assistant",
      content: "",
      turnId: "u1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "create_video",
        kind: "draft",
        status: "active",
        key: "chat.activity.videoDesign",
      },
    },
    { id: "ip1", role: "assistant", content: "正在编排第 1 版分镜", turnId: "u1", interim: true },
  ]
  const liveUnits = foldActivityUnits(buildConversationUnits(rows), undefined, "u1")
  const { container, rerender } = render(
    <ChatConversation
      conversationUnits={liveUnits}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set(["act1"]) }}
      liveWorkFoldKey="act1"
      liveFocus="编排分镜与字幕动效"
      liveSteps={liveSteps}
      nowRow={rows[1].activity ?? null}
      bottomNowRow={null}
      activeTurnId="u1"
      scrollerSendRef={{ current: null }}
    />,
  )

  // Standalone StepsPlanCard is visible above ThinkingState; no redundant live-brief-stream or steps inside drawer
  const card = screen.getByTestId("steps-plan-card")
  expect(card.textContent).toContain("准备素材与配音配乐")
  expect(card.textContent).toContain("编排分镜与字幕动效")
  expect(screen.queryByTestId("live-brief-stream")).toBeNull()
  expect(container.querySelector(".ui-thinkc__plan")).toBeNull()
  expect(container.querySelector(".ui-thinkc__steps-badge")).toBeNull()

  // Mid-turn refresh (liveSteps=null, hydrated from opening user.steps with in_progress) keeps StepsPlanCard open
  rerender(
    <ChatConversation
      conversationUnits={liveUnits}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy={false}
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set() }}
      liveWorkFoldKey={null}
      liveFocus={null}
      liveSteps={null}
      nowRow={null}
      bottomNowRow={null}
      activeTurnId={null}
      scrollerSendRef={{ current: null }}
    />,
  )
  expect(screen.getByTestId("steps-plan-card").textContent).toContain("编排分镜与字幕动效")

  // Settled state (and post-refresh): collapses into compact "3/3 steps" pill beside "Worked for …",
  // and clicking the pill independently opens StepsPlanCard without expanding the tool drawer
  const doneSteps = liveSteps.map((s) => ({ ...s, status: "done" as const }))
  const settledRows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "开工", turnId: "u1", steps: doneSteps },
    {
      ...rows[1],
      activity: {
        ...rows[1].activity!,
        status: "completed",
        at: "2026-11-26T12:00:00Z",
        duration_ms: 9000,
      },
    },
    { id: "final1", serverMessageId: "final1", role: "assistant", content: "成片已交付。", turnId: "u1", steps: doneSteps, turnProse: true },
  ]
  const settledUnits = foldActivityUnits(buildConversationUnits(settledRows), undefined, null)
  rerender(
    <ChatConversation
      conversationUnits={settledUnits}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy={false}
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set() }}
      liveWorkFoldKey={null}
      liveFocus={null}
      liveSteps={null}
      nowRow={null}
      bottomNowRow={null}
      activeTurnId={null}
      scrollerSendRef={{ current: null }}
    />,
  )
  expect(screen.queryByTestId("steps-plan-card")).toBeNull()
  const pill = screen.getByTestId("steps-toggle-pill")
  expect(pill.getAttribute("aria-expanded")).toBe("false")

  fireEvent.click(pill)
  expect(pill.getAttribute("aria-expanded")).toBe("true")
  expect(screen.getByTestId("steps-plan-card").textContent).toContain("渲染成片并逐帧审片")
  // Tool drawer remains independently closed
  expect(container.querySelector(".ui-thinkc__body")?.getAttribute("data-open")).toBe("false")
})

it("preserves a turnProse handoff message between interleaved work folds on the same turnId", () => {
  const rows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "修完后跑测试", turnId: "u1" },
    {
      id: "act1",
      role: "assistant",
      content: "",
      turnId: "u1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "edit_timeline",
        kind: "draft",
        status: "completed",
        key: null,
        at: "2026-11-26T12:00:00Z",
        duration_ms: 4000,
      },
    },
    { id: "handoff", serverMessageId: "handoff", role: "assistant", content: "已定位并修复，正在等待后台导出完成。", turnId: "u1", turnProse: true },
    {
      id: "act2",
      role: "assistant",
      content: "",
      turnId: "u1",
      activity: {
        activity_id: "c2",
        call_id: "c2",
        tool_name: "review_video",
        kind: "read",
        status: "completed",
        key: null,
        at: "2026-11-26T12:01:00Z",
        duration_ms: 5000,
      },
    },
    { id: "final", serverMessageId: "final", role: "assistant", content: "审片通过，成片已交付。", turnId: "u1", turnProse: true },
  ]
  const units = foldActivityUnits(buildConversationUnits(rows))
  expect(units.map((u) => u.kind)).toEqual(["message", "activityFold", "message", "activityFold", "message"])
  expect(units[2].kind === "message" && units[2].message.content).toBe("已定位并修复，正在等待后台导出完成。")
  expect(units[4].kind === "message" && units[4].message.content).toBe("审片通过，成片已交付。")
})

it("keeps orphan asset-reading rows folded with their tool batch, preserves stage notes visibly, and hides ActionBar on short questionEcho stubs", () => {
  const rows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "制作宣传片", turnId: "u1" },
    { id: "q1-echo", serverMessageId: "q1", role: "assistant", questionEcho: true, displayRole: "question_framing_stub", content: "下面是规格卡，请确认。", turnId: "u1", hydrated: true },
    { id: "q1", role: "assistant", content: "", turnId: "u1", independentKind: "qa", qa: { question: "成片多长?", answer: "45 秒", muted: false, questionId: "q1" } },
    { id: "ip0", role: "assistant", content: "规格已定，开始检索素材。", turnId: "u1", runId: "run-2", interim: true, displayRole: "stage_note" },
    {
      id: "a1",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-2",
      activity: { activity_id: "c1", call_id: "c1", tool_name: "capture_web", kind: "read", status: "completed", key: null, at: "2026-11-26T17:00:00Z", duration_ms: 5000 },
    },
    {
      id: "orphan-asset-reading",
      role: "assistant",
      content: "",
      activity: { activity_id: "asset-reading:83e1b6cb", kind: "read", status: "completed", key: "chat.material.readingDoneProgress", at: "2026-11-26T17:00:31Z", duration_ms: 25000 },
    },
    { id: "ip1", role: "assistant", content: "品牌视觉语言已摸清，补拍关键面板。", turnId: "u1", runId: "run-2", interim: true, displayRole: "stage_note" },
    {
      id: "a2",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-2",
      activity: { activity_id: "c2", call_id: "c2", tool_name: "get_blocks", kind: "read", status: "completed", key: null, at: "2026-11-26T17:01:00Z", duration_ms: 2000 },
    },
  ]
  const units = foldActivityUnits(buildConversationUnits(rows), undefined, "u1")
  // Orphan asset-reading AND mid-run ip1 stay inside Run 2's SINGLE fold;
  // opening stage_note ip0 stays cleanly visible above the fold.
  expect(units.filter((u) => u.kind === "activityFold")).toHaveLength(1)
  expect(units.some((u) => u.kind === "message" && u.message.id === "ip0")).toBe(true)
  expect(units.some((u) => u.kind === "message" && u.message.id === "ip1")).toBe(false)

  const { container } = render(
    <ChatConversation
      conversationUnits={units}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy={false}
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set() }}
      liveWorkFoldKey={null}
      nowRow={null}
      bottomNowRow={null}
      activeTurnId={null}
      scrollerSendRef={{ current: null }}
    />,
  )
  // Short questionEcho stub renders without MessageActionBar; stage notes render visibly without ActionBar
  expect(screen.getByText("下面是规格卡，请确认。")).toBeTruthy()
  expect(screen.getByText("规格已定，开始检索素材。")).toBeTruthy()
  expect(container.querySelector("[data-slot='message-action-bar']")).toBeNull()
})

it("keeps hover ActionBar stable across Live QA, post-QA run_2 busy state, and refresh, and isolates run_2 failure checkpoint with failed StepsPlanCard", () => {
  const onRetry = vi.fn()
  const substantiveSummary =
    "官网已经采到真实内容了。OxValue 是一家做专利与无形资产估值的受治理 AI 工作台，技术底座是 VEST 框架、8 个行业数据库和 27 个 AI 算法。下面确认几个关键偏好。"
  const rows: OverlayMessage[] = [
    {
      id: "u1",
      role: "user",
      content: "给 https://agent.oxvalue.ai/ 制作一个宣传片",
      turnId: "u1",
      steps: [
        { title: "采集官网真实界面与文案证据", status: "done" },
        { title: "编排 16 幕工作流实演分镜与旁白", status: "failed" },
        { title: "审片交付成片", status: "pending" },
      ],
    },
    {
      id: "a1",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "prepare_video_materials",
        kind: "read",
        status: "completed",
        key: "chat.activity.viewWebPageDone",
        at: "2026-11-26T18:37:59Z",
        duration_ms: 45000,
      },
    },
    {
      id: "q1-echo",
      serverMessageId: "q1",
      role: "assistant",
      questionEcho: true,
      displayRole: "question_framing",
      runId: "run-1",
      content: substantiveSummary,
      turnId: "u1",
      hydrated: true,
    },
    {
      id: "q1",
      role: "assistant",
      content: "",
      turnId: "u1",
      independentKind: "qa",
      qa: {
        question: "OxValue 宣传片的关键偏好",
        answer: "产品工作流实演 · 45 秒",
        muted: false,
        questionId: "q1",
      },
    },
    {
      id: "a2",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-2",
      activity: {
        activity_id: "c2",
        call_id: "c2",
        tool_name: "create_video",
        kind: "read",
        status: "failed",
        key: "chat.activity.createVideo",
        at: "2026-11-26T18:43:01Z",
        duration_ms: 2400,
      },
    },
    {
      id: "fail-1",
      role: "assistant",
      content: "执行后续创作时遇到系统异常，你的确认选项与已采集素材已安全保留，点击重试即可继续。",
      turnId: "u1",
      runId: "run-2",
      meta: "error",
      displayRole: "failure_checkpoint",
      failureCheckpoint: {
        code: "execution_error",
        run_id: "run-2",
        retryable: true,
        decision_committed: true,
      },
    },
  ]

  const units = foldActivityUnits(buildConversationUnits(rows), undefined, null)
  // Run 1 and Run 2 are strictly isolated into 2 separate folds; Run 2 failure never hijacks Run 1
  const folds = units.filter((u) => u.kind === "activityFold")
  expect(folds).toHaveLength(2)

  const { container } = render(
    <ChatConversation
      conversationUnits={units}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy={false}
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      onRetryCheckpoint={onRetry}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set() }}
      liveWorkFoldKey={null}
      nowRow={null}
      bottomNowRow={null}
      activeTurnId="u1"
      activeRunId="run-2"
      scrollerSendRef={{ current: null }}
    />,
  )

  // Substantive question_framing keeps its hover ActionBar stably
  const actionBar = container.querySelector("[data-slot='message-action-bar']")
  expect(actionBar).toBeTruthy()
  expect(actionBar?.getAttribute("data-reveal-mode")).toBe("hover")

  // Failed StepsPlanCard stays open with the failed step marked red
  const stepsCard = container.querySelector("[data-testid='steps-plan-card']")
  expect(stepsCard).toBeTruthy()
  expect(stepsCard?.querySelector("[data-status='failed']")?.textContent).toContain(
    "编排 16 幕工作流实演分镜与旁白",
  )

  // FailureCheckpointCard renders with clickable Retry CTA
  const checkpointCard = container.querySelector("[data-slot='failure-checkpoint-card']")
  expect(checkpointCard).toBeTruthy()
  const retryBtn = checkpointCard?.querySelector("button")
  expect(retryBtn).toBeTruthy()
  retryBtn?.click()
  expect(onRetry).toHaveBeenCalledTimes(1)
})

it("keeps a pre-QA website summary visible above a bare QA bubble when no questionEcho row exists", () => {
  const rows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "给 https://agent.oxvalue.ai/ 制作一个宣传片", turnId: "u1" },
    {
      id: "a1",
      role: "assistant",
      content: "",
      turnId: "u1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "prepare_video_materials",
        kind: "read",
        status: "completed",
        key: "chat.activity.videoMaterialsDone",
        at: "2026-11-26T18:10:00Z",
        duration_ms: 48000,
      },
    },
    {
      id: "summary1",
      role: "assistant",
      content: "官网已采集完成：OxValue Agent 是科研成果商业化与技术估值工具。确认下面几个规格后就开工。",
      turnId: "u1",
      interim: true,
    },
    {
      id: "qa1",
      role: "assistant",
      content: "",
      turnId: "u1",
      independentKind: "qa",
      qa: {
        question: "确认方向",
        answer: "产品工作流实演",
        muted: false,
        items: [{ question: "这支片子主要讲哪条线?", answer: "产品工作流实演" }],
      },
    },
  ]
  const units = foldActivityUnits(buildConversationUnits(rows), undefined, null)
  // The pre-QA summary stays promoted outside Worked even after the QA bubble lands
  expect(units.some((u) => u.kind === "message" && u.message.id === "summary1")).toBe(true)

  render(<ChatConversation {...props(rows)} />)
  const summary = screen.getByText("官网已采集完成：OxValue Agent 是科研成果商业化与技术估值工具。确认下面几个规格后就开工。")
  const qaAnswer = screen.getByText("产品工作流实演")
  expect(summary.compareDocumentPosition(qaAnswer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it("Option A single-rail: keeps one opening stage_note above the fold and absorbs mid-run notes into ONE work fold", () => {
  const rows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "给官网做一个 45 秒宣传片", turnId: "u1" },
    {
      id: "qa1",
      role: "assistant",
      content: "",
      turnId: "u1",
      independentKind: "qa",
      qa: { question: "成片做多长?", answer: "45 秒", muted: false },
    },
    {
      id: "open-note",
      role: "assistant",
      content: "方向已确认：工作流实演、英文旁白、45 秒。我现在同步备料。",
      turnId: "u1",
      runId: "run-2",
      interim: true,
      displayRole: "stage_note",
    },
    {
      id: "a1",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-2",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "analyze_brand",
        kind: "read",
        status: "completed",
        key: "chat.activity.brandDone",
        at: "2026-11-26T18:10:00Z",
        duration_ms: 6000,
      },
    },
    {
      id: "mid-note-1",
      role: "assistant",
      content: "官网截图齐了，现在读积木参数。",
      turnId: "u1",
      runId: "run-2",
      interim: true,
      displayRole: "rail_note",
    },
    {
      id: "a2",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-2",
      activity: {
        activity_id: "c2",
        call_id: "c2",
        tool_name: "create_video",
        kind: "read",
        status: "completed",
        key: "chat.activity.videoCreateDone",
        at: "2026-11-26T18:10:10Z",
        duration_ms: 35000,
      },
    },
    {
      id: "final",
      role: "assistant",
      content: "成片已经交付完成。",
      turnId: "u1",
      runId: "run-2",
      displayRole: "prose",
      serverMessageId: "final",
    },
  ]

  const units = foldActivityUnits(buildConversationUnits(rows), undefined, null)
  // Opening stage_note stays visible outside the fold (never swallowed)
  expect(units.some((u) => u.kind === "message" && u.message.id === "open-note")).toBe(true)
  // Mid-run rail_note is absorbed inside the SINGLE work fold — NEVER splits into multiple "工作了 Xs"
  expect(units.some((u) => u.kind === "message" && u.message.id === "mid-note-1")).toBe(false)
  const folds = units.filter((u) => u.kind === "activityFold")
  expect(folds).toHaveLength(1)
  expect(
    folds[0].kind === "activityFold" &&
      folds[0].trail.some((entry) => entry.kind === "note" && entry.text === "官网截图齐了，现在读积木参数。"),
  ).toBe(true)

  // Safety net: if a settled run ends with NO following reply/echo (e.g. pending
  // QuestionDock with bare title), its trailing summary note is rescued out of the
  // fold so the user never sees a blank void above QuestionDock.
  const pendingQaRows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "给官网做宣传片", turnId: "u1" },
    {
      id: "open1",
      role: "assistant",
      content: "我先采集官网内容。",
      turnId: "u1",
      runId: "run-1",
      interim: true,
      displayRole: "stage_note",
    },
    {
      id: "a1",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "prepare_video_materials",
        kind: "read",
        status: "completed",
        key: "chat.activity.viewWebPageDone",
        at: "2026-11-26T20:27:48Z",
        duration_ms: 48000,
      },
    },
    {
      id: "summary-rail",
      role: "assistant",
      content: "网站采集已完成，我核对了官网真实内容：OxValue 是受治理 AI 估值工作台。下面先确认几项。",
      turnId: "u1",
      runId: "run-1",
      interim: true,
      displayRole: "rail_note",
    },
  ]
  const rescuedUnits = foldActivityUnits(buildConversationUnits(pendingQaRows), undefined, null)
  expect(rescuedUnits.some((u) => u.kind === "message" && u.message.id === "summary-rail")).toBe(true)

  // Even AFTER the user submits QA and Run 2 starts live on the SAME turnId ("u1"),
  // the rescued pre-QA summary from frozen Run 1 must stay visible outside Run 1's fold!
  const afterQaSubmitRows: OverlayMessage[] = [
    ...pendingQaRows,
    {
      id: "qa-submitted",
      role: "assistant",
      content: "",
      turnId: "u1",
      independentKind: "qa",
      qa: { question: "制作偏好", answer: "产品工作流实演", muted: false },
    },
    {
      id: "run2-open",
      role: "assistant",
      content: "收到，方向确定。",
      turnId: "u1",
      runId: "run-2",
      interim: true,
      displayRole: "stage_note",
    },
  ]
  const liveAfterQaUnits = foldActivityUnits(buildConversationUnits(afterQaSubmitRows), undefined, "u1")
  expect(liveAfterQaUnits.some((u) => u.kind === "message" && u.message.id === "summary-rail")).toBe(true)
})

it("suppresses running export boilerplate so active export never shatters the work fold, and hides legacy delivery stub copy", () => {
  const runningExportRows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "制作宣传片", turnId: "u1" },
    {
      id: "a1",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "preview_range",
        kind: "read",
        status: "completed",
        key: "chat.activity.previewRangeDone",
      },
    },
    {
      id: "a2",
      role: "assistant",
      content: "",
      turnId: "u1",
      runId: "run-1",
      activity: {
        activity_id: "c2",
        call_id: "c2",
        tool_name: "export_video",
        kind: "read",
        status: "active",
        call_state: "running",
        key: "chat.activity.exportVideo",
      },
    },
    {
      id: "job-export-running",
      role: "assistant",
      content: "正在渲染 MP4。",
      turnId: "u1",
      runId: "run-1",
      jobReceipt: {
        callId: "c2",
        operation: "export_video",
        status: "running",
      },
    },
  ]
  const units = foldActivityUnits(buildConversationUnits(runningExportRows), undefined, "u1")
  // Running export receipt must NEVER appear as a standalone prose message or close the fold
  expect(units.some((u) => u.kind === "message" && u.message.content.includes("正在渲染 MP4"))).toBe(false)
  const folds = units.filter((u) => u.kind === "activityFold")
  expect(folds).toHaveLength(1)
  expect(folds[0].openTail).toBe(true)
  expect(folds[0].liveActivity?.tool_name).toBe("export_video")

  // Legacy delivery stub with outputRefs suppresses redundant "正式成片已交付。" text & action bar
  const deliveredRows: OverlayMessage[] = [
    { id: "u2", role: "user", content: "制作宣传片", turnId: "u2" },
    {
      id: "del-1",
      serverMessageId: "del-1",
      role: "assistant",
      content: "正式成片已交付。",
      turnId: "u2",
      hydrated: true,
      reviewedVersionId: "ver-1",
      outputRefs: ["out-1"],
    },
    {
      id: "final-1",
      serverMessageId: "final-1",
      role: "assistant",
      content: "成片做好了，右侧可以直接看。",
      turnId: "u2",
      hydrated: true,
      turnProse: true,
    },
  ]
  const rendered = render(
    <ChatConversation
      conversationUnits={foldActivityUnits(buildConversationUnits(deliveredRows))}
      chatOutputs={[
        {
          id: "out-1",
          project_id: "p1",
          type: "video",
          render_status: "completed",
          files: { video: "https://cdn.example.com/final.mp4" },
          payload: { duration_seconds: 45 },
          created_at: "2026-11-27T00:00:00Z",
        } as never,
      ]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy={false}
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set() }}
      liveWorkFoldKey={null}
      nowRow={null}
      bottomNowRow={null}
      activeTurnId={null}
      scrollerSendRef={{ current: null }}
    />,
  )
  expect(rendered.queryByText("正式成片已交付。")).toBeNull()
  expect(rendered.getByText("成片做好了，右侧可以直接看。")).toBeTruthy()
})

it("shows Thinking honestly during live_post_tool_thinking instead of snapping back to stale liveFocus", () => {
  const rows: OverlayMessage[] = [
    { id: "u1", role: "user", content: "制作宣传片", turnId: "u1" },
    {
      id: "act1",
      role: "assistant",
      content: "",
      turnId: "u1",
      activity: {
        activity_id: "c1",
        call_id: "c1",
        tool_name: "capture_web",
        kind: "read",
        key: "chat.activity.captureWebDone",
        status: "completed",
        duration_ms: 4000,
      },
    },
  ]
  const units = foldActivityUnits(buildConversationUnits(rows), undefined, "u1")
  const { container } = render(
    <ChatConversation
      conversationUnits={units}
      chatOutputs={[]}
      skillOptions={[]}
      openOutputViewer={vi.fn()}
      chatBusy
      onSuggestionClick={vi.fn()}
      onStructureVisible={vi.fn()}
      presentationRecovery={null}
      currentActivityRowKeysRef={{ current: new Set(["act1"]) }}
      liveWorkFoldKey="act1"
      liveMode="live_post_tool_thinking"
      liveFocus="正在编排 45 秒分镜与字幕"
      postToolThinkingStartedAtMs={Date.now() - 3000}
      nowRow={{ activity_id: "__think__", kind: "think", status: "active", key: null }}
      bottomNowRow={null}
      activeTurnId="u1"
      scrollerSendRef={{ current: null }}
    />,
  )
  const title = container.querySelector(".ui-thinkc__title")?.textContent ?? ""
  expect(title).toContain("chat.thinking")
  expect(title).not.toContain("正在编排 45 秒分镜与字幕")
})
