// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
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

it("keeps live chat work noninteractive and allows keyboard access to work details", () => {
  const view = render(<WorkSegmentRow activity={{ activity_id: "upload", kind: "read", status: "active", key: "chat.activity.upload" }} />)
  expect(screen.queryByRole("button")).toBeNull()
  view.rerender(<WorkSegmentRow liveLabel="Making video" liveDetails={<span>Render</span>} />)
  const header = screen.getByRole("button")
  expect(header.getAttribute("aria-expanded")).toBe("true")
  fireEvent.keyDown(header, { key: "Enter" })
  expect(header.getAttribute("aria-expanded")).toBe("false")
})
