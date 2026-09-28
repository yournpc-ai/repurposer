/** Answer-envelope settlement contract (ADR-093 §1 信封对账补全): the
 * answer SSE seam's pacing + splice branch matrix. The load-bearing laws:
 * the envelope ALWAYS wins (content truth replacement, not just identity
 * stamping), the paced prose IS the stamped prose (same value), and the
 * splice never remounts (same index, same key). */

import { describe, expect, it } from "vitest"

import {
  answerEnvelopeProse,
  planEnvelopePacing,
  spliceAnswerEnvelope,
} from "./answerSettlement"
import type { OverlayMessage, QuestionMessage } from "./historyReplay"

function followUp(overrides: Partial<QuestionMessage>): QuestionMessage {
  return {
    id: "fu1",
    content: null,
    question: null,
    answer: null,
    workflow_run_id: null,
    created_at: "2026-09-28T10:00:00Z",
    ...overrides,
  }
}

function flowRow(overrides: Partial<OverlayMessage> & { id: string }): OverlayMessage {
  return {
    role: "assistant",
    content: "",
    ...overrides,
  }
}

describe("answerEnvelopeProse", () => {
  it("plain prose row: the raw content is the truth (no trim — byte parity with the archive)", () => {
    expect(
      answerEnvelopeProse(followUp({ content: "Done, your post is ready.\n\n" })),
    ).toBe("Done, your post is ready.\n\n")
  })

  it("task_book dock: the echo prose is the raw content (it differs from the bare question)", () => {
    expect(
      answerEnvelopeProse(
        followUp({
          content: "Here is the plan I prepared. ",
          question: { kind: "task_book" },
        }),
      ),
    ).toBe("Here is the plan I prepared. ")
  })

  it("options question with framing: the framing prose is the echo", () => {
    expect(
      answerEnvelopeProse(
        followUp({
          content: "Which language should I use?",
          question: {
            kind: "question",
            question: "Which language?",
            options: [{ id: "a", label: "English" }],
          },
        }),
      ),
    ).toBe("Which language should I use?")
  })

  it("code-composed row (content IS the bare question): no prose", () => {
    expect(
      answerEnvelopeProse(
        followUp({
          content: "Which language?",
          question: {
            kind: "question",
            question: "Which language?",
            options: [{ id: "a", label: "English" }],
          },
        }),
      ),
    ).toBe("")
  })

  it("empty / null content: no prose", () => {
    expect(answerEnvelopeProse(followUp({ content: null }))).toBe("")
    expect(answerEnvelopeProse(followUp({ content: "   " }))).toBe("")
  })
})

describe("planEnvelopePacing", () => {
  it("zero-delta turn: the full envelope prose paces (the last gate — prose leads, dock follows)", () => {
    expect(
      planEnvelopePacing({
        envelopeProse: "Here is the plan.",
        previewStreamed: false,
        previewText: "",
      }),
    ).toEqual({ paceText: "Here is the plan." })
  })

  it("envelope extends the streamed prefix: only the unseen tail paces", () => {
    expect(
      planEnvelopePacing({
        envelopeProse: "I checked the library. Here is the plan.",
        previewStreamed: true,
        previewText: "I checked the library.",
      }),
    ).toEqual({ paceText: " Here is the plan." })
  })

  it("same-value happy path: nothing paces", () => {
    expect(
      planEnvelopePacing({
        envelopeProse: "Here is the plan.",
        previewStreamed: true,
        previewText: "Here is the plan.",
      }),
    ).toBeNull()
  })

  it("non-prefix flip (replaced speech): nothing paces — the splice's replacement reconciles", () => {
    expect(
      planEnvelopePacing({
        envelopeProse: "Actually, let me redo that.",
        previewStreamed: true,
        previewText: "Here is the plan.",
      }),
    ).toBeNull()
  })

  it("prose-less envelope: nothing paces", () => {
    expect(
      planEnvelopePacing({
        envelopeProse: "",
        previewStreamed: false,
        previewText: "",
      }),
    ).toBeNull()
  })
})

describe("spliceAnswerEnvelope", () => {
  const answeredRow: Omit<OverlayMessage, "id"> = {
    role: "assistant",
    content: "",
    at: "2026-09-28T09:59:59Z",
    qa: { question: "Which language?", answer: "English", muted: false, questionId: "q1" },
  }
  const base: OverlayMessage[] = [
    flowRow({ id: "u1", role: "user", content: "make clips" }),
    flowRow({
      id: "opt1",
      content: "",
      qa: { question: "Which language?", answer: "English", muted: false },
      at: "2026-09-28T09:59:00Z",
    }),
    flowRow({
      id: "prev1",
      content: "Here is the",
      streaming: true,
      at: "2026-09-28T09:59:01Z",
    }),
  ]

  it("happy path: QA row lands at the optimistic block's own index+key; the preview settles with envelope truth", () => {
    const out = spliceAnswerEnvelope(base, {
      optimisticId: "opt1",
      previewId: "prev1",
      answeredRow,
      followUp: followUp({
        content: "Here is the plan.",
        workflow_run_id: "run1",
      }),
    })
    expect(out.map((m) => m.id)).toEqual(["u1", "opt1", "prev1"])
    // Same index AND same key (the id survives) — zero remount.
    expect(out[1].qa?.questionId).toBe("q1")
    expect(out[1].at).toBe("2026-09-28T09:59:59Z")
    // Content truth replacement + identity stamping + at re-anchor.
    expect(out[2]).toMatchObject({
      content: "Here is the plan.",
      runId: "run1",
      at: "2026-09-28T10:00:00Z",
      streaming: false,
    })
  })

  it("flip reconciliation: the envelope's prose REPLACES a divergent typed text", () => {
    const out = spliceAnswerEnvelope(base, {
      optimisticId: "opt1",
      previewId: "prev1",
      answeredRow,
      followUp: followUp({ content: "Actually, let me redo that." }),
    })
    expect(out[2].content).toBe("Actually, let me redo that.")
    expect(out[2].streaming).toBe(false)
  })

  it("no QA row (task_book start / text question): the optimistic block leaves the flow", () => {
    const out = spliceAnswerEnvelope(base, {
      optimisticId: "opt1",
      previewId: "prev1",
      answeredRow: null,
      followUp: followUp({ content: "Starting now." }),
    })
    expect(out.map((m) => m.id)).toEqual(["u1", "prev1"])
  })

  it("no follow-up: identity stays, typed text untouched (nothing to stamp)", () => {
    const out = spliceAnswerEnvelope(base, {
      optimisticId: "opt1",
      previewId: "prev1",
      answeredRow,
      followUp: null,
    })
    expect(out[2]).toMatchObject({
      content: "Here is the",
      streaming: false,
    })
    expect(out[2].runId).toBeUndefined()
    expect(out[2].at).toBe("2026-09-28T09:59:01Z")
  })

  it("prose-less follow-up (code-composed question): identity stamped, typed text kept", () => {
    const out = spliceAnswerEnvelope(base, {
      optimisticId: "opt1",
      previewId: "prev1",
      answeredRow,
      followUp: followUp({
        content: "Which language?",
        question: {
          kind: "question",
          question: "Which language?",
          options: [{ id: "a", label: "English" }],
        },
      }),
    })
    expect(out[2].content).toBe("Here is the")
    expect(out[2].streaming).toBe(false)
  })

  it("missing rows are tolerated (a zero-delta turn may never birth the preview bubble)", () => {
    const out = spliceAnswerEnvelope([flowRow({ id: "u1", role: "user" })], {
      optimisticId: "opt1",
      previewId: "prev1",
      answeredRow,
      followUp: followUp({ content: "Here is the plan." }),
    })
    expect(out.map((m) => m.id)).toEqual(["u1"])
  })
})
