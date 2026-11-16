import { describe, expect, it, vi } from "vitest"

const fetchEventSourceMock = vi.hoisted(() => vi.fn())

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: fetchEventSourceMock,
}))
vi.mock("@/lib/api", () => ({
  API_URL: "http://localhost:8000",
  UNAUTHORIZED_EVENT: "test:unauthorized",
}))
vi.mock("@/lib/auth", () => ({
  clearAuth: vi.fn(),
  getToken: () => "test-token",
}))
vi.mock("@/lib/i18n", () => ({
  default: { language: "en" },
}))
vi.mock("@/lib/sse-probe", () => ({
  sseProbe: vi.fn(),
}))

import { streamChat } from "@/lib/chat-stream"

describe("chat stream Stop transport", () => {
  it("rejects when the dependency resolves after an external abort", async () => {
    // @microsoft/fetch-event-source@2.0.1 resolves on the caller's abort.
    fetchEventSourceMock.mockImplementation(
      (_url: string, options: { signal?: AbortSignal }) =>
        new Promise<void>((resolve) => {
          options.signal?.addEventListener("abort", () => resolve(), { once: true })
        }),
    )
    const controller = new AbortController()
    const pending = streamChat(
      { project_id: "project-1", message: "find sound effects" },
      { signal: controller.signal },
    )
    const rejection = expect(pending).rejects.toMatchObject({ name: "AbortError" })

    controller.abort()

    await rejection
  })
})
