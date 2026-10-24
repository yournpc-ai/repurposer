/** Start-envelope prose contract: auto-started plans must be seen before the
 * run lands; starting an earlier dock must not retype its visible echo. */

import { describe, expect, it } from "vitest"

import type { OverlayMessage } from "./historyReplay"
import { shouldPaceStartEnvelopeProse } from "./startSettlement"

function row(overrides: Partial<OverlayMessage> & { id: string }): OverlayMessage {
  return {
    role: "assistant",
    content: "",
    ...overrides,
  }
}

const BOARD = "22 scenes\n\n| # | time | words |\n| --- | --- | --- |\n| 1 | 0–2s | 如果觉 |"

function gate(overrides?: {
  content?: string
  assistantMessageId?: string
  answeredQuestionId?: string | null
  messages?: OverlayMessage[]
}): boolean {
  return shouldPaceStartEnvelopeProse({
    content: BOARD,
    assistantMessageId: "plan-1",
    answeredQuestionId: "plan-1",
    messages: [],
    ...overrides,
  })
}

describe("shouldPaceStartEnvelopeProse", () => {
  it("a plan born and auto-started in this turn paces its full unseen echo", () => {
    expect(
      gate({
        messages: [
          row({ id: "checkpoint", content: "I chose the quiet piano track." }),
          row({ id: "activity", content: "" }),
        ],
      }),
    ).toBe(true)
  })

  it("an ordinary start of an earlier dock does not retype its visible echo", () => {
    expect(
      gate({
        messages: [row({ id: "local-plan-echo", content: BOARD })],
      }),
    ).toBe(false)
  })

  it("a zero-prose start stays silent and births no empty bubble", () => {
    expect(gate({ content: "  \n" })).toBe(false)
  })

  it("a distinct start-speech row paces even when its words match an old echo", () => {
    expect(
      gate({
        assistantMessageId: "start-speech-1",
        messages: [row({ id: "local-plan-echo", content: BOARD })],
      }),
    ).toBe(true)
  })

  it("only real assistant prose counts as a visible echo, not user or error rows", () => {
    const messages = [
      row({ id: "user-1", role: "user", content: BOARD }),
      row({ id: "error-1", content: BOARD, meta: "error" }),
    ]
    expect(gate({ messages })).toBe(true)
  })

  it("a different visible text does not suppress the current plan's echo", () => {
    expect(
      gate({
        messages: [row({ id: "older-plan", content: "an earlier plan" })],
      }),
    ).toBe(true)
  })
})
