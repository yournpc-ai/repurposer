// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { ApprovalCard } from "./approval-card-clean"
import { ToolCallCard, ToolCallGroup } from "./tool-call-card-clean"

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
afterEach(cleanup)

it("retains order and distinct outcomes for consecutive invocations of the same tool", () => {
  render(<ToolCallGroup>
    <ToolCallCard key="a" name="voice" status="unknown">First receipt</ToolCallCard>
    <ToolCallCard key="b" name="voice" status="notExecuted">Second receipt</ToolCallCard>
  </ToolCallGroup>)
  fireEvent.click(screen.getByRole("button", { name: "agentReceipt.group" }))
  const labels = screen.getAllByRole("status").map(node => node.textContent)
  expect(labels.slice(-2)).toEqual(["voice · agentReceipt.unknown", "voice · agentReceipt.notExecuted"])
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
