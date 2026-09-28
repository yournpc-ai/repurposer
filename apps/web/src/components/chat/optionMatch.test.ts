/** Client autoResume mapping contract: field-aligned with the server's
 * `_match_option` — a hit must settle as the SAME option on both sides of
 * the wire (the pencil row converts pre-post; the chat input's typed text
 * still resolves server-side). */

import { describe, expect, it } from "vitest"

import { matchOptionByText } from "./optionMatch"

const options = [
  { id: "opt_a", label: "English" },
  { id: "opt_b", label: "中文" },
  { id: "opt_c", label: "Français" },
]

describe("matchOptionByText", () => {
  it("resolves a 1-based number", () => {
    expect(matchOptionByText("2", options)).toBe(options[1])
  })

  it("resolves a positional letter (slug ids stay answerable)", () => {
    expect(matchOptionByText("a", options)).toBe(options[0])
    expect(matchOptionByText("C", options)).toBe(options[2])
  })

  it("resolves the verbatim label, case-insensitive", () => {
    expect(matchOptionByText("english", options)).toBe(options[0])
    expect(matchOptionByText("中文", options)).toBe(options[1])
  })

  it("resolves the raw option id", () => {
    expect(matchOptionByText("opt_b", options)).toBe(options[1])
  })

  it("trailing punctuation never defeats a hit (the server's rstrip set)", () => {
    expect(matchOptionByText("2.", options)).toBe(options[1])
    expect(matchOptionByText("English！", options)).toBe(options[0])
    expect(matchOptionByText(" 3）", options)).toBe(options[2])
  })

  it("anything else is deliberately NOT a match (freeform's domain)", () => {
    expect(matchOptionByText("都行，你定吧", options)).toBeNull()
    expect(matchOptionByText("4", options)).toBeNull()
    expect(matchOptionByText("engl", options)).toBeNull()
  })

  it("blank text never matches", () => {
    expect(matchOptionByText("", options)).toBeNull()
    expect(matchOptionByText(" 。", options)).toBeNull()
  })

  it("no options → no match", () => {
    expect(matchOptionByText("1", [])).toBeNull()
  })
})
