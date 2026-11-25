// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { MessageActionBar } from "./MessageActionBar"

const { submitMock } = vi.hoisted(() => ({
  submitMock: vi.fn(),
}))

vi.mock("@/lib/workbench", async () => {
  const actual = await vi.importActual<typeof import("@/lib/workbench")>("@/lib/workbench")
  return {
    ...actual,
    submitMessageFeedback: submitMock,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.count != null ? `${key}:${opts.count}` : key,
  }),
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

beforeEach(() => {
  submitMock.mockReset()
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: vi.fn().mockResolvedValue(undefined),
    },
  })
})

afterEach(() => {
  cleanup()
})

describe("MessageActionBar", () => {
  it("copies markdown text and displays relative timestamp", async () => {
    const twoMinAgo = new Date(Date.now() - 120_000).toISOString()
    render(
      <MessageActionBar
        messageId="msg-1"
        text="# Hello video"
        createdAt={twoMinAgo}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "chat.feedback.copy" }))
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("# Hello video")
    })
    const copiedBtn = screen.getByRole("button", { name: "chat.feedback.copied" })
    const checkSvg = copiedBtn.querySelector("svg")
    expect(checkSvg?.getAttribute("class") ?? "").toContain("text-foreground")
    expect(checkSvg?.getAttribute("class") ?? "").not.toMatch(/text-(emerald|green|sky|blue)-/)
    expect(screen.getByText("notifications.minutesAgo:2")).toBeTruthy()
  })

  it("toggles good feedback optimistically and rolls back on failure", async () => {
    submitMock.mockResolvedValueOnce({
      message_id: "msg-1",
      feedback: { rating: "good", tags: [], reason: null },
    })
    const onChange = vi.fn()
    render(
      <MessageActionBar
        messageId="msg-1"
        text="Great cut"
        onFeedbackChange={onChange}
      />,
    )

    const goodBtn = screen.getByRole("button", { name: "chat.feedback.good" })
    fireEvent.click(goodBtn)
    expect(goodBtn.getAttribute("aria-pressed")).toBe("true")
    await waitFor(() => {
      expect(submitMock).toHaveBeenCalledWith("msg-1", {
        rating: "good",
        tags: [],
        reason: null,
      })
    })

    // Failure rollback when clicking again to clear
    submitMock.mockRejectedValueOnce(new Error("Network down"))
    fireEvent.click(goodBtn)
    await waitFor(() => {
      expect(goodBtn.getAttribute("aria-pressed")).toBe("true")
    })
  })

  it("opens non-blocking Popover on bad click and submits tags + reason", async () => {
    submitMock
      .mockResolvedValueOnce({
        message_id: "msg-2",
        feedback: { rating: "bad", tags: [], reason: null },
      })
      .mockResolvedValueOnce({
        message_id: "msg-2",
        feedback: {
          rating: "bad",
          tags: ["pacing"],
          reason: "字幕略快",
        },
      })

    render(<MessageActionBar messageId="msg-2" text="Draft reply" />)

    const badBtn = screen.getByRole("button", { name: "chat.feedback.bad" })
    fireEvent.click(badBtn)
    expect(badBtn.getAttribute("aria-pressed")).toBe("true")

    await waitFor(() => {
      expect(submitMock).toHaveBeenCalledWith("msg-2", {
        rating: "bad",
        tags: [],
        reason: null,
      })
    })

    // Select a tag and enter reason in Popover (JSDOM lacks native [popover] top-layer visibility)
    fireEvent.click(screen.getByRole("button", { name: "chat.feedback.tags.pacing", hidden: true }))
    fireEvent.change(screen.getByPlaceholderText("chat.feedback.reasonPlaceholder"), {
      target: { value: "字幕略快" },
    })
    fireEvent.click(screen.getByRole("button", { name: "chat.feedback.submit", hidden: true }))

    await waitFor(() => {
      expect(submitMock).toHaveBeenLastCalledWith("msg-2", {
        rating: "bad",
        tags: ["pacing"],
        reason: "字幕略快",
      })
    })
  })
})
