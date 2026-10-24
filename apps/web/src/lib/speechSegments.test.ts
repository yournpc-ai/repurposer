/** speechSegments — the answer stream's checkpoint segmentation machine
 * (sendChat's inline law, extracted). The incident shape under test: an
 * option-pick continuation that speaks expectation prose, then runs a
 * design beat (activity rows land mid-turn), then streams the follow-up —
 * the live order must equal the persisted order (checkpoint → activity
 * rows → reply), across every prose-arrival timing. Pure node, zero DOM:
 * a manual-release typewriter makes the pacing deterministic (the cadence
 * is the real typewriter's job; ordering semantics don't depend on it),
 * and `tick()` marks the SSE frame boundary (frames arrive as separate
 * macrotasks — the checkpoint chain's microtasks settle between them). */

import { describe, expect, it } from "vitest"

import type { OverlayMessage } from "@/components/chat/historyReplay"
import { createSpeechSegments, isSpeechSegmentRow } from "./speechSegments"

/** A frame boundary: pending chain microtasks settle before the next SSE
 * frame is processed (fetch-event-source delivers frames as macrotasks). */
const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

/** A manual typewriter: push buffers, drain() parks until release() — so a
 * test can land an activity row WHILE a checkpoint is still typing (the
 * 14.6s design settle arriving mid-drain is the incident's interleaving). */
function manualTypewriter(append: (text: string) => void) {
  let buffer = ""
  let waiters: (() => void)[] = []
  return {
    push(text: string) {
      buffer += text
    },
    drain(): Promise<void> {
      if (!buffer) return Promise.resolve()
      return new Promise<void>((resolve) => waiters.push(resolve))
    },
    /** Release the buffered text through append and resolve the waiters. */
    release() {
      if (buffer) {
        const rest = buffer
        buffer = ""
        append(rest)
      }
      const pending = waiters
      waiters = []
      for (const resolve of pending) resolve()
    },
    /** Release only the first n chars — the mid-typing window (P1 回归:
     * 归属必须在输入边界钉死, 不能由「显示进度」决定). */
    releaseSome(n: number) {
      if (!buffer) return
      const part = buffer.slice(0, n)
      buffer = buffer.slice(n)
      append(part)
      if (!buffer) {
        const pending = waiters
        waiters = []
        for (const resolve of pending) resolve()
      }
    },
    flush() {
      this.release()
    },
    pending: () => buffer.length,
  }
}

function harness(baseId = "preview-1") {
  let rows: OverlayMessage[] = []
  const visible: { rowId: string; atMs: number }[] = []
  let tw!: ReturnType<typeof manualTypewriter>
  const segments = createSpeechSegments({
    baseId,
    apply: (fn) => {
      rows = fn(rows)
    },
    setProseActive: () => {},
    onVisible: (rowId, atMs) => visible.push({ rowId, atMs }),
    typewriterFactory: ((append: (text: string) => void) => {
      tw = manualTypewriter(append)
      return tw
    }) as never,
  })
  /** An activity row-append landing synchronously mid-turn (the design
   * beat's settle) — appended at the live edge exactly like ChatDock's
   * handleRowAppend. */
  const appendActivityRow = (id: string) => {
    rows = [
      ...rows,
      {
        id,
        role: "assistant" as const,
        content: "",
        at: new Date().toISOString(),
        activity: {
          activity_id: id,
          seq: 0,
          kind: "draft" as const,
          status: "completed" as const,
          key: "chat.activity.storyboardDone",
          duration_ms: 14628,
        },
      },
    ]
  }
  return {
    segments,
    tw: () => tw,
    appendActivityRow,
    ids: () => rows.map((m) => m.id),
    row: (id: string) => rows.find((m) => m.id === id),
    visible,
  }
}

describe("createSpeechSegments", () => {
  it("incident shape: pre-design prose → checkpoint → activity row → reply keeps the persisted order", async () => {
    // The incident's event sequence: expectation prose streams, the
    // checkpoint frame settles it, the design beat's settle row appends,
    // then the storyboard reply streams. Live order == DB order.
    const h = harness()
    h.segments.onDelta("那文案我来写：")
    h.segments.onDelta("先给你看结构，不直接开工。")
    h.segments.onCheckpoint(
      "那文案我来写：先给你看结构，不直接开工。",
      "2026-10-22T12:09:12Z",
    )
    h.tw().release() // the prose finishes typing (frame boundary)
    await tick() // the Path-A settle (rekey) runs between frames
    h.appendActivityRow("activity-row-1")
    h.segments.onDelta("分镜排好了：")
    h.segments.onDelta("七幕文字片。")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1#cp1", "activity-row-1", "preview-1"])
    const cp = h.row("preview-1#cp1")
    expect(cp?.content).toBe("那文案我来写：先给你看结构，不直接开工。")
    expect(cp?.streaming).toBe(false)
    // The trailing segment carries ONLY the reply — the checkpoint text
    // never merges into it (the live-only merged-bubble bug class). It
    // stays `streaming` until the ENVELOPE settles it (the splice's job —
    // the machine paces content, never settles the final row).
    const reply = h.row("preview-1")
    expect(reply?.content).toBe("分镜排好了：七幕文字片。")
    expect(reply?.streaming).toBe(true)
    // The suffix-pacing reference tracks only the settled bubble.
    expect(h.segments.previewText).toBe("分镜排好了：七幕文字片。")
    expect(h.segments.streamedAny).toBe(true)
  })

  it("an activity row landing WHILE the checkpoint is still typing still sorts after it (出生钉位)", async () => {
    // The design beat's 14.6s settle can land mid-drain: the checkpoint
    // bubble's position was pinned at its first delta's receipt, so the
    // row-append appends AFTER it even though the text hasn't finished.
    const h = harness()
    h.segments.onDelta("先给你看结构，不直接开工。")
    h.segments.onCheckpoint("先给你看结构，不直接开工。", "2026-10-22T12:09:12Z")
    await tick() // the settle starts; its drain is parked (text unreleased)
    h.appendActivityRow("activity-row-1")
    h.tw().release() // the checkpoint text finishes typing now
    await tick() // the rekey lands
    h.segments.onDelta("分镜排好了。")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1#cp1", "activity-row-1", "preview-1"])
    expect(h.row("preview-1#cp1")?.content).toBe("先给你看结构，不直接开工。")
    expect(h.row("preview-1")?.content).toBe("分镜排好了。")
  })

  it("Path B: a checkpoint frame with no prior streamed prose pins its row at arrival", async () => {
    const h = harness()
    h.segments.onCheckpoint("先去读一下版本事实。", "2026-10-22T12:00:00Z")
    // The row exists SYNCHRONOUSLY (出生钉位) — an activity row landing
    // before the drain still sorts after it.
    h.appendActivityRow("activity-row-1")
    await tick()
    h.tw().release()
    await tick() // Path B completes; the target returns to the main segment
    h.segments.onDelta("读完了：版本 2。")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1#cp1", "activity-row-1", "preview-1"])
    expect(h.row("preview-1#cp1")?.content).toBe("先去读一下版本事实。")
    expect(h.row("preview-1")?.content).toBe("读完了：版本 2。")
  })

  it("zero-delta reply after a checkpoint: the envelope-paced text births a fresh main row after the activity rows", async () => {
    const h = harness()
    h.segments.onDelta("先给你看结构。")
    h.segments.onCheckpoint("先给你看结构。", "2026-10-22T12:09:12Z")
    h.tw().release()
    await tick()
    h.appendActivityRow("activity-row-1")
    // The follow-up never streamed (repair round / non-streaming path) —
    // the envelope paces the full text through the same machine, and the
    // settled-bubble facts were reset by the Path-A settle.
    expect(h.segments.streamedAny).toBe(false)
    expect(h.segments.previewText).toBe("")
    h.segments.push("分镜排好了：七幕文字片。")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1#cp1", "activity-row-1", "preview-1"])
    expect(h.row("preview-1")?.content).toBe("分镜排好了：七幕文字片。")
    expect(h.segments.streamedAny).toBe(true)
  })

  it("no checkpoint at all: one bubble, unchanged pre-machine behavior", async () => {
    const h = harness()
    h.segments.onDelta("你好")
    h.segments.onDelta("，世界。")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1"])
    expect(h.row("preview-1")?.content).toBe("你好，世界。")
    expect(h.segments.previewText).toBe("你好，世界。")
    expect(h.segments.streamedAny).toBe(true)
  })

  it("two checkpoints serialize on one chain and keep birth order", async () => {
    const h = harness()
    h.segments.onDelta("第一句话。")
    h.segments.onCheckpoint("第一句话。", "2026-10-22T12:00:00Z")
    h.tw().release()
    await tick()
    h.segments.onDelta("第二句话。")
    h.segments.onCheckpoint("第二句话。", "2026-10-22T12:00:05Z")
    h.tw().release()
    await tick()
    h.appendActivityRow("activity-row-1")
    h.segments.onDelta("最终回复。")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual([
      "preview-1#cp1",
      "preview-1#cp2",
      "activity-row-1",
      "preview-1",
    ])
    expect(h.row("preview-1#cp1")?.content).toBe("第一句话。")
    expect(h.row("preview-1#cp2")?.content).toBe("第二句话。")
    expect(h.row("preview-1")?.content).toBe("最终回复。")
  })

  it("blank checkpoints are ignored", async () => {
    const h = harness()
    h.segments.onCheckpoint("   ")
    await h.segments.drain()
    expect(h.ids()).toEqual([])
  })

  it("flush mid-turn still releases buffered text (abort path never eats speech already pushed)", async () => {
    const h = harness()
    h.segments.onDelta("前半。")
    h.segments.flush()
    expect(h.row("preview-1")?.content).toBe("前半。")
  })
})

describe("first-visible display lifecycle", () => {
  it("receipt / empty / whitespace-only input never fires; the first real released character fires once", () => {
    const h = harness()
    h.segments.onDelta("")
    expect(h.ids()).toEqual([])
    h.segments.onDelta(" ")
    h.tw().release()
    expect(h.visible).toEqual([])

    h.segments.onDelta("Hi")
    expect(h.visible).toEqual([]) // buffered, still unseen
    h.tw().release()
    expect(h.visible.map((v) => v.rowId)).toEqual(["preview-1"])
    expect(h.row("preview-1")?.content).toBe(" Hi")
    h.tw().release()
    expect(h.visible).toHaveLength(1)
  })

  it("zero-delta envelope pacing seals on RELEASE, not on push", () => {
    const h = harness()
    h.segments.push("Envelope reply")
    expect(h.visible).toEqual([])
    h.tw().release()
    expect(h.visible.map((v) => v.rowId)).toEqual(["preview-1"])
  })

  it("Path A rekey preserves first-visible identity and stamps the checkpoint's drain", async () => {
    const h = harness()
    h.segments.onDelta("前")
    h.tw().release()
    expect(h.visible.map((v) => v.rowId)).toEqual(["preview-1"])

    h.segments.onCheckpoint("前文")
    h.appendActivityRow("activity-row-1")
    h.segments.onDelta("后")
    h.tw().release()
    await h.segments.drain()

    // No second signal for the promoted checkpoint: later activity belongs
    // to a NEW segment and must not be sealed by the old row's continuation.
    expect(h.visible.map((v) => v.rowId)).toEqual(["preview-1", "preview-1"])
    expect(h.row("preview-1#cp1")?.proseDrainedAtMs).toEqual(expect.any(Number))
    expect(h.ids()).toEqual(["preview-1#cp1", "activity-row-1", "preview-1"])
  })
})

describe("isSpeechSegmentRow", () => {
  it("matches the preview and its checkpoint segments, nothing else", () => {
    expect(isSpeechSegmentRow("preview-1", "preview-1")).toBe(true)
    expect(isSpeechSegmentRow("preview-1#cp1", "preview-1")).toBe(true)
    expect(isSpeechSegmentRow("preview-1#cp12", "preview-1")).toBe(true)
    expect(isSpeechSegmentRow("preview-1x", "preview-1")).toBe(false)
    expect(isSpeechSegmentRow("preview-1#c", "preview-1")).toBe(false)
    expect(isSpeechSegmentRow("activity-row-1", "preview-1")).toBe(false)
    expect(isSpeechSegmentRow("optimistic-1", "preview-1")).toBe(false)
  })
})


describe("P1 — 段归属在输入事件边界钉死 (事故回归: 显示进度不再决定归属)", () => {
  it("1. 同一同步栈内 delta→checkpoint→activity→delta: 后文永不被 checkpoint 覆盖", async () => {
    // 事故复现形状: 全部事件同一同步栈到达, 旧实现把后文并入主段后被
    // Path A settle 的 frame text 覆盖, previewText 被清零。
    const h = harness()
    h.segments.onDelta("前文")
    h.segments.onCheckpoint("前文", "2026-10-22T12:09:12Z")
    h.appendActivityRow("activity-row-1")
    h.segments.onDelta("后文")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1#cp1", "activity-row-1", "preview-1"])
    expect(h.row("preview-1#cp1")?.content).toBe("前文")
    expect(h.row("preview-1#cp1")?.streaming).toBe(false)
    expect(h.row("preview-1")?.content).toBe("后文")
    expect(h.segments.previewText).toBe("后文")
    expect(h.segments.streamedAny).toBe(true)
  })

  it("2. 前段打字机未排空 (部分释放) 时下一段 delta 到达: 各归各段", async () => {
    const h = harness()
    h.segments.onDelta("前文")
    h.tw().releaseSome(1) // 前段只打出「前」——显示进度在中途
    h.segments.onCheckpoint("前文", "2026-10-22T12:09:12Z")
    h.segments.onDelta("后文")
    h.tw().release()
    await h.segments.drain()

    expect(h.row("preview-1#cp1")?.content).toBe("前文")
    expect(h.row("preview-1")?.content).toBe("后文")
    expect(h.segments.previewText).toBe("后文")
  })

  it("3. 无前置 delta 的 checkpoint 尚在播放时下一段 delta 到达: 不并入 checkpoint 泡", async () => {
    const h = harness()
    h.segments.onCheckpoint("检查点一。", "2026-10-22T12:00:00Z")
    h.segments.onDelta("后文") // checkpoint 文字还在缓冲里
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1#cp1", "preview-1"])
    expect(h.row("preview-1#cp1")?.content).toBe("检查点一。")
    expect(h.row("preview-1#cp1")?.streaming).toBe(false)
    expect(h.row("preview-1")?.content).toBe("后文")
  })

  it("4. 连续多个 Path A checkpoint: 每段各归各, 出生序不变", async () => {
    const h = harness()
    h.segments.onDelta("一")
    h.segments.onCheckpoint("一", "2026-10-22T12:00:00Z")
    h.segments.onDelta("二")
    h.segments.onCheckpoint("二", "2026-10-22T12:00:05Z")
    h.segments.onDelta("三")
    h.tw().release()
    await h.segments.drain()

    expect(h.ids()).toEqual(["preview-1#cp1", "preview-1#cp2", "preview-1"])
    expect(h.row("preview-1#cp1")?.content).toBe("一")
    expect(h.row("preview-1#cp2")?.content).toBe("二")
    expect(h.row("preview-1")?.content).toBe("三")
    expect(h.segments.previewText).toBe("三")
  })

  it("5. checkpoint 窗口内 abort/flush: 各段落到正确行, 清理后不再有迟到改写", async () => {
    const h = harness()
    h.segments.onDelta("前文")
    h.segments.onCheckpoint("前文", "2026-10-22T12:09:12Z")
    h.segments.onDelta("后文")
    h.segments.flush() // abort: 缓冲全放, 各归各段
    expect(h.row("preview-1#cp1")?.content).toBe("前文")
    expect(h.row("preview-1#cp1")?.streaming).toBe(false)
    expect(h.row("preview-1")?.content).toBe("后文")
    // 清理后 (rollback 撤行) 不得再有迟到的 settle 改写世界。
    const snapshot = JSON.stringify(h.ids().map((id) => h.row(id)))
    await tick()
    await tick()
    expect(JSON.stringify(h.ids().map((id) => h.row(id)))).toBe(snapshot)
  })

  it("6. 最终 envelope 不重复播放已正确显示的后文 (previewText 只随主段)", async () => {
    const h = harness()
    h.segments.onDelta("前文")
    h.segments.onCheckpoint("前文", "2026-10-22T12:09:12Z")
    h.segments.onDelta("后文")
    h.tw().release()
    await h.segments.drain()
    // envelope 到来: ChatDock 的 paceUnstreamedTail 只推 previewText 之后的
    // 尾巴——previewText 必须是主段真实已显示的「后文」, 不是被清零的空串。
    expect(h.segments.previewText).toBe("后文")
    const full = "后文，还有尾巴。"
    h.segments.push(full.slice(h.segments.previewText.length))
    h.tw().release()
    await h.segments.drain()
    expect(h.row("preview-1")?.content).toBe("后文，还有尾巴。")
  })
})
