// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { ApprovalCard } from "./approval-card-clean"
import { WorkSegmentRow } from "@/components/chat/ActivityStream"
import type { WorkTrailEntry } from "@/components/chat/timeline/types"

vi.mock("@/components/chat/MessageScroller", () => ({
  useMessageScrollerViewportAnchor: () => vi.fn(),
}))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
afterEach(cleanup)

it("retains order and distinct outcomes for consecutive invocations of the same tool in WorkSegmentRow", () => {
  const trail: WorkTrailEntry[] = [
    {
      kind: "activity",
      rowKey: "a",
      activity: {
        activity_id: "a",
        call_id: "a",
        tool_name: "generate_voice",
        kind: "read",
        status: "completed",
        call_state: "provider_unknown",
        key: null,
      },
    },
    {
      kind: "activity",
      rowKey: "b",
      activity: {
        activity_id: "b",
        call_id: "b",
        tool_name: "generate_voice",
        kind: "read",
        status: "completed",
        call_state: "not_executed",
        key: null,
      },
    },
  ]
  render(<WorkSegmentRow trail={trail} elapsedMs={3000} />)
  fireEvent.click(screen.getByRole("button"))
  const items = screen.getAllByRole("listitem").map(node => node.textContent)
  expect(items).toHaveLength(2)
  expect(items[0]).toContain("chat.toolName.generate_voice")
  expect(items[0]).toContain("agentReceipt.unknown")
  expect(items[1]).toContain("chat.toolName.generate_voice")
  expect(items[1]).toContain("agentReceipt.notExecuted")
})

it("requests a decision and waits for its owner to supply the outcome", () => {
  const onDecision = vi.fn()
  const props = { title: "Narration", quote: "2", limit: "3", submitting: false, onDecision }
  const view = render(<ApprovalCard {...props} status="pending" />)
  fireEvent.click(screen.getByRole("button", { name: "agentReceipt.approve" }))
  expect(onDecision).toHaveBeenCalledWith(true)
  expect(screen.getByRole("status").textContent).toBe("agentReceipt.pending")
  view.rerender(<ApprovalCard {...props} status="denied" />)
  expect(screen.queryByRole("button")).toBeNull()
  expect(screen.getByRole("status").textContent).toBe("agentReceipt.denied")
})
