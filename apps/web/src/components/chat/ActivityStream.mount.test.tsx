// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import type { ActivitySemanticDetail, WorkTrailEntry } from "./timeline/types"
import { semanticActivityLabel, TOOL_ACTIONS, WorkSegmentRow } from "./ActivityStream"
import en from "@/lib/i18n/locales/en"
import zh from "@/lib/i18n/locales/zh"
import type { TFunction } from "i18next"

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

it("collapses live and settled trails by default, honors manual toggle, and resets on settlement", () => {
  const view = render(<WorkSegmentRow liveLabel="Checking" trail={trail} />)
  const header = screen.getByRole("button")
  expect(header.tagName).toBe("BUTTON")
  header.focus()
  expect(header.tabIndex).toBe(0)
  // Both live and settled status rows default collapsed; clicking expands on demand
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(screen.queryByRole("listitem")).toBeNull()
  expect(screen.queryByTestId("live-brief-stream")).toBeNull()
  // Manual expand override is respected while live
  fireEvent.click(header)
  expect(header.getAttribute("aria-expanded")).toBe("true")
  expect(screen.getAllByRole("listitem")).toHaveLength(2)
  // Settlement resets override and stays collapsed as Worked for ...
  view.rerender(<WorkSegmentRow elapsedMs={16000} trail={trail} />)
  expect(header).toBe(document.activeElement)
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(screen.queryByRole("listitem")).toBeNull()
  // Clicking collapsed settled row expands cleanly
  fireEvent.click(header)
  expect(screen.getAllByRole("listitem")[1].textContent).toBe("Checking the edit.")
  expect(anchor).toHaveBeenCalledTimes(2)
})

it("renders a live-timed Thinking row at the bottom of the trail when expanded during post-tool thinking", () => {
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
    fireEvent.click(screen.getByRole("button"))
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
    "insert_text",
    "edit_text",
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

function makeLocaleT(dict: Record<string, unknown>): TFunction {
  const resolve = (key: string): string | undefined => {
    const parts = key.split(".")
    let cur: unknown = dict
    for (const part of parts) {
      if (cur == null || typeof cur !== "object") return undefined
      cur = (cur as Record<string, unknown>)[part]
    }
    return typeof cur === "string" ? cur : undefined
  }
  return ((key: string, opts?: Record<string, unknown>) => {
    const raw = resolve(key)
    if (raw === undefined) {
      return typeof opts?.defaultValue === "string" ? opts.defaultValue : key
    }
    if (!opts) return raw
    return raw.replace(/\{\{(\w+)\}\}/g, (_, k: string) => String(opts[k] ?? ""))
  }) as unknown as TFunction
}

it("renders deterministic semantic parameter labels in both ZH and EN for all 8 high-frequency tools", () => {
  const tZh = makeLocaleT(zh as unknown as Record<string, unknown>)
  const tEn = makeLocaleT(en as unknown as Record<string, unknown>)

  const cases: { detail: ActivitySemanticDetail; zhActive: string; enActive: string; zhDone: string; enDone: string }[] = [
    {
      detail: { kind: "style", preset: "vox_editorial" },
      zhActive: "切换整片为Vox 报刊风格",
      zhDone: "已切换整片为Vox 报刊风格",
      enActive: "Switching style to Vox Editorial",
      enDone: "Switched style to Vox Editorial",
    },
    {
      detail: { kind: "motion_block_insert", block: "data_chart", window: "12–17s" },
      zhActive: "加入数据图表幕（12–17s）",
      zhDone: "已加入数据图表幕（12–17s）",
      enActive: "Adding Data Chart act (12–17s)",
      enDone: "Added Data Chart act (12–17s)",
    },
    {
      detail: { kind: "motion_block_update", aspects: ["camera", "callout"] },
      zhActive: "调整动效幕 · 镜头运镜 / 焦点标注",
      zhDone: "已调整动效幕 · 镜头运镜 / 焦点标注",
      enActive: "Updating motion block · camera / callouts",
      enDone: "Updated motion block · camera / callouts",
    },
    {
      detail: { kind: "text_insert", preset: "lower_third_tag", position: "bottom_left", snippet: "SARAH LIN" },
      zhActive: "左下角加入人名条 · SARAH LIN",
      zhDone: "左下角已加入人名条 · SARAH LIN",
      enActive: "Adding Lower Third (bottom-left) · SARAH LIN",
      enDone: "Added Lower Third (bottom-left) · SARAH LIN",
    },
    {
      detail: { kind: "text_insert", preset: "bilingual_cinema", bilingual: true, window: "0.5–4s" },
      zhActive: "加入双语字幕（0.5–4s）",
      zhDone: "已加入双语字幕（0.5–4s）",
      enActive: "Adding bilingual captions (0.5–4s)",
      enDone: "Added bilingual captions (0.5–4s)",
    },
    {
      detail: { kind: "text_edit", scope: "all_derived_captions", preset: "karaoke_focus" },
      zhActive: "字幕切换为逐词高亮",
      zhDone: "已将字幕切换为逐词高亮",
      enActive: "Switching captions to Karaoke Focus",
      enDone: "Switched captions to Karaoke Focus",
    },
    {
      detail: { kind: "sfx", recipe: "sub_swell" },
      zhActive: "合成音效 · 低频起势",
      zhDone: "已合成音效 · 低频起势",
      enActive: "Synthesizing SFX · Sub Swell",
      enDone: "Synthesized SFX · Sub Swell",
    },
    {
      detail: { kind: "audio_edit", aspects: ["gain", "fade"] },
      zhActive: "调整音频 · 电平 / 淡入淡出",
      zhDone: "已调整音频 · 电平 / 淡入淡出",
      enActive: "Adjusting audio · gain / fades",
      enDone: "Adjusted audio · gain / fades",
    },
    {
      detail: { kind: "transition", preset: "zoom_through" },
      zhActive: "设置镜头转场 · 推进缩放",
      zhDone: "已设置镜头转场 · 推进缩放",
      enActive: "Setting transition · Zoom Through",
      enDone: "Set transition · Zoom Through",
    },
  ]

  for (const c of cases) {
    expect(semanticActivityLabel(c.detail, false, tZh)).toBe(c.zhActive)
    expect(semanticActivityLabel(c.detail, true, tZh)).toBe(c.zhDone)
    expect(semanticActivityLabel(c.detail, false, tEn)).toBe(c.enActive)
    expect(semanticActivityLabel(c.detail, true, tEn)).toBe(c.enDone)
  }

  // Unknown enum tokens gracefully return null so callers fall back to static TOOL_ACTIONS
  expect(semanticActivityLabel({ kind: "style", preset: "unknown_style" }, false, tEn)).toBeNull()
  expect(semanticActivityLabel({ kind: "sfx", recipe: "unknown_recipe" }, true, tZh)).toBeNull()
})

it("displays liveFocus header while active and collapses cleanly to Worked on settlement", () => {
  const semanticTrail: WorkTrailEntry[] = [
    {
      kind: "activity",
      rowKey: "a1",
      activity: {
        activity_id: "a1",
        kind: "read",
        status: "completed",
        tool_name: "set_composition_style",
        key: "chat.activity.setCompositionStyleDone",
        detail: { kind: "style", preset: "vox_editorial" },
      },
    },
  ]
  const view = render(<WorkSegmentRow liveLabel="正在将 6 幕脚本编排为 Vox 风格" trail={semanticTrail} />)
  expect(screen.getByRole("button").textContent).toContain("正在将 6 幕脚本编排为 Vox 风格")
  view.rerender(<WorkSegmentRow elapsedMs={9000} trail={semanticTrail} />)
  expect(screen.getByRole("button").getAttribute("aria-expanded")).toBe("false")
  expect(screen.getByRole("button").textContent).toBe("chat.activityFold.worked 9s")
})

it("renders dynamic N/M steps progress ring and collapsible checklist for live and settled turns", () => {
  const plan = [
    { title: "采集网页与品牌资产", status: "done" as const },
    { title: "编写分幕脚本与旁白", status: "done" as const },
    { title: "编排 6 幕动效与字幕", status: "done" as const },
    { title: "叠加多轨音效与转场", status: "in_progress" as const },
    { title: "局部预览与视觉自检", status: "pending" as const },
  ]
  const view = render(
    <WorkSegmentRow
      liveLabel="正在叠加音效与转场"
      trail={trail}
      stepsPlan={plan}
    />,
  )
  const header = screen.getByRole("button")
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(header.textContent).toContain("chat.activityFold.stepsProgress")
  fireEvent.click(header)
  expect(screen.getByText("采集网页与品牌资产")).toBeTruthy()
  expect(screen.getByText("叠加多轨音效与转场")).toBeTruthy()

  // Settle all 5 steps: header collapses with 5/5 badge, expanding reveals persisted checklist
  const settledPlan = plan.map((s) => ({ ...s, status: "done" as const }))
  view.rerender(<WorkSegmentRow elapsedMs={14000} trail={trail} stepsPlan={settledPlan} />)
  expect(header.getAttribute("aria-expanded")).toBe("false")
  expect(header.textContent).toContain("chat.activityFold.worked 14s")
  expect(header.textContent).toContain("chat.activityFold.stepsProgress")
  fireEvent.click(header)
  expect(screen.getByText("局部预览与视觉自检")).toBeTruthy()
})

it("keeps a mid-turn recovered failure calm as Worked while preserving trail inspection", () => {
  const failed: WorkTrailEntry = {
    kind: "activity",
    rowKey: "export-guard",
    activity: {
      activity_id: "export-guard",
      tool_name: "export_video",
      kind: "run",
      key: null,
      status: "failed",
      error: "Preview required before export",
    },
  }
  render(<WorkSegmentRow trail={[failed]} elapsedMs={2000} recovered />)
  const header = screen.getByRole("button")
  expect(header.textContent).toBe("chat.activityFold.worked 2s")
  fireEvent.click(header)
  expect(screen.getByRole("listitem").textContent).toContain("Preview required before export")
})

it("drops synthetic repair/exhaustion markers from tool trail and displays normal Worked elapsed header", () => {
  const repairFailure = {
    activity_id: "rep-1",
    kind: "repair" as const,
    status: "failed" as const,
    key: "chat.activity.repair",
    duration_ms: 0,
  }
  render(<WorkSegmentRow trail={trail} failure={repairFailure} elapsedMs={125_000} />)
  const header = screen.getByRole("button")
  expect(header.textContent).toBe("chat.activityFold.worked 2m 5s")
  fireEvent.click(header)
  expect(screen.getAllByRole("listitem")).toHaveLength(2)
})
