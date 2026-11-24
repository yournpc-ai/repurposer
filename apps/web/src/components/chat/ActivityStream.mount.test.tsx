// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import type { WorkTrailEntry } from "./timeline/types"
import { TOOL_ACTIONS, WorkSegmentRow } from "./ActivityStream"
import en from "@/lib/i18n/locales/en"
import zh from "@/lib/i18n/locales/zh"

const { anchor } = vi.hoisted(() => ({ anchor: vi.fn() }))
vi.mock("@/components/chat/MessageScroller", () => ({
  useMessageScrollerViewportAnchor: () => anchor,
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count?: number; elapsed?: string }) =>
      [key, values?.count ?? values?.elapsed].filter(v => v != null).join(" "),
  }),
}))
afterEach(() => { cleanup(); anchor.mockClear() })

const trail: WorkTrailEntry[] = [
  { kind: "activity", rowKey: "upload", activity: {
    activity_id: "upload", kind: "read", status: "completed", key: "chat.activity.uploadDone",
  } },
  { kind: "note", rowKey: "note", text: "Checking the edit." },
]

it("opens live trail by default, honors manual collapse, and auto-collapses on settlement", () => {
  const view = render(<WorkSegmentRow liveLabel="Checking" trail={trail} />)
  const header = screen.getByRole("button")
  expect(header.tagName).toBe("BUTTON")
  header.focus()
  expect(header.tabIndex).toBe(0)
  // Phase 1: live working defaults open so interleaved steps & notes are visible immediately
  expect(header.getAttribute("aria-expanded")).toBe("true")
  expect(screen.getAllByRole("listitem")).toHaveLength(2)
  // Manual collapse override is respected while live
  fireEvent.click(header)
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(screen.queryByRole("listitem")).toBeNull()
  // Phase 3: settlement resets override and auto-collapses into Worked for ...
  view.rerender(<WorkSegmentRow elapsedMs={16000} trail={trail} />)
  expect(header).toBe(document.activeElement)
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(screen.queryByRole("listitem")).toBeNull()
  // Clicking collapsed settled row expands cleanly
  fireEvent.click(header)
  expect(screen.getAllByRole("listitem")[1].textContent).toBe("Checking the edit.")
  expect(anchor).toHaveBeenCalledTimes(2)
})

it("renders a live-timed Thinking row at the bottom of the trail during post-tool thinking", () => {
  vi.useFakeTimers()
  try {
    vi.setSystemTime(20_000)
    const view = render(
      <WorkSegmentRow
        liveLabel="Thinking"
        startedAtMs={10_000}
        postToolThinking={{ label: "Thinking", startedAtMs: 16_000 }}
        trail={trail}
      />,
    )
    const items = screen.getAllByRole("listitem")
    expect(items).toHaveLength(3)
    expect(items[2].getAttribute("data-kind")).toBe("thinking")
    expect(items[2].textContent).toContain("Thinking")
    expect(items[2].textContent).toContain("4s")
    act(() => vi.advanceTimersByTime(1000))
    expect(items[2].textContent).toContain("5s")
    // Settlement removes the thinking row and collapses to Worked
    view.rerender(<WorkSegmentRow elapsedMs={11_000} trail={trail} />)
    expect(screen.getByRole("button").getAttribute("aria-expanded")).toBe("false")
    expect(screen.getByRole("button").textContent).toBe("chat.activityFold.worked 11s")
  } finally {
    vi.useRealTimers()
  }
})

it("keeps a wait without evidence noninteractive and freezes the real clock on settlement", () => {
  vi.useFakeTimers()
  try {
    vi.setSystemTime(10_000)
    const view = render(<WorkSegmentRow liveLabel="Waiting" startedAtMs={8000} />)
    expect(screen.queryByRole("button")).toBeNull()
    expect(screen.getByText("2s")).toBeTruthy()
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByText("3s")).toBeTruthy()
    view.rerender(<WorkSegmentRow elapsedMs={3000} trail={trail} />)
    expect(vi.getTimerCount()).toBe(0)
    expect(screen.getByRole("button").textContent).toBe("chat.activityFold.worked 3s")
  } finally {
    vi.useRealTimers()
  }
})

it("opens the fixed export and shows the charged amount for its own call", () => {
  const onOpen = vi.fn()
  const exportTrail: WorkTrailEntry[] = [{
    kind: "activity", rowKey: "export", activity: {
      activity_id: "e", call_id: "native-e", tool_name: "export_video", status: "completed", kind: "run", key: null,
      jobReceipt: { callId: "native-e", status: "available", role: "export", outputId: "fixed-e", chargedCredits: 7 },
    },
  }]
  render(<WorkSegmentRow trail={exportTrail} elapsedMs={4000} onOpen={onOpen} />)
  expect(screen.queryByRole("button", { name: "common.preview" })).toBeNull()
  fireEvent.click(screen.getByRole("button"))
  expect(screen.getByRole("listitem").textContent).toContain("agentReceipt.chargedCredits 7")
  fireEvent.click(screen.getByRole("button", { name: "common.preview" }))
  expect(onOpen).toHaveBeenCalledWith("fixed-e")
})

it("keeps a terminal failure visible, and a recovered failure inspectable", () => {
  const failed: WorkTrailEntry = { kind: "activity", rowKey: "failure", activity: {
    activity_id: "failure", kind: "read", key: null, status: "failed", error: "Source unavailable",
  } }
  const view = render(<WorkSegmentRow trail={[...trail, failed]} elapsedMs={1000} />)
  expect(screen.getByRole("button").textContent).toContain("chat.failed")
  view.rerender(<WorkSegmentRow trail={[failed, ...trail]} elapsedMs={2000} />)
  const header = screen.getByRole("button")
  expect(header.textContent).toBe("chat.activityFold.worked 2s")
  fireEvent.click(header)
  expect(screen.getAllByRole("listitem")[0].textContent).toContain("Source unavailable")
})

it("covers 100% of high-frequency video tools in TOOL_ACTIONS, en.ts, and zh.ts with zero generic Job fallback", () => {
  const requiredTools = [
    "create_video",
    "preview_range",
    "inspect_timeline",
    "inspect_clip",
    "insert_audio",
    "insert_visual",
    "remove_clip",
    "split_clip",
    "trim_clip",
    "move_clip",
    "set_keyframe",
    "translate",
    "scale",
    "extend_still",
    "bind_clip_source",
    "deliver_video",
    "export_video",
    "review_video",
    "generate_image",
    "generate_voice",
    "generate_music",
    "generate_sfx",
    "edit_audio_clip",
    "insert_motion_block",
    "update_motion_block",
    "set_composition_style",
    "set_transition",
    "save_composition_as_skill",
    "instantiate_skill_blueprint",
    "prepare_video_materials",
    "capture_web",
    "analyze_brand",
    "search_music",
    "show_music_candidates",
    "select_music",
    "align_recording",
    "get_narration_alignment",
    "annotate_narration",
  ]
  const enActivity = en.chat.activity as Record<string, string | undefined>
  const zhActivity = zh.chat.activity as Record<string, string | undefined>
  const enToolName = en.chat.toolName as Record<string, string | undefined>
  const zhToolName = zh.chat.toolName as Record<string, string | undefined>

  for (const tool of requiredTools) {
    const action = TOOL_ACTIONS[tool]
    expect(action, `Missing TOOL_ACTIONS entry for ${tool}`).toBeTruthy()
    expect(enActivity[action!], `Missing en chat.activity.${action} for ${tool}`).toBeTruthy()
    expect(enActivity[`${action!}Done`], `Missing en chat.activity.${action}Done for ${tool}`).toBeTruthy()
    expect(zhActivity[action!], `Missing zh chat.activity.${action} for ${tool}`).toBeTruthy()
    expect(zhActivity[`${action!}Done`], `Missing zh chat.activity.${action}Done for ${tool}`).toBeTruthy()
    expect(enToolName[tool], `Missing en chat.toolName.${tool}`).toBeTruthy()
    expect(zhToolName[tool], `Missing zh chat.toolName.${tool}`).toBeTruthy()
    expect(enToolName[tool]).not.toBe(en.agentReceipt.job)
    expect(zhToolName[tool]).not.toBe(zh.agentReceipt.job)
  }
})
