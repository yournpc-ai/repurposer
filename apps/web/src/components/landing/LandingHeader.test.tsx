// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "@/lib/i18n"
import { LandingHeader } from "./LandingHeader"

vi.mock("./useLandingCreate", () => ({ useLandingCreate: () => vi.fn() }))
vi.mock("./MobileNavigation", () => ({ MobileNavigation: () => null }))
vi.mock("@/components/theme-toggle", () => ({ ThemeToggle: () => null }))
vi.mock("@/components/language-switcher", () => ({ LanguageSwitcher: () => null }))

afterEach(cleanup)

function renderHeader(locale: "en" | "zh") {
  render(<I18nextProvider i18n={createI18n(locale)}><LandingHeader /></I18nextProvider>)
  return screen.getByRole("button", { name: locale === "en" ? "Features" : "功能" })
}

describe("LandingHeader features", () => {
  it.each([
    ["en", ["Conversational Editing", "Studio Presets", "Instant Remix", "Multi-Source Cuts"]],
    ["zh", ["对话式精剪", "高质量影棚预设", "模板一键同款", "多素材与官网直采"]],
  ] as const)("shows all four %s features while hovering over the trigger or panel", (locale, titles) => {
    const trigger = renderHeader(locale)
    expect(trigger.getAttribute("aria-expanded")).toBe("false")
    fireEvent.mouseEnter(trigger)
    // jsdom does not implement the native popover top layer.
    const panel = screen.getByRole("region", { hidden: true })
    expect(panel.getAttribute("aria-label")).toBe(trigger.textContent)
    expect(trigger.getAttribute("aria-controls")).toBe(panel.id)
    expect(within(panel).getAllByRole("term", { hidden: true }).map(term => term.textContent)).toEqual(titles)
    expect(within(panel).getAllByRole("definition", { hidden: true })).toHaveLength(4)
    expect(within(panel).queryByRole("link", { hidden: true })).toBeNull()
    fireEvent.mouseOut(trigger, { relatedTarget: panel })
    expect(trigger.getAttribute("aria-expanded")).toBe("true")
    fireEvent.mouseOut(panel, { relatedTarget: document.body })
    expect(screen.queryByRole("region", { hidden: true })).toBeNull()
  })

  it("opens on focus, dismisses with Escape and closes when focus moves to FAQ", () => {
    const trigger = renderHeader("en")
    fireEvent.focusIn(trigger)
    expect(trigger.getAttribute("aria-expanded")).toBe("true")
    fireEvent.keyDown(trigger, { key: "Escape" })
    expect(screen.queryByRole("region", { hidden: true })).toBeNull()
    fireEvent.click(trigger)
    expect(trigger.getAttribute("aria-expanded")).toBe("true")
    fireEvent.focusOut(trigger, { relatedTarget: screen.getByRole("link", { name: "FAQ" }) })
    expect(screen.queryByRole("region", { hidden: true })).toBeNull()
  })
})
