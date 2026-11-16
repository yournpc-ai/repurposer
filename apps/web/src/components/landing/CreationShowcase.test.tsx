// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CreationShowcase } from "./CreationShowcase"

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("./motion", () => ({ useReducedMotion: () => false }))
vi.mock("./useLandingCreate", () => ({ useLandingCreate: () => vi.fn() }))

let visibility: IntersectionObserverCallback
beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(document, "hidden", "get").mockReturnValue(false)
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined)
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {})
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: IntersectionObserverCallback) { visibility = callback }
    observe() { visibility([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver) }
    disconnect() {}
  })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const selected = () => screen.getAllByRole("tab").findIndex((tab) => tab.getAttribute("aria-selected") === "true")

describe("showcase playback", () => {
  it("reveals video with the reply and automatically advances to the next tab", () => {
    const { container } = render(<CreationShowcase />)
    expect(container.querySelector("video")?.autoplay).toBe(false)
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(4_080))
    expect(container.querySelector("video")?.autoplay).toBe(true)
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(3_920))
    expect(selected()).toBe(1)
    expect(container.querySelector("video")?.autoplay).toBe(false)
  })

  it("continues autoplay and rotation after a manual tab selection", () => {
    const { container } = render(<CreationShowcase />)
    fireEvent.click(screen.getAllByRole("tab")[2])
    expect(selected()).toBe(2)
    expect(container.querySelector("video")?.autoplay).toBe(false)
    act(() => vi.advanceTimersByTime(8_000))
    expect(selected()).toBe(3)
  })

  it("pauses offscreen and resumes without losing the selected tab", () => {
    const { container } = render(<CreationShowcase />)
    const source = container.querySelector("video")?.getAttribute("src")
    act(() => visibility([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver))
    expect(container.querySelector("video")?.autoplay).toBe(false)
    expect(container.querySelector("video")?.getAttribute("src")).toBe(source)
    act(() => vi.advanceTimersByTime(16_000))
    expect(selected()).toBe(0)
    act(() => visibility([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver))
    act(() => vi.advanceTimersByTime(4_080))
    expect(container.querySelector("video")?.autoplay).toBe(true)
  })
})
