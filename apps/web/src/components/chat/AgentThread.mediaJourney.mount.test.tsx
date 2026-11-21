// @vitest-environment jsdom
import type { ReactNode } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { apiFetch } from "@/lib/api"
import { AgentThread } from "./AgentThread"
import type { HistoryRow } from "./timeline/history"

vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(), apiFetch: vi.fn(),
}))
const { t } = vi.hoisted(() => ({ t: (key: string, values?: {name?: string}) => {
  if (key.endsWith("pictureScene")) return "正在准备第" + values?.name + "条分镜…"
  if (key.endsWith("voiceScene")) return "正在录制第" + values?.name + "条旁白…"
  return key
} }))
vi.mock("react-i18next", async (original) => ({
  ...await original<typeof import("react-i18next")>(), useTranslation: () => ({ t }),
}))
vi.mock("@/components/settings/settings-dialog-context", () => ({ useSettingsDialog: () => ({ openCreditTopup: vi.fn() }) }))
vi.mock("@/components/mentions/MentionEditor", () => ({ MentionEditor: () => null }))
vi.mock("@/components/ui/message-scroller", () => {
  const Container = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  return {
    MessageScroller: Container, MessageScrollerProvider: Container, MessageScrollerContent: Container,
    MessageScrollerItem: Container, MessageScrollerViewport: Container,
    MessageScrollerButton: () => null, useMessageScrollerViewportAnchor: () => vi.fn(), useMessageScroller: () => ({ scrollToEnd: vi.fn() }),
  }
})
afterEach(() => { cleanup(); vi.mocked(apiFetch).mockReset() })

it("restores an in-flight native job and stops its original opening after refresh", async () => {
  const time = "2026-11-21T12:00:00Z"
  const base = { question: null, answer: null, workflow_run_id: null }
  const rows: HistoryRow[] = [
    { ...base, id: "opening", seq: 1, role: "user", turn_state: "in_flight", content: "record", created_at: time },
    { ...base, id: "activity", seq: 2, role: "assistant", turn_id: "opening", content: "", created_at: time,
      intent: { type: "activity", frame: { activity_id: "a", kind: "read", status: "active",
        key: "chat.activity.audio", call_id: "call", group_id: "g", call_index: 0 } } },
    { ...base, id: "receipt", seq: 3, role: "assistant", turn_id: "opening", content: "", created_at: time,
      intent: { media_job: "job", native_call_id: "call", operation: "generate_voice", media_status: "accepted" } },
  ]
  vi.mocked(apiFetch).mockImplementation(async (path, options) => {
    if (path.endsWith("/messages")) return Response.json({ items: rows })
    if (path.includes("/chat/conversation?")) return Response.json({ id: "c" })
    if (path.endsWith("/results")) return Response.json({ outputs: [] })
    if (path.endsWith("/assets") || path.endsWith("/outputs")) return Response.json([])
    if (path === "/api/v1/chat/turns/opening/stop") {
      expect(options?.body).toMatchObject({ activity_ids: ["activity"] })
      rows[0].turn_state = "cancelled"
      rows[2] = { ...rows[2], content: "Recording outcome unknown", intent: {
        native_call_id: "call", media_job: "job", media_result: { status: "provider_unknown" },
      } }
      return Response.json({ turn_state: "cancelled" })
    }
    return new Response(null, { status: 404 })
  })
  render(<AgentThread projectId="p" prompt="" onProjectChanged={vi.fn()} />)
  fireEvent.click(await screen.findByRole("button", { name: "chat.stop" }))
  expect(await screen.findByText("Recording outcome unknown")).toBeDefined()
  expect(screen.queryByRole("button", { name: "chat.stop" })).toBeNull()
})
