/** History replay mapper contract (Phase 3 Batch A): the archive→flow
 * projection's branch matrix. The load-bearing law (ADR-087 原则 2): the
 * replay rebuilds what the live flow SHOWED and never derives lifecycle —
 * no readiness, no plan state, no canvas signal is computed from which rows
 * exist. Read tolerance: off-shape payloads degrade to the plain row, never
 * a crash. */

import { describe, expect, it } from "vitest"

import { mapHistoryRows, type HistoryRow } from "./historyReplay"

/** A t() that echoes the key — the QA archive's localized line is the
 * i18n layer's business; the mapper only routes the answer kind. */
const t = (key: string) => key

function row(overrides: Partial<HistoryRow>): HistoryRow {
  return {
    id: "m1",
    role: "assistant",
    content: null,
    question: null,
    answer: null,
    workflow_run_id: null,
    ...overrides,
  }
}

const ctx = { prompt: "the opening prompt", t }

describe("user rows", () => {
  it("map straight through, attachments rebuilt as completed chips", () => {
    const [m] = mapHistoryRows(
      [
        row({
          role: "user",
          content: "make clips",
          attachments: [{ id: "a1", name: "talk.mp4", type: "video", url: "u" }],
        }),
      ],
      ctx,
    )
    expect(m).toMatchObject({
      id: "m1",
      role: "user",
      content: "make clips",
      assets: [
        { id: "a1", type: "video", file_url: "u", title: "talk.mp4", processing_status: "completed" },
      ],
    })
  })

  it("skips the seeded opening-prompt row (it renders from the prop)", () => {
    const out = mapHistoryRows(
      [row({ role: "user", content: "the opening prompt" })],
      ctx,
    )
    expect(out).toEqual([])
  })
})

describe("answered task_book rows — echo, never a QA block", () => {
  it("replays the echo prose as its own flow message with the run stamp", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "here is the plan",
          question: { kind: "task_book" },
          answer: { kind: "start" },
          workflow_run_id: "run-1",
        }),
      ],
      ctx,
    )
    expect(out).toEqual([
      expect.objectContaining({
        id: "m1-echo",
        role: "assistant",
        content: "here is the plan",
        runId: "run-1",
      }),
    ])
  })

  it("an empty echo pushes nothing (no ghost row)", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "  ",
          question: { kind: "task_book" },
          answer: { kind: "start" },
        }),
      ],
      ctx,
    )
    expect(out).toEqual([])
  })
})

describe("answered OPTIONS questions — echo first, then the QA archive", () => {
  it("framing prose replays above the collapsed QA block", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "let me ask you something",
          question: {
            kind: "question",
            question: "which language?",
            options: [{ id: "en", label: "English" }],
          },
          answer: { kind: "option", option_id: "en" },
        }),
      ],
      ctx,
    )
    expect(out).toHaveLength(2)
    expect(out[0]).toMatchObject({ id: "m1-echo", content: "let me ask you something" })
    expect(out[1]).toMatchObject({
      id: "m1",
      qa: { question: "which language?", answer: "en", muted: false, questionId: "m1" },
    })
  })

  it("bail answers resolve through i18n and render muted", () => {
    const out = mapHistoryRows(
      [
        row({
          question: { kind: "question", options: [{ id: "a", label: "A" }] },
          answer: { kind: "bail" },
        }),
      ],
      ctx,
    )
    expect(out[0].qa).toMatchObject({ answer: "chat.qa.cancelled", muted: true })
  })

  it("legacy rows without a bare-question field fall back to content (读容忍)", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "which language?",
          question: { kind: "question", options: [{ id: "en", label: "English" }] },
          answer: { kind: "freeform", text: "English" },
        }),
      ],
      ctx,
    )
    // questionEcho compares against the payload's bare-question FIELD (absent
    // here), so the content replays as the echo row; the QA archive's Q line
    // itself falls back to content via bareQuestion().
    expect(out).toHaveLength(2)
    expect(out[0]).toMatchObject({ id: "m1-echo", content: "which language?" })
    expect(out[1].qa).toMatchObject({ question: "which language?", answer: "English" })
  })
})

describe("answered TEXT questions — the plain message pair", () => {
  it("an options-empty answered question is a plain assistant message", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "what is this about?",
          question: { kind: "question" },
          answer: { kind: "freeform", text: "a talk" },
        }),
      ],
      ctx,
    )
    expect(out).toEqual([
      expect.objectContaining({ id: "m1", role: "assistant", content: "what is this about?" }),
    ])
    expect(out[0].qa).toBeUndefined()
  })
})

describe("pending questions", () => {
  it("a pending TEXT question stays a plain flow message (never docks)", () => {
    const out = mapHistoryRows(
      [row({ content: "what is this about?", question: { kind: "question" } })],
      ctx,
    )
    expect(out).toEqual([
      expect.objectContaining({ id: "m1", content: "what is this about?" }),
    ])
  })

  it("a pending OPTIONS question replays only its framing prose (the pill revives elsewhere)", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "let me ask",
          question: {
            kind: "question",
            question: "which one?",
            options: [{ id: "a", label: "A" }],
          },
        }),
      ],
      ctx,
    )
    expect(out).toEqual([
      expect.objectContaining({ id: "m1-echo", content: "let me ask" }),
    ])
  })

  it("a pending task_book row replays nothing (the dock owns the live plan)", () => {
    const out = mapHistoryRows(
      [row({ content: "plan", question: { kind: "task_book" } })],
      ctx,
    )
    expect(out).toEqual([])
  })
})

describe("plain assistant rows + legacy trigger pills", () => {
  it("plain rows pass through with the run stamp; trigger pills rebuild from the intent dump", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "review this",
          workflow_run_id: "run-9",
          intent: {
            type: "trigger_review",
            suggestions: [
              { label: "post it", action: "send", text: "post it" },
              { label: "bad shape" }, // filtered out — off-shape
            ],
          },
        }),
      ],
      ctx,
    )
    expect(out[0]).toMatchObject({ runId: "run-9" })
    expect(out[0].suggestions).toEqual([
      { label: "post it", action: "send", text: "post it", output_id: null },
    ])
  })

  it("off-shape intent → suggestions undefined (read tolerance, never a crash)", () => {
    const out = mapHistoryRows(
      [row({ content: "hi", intent: { type: "something_else" } })],
      ctx,
    )
    expect(out[0].suggestions).toBeUndefined()
  })
})

describe("no lifecycle derivation (恢复不推导 lifecycle)", () => {
  it("the output vocabulary carries no readiness/plan fields at all", () => {
    // The mapper's result type is the flow's display row — if a readiness
    // signal ever leaks into the replay (planReady/confirm/canvas), this
    // keys-set lock names it.
    const out = mapHistoryRows(
      [
        row({
          content: "plan",
          question: { kind: "task_book" },
          answer: { kind: "start" },
          workflow_run_id: "run-1",
        }),
        row({ role: "user", content: "go" }),
        row({ content: "done" }),
      ],
      ctx,
    )
    const ALLOWED = new Set([
      "id",
      "role",
      "content",
      "runId",
      "at",
      "assets",
      "streaming",
      "qa",
      "focus",
      "meta",
      "suggestions",
      "beat",
      "milestones",
    ])
    for (const m of out) {
      for (const key of Object.keys(m)) {
        expect(ALLOWED.has(key)).toBe(true)
      }
    }
  })
})

describe("material beats (2026-09-24 素材节拍入库)", () => {
  it("a persisted beat row replays as a settled activity payload, never a bubble", () => {
    const out = mapHistoryRows(
      [
        row({
          id: "beat-1",
          created_at: "2026-09-24T10:00:00Z",
          intent: {
            type: "material_beat",
            beat: "reading",
            status: "completed",
            name: "keynote.mp4",
            count: 1,
            total: 2,
            ref: "asset-1",
          },
        }),
        row({
          id: "beat-2",
          created_at: "2026-09-24T10:03:00Z",
          intent: {
            type: "material_beat",
            beat: "understanding",
            status: "completed",
            count: 2,
            ref: "digest-9",
          },
        }),
      ],
      ctx,
    )
    expect(out).toHaveLength(2)
    expect(out[0].content).toBe("")
    expect(out[0].beat).toMatchObject({
      kind: "read",
      status: "completed",
      key: "chat.material.readingDoneProgress",
      count: 1,
      total: 2,
      name: "keynote.mp4",
      at: "2026-09-24T10:00:00Z",
    })
    expect(out[1].beat).toMatchObject({
      kind: "read",
      status: "completed",
      key: "chat.material.understandingDone",
      count: 2,
    })
  })

  it("a lone file drops the progress form; a failed read takes the failed key", () => {
    const out = mapHistoryRows(
      [
        row({
          intent: {
            type: "material_beat",
            beat: "reading",
            status: "completed",
            name: "a.pdf",
            count: 1,
            total: 1,
            ref: "asset-1",
          },
        }),
        row({
          id: "beat-f",
          intent: {
            type: "material_beat",
            beat: "reading",
            status: "failed",
            name: "b.mov",
            ref: "asset-2",
          },
        }),
      ],
      ctx,
    )
    expect(out[0].beat?.key).toBe("chat.material.readingDone")
    expect(out[1].beat).toMatchObject({
      status: "failed",
      key: "chat.material.readingFailed",
      name: "b.mov",
    })
  })

  it("an off-shape beat dump degrades to a plain assistant row (read tolerance)", () => {
    const out = mapHistoryRows(
      [row({ content: "", intent: { type: "material_beat", beat: "mystery" } })],
      ctx,
    )
    expect(out[0].beat).toBeUndefined()
  })
})

describe("activity logs (2026-09-25 activity 持久化)", () => {
  const frame = (over: Record<string, unknown>) => ({
    activity_id: "a1",
    seq: 1,
    kind: "read",
    status: "completed",
    key: "chat.inspectingDone.searchTranscript",
    at: "2026-09-25T10:00:01Z",
    duration_ms: 820,
    ...over,
  })

  it("a persisted turn log replays as settled milestone frames, never a bubble", () => {
    const out = mapHistoryRows(
      [
        row({
          id: "log-1",
          created_at: "2026-09-25T10:00:05Z",
          intent: {
            type: "activity_log",
            ref: "user-msg-1",
            frames: [
              frame({}),
              frame({
                activity_id: "a2",
                seq: 2,
                kind: "draft",
                key: "chat.activity.draftDone",
                count: 3,
              }),
            ],
          },
        }),
      ],
      ctx,
    )
    expect(out).toHaveLength(1)
    expect(out[0].content).toBe("")
    expect(out[0].milestones).toHaveLength(2)
    expect(out[0].milestones?.[0]).toMatchObject({
      activity_id: "a1",
      kind: "read",
      status: "completed",
      key: "chat.inspectingDone.searchTranscript",
      at: "2026-09-25T10:00:01Z",
      duration_ms: 820,
    })
    expect(out[0].milestones?.[1]).toMatchObject({ kind: "draft", count: 3 })
  })

  it("an active frame inside the dump drops the whole row (settled-only law, read tolerance)", () => {
    const out = mapHistoryRows(
      [
        row({
          content: "",
          intent: {
            type: "activity_log",
            ref: "x",
            frames: [frame({ status: "active" })],
          },
        }),
      ],
      ctx,
    )
    expect(out[0].milestones).toBeUndefined()
  })

  it("a non-array frames payload degrades to a plain assistant row", () => {
    const out = mapHistoryRows(
      [row({ content: "", intent: { type: "activity_log", ref: "x", frames: "no" } })],
      ctx,
    )
    expect(out[0].milestones).toBeUndefined()
  })
})
