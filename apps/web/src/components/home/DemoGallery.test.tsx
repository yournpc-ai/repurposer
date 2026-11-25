// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { createRef } from "react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { createI18n } from "@/lib/i18n"
import { DemoCard, DemoGallery } from "./DemoGallery"

const i18n = createI18n("en")
const play = vi.fn().mockResolvedValue(undefined)
beforeEach(() => {
  const observer = class { observe() {} disconnect() {} }
  vi.stubGlobal("ResizeObserver", observer)
  vi.stubGlobal("IntersectionObserver", observer)
  vi.stubGlobal("matchMedia", () => ({ matches: false }))
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(play)
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); play.mockClear() })

function gallery() {
  const onPrefill = vi.fn()
  render(<I18nextProvider i18n={i18n}>
    <DemoGallery scrollRef={createRef<HTMLDivElement>()} onPrefill={onPrefill} />
  </I18nextProvider>)
  return onPrefill
}

it("starts with every sample on the mixed shelf and selects only real template entries", () => {
  const onPrefill = gallery()
  const tabs = screen.getAllByRole("radio")
  expect(tabs.map(tab => tab.textContent)).toEqual([
    "Discover", "Templates", "Product Promo", "Text Animation", "Knowledge Explainer", "Talking Head",
  ])
  expect(tabs[0].getAttribute("aria-checked")).toBe("true")
  const cards = screen.getAllByRole("article")
  expect(cards).toHaveLength(8)
  expect(cards[0].classList.contains("aspect-video")).toBe(true)
  expect(cards[1].classList.contains("aspect-[9/16]")).toBe(true)
  for (const card of cards) {
    expect(card.classList.contains("h-[13.5rem]")).toBe(true)
    expect(card.classList.contains("sm:h-[15rem]")).toBe(true)
    expect(card.querySelector("video")?.classList.contains("object-cover")).toBe(true)
    expect(within(card).queryByText("Template")).toBeNull()
  }
  fireEvent.click(within(cards[1]).getByRole("button", { name: /Make one like this/ }))
  expect(onPrefill).toHaveBeenCalledWith("recipes.shelf.demos.talking-head.prompt", null)
  fireEvent.keyDown(tabs[0], { key: "ArrowRight" })
  expect(tabs[1].getAttribute("aria-checked")).toBe("true")
  expect(screen.getByText("No templates available yet.")).toBeTruthy()
  expect(screen.queryByRole("article")).toBeNull()
})

it.each([
  ["Product Promo", ["Product launches", "Website promos", "Walkthroughs"]],
  ["Text Animation", ["Manifestos & announcements", "Ideas & quotes"]],
  ["Knowledge Explainer", ["Concepts & principles", "Research & reports"]],
  ["Talking Head", ["Perspectives", "Interviews & lectures"]],
] as const)("shows the %s subnavigation and its matching shelves", (name, labels) => {
  gallery()
  fireEvent.click(screen.getByRole("radio", { name }))
  expect(within(screen.getByRole("navigation")).getAllByRole("button").map(el => el.textContent)).toEqual(labels)
  expect(screen.getAllByRole("heading").map(el => el.textContent)).toEqual(labels)
})

it("previews with sound on mouse hover, supports the volume button and mutes on leave", () => {
  gallery()
  const card = screen.getAllByRole("article")[0]
  const video = card.querySelector("video")!
  fireEvent.pointerEnter(card, { pointerType: "mouse" })
  expect(play).toHaveBeenCalledOnce()
  expect(video.muted).toBe(false)
  fireEvent.volumeChange(video)
  fireEvent.click(within(card).getByRole("button", { name: "Mute" }))
  expect(video.muted).toBe(true)
  fireEvent.volumeChange(video)
  fireEvent.click(within(card).getByRole("button", { name: "Play sound" }))
  expect(video.muted).toBe(false)
  fireEvent.pointerLeave(card)
  expect(video.muted).toBe(true)
})

it.each([["1:1", "aspect-square"], ["4:5", "aspect-[4/5]"]] as const)(
  "labels a bound %s card and preserves its exact reference", (aspect, aspectClass) => {
    const demo = {
      section: "website", title: "Sample", prompt: "Brief", src: "/sample.mp4", aspect,
      templateReference: { kind: "external" as const, skill_version_id: "test-only" },
    }
    const onPrefill = vi.fn()
    render(<I18nextProvider i18n={i18n}><DemoCard demo={demo} onPrefill={onPrefill} /></I18nextProvider>)
    expect(screen.getByRole("article").classList.contains(aspectClass)).toBe(true)
    expect(screen.getByText("Template")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Use template · Sample" }))
    expect(onPrefill).toHaveBeenCalledWith(demo)
  },
)
