import { describe, expect, it } from "vitest"
import { selectChatLiveState, type ChatLiveStateInput } from "./liveState"
import type { ConversationUnit, OverlayMessage, ProjectAsset } from "./types"

function baseInput(overrides: Partial<ChatLiveStateInput> = {}): ChatLiveStateInput {
  return {
    chatBusy: false,
    proseActive: false,
    messages: [],
    conversationUnits: [],
    activities: [],
    thinkingPhase: null,
    assets: [],
    sentAssetIds: new Set(),
    currentActivityRowKeys: new Set(),
    recoveredJobTurn: null,
    interimActivityGateCount: 0,
    ...overrides,
  }
}

function makeFold(overrides: Partial<Extract<ConversationUnit, { kind: "activityFold" }>> = {}): Extract<ConversationUnit, { kind: "activityFold" }> {
  return {
    kind: "activityFold",
    rowKey: "act-1",
    clockRowKey: "act-1",
    turnId: "turn-1",
    trail: [
      {
        kind: "activity",
        rowKey: "act-1",
        activity: {
          activity_id: "a1",
          kind: "read",
          status: "completed",
          key: "chat.activity.createVideoDone",
          at: "2026-11-24T10:00:00.000Z",
          duration_ms: 2500,
        },
      },
    ],
    rows: [
      {
        activity_id: "a1",
        kind: "read",
        status: "completed",
        key: "chat.activity.createVideoDone",
        at: "2026-11-24T10:00:00.000Z",
        duration_ms: 2500,
      },
    ],
    failure: null,
    firstActivityAt: "2026-11-24T10:00:00.000Z",
    startedAtMs: Date.parse("2026-11-24T10:00:00.000Z"),
    endedAtMs: null,
    elapsedMs: null,
    openTail: true,
    ...overrides,
  }
}

describe("selectChatLiveState", () => {
  it("returns idle when nothing is busy or processing", () => {
    const state = selectChatLiveState(baseInput())
    expect(state).toEqual({
      mode: "idle",
      nowRow: null,
      liveFocus: null,
      liveWorkFoldKey: null,
      bottomNowRow: null,
      postToolThinkingStartedAtMs: null,
    })
  })

  it("enters live_working with bottomNowRow before the first tool host opens", () => {
    const state = selectChatLiveState(
      baseInput({
        chatBusy: true,
        thinkingPhase: "storyboarding",
      }),
    )
    expect(state.mode).toBe("live_working")
    expect(state.liveWorkFoldKey).toBeNull()
    expect(state.bottomNowRow?.kind).toBe("think")
    expect(state.bottomNowRow?.key).toBe("chat.thinkingPhases.storyboarding")
    expect(state.postToolThinkingStartedAtMs).toBeNull()
  })

  it("enters live_working with liveWorkFoldKey while an activity is actively running", () => {
    const active = {
      activity_id: "a2",
      seq: 2,
      kind: "read" as const,
      status: "active" as const,
      key: "chat.activity.insertMotionBlock",
    }
    const fold = makeFold({ liveActivity: active })
    const state = selectChatLiveState(
      baseInput({
        chatBusy: true,
        conversationUnits: [fold],
        activities: [active],
        currentActivityRowKeys: new Set(["act-1"]),
      }),
    )
    expect(state.mode).toBe("live_working")
    expect(state.liveWorkFoldKey).toBe("act-1")
    expect(state.nowRow).toBe(active)
    expect(state.bottomNowRow).toBeNull()
    expect(state.postToolThinkingStartedAtMs).toBeNull()
  })

  it("enters live_post_tool_thinking when all issued tools have settled and final prose has not started", () => {
    const fold = makeFold({
      rows: [
        {
          activity_id: "a1",
          kind: "read",
          status: "completed",
          key: "chat.activity.videoCapturePlanDone",
          at: "2026-11-24T10:00:00.000Z",
          duration_ms: 2000,
        },
        {
          activity_id: "a2",
          kind: "read",
          status: "completed",
          key: "chat.activity.generateSfxDone",
          at: "2026-11-24T10:00:04.000Z",
          duration_ms: 1500,
        },
      ],
      liveActivity: undefined,
      openTail: true,
    })
    const state = selectChatLiveState(
      baseInput({
        chatBusy: true,
        conversationUnits: [fold],
        activities: [
          { activity_id: "a1", seq: 1, kind: "read", status: "completed", key: "chat.activity.videoCapturePlanDone" },
          { activity_id: "a2", seq: 2, kind: "read", status: "completed", key: "chat.activity.generateSfxDone" },
        ],
        currentActivityRowKeys: new Set(["act-1"]),
      }),
    )
    expect(state.mode).toBe("live_post_tool_thinking")
    expect(state.liveWorkFoldKey).toBe("act-1")
    expect(state.bottomNowRow).toBeNull()
    expect(state.nowRow?.kind).toBe("think")
    expect(state.postToolThinkingStartedAtMs).toBe(Date.parse("2026-11-24T10:00:05.500Z"))
  })

  it("switches to streaming_final as soon as visible non-whitespace streaming prose arrives", () => {
    const fold = makeFold({ openTail: false, endedAtMs: Date.parse("2026-11-24T10:00:08.000Z") })
    const streamingMsg: OverlayMessage = {
      id: "m-final",
      role: "assistant",
      content: "已经按旁白节拍完成 3 幕编排。",
      streaming: true,
      turnId: "turn-1",
    }
    const state = selectChatLiveState(
      baseInput({
        chatBusy: true,
        proseActive: true,
        messages: [streamingMsg],
        conversationUnits: [fold],
        currentActivityRowKeys: new Set(["act-1"]),
      }),
    )
    expect(state.mode).toBe("streaming_final")
    expect(state.liveWorkFoldKey).toBeNull()
    expect(state.bottomNowRow).toBeNull()
    expect(state.postToolThinkingStartedAtMs).toBeNull()
  })

  it("never reopens a historical open fold that does not belong to currentActivityRowKeys", () => {
    const historicalFold = makeFold({ rowKey: "old-act" })
    const state = selectChatLiveState(
      baseInput({
        chatBusy: true,
        conversationUnits: [historicalFold],
        currentActivityRowKeys: new Set(["new-act"]),
      }),
    )
    expect(state.liveWorkFoldKey).toBeNull()
    expect(state.mode).toBe("live_working")
    expect(state.bottomNowRow?.kind).toBe("think")
  })

  it("surfaces processing asset stages when chat is idle", () => {
    const videoAsset: ProjectAsset = {
      id: "asset-1",
      type: "video",
      file_url: null,
      title: "demo.mp4",
      processing_status: "processing",
      processing_stage: "asr",
    }
    const state = selectChatLiveState(
      baseInput({
        assets: [videoAsset],
        sentAssetIds: new Set(["asset-1"]),
      }),
    )
    expect(state.mode).toBe("live_working")
    expect(state.bottomNowRow?.key).toBe("chat.material.transcribing")
    expect(state.bottomNowRow?.name).toBe("demo.mp4")
  })

  it("surfaces trimmed liveFocus only while chatBusy and not streaming final prose", () => {
    const busy = selectChatLiveState(
      baseInput({
        chatBusy: true,
        liveFocus: "  正在将 6 幕脚本编排为 Vox 风格  ",
      }),
    )
    expect(busy.liveFocus).toBe("正在将 6 幕脚本编排为 Vox 风格")

    const idle = selectChatLiveState(
      baseInput({
        chatBusy: false,
        liveFocus: "正在将 6 幕脚本编排为 Vox 风格",
      }),
    )
    expect(idle.liveFocus).toBeNull()

    const streaming = selectChatLiveState(
      baseInput({
        chatBusy: true,
        proseActive: true,
        liveFocus: "正在将 6 幕脚本编排为 Vox 风格",
        messages: [{ id: "m1", role: "assistant", content: "已完成编排", streaming: true }],
      }),
    )
    expect(streaming.mode).toBe("streaming_final")
    expect(streaming.liveFocus).toBeNull()
  })

  it("ignores focus and steps frames inside activities when determining active tool state", () => {
    const fold = makeFold({ liveActivity: undefined, openTail: true })
    const state = selectChatLiveState(
      baseInput({
        chatBusy: true,
        conversationUnits: [fold],
        activities: [
          { activity_id: "__focus__", seq: 1, kind: "focus", status: "active", key: null, focus: "正在编排" },
          {
            activity_id: "__steps__",
            seq: 2,
            kind: "steps",
            status: "active",
            key: null,
            steps: [
              { title: "采集网页", status: "done" },
              { title: "编排动效", status: "in_progress" },
            ],
          },
        ],
        currentActivityRowKeys: new Set(["act-1"]),
      }),
    )
    expect(state.mode).toBe("live_post_tool_thinking")
    expect(state.nowRow?.kind).toBe("think")
  })
})
