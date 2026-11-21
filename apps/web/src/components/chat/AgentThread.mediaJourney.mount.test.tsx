// @vitest-environment jsdom
import type { ReactNode } from "react"
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { apiFetch } from "@/lib/api"
import { AgentThread } from "./AgentThread"
import type { WorkflowStep } from "@/lib/types"
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
const runState = vi.hoisted(() => ({ steps: [] as WorkflowStep[], status: "running", terminal: false, uploadRetryCount: 0 }))
vi.mock("@/lib/use-run-events", async (original) => ({
  ...await original<typeof import("@/lib/use-run-events")>(),
  useRunEvents: () => runState,
}))
vi.mock("@/components/ui/message-scroller", () => {
  const Container = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  return {
    MessageScroller: Container, MessageScrollerProvider: Container, MessageScrollerContent: Container,
    MessageScrollerItem: Container, MessageScrollerViewport: Container,
    MessageScrollerButton: () => null, useMessageScrollerViewportAnchor: () => vi.fn(), useMessageScroller: () => ({ scrollToEnd: vi.fn() }),
  }
})
const reply = vi.hoisted(() => ({
  hold: "", first: () => {}, rest: () => {},
}))
vi.mock("@/lib/typewriter", () => ({
  createTypewriter: (append: (text: string) => void) => {
    let drained = Promise.resolve()
    return {
      push(text: string) {
        if (!text || text !== reply.hold) return append(text)
        drained = new Promise<void>((resolve) => {
          reply.first = () => append(text.slice(0, 1))
          reply.rest = () => { append(text.slice(1)); resolve() }
        })
      },
      drain: () => drained, flush: vi.fn(),
    }
  },
}))

function mark(seq: number, run: string | null, state: string, role?: "music" | "narration"): HistoryRow {
  return {
    id: `m${seq}`, seq, role: "assistant", content: role === "narration" ? "" : `message ${seq}`, created_at: "2026-11-18T12:00:00Z",
    workflow_run_id: run, question: null, answer: null, turn_id: "opening",
    intent: {
      ...(run && role ? { type: "trigger_review", trigger: "run_completed", suggestions: [] } : {}),
      ...(role === "narration" ? { presentation: "media_progress", prepared_audio: { role, scene_id: `scene-${seq}` } } : {}),
      media_journey: { opening_id: "opening", state },
    },
    blocks: role === "music" && state === "complete" ? [{
      kind: "audio_playback", project_id: "p", items: [{
        role, scene_id: null, title: role + seq,
        snapshot_id: "fixed", digest: "hash", duration_seconds: 2, peaks: [0.7, 0.1], analysis_digest: "report",
      }],
    }] : [],
  }
}

afterEach(() => {
  cleanup()
  reply.hold = ""
  Object.assign(runState, { steps: [], status: "running", terminal: false })
  vi.mocked(apiFetch).mockReset()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

it("folds routine recording and delivers one playable score live and after reopening", async () => {
  vi.useFakeTimers()
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {})
  const rows = [mark(1, "image-run", "active")]
  const messagesPath = "/api/v1/chat/conversations/conversation/messages"
  let reads = 0
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path.endsWith("/results")) return Response.json({ outputs: [] })
    if (path === "/api/v1/chat/conversation?project_id=p") return Response.json({ id: "conversation" })
    if (path === messagesPath) { reads++; return Response.json({ items: rows }) }
    if (path.endsWith("/assets") || path.endsWith("/outputs")) return Response.json([])
    return new Response(null, { status: 404 })
  })
  const onProjectChanged = vi.fn()
  const dock = <AgentThread projectId="p" prompt="" initialRunId="image-run" onProjectChanged={onProjectChanged} />
  const view = render(dock)
  await act(async () => {})
  expect(screen.getByText("message 1")).toBeDefined()
  rows.push(mark(2, "voice-run", "active"), mark(3, "voice-run", "active", "narration"))
  rows.push({ ...mark(4, "other-run", "active"), intent: { media_journey: { opening_id: "unrelated", state: "active" } } })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(onProjectChanged).toHaveBeenCalledWith("voice-run")
  expect(screen.queryByRole("button", { name: "chat.audio.play" })).toBeNull()
  expect(screen.queryByText("message 4")).toBeNull()
  rows.push(mark(5, null, "active", "narration"), mark(6, "music-run", "active"))
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(onProjectChanged).toHaveBeenCalledWith("music-run")
  const music = mark(7, "music-run", "active", "music")
  rows.push({ ...music, content: "配乐已准备好。" })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.queryByText("music7")).toBeNull()
  rows[rows.length - 1] = { ...mark(7, "music-run", "complete", "music"), content: "配乐已准备好。" }
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getAllByRole("button", { name: "chat.audio.play" })).toHaveLength(1)
  expect(screen.getAllByText("配乐已准备好。")).toHaveLength(1)
  const stoppedReads = reads
  await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
  expect(reads).toBe(stoppedReads)
  view.unmount()
  render(dock)
  await act(async () => {})
  expect(screen.getAllByRole("button", { name: "chat.audio.play" })).toHaveLength(1)
  expect(screen.getAllByText("配乐已准备好。")).toHaveLength(1)
  expect(screen.queryByText("narration5")).toBeNull()
})

it("updates tool status in place and shows each worker reply once, live and on reopen", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "performance"] })
  const start = "2026-11-18T12:00:00Z"
  const rows: HistoryRow[] = [{
    ...mark(1, null, "active"), intent: {
      type: "activity", frame: { activity_id: "inspect", kind: "read", status: "completed",
        key: "chat.activity.visualAssetsDone", at: start, duration_ms: 1000 },
    },
  }, {
    ...mark(2, "image-run", "active"), content: "分镜图片准备",
    question: { kind: "task_book", question: "", requires_confirmation: false }, answer: { kind: "start" },
    intent: { media_journey: { opening_id: "opening", state: "active", scene_order: ["intro", "end"] }, tasks: [{ tool: "prepare_visual_assets" }] },
    blocks: [{ kind: "system_notice", text: "估价随运行确定" }],
  }]
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path.endsWith("/messages")) return Response.json({ items: rows })
    if (path.includes("/chat/conversation?")) return Response.json({ id: "c" })
    if (path.endsWith("/results")) return Response.json({ outputs: [] })
    if (path.endsWith("/assets") || path.endsWith("/outputs")) return Response.json([])
    return new Response(null, { status: 404 })
  })
  const dock = (prompt: string) => <AgentThread projectId="p" prompt={prompt}
    initialRunId="image-run" onProjectChanged={vi.fn()} />
  const view = render(dock(""))
  await act(async () => {})
  const line = screen.getByText("chat.stepKinds.prepare_visual_assets")
  expect(screen.queryByText("分镜图片准备")).toBeNull()
  expect(screen.queryByText("估价随运行确定")).toBeNull()
  expect(screen.queryByText("chat.activityFold.worked")).toBeNull()
  expect(document.querySelector('[data-slot="run-response"]')).toBeNull()
  runState.steps = [{
    id: "step", kind: "prepare_visual_assets", seq: 0, status: "running", error: null, cost: null,
    started_at: start, finished_at: null, production_stages: [{
      event_id: "images", kind: "visual_assets", run_id: "image-run", step_id: "step", attempt: 0,
      seq: 1, status: "running", started_at: start, finished_at: null, item_count: 0, scene_id: "intro",
    }],
  }]
  view.rerender(dock("progress"))
  await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
  expect(screen.getByText("正在准备第一条分镜…")).toBe(line)
  Object.assign(runState, { terminal: true, status: "completed" })
  view.rerender(dock("review"))
  await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
  expect(screen.getByText("chat.closingReview")).toBe(line)
  reply.hold = "五个分镜已准备好。"
  rows.push({
    ...mark(3, "image-run", "active"), turn_id: null, content: reply.hold,
    created_at: "2026-11-18T12:00:10Z", intent: { type: "trigger_review", trigger: "run_completed",
      presentation: "stage_summary", media_journey: { opening_id: "opening", state: "active" } },
  })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.queryByText(reply.hold)).toBeNull()
  await act(async () => reply.first())
  await act(async () => reply.rest())
  expect(screen.getAllByText(reply.hold)).toHaveLength(1)
  expect(screen.getByRole("button", { name: "chat.stop" })).toBeDefined()
  rows.push({
    ...rows[1], id: "m4", seq: 4, workflow_run_id: "voice-run", content: "分镜旁白准备",
    intent: { media_journey: { opening_id: "opening", state: "active" }, tasks: [{ tool: "prepare_narration", params: { scene_id: "intro" } }, { tool: "prepare_narration", params: { scene_id: "end" } }] },
    blocks: [{ kind: "system_notice", text: "估价 8–8 积分" }],
  })
  Object.assign(runState, { terminal: false, status: "running", steps: [] })
  await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
  const recordingLine = screen.getByText("chat.stepKinds.prepare_narration")
  expect(screen.queryByText("分镜旁白准备")).toBeNull()
  expect(screen.queryByText("估价 8–8 积分")).toBeNull()
  expect(document.querySelector('[data-slot="run-response"]')).toBeNull()
  runState.steps = [{
    id: "voice", kind: "prepare_narration", seq: 1, scene_index: 2, status: "running", error: null, cost: null,
    started_at: start, finished_at: null, production_stages: [{
      event_id: "record", kind: "speech_media", run_id: "voice-run", step_id: "voice", attempt: 0,
      seq: 2, status: "running", started_at: start, finished_at: null,
    }],
  }]
  view.rerender(dock("voice"))
  await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
  expect(screen.getByText("正在录制第二条旁白…")).toBe(recordingLine)
  expect(screen.queryByText("audio_snapshot")).toBeNull()
  rows.push({ ...mark(5, "voice-run", "active", "narration"), content: "分镜旁白已录制。" })
  rows.push({ ...mark(6, null, "active"), intent: { type: "interim_prose" }, content: "继续准备 s3。" })
  Object.assign(runState, { terminal: true, status: "completed" })
  view.rerender(dock("handoff"))
  await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
  expect(screen.getAllByText("分镜旁白已录制。")).toHaveLength(1)
  expect(screen.getAllByText("继续准备 s3。")).toHaveLength(1)
  reply.hold = "本次制作已完成。"
  rows.push({ ...mark(7, null, "complete"), content: reply.hold })
  await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
  await act(async () => reply.first())
  expect(screen.getAllByText("chat.activityFold.worked")).toContain(line)
  await act(async () => reply.rest())
  expect(screen.queryByText("chat.thinking")).toBeNull()
  expect(screen.queryByRole("button", { name: "chat.stop" })).toBeNull()
  fireEvent.click(line.closest('[role="button"]')!)
  expect(screen.queryByText("估价 8–8 积分")).toBeNull()
  view.unmount()
  render(dock(""))
  await act(async () => {})
  expect(screen.getAllByText("五个分镜已准备好。")).toHaveLength(1)
  expect(screen.getAllByText("分镜旁白已录制。")).toHaveLength(1)
  expect(screen.getAllByText("继续准备 s3。")).toHaveLength(1)
  expect(screen.getAllByText(reply.hold)).toHaveLength(1)
  expect(screen.queryByText("分镜图片准备")).toBeNull()
  expect(screen.queryByText("分镜旁白准备")).toBeNull()
  expect(document.querySelector('[data-slot="run-response"]')).toBeNull()
})

it("stops the original request between image delivery and narration and stays stopped on reopen", async () => {
  vi.useFakeTimers()
  Object.assign(runState, { terminal: true, status: "completed" })
  const result = { ...mark(2, "image-run", "active"), turn_id: null, intent: {
    type: "trigger_review", trigger: "run_completed", media_journey: { opening_id: "opening", state: "active" },
  } }
  const rows: HistoryRow[] = [{ ...mark(1, null, "active"), id: "opening", role: "user", intent: {} }, result]
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path.endsWith("/stop")) {
      result.intent.media_journey.state = "stopped"
      return Response.json({ accepted: true, journey_message: result })
    }
    if (path.endsWith("/messages")) return Response.json({ items: rows })
    if (path.includes("/chat/conversation?")) return Response.json({ id: "c" })
    if (path.endsWith("/results")) return Response.json({ outputs: [] })
    if (path.endsWith("/assets") || path.endsWith("/outputs")) return Response.json([])
    return new Response(null, { status: 404 })
  })
  const dock = <AgentThread projectId="p" prompt="" initialRunId="image-run" onProjectChanged={vi.fn()} />
  const view = render(dock)
  await act(async () => {})
  expect(screen.getByText("chat.thinking")).toBeDefined()
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "chat.stop" })))
  expect(apiFetch).toHaveBeenCalledWith("/api/v1/chat/turns/opening/stop", { method: "POST", body: { scope: "media_preparation" } })
  expect(screen.queryByText("chat.thinking")).toBeNull()
  expect(screen.getByText("message 2")).toBeDefined()
  view.unmount()
  render(dock)
  await act(async () => {})
  expect(screen.queryByRole("button", { name: "chat.stop" })).toBeNull()
  expect(screen.queryByText("chat.thinking")).toBeNull()
})

it.each(["blocked", "stopped"])("stops following a journey after its durable %s message", async (state) => {
  vi.useFakeTimers()
  const rows = [mark(1, "image-run", "active")]
  let reads = 0
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path === "/api/v1/chat/conversation?project_id=p") return Response.json({ id: "c" })
    if (path.endsWith("/messages")) { reads++; return Response.json({ items: rows }) }
    if (path.endsWith("/results")) return Response.json({ outputs: [] })
    if (path.endsWith("/assets") || path.endsWith("/outputs")) return Response.json([])
    return new Response(null, { status: 404 })
  })
  render(<AgentThread projectId="p" prompt="" initialRunId="image-run" onProjectChanged={vi.fn()} />)
  await act(async () => {})
  rows.push({ ...mark(2, null, state), content: state })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getAllByText(state)).toHaveLength(1)
  const finalReads = reads
  await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
  expect(reads).toBe(finalReads)
  expect(screen.queryByRole("button", { name: "chat.audio.play" })).toBeNull()
})

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
