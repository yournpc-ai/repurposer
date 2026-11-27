import { describe, expect, it } from "vitest"

import {
  buildCheckoutReturnPath,
  formatAmountInput,
  parseAmountMinor,
  pickInitialTopup,
  type CreditPackageCatalog,
} from "./payments"

const CATALOG: CreditPackageCatalog = {
  items: [
    { key: "starter", credits: 10000, amount_minor: 1000, currency: "eur" },
    { key: "topup_20", credits: 20000, amount_minor: 2000, currency: "eur" },
    { key: "topup_50", credits: 50000, amount_minor: 5000, currency: "eur" },
  ],
  custom: {
    currency: "eur",
    min_amount_minor: 100,
    max_amount_minor: 100000,
    credits_per_major: 1000,
  },
}

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

describe("buildCheckoutReturnPath", () => {
  it("preserves current route and non-checkout query params for inline top-up", () => {
    expect(
      buildCheckoutReturnPath(
        "/projects/p-1",
        "?c=conv-9&checkout=cancelled&order_id=old&checkout_surface=settings",
        "inline",
      ),
    ).toBe("/projects/p-1?c=conv-9")
  })

  it("tags settings surface while keeping underlying route", () => {
    expect(buildCheckoutReturnPath("/projects/p-1", "?c=conv-9", "settings")).toBe(
      "/projects/p-1?c=conv-9&checkout_surface=settings",
    )
    expect(buildCheckoutReturnPath("/home", "", "settings")).toBe(
      "/home?checkout_surface=settings",
    )
  })
})

describe("pickInitialTopup", () => {
  it("defaults to the first preset without a shortfall", () => {
    expect(pickInitialTopup(CATALOG, null)).toEqual({
      selectedKey: "starter",
      amountInput: "10.00",
    })
  })

  it("picks the smallest preset covering a spend-point shortfall", () => {
    expect(pickInitialTopup(CATALOG, { balance: 45, required: 12000 })).toEqual({
      selectedKey: "topup_20",
      amountInput: "20.00",
    })
  })

  it("fills a custom amount when the shortfall exceeds every preset", () => {
    expect(pickInitialTopup(CATALOG, { balance: 500, required: 60500 })).toEqual({
      selectedKey: null,
      amountInput: "60.00",
    })
  })
})
