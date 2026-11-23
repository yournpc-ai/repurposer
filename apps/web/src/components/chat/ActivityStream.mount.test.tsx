// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import type { WorkTrailEntry } from "./timeline/types"
import { WorkSegmentRow } from "./ActivityStream"

const { anchor } = vi.hoisted(() => ({ anchor: vi.fn() }))
vi.mock("@/components/chat/MessageScroller", () => ({
  useMessageScrollerViewportAnchor: () => anchor,
}))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string, values?: { count?: number; elapsed?: string }) => [key, values?.count ?? values?.elapsed].filter(v => v != null).join(" ") }) }))
afterEach(() => { cleanup(); anchor.mockClear() })

const trail: WorkTrailEntry[] = [
  { kind: "activity", rowKey: "upload", activity: {
    activity_id: "upload", kind: "read", status: "completed", key: "chat.activity.uploadDone",
  } },
  { kind: "note", rowKey: "note", text: "Checking the edit." },
]

it("keeps the same focusable disclosure across settlement and anchors manual changes", () => {
  const view = render(<WorkSegmentRow liveLabel="Checking" trail={trail} />)
  const header = screen.getByRole("button")
  expect(header.tagName).toBe("BUTTON")
  header.focus()
  expect(header.tabIndex).toBe(0)
  expect(header.getAttribute("aria-expanded")).toBe("false")
  fireEvent.click(header)
  expect(screen.getAllByRole("listitem")).toHaveLength(2)
  view.rerender(<WorkSegmentRow elapsedMs={16000} trail={trail} />)
  expect(header).toBe(document.activeElement)
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(screen.queryByRole("listitem")).toBeNull()
  fireEvent.click(header)
  expect(screen.getAllByRole("listitem")[1].textContent).toBe("Checking the edit.")
  expect(anchor).toHaveBeenCalledTimes(2)
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
