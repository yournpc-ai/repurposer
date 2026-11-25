// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AssistantText } from "./AssistantText"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

afterEach(() => {
  cleanup()
})

const WIDE_TABLE_MD = [
  "Here is the act-by-act comparison across our current cut:",
  "",
  "| Act | Timecode | Visual Focus | Audio / SFX Layer | Pacing Notes |",
  "| --- | --- | --- | --- | --- |",
  "| Act 1: Hook | 0:00–0:04 | Hero kinetic headline + dark matte gradient | Sub-bass impact + crisp riser | Immediate punch, zero dead air |",
  "| Act 2: Problem | 0:04–0:10 | Split-screen noisy timeline comparison | Soft tape click + low bed | Build tension into reveal |",
  "| Act 3: Product | 0:10–0:22 | Live Studio workbench + frame callouts | Warm synth pulse + UI clicks | Hold 1.8s on each highlight |",
  "| Act 4: Proof | 0:22–0:28 | Metrics counter strip + customer quote | Swell into clean snare hit | Anchor typography center-left |",
  "| Act 5: Outro | 0:28–0:32 | Monochrome wordmark lockup | Tail reverb decay | Clean fade to black |",
  "",
  "Let me know which act you want to tighten next.",
].join("\n")

describe("AssistantText breakout tables", () => {
  it("wraps Markdown tables in a single semantic breakout container in static mode", () => {
    const { container } = render(<AssistantText text={WIDE_TABLE_MD} hydrated />)

    const breakout = container.querySelector('[data-breakout-table="true"]')
    expect(breakout).toBeTruthy()
    expect(breakout?.classList.contains("ui-th-table-breakout")).toBe(true)

    const frame = breakout?.querySelector(".ui-th-table-frame")
    expect(frame).toBeTruthy()

    const table = frame?.querySelector("table.ui-th-table")
    expect(table).toBeTruthy()

    // Overrides Streamdown's default nested table wrapper so breakout is never double-wrapped or clipped
    expect(container.querySelector('[data-streamdown="table-wrapper"]')).toBeNull()

    const headers = Array.from(table?.querySelectorAll("thead th.ui-th-table__th") ?? []).map(
      (th) => th.textContent?.trim(),
    )
    expect(headers).toEqual([
      "Act",
      "Timecode",
      "Visual Focus",
      "Audio / SFX Layer",
      "Pacing Notes",
    ])

    const rows = table?.querySelectorAll("tbody tr.ui-th-table__row") ?? []
    expect(rows.length).toBe(5)
    expect(rows[0]?.querySelectorAll("td.ui-th-table__td").length).toBe(5)
  })

  it("renders the same breakout table wrapper while streaming", () => {
    const { container } = render(<AssistantText text={WIDE_TABLE_MD} streaming />)

    const breakout = container.querySelector('[data-breakout-table="true"]')
    expect(breakout).toBeTruthy()
    expect(breakout?.querySelector(".ui-th-table-frame table.ui-th-table")).toBeTruthy()
    expect(container.querySelector('[data-streamdown="table-wrapper"]')).toBeNull()
  })
})
