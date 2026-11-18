// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { RunTaskList } from "./RunTaskList"
import { WorkSegmentRow } from "./ActivityStream"

const { anchor } = vi.hoisted(() => ({ anchor: vi.fn() }))
vi.mock("@/components/ui/message-scroller", () => ({
  useMessageScrollerViewportAnchor: () => anchor,
}))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
afterEach(() => { cleanup(); anchor.mockClear() })

it("opens and closes a settled upload receipt with keyboard and anchors both changes", () => {
  render(<WorkSegmentRow elapsedMs={1000} rows={[{
    activity_id: "upload", kind: "read", status: "completed", key: "chat.activity.uploadDone",
  }]} />)
  const header = screen.getByRole("button")
  expect(header.tabIndex).toBe(0)
  expect(header.getAttribute("aria-expanded")).toBe("false")
  fireEvent.keyDown(header, { key: "Enter" })
  expect(header.getAttribute("aria-expanded")).toBe("true")
  fireEvent.keyDown(header, { key: " " })
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(anchor).toHaveBeenCalledTimes(2)
})

it("keeps live chat work noninteractive and allows keyboard access to Run details", () => {
  const view = render(<WorkSegmentRow activity={{ activity_id: "upload", kind: "read", status: "active", key: "chat.activity.upload" }} />)
  expect(screen.queryByRole("button")).toBeNull()
  view.rerender(<WorkSegmentRow liveLabel="Making video" liveDetails={<span>Render</span>} />)
  const header = screen.getByRole("button")
  expect(header.getAttribute("aria-expanded")).toBe("true")
  fireEvent.keyDown(header, { key: "Enter" })
  expect(header.getAttribute("aria-expanded")).toBe("false")
})


it.each([
  ["2026-11-18T12:00:03Z", "chat.activityFold.worked"],
  [null, "chat.activityFold.workedWithoutTime"],
])("keeps a failed run neutral and shows its error on disclosure (%s)", (finished, label) => {
  const start = "2026-11-18T12:00:00Z"
  render(<RunTaskList
    steps={[{ id: "image", kind: "prepare_visual_assets", seq: 0, status: "failed",
      error: "Image preparation failed", cost: null, started_at: start, finished_at: finished }]}
    runStartedAt={start} workEndedAtMs={null} title="Run failed" terminal failed
    reviewPending={false} narrativeFallback="" hasUploads={false}
  />)
  const header = screen.getByRole("button")
  expect(header.textContent).toBe(label)
  expect(header.querySelector(".text-destructive")).toBeNull()
  expect(screen.queryByText(/Image preparation failed/)).toBeNull()
  fireEvent.click(header)
  expect(screen.getByText(/Image preparation failed/).classList.contains("text-destructive")).toBe(true)
  expect(header.textContent).toBe(label)
})
