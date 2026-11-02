import { describe, expect, it } from "vitest"

import { formatAmountInput, parseAmountMinor } from "./payments"

describe("top-up amount parsing", () => {
  it.each([
    ["10", 1000],
    ["10.50", 1050],
    ["10,50", 1050],
    ["0.01", 1],
    [" 10. ", 1000],
  ])("converts %s to integer minor units", (input, expected) => {
    expect(parseAmountMinor(input)).toBe(expected)
  })

  it.each(["", "abc", "-1", "1.234", "1.2.3", "1,2,3"])(
    "rejects invalid amount %s",
    (input) => {
      expect(parseAmountMinor(input)).toBeNull()
    },
  )

  it("fills preset amounts as decimal major units", () => {
    expect(formatAmountInput(1000)).toBe("10.00")
    expect(formatAmountInput(123)).toBe("1.23")
  })
})
