/** History replay mapper contract (Phase 3 Batch A): the archive→flow
 * projection's branch matrix. The load-bearing law (ADR-087 原则 2): the
 * replay rebuilds what the live flow SHOWED and never derives lifecycle —
 * no readiness, no plan state, no canvas signal is computed from which rows
 * exist. Read tolerance: off-shape payloads degrade to the plain row, never
 * a crash. */

import { describe, expect, it } from "vitest"

import { mapHistoryRows, deliveryOutputRefs, type HistoryRow } from "./history"
import { buildConversationBlocks, buildConversationUnits, conversationBlockUnits } from "./project"
import type { OverlayMessage } from "./types"

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
    ...overrides,
  }
}

const ctx = { t }

function visibleMessageIds(rows: OverlayMessage[]): string[] {
  return buildConversationBlocks(buildConversationUnits(rows)).flatMap((block) =>
    conversationBlockUnits(block).flatMap((unit) => unit.kind === "message" ? [unit.message.id] : []),
  )
}

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
        { id: "a1", type: "video", file_url: "u", stream_url: "u", title: "talk.mp4", processing_status: "completed" },
      ],
    })
  })

  it("replays the exact persisted Skill reference without resolving a newer version", () => {
    const reference = {
      kind: "external",
      skill_version_id: "11111111-1111-4111-8111-111111111111",
    } as const
    const [message] = mapHistoryRows(
      [row({ role: "user", content: "use the pinned method", skill: reference })],
      ctx,
    )
    expect(message.skill).toEqual(reference)
  })

  it("the opener row maps straight through (归档单一源: every row renders, the opener included)", () => {
    // The mapper's own law names this case: no prop-rendered side lane, no
    // skip predicate — a user row whose content is the opening prompt is a
    // plain user row like any other.
    const out = mapHistoryRows(
      [row({ role: "user", content: "the opening prompt" })],
      ctx,
    )
    expect(out).toEqual([
      expect.objectContaining({ id: "m1", role: "user", content: "the opening prompt" }),
    ])
  })
  it("carries the same explicit turn id onto user, assistant and activity history rows", () => {
    const out = mapHistoryRows(
      [
        row({ id: "u1", role: "user", content: "make it", turn_id: "u1" }),
        row({
          id: "a1",
          content: "",
          turn_id: "u1",
          intent: {
            type: "activity",
            frame: {
              activity_id: "a1",
              kind: "read",
              status: "completed",
              key: "chat.inspectingDone.transcript",
            },
          },
        }),
        row({ id: "m2", content: "done", turn_id: "u1" }),
      ],
      ctx,
    )
    expect(out.map((message) => message.turnId)).toEqual(["u1", "u1", "u1"])
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
          seq: 9,
        }),
      ],
      ctx,
    )
    expect(out).toHaveLength(2)
    expect(out[0]).toMatchObject({ id: "m1-echo", content: "let me ask you something", seq: 9 })
    expect(out[1]).toMatchObject({
      id: "m1",
      seq: 9,
      qa: { question: "which language?", answer: "en", muted: false, questionId: "m1" },
    })
  })


  it("keeps a question's preview blocks above the dock and its answered archive", () => {
    const preview = row({
      content: "Approve export?",
      question: { kind: "question", question: "Approve export?", options: [{ id: "ok", label: "Yes" }] },
      blocks: [{ kind: "system_notice", text: "Preview is ready" }],
    })
    for (const answer of [null, { kind: "option" as const, option_id: "ok" }]) {
      const history = mapHistoryRows([{ ...preview, answer }], ctx)
      expect(history.filter((message) => message.blocks?.length)).toMatchObject([
        { id: "m1-echo", serverMessageId: "m1", blocks: preview.blocks },
      ])
    }
  })

  it("replays partial and recovery Outputs at their own delivery array positions", () => {
    const out = mapHistoryRows(
      [
        row({
          id: "delivery-a",
          content: "A is ready",
          intent: { output_refs: ["output-a"] },
        }),
        row({
          id: "delivery-b",
          content: "B is ready",
          intent: { output_refs: ["output-b"] },
        }),
        row({
          id: "missing-refs",
          content: "old receipt",
          intent: {},
        }),
      ],
      ctx,
    )
    expect(out.map((message) => [message.id, message.outputRefs])).toEqual([
      ["delivery-a", ["output-a"]],
      ["delivery-b", ["output-b"]],
      ["missing-refs", []],
    ])
  })

  it("live and hydrated history produce the same message order and per-delivery refs", () => {
    const persisted = [
      row({ id: "birth", content: "Starting", turn_id: "opening", seq: 1 }),
      row({
        id: "delivery-a",
        content: "A is ready",
        intent: { output_refs: ["output-a"] },
        seq: 2,
      }),
      row({
        id: "delivery-b",
        content: "B is ready",
        intent: { output_refs: ["output-b"] },
        seq: 3,
      }),
    ]
    const live: OverlayMessage[] = [
      { id: "birth", role: "assistant", content: "Starting", turnId: "opening", seq: 1 },
      {
        id: "delivery-a",
        role: "assistant",
        content: "A is ready",
        outputRefs: ["output-a"],
        seq: 2,
      },
      {
        id: "delivery-b",
        role: "assistant",
        content: "B is ready",
        outputRefs: ["output-b"],
        seq: 3,
      },
    ]
    const project = (messages: OverlayMessage[]) =>
      buildConversationBlocks(buildConversationUnits(messages)).flatMap((block) =>
        conversationBlockUnits(block).flatMap((unit) => unit.kind === "message"
          ? [[unit.message.id, ...(unit.message.outputRefs ?? [])]] : []),
      )
    const history = mapHistoryRows(persisted, ctx)
    expect(project(history)).toEqual(project(live))
    expect(project(history)).toEqual([
      ["birth"],
      ["delivery-a", "output-a"],
      ["delivery-b", "output-b"],
    ])
    expect(history.every((message) => message.hydrated === true)).toBe(true)
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

describe("OPTIONS answer single-display projection", () => {
  const optionQuestion = (overrides: Partial<HistoryRow> = {}) => row({
    id: "q1",
    content: null,
    question: {
      kind: "question",
      question: "Which language?",
      options: [{ id: "en", label: "English" }],
    },
    answer: { kind: "option", option_id: "en", text: "English" },
    ...overrides,
  })
  const followingReply = () => row({ id: "a1", content: "Got it", turn_id: "u1" })

  it("uses the new explicit association and leaves the assistant in the real user Turn", () => {
    const mapped = mapHistoryRows([
      optionQuestion(),
      row({
        id: "u1",
        role: "user",
        content: "English",
        turn_id: "u1",
        intent: { answered_question_id: "q1" },
      }),
      followingReply(),
    ], ctx)
    const blocks = buildConversationBlocks(buildConversationUnits(mapped))
    expect(visibleMessageIds(mapped)).toEqual(["q1", "a1"])
    expect(blocks[1]).toMatchObject({ kind: "turn", turnId: "u1", key: "turn:u1" })
    expect(mapped.find((message) => message.id === "u1")).toMatchObject({
      role: "user",
      turnId: "u1",
      answeredQuestionId: "q1",
    })
  })

  it("never lets an expired machine answer inherit the legacy option fallback", () => {
    const mapped = mapHistoryRows([
      optionQuestion({ answer: { kind: "option", option_id: "en", text: "expired" } }),
      row({ id: "u1", role: "user", content: "English", turn_id: "u1" }),
      followingReply(),
    ], ctx)
    expect(mapped.find((message) => message.id === "u1")?.answeredQuestionId).toBeUndefined()
    expect(visibleMessageIds(mapped)).toContain("u1")
  })

  it("never extends the legacy fallback to other answers, messages, labels or positions", () => {
    const cases: HistoryRow[][] = [
      [
        optionQuestion({ answer: { kind: "freeform", text: "English" } }),
        row({ id: "u1", role: "user", content: "English", turn_id: "u1" }),
      ],
      [row({ id: "u1", role: "user", content: "English", turn_id: "u1" })],
      [
        optionQuestion(),
        row({ id: "between", content: "another persisted row" }),
        row({ id: "u1", role: "user", content: "English", turn_id: "u1" }),
      ],
      [
        optionQuestion(),
        row({ id: "u1", role: "user", content: "Eng", turn_id: "u1" }),
      ],
      [
        optionQuestion(),
        row({ id: "u1", role: "user", content: " English ", turn_id: "u1" }),
      ],
      [
        optionQuestion({ answer: { kind: "option", option_id: "en", text: "superseded" } }),
        row({ id: "u1", role: "user", content: "English", turn_id: "u1" }),
      ],
      [
        optionQuestion({ answer: { kind: "option", option_id: "en", text: "French" } }),
        row({ id: "u1", role: "user", content: "English", turn_id: "u1" }),
      ],
      [
        optionQuestion({ answer: { kind: "bail", text: "superseded" } }),
        row({ id: "u1", role: "user", content: "English", turn_id: "u1" }),
      ],
    ]
    for (const rows of cases) {
      const mapped = mapHistoryRows(rows, ctx)
      expect(mapped.find((message) => message.id === "u1")?.answeredQuestionId).toBeUndefined()
      expect(visibleMessageIds(mapped)).toContain("u1")
    }
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




})

describe("plain assistant rows + legacy trigger pills", () => {

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
          content: "Authorized",
          question: { kind: "question", options: [{id: "approve", label: "Allow"}] },
          answer: { kind: "option", option_id: "approve" },
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
      // Delivery transcript ownership only — not a lifecycle/readiness signal.
      // Persistent recovery identity (upload-retry-N), never a readiness stamp.
      // This delivery row's persisted product ids — content, not readiness.
      "outputRefs",
      // Turn identity + history hydration metadata — not lifecycle/readiness.
      "turnId",
      "serverMessageId",
      // Option-answer duplicate-Slot association — never turn/lifecycle derivation.
      "answeredQuestionId",
      // Exact Skill reference on its owning user message — not turn state.
      "skill",
      "hydrated",
      // Explicit block ownership for QA/candidate/trigger/material facts.
      "independentKind",
      // Persisted activity/candidate world facts replayed by the mapper.
      "activity",
      "candidates",
      "seq",
      "at",
      "assets",
      "streaming",
      "qa",
      "focus",
      "meta",
      "suggestions",
      "beat",
      "milestones",
      "blocks",
      "questionEcho",
      "turnProse",
      "runId",
      "displayRole",
      "failureCheckpoint",
    ])
    const illegalKeys = [
      ...new Set(
        out.flatMap((m) => Object.keys(m).filter((key) => !ALLOWED.has(key))),
      ),
    ]
    expect(illegalKeys).toEqual([])
  })
})

describe("turn_failed rows (失败行回放)", () => {
  it("a persisted turn-failure row replays as the grey meta error row", () => {
    const out = mapHistoryRows(
      [
        row({
          id: "tf-1",
          content: "The storyboard took too long. No production has started; ask me to retry the storyboard.",
          intent: { type: "turn_failed" },
        }),
      ],
      ctx,
    )
    expect(out).toEqual([
      expect.objectContaining({ id: "tf-1", meta: "error", content: expect.stringContaining("took too long") }),
    ])
  })

  it("an empty turn_failed row skips (no-empty-bubble law)", () => {
    const out = mapHistoryRows(
      [row({ content: "", intent: { type: "turn_failed" } })],
      ctx,
    )
    expect(out).toEqual([])
  })
})

describe("activity array rows (ADR-108 — 每帧一行)", () => {
  const frame = (over: Record<string, unknown>) => ({
    activity_id: "a1",
    kind: "read",
    status: "completed",
    key: "chat.inspectingDone.searchTranscript",
    at: "2026-09-25T10:00:00.180Z",
    duration_ms: 820,
    ...over,
  })

  it("a persisted activity row replays IN ITS ARRAY POSITION as an activity unit, never a bubble", () => {
    const out = mapHistoryRows(
      [
        row({ id: "u1", role: "user", content: "剪哪一句" }),
        row({
          id: "act-1",
          created_at: "2026-09-25T10:00:01Z",
          intent: { type: "activity", frame: frame({}) },
        }),
        row({
          id: "act-2",
          created_at: "2026-09-25T10:00:02Z",
          intent: {
            type: "activity",
            frame: frame({ activity_id: "a2", key: "chat.inspectingDone.segment" }),
          },
        }),
        row({ id: "r1", content: "我推荐剪这句" }),
      ],
      ctx,
    )
    // 数组位置律: the rows render in array order — no timestamp re-sort.
    expect(out.map((m) => m.id)).toEqual(["u1", "act-1", "act-2", "r1"])
    expect(out[1].content).toBe("")
    // The persisted `at` is the birth stamp (execute entry) — replay reads
    // it verbatim, no derivation.
    expect(out[1].activity).toMatchObject({
      activity_id: "a1",
      kind: "read",
      status: "completed",
      key: "chat.inspectingDone.searchTranscript",
      at: "2026-09-25T10:00:00.180Z",
      duration_ms: 820,
    })
    expect(out[2].activity).toMatchObject({
      activity_id: "a2",
      key: "chat.inspectingDone.segment",
    })
  })

  it("an honestly-open row (a read still in flight when the stream dropped) replays active", () => {
    const out = mapHistoryRows(
      [
        row({
          id: "act-open",
          intent: {
            type: "activity",
            frame: frame({ status: "active", key: "chat.inspecting.transcript", duration_ms: undefined }),
          },
        }),
      ],
      ctx,
    )
    expect(out[0].activity).toMatchObject({ status: "active" })
  })

  it("a malformed frame skips the row entirely — never an empty bubble", () => {
    const out = mapHistoryRows(
      [row({ content: "", intent: { type: "activity", frame: { kind: "mystery" } } })],
      ctx,
    )
    expect(out).toHaveLength(0)
  })

  it("never-render rows skip: the rejection forensics ledger", () => {
    const out = mapHistoryRows(
      [
        row({
          id: "fx",
          intent: { type: "activity_forensics", ref: "u1", rejections: [{ reason: "x" }] },
        }),
        row({ id: "r1", content: "answer" }),
      ],
      ctx,
    )
    expect(out.map((m) => m.id)).toEqual(["r1"])
  })
})


it("upload results attach to the current answer without a Run anchor", () => {
  expect(deliveryOutputRefs({ type: "answer", output_refs: ["uploaded-video"] }))
    .toEqual(["uploaded-video"])
  const messages = mapHistoryRows([row({
    id: "upload-answer", role: "assistant", content: "上传好了",
    intent: { type: "answer", output_refs: ["uploaded-video"] },
  })], ctx)
  expect(messages.find((message) => message.id === "upload-answer"))
    .toMatchObject({ outputRefs: ["uploaded-video"] })
})


it("upload refs stay on a follow-up question's framing speech through QA hydration", () => {
  const question = row({
    id: "upload-question", role: "assistant", content: "上传好了。还要调整吗？",
    intent: { type: "ask_user", output_refs: ["uploaded-video"] },
    question: { kind: "question", question: "还要调整吗？", options: [{ id: "yes", label: "调整" }] },
  })
  const pending = mapHistoryRows([question], ctx)
  expect(pending.find((m) => m.id === "upload-question-echo")?.outputRefs).toEqual(["uploaded-video"])
  const answered = mapHistoryRows([{ ...question, answer: { kind: "option", option_id: "yes" } }], ctx)
  expect(answered.find((m) => m.id === "upload-question-echo")?.outputRefs).toEqual(["uploaded-video"])
})


describe("question groups", () => {
  it("replays every Q/A item instead of flattening the group", () => {
    const messages = mapHistoryRows([
      row({
        id: "group-1",
        content: "Production setup",
        question: {
          kind: "question",
          question: "Production setup",
          items: [
            { slot: "purpose", question: "Where will it run?", options: [{ id: "1", label: "Website", value: "website" }] },
            { slot: "target_seconds", question: "How long?", options: [{ id: "2", label: "60 seconds", value: 60 }] },
          ],
          group_digest: "digest-1",
        },
        answer: {
          kind: "group",
          group_digest: "digest-1",
          text: "Website · 60 seconds",
          answers: [
            { slot: "purpose", kind: "option", option_id: "1" },
            { slot: "target_seconds", kind: "option", option_id: "2" },
          ],
          answered_at: "2026-01-01T00:00:00Z",
        },
      }),
    ], ctx)
    const qa = messages.find((message) => message.qa)?.qa
    expect(qa?.items).toEqual([
      { question: "Where will it run?", answer: "Website" },
      { question: "How long?", answer: "60 seconds" },
    ])
    expect(qa?.answerKind).toBe("group")
  })

  it("removes a legacy group title suffix from the pending echo", () => {
    const messages = mapHistoryRows([
      row({
        id: "group-pending",
        content: "Brand evidence is ready.\n\nProduction setup",
        question: {
          kind: "question",
          question: "Production setup",
          options: [],
          items: [{ slot: "purpose", question: "Where?", options: [] }],
        },
        answer: null,
      }),
    ], ctx)

    expect(messages).toHaveLength(1)
    expect(messages[0].content).toBe("Brand evidence is ready.")
  })

  it("replays persisted semantic activity detail and ignores malformed detail safely", () => {
    const messages = mapHistoryRows([
      row({
        id: "act-semantic",
        content: "",
        intent: {
          type: "activity",
          frame: {
            activity_id: "a-sem",
            kind: "read",
            status: "completed",
            tool_name: "insert_motion_block",
            key: "chat.activity.insertMotionBlockDone",
            detail: { kind: "motion_block_insert", block: "data_chart", window: "12–17s" },
          },
        },
      }),
      row({
        id: "act-bad-detail",
        content: "",
        intent: {
          type: "activity",
          frame: {
            activity_id: "a-bad",
            kind: "read",
            status: "completed",
            tool_name: "insert_motion_block",
            key: "chat.activity.insertMotionBlockDone",
            detail: { kind: "unknown_future_kind", foo: 123 },
          },
        },
      }),
    ], ctx)

    expect(messages).toHaveLength(2)
    expect(messages[0].activity?.detail).toEqual({
      kind: "motion_block_insert",
      block: "data_chart",
      window: "12–17s",
    })
    expect(messages[1].activity?.detail).toBeUndefined()
  })

  it("replays persisted steps and feedback on settled assistant messages", () => {
    const messages = mapHistoryRows([
      row({
        id: "u1",
        role: "user",
        content: "做一个 60 秒产品宣传片",
      }),
      row({
        id: "a1",
        role: "assistant",
        content: "已生成首版草稿。",
        steps: [
          { title: "分析官网与素材", status: "done" },
          { title: "编排 6 幕动效", status: "done" },
        ],
        feedback: {
          rating: "bad",
          tags: ["pacing"],
          reason: "开场稍慢",
          updated_at: "2026-11-24T12:00:00Z",
        },
      }),
    ], ctx)

    expect(messages).toHaveLength(2)
    expect(messages[1].steps).toEqual([
      { title: "分析官网与素材", status: "done" },
      { title: "编排 6 幕动效", status: "done" },
    ])
    expect(messages[1].feedback).toEqual({
      rating: "bad",
      tags: ["pacing"],
      reason: "开场稍慢",
      updated_at: "2026-11-24T12:00:00Z",
    })
  })
})
