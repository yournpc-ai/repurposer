// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { SOUND_RECIPES, TUNE_SCHEMA } from "@repurposer/sound-engine"
import { apiFetch } from "@/lib/api"
import SoundLabPanel from "./SoundLabPanel"

const { cite, start, stop } = vi.hoisted(() => ({ cite: vi.fn((_text: string) => true), start: vi.fn(), stop: vi.fn() }))
vi.mock("./WorkbenchContext", () => ({ useWorkbench: () => ({ citeText: cite }) }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({
  i18n: { language: "en" }, t: (key: string, opts?: { settings: string }) => opts?.settings ?? key,
}) }))
vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }))

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} })
  vi.stubGlobal("AudioContext", class {
    state = "running"
    createBuffer(_channels: number, length: number) { return { getChannelData: () => new Float32Array(length) } }
    createBufferSource() { return { connect() {}, disconnect() {}, start, stop } }
    close() {}
  })
  vi.mocked(apiFetch).mockImplementation(async path => {
    const query = new URL(path, "http://localhost").searchParams
    const offset = Number(query.get("offset"))
    const items = SOUND_RECIPES.filter(r => r.domain === query.get("domain")).slice(offset, offset + 20)
      .map(r => ({ ...r, id: "dsp_" + r.id, recipe_id: r.id, engine_kind: "dsp_recipe",
        duration_ms: 200, waveform_peaks: [0.2, 0.8], summary: r.desc }))
    return new Response(JSON.stringify({ items }))
  })
})

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals() })

describe("Sound Lab", () => {
  it("filters both domains across all categories and searches bilingual names", async () => {
    render(<SoundLabPanel />)
    await screen.findByText("Tap Glass")
    for (const domain of ["interface", "video"]) {
      if (domain === "video") {
        fireEvent.click(screen.getByRole("radio", { name: "soundLab.video" }))
        await screen.findByText("Trans Shutter")
      }
      fireEvent.click(screen.getByRole("combobox"))
      const list = screen.getByRole("listbox", { hidden: true })
      expect(within(list).getAllByRole("option", { hidden: true })).toHaveLength(13)
      const categories = new Set(SOUND_RECIPES.filter(r => r.domain === domain).map(r => r.category))
      for (const c of categories) expect(within(list).getByText("soundLab.categories." + c)).toBeTruthy()
      fireEvent.click(within(list).getByText("soundLab.categories." + (domain === "video" ? "transitions" : "tap")))
    }
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "黑胶" } })
    expect(screen.getByRole("button", { name: /Trans Vinyl Pull/ })).toBeTruthy()
    expect(screen.queryByText("Trans Shutter")).toBeNull()
  })

  it("plays a recording URL, stops it on unmount and cites its permanent slug", async () => {
    const play = vi.fn(async () => {})
    const pause = vi.fn()
    const audio = vi.fn(function () { return { play, pause } })
    vi.stubGlobal("Audio", audio)
    vi.mocked(apiFetch).mockResolvedValue(new Response(JSON.stringify({ items: [{
      id: "foley_switch", name: "Switch", category: "toggle", engine_kind: "sample",
      audio_url: "/media/switch.wav", duration_ms: 385, waveform_peaks: [], moods: [], use_for: [],
    }] })))
    const page = render(<SoundLabPanel />)
    fireEvent.click(await screen.findByRole("button", { name: /Switch/ }))
    expect(audio).toHaveBeenCalledWith("/media/switch.wav")
    expect(play).toHaveBeenCalledOnce()
    expect(screen.queryAllByRole("slider")).toHaveLength(0)
    fireEvent.click(screen.getByText("soundLab.cite"))
    expect(JSON.parse(cite.mock.calls.at(-1)![0])).toEqual({ sfx_id: "foley_switch", sfx_slug: "foley_switch" })
    page.unmount()
    expect(pause).toHaveBeenCalledOnce()
  })

  it("previews stereo synthesis, cites only changed axes and restores all defaults", async () => {
    const { container } = render(<SoundLabPanel />)
    fireEvent.click(await screen.findByText("Tap Glass"))
    expect(start).toHaveBeenCalledOnce()
    const sliders = screen.getAllByRole("slider")
    expect(sliders).toHaveLength(7)
    for (const key of Object.keys(TUNE_SCHEMA) as (keyof typeof TUNE_SCHEMA)[]) {
      const slider = screen.getByRole("slider", { name: "soundLab.axes." + key })
      fireEvent.change(slider, { target: { value: TUNE_SCHEMA[key].max } })
    }
    fireEvent.pointerUp(sliders[0])
    expect(start).toHaveBeenCalledTimes(2)
    expect(stop).toHaveBeenCalled()
    fireEvent.click(screen.getByText("soundLab.cite"))
    expect(JSON.parse(cite.mock.calls.at(-1)![0])).toMatchObject({
      recipe_id: "tap_glass", sfx_id: "dsp_tap_glass", tune: { length_scale: 3, pitch_st: 12 },
    })
    fireEvent.click(screen.getByText("soundLab.reset"))
    fireEvent.click(screen.getByText("soundLab.cite"))
    expect(JSON.parse(cite.mock.calls.at(-1)![0])).not.toHaveProperty("tune")
    await waitFor(() => expect((sliders[0] as HTMLInputElement).value).toBe("0"))
    expect(container.innerHTML).not.toMatch(/(?:bg-|text-|border-|accent-)(?:blue|green|emerald|cyan)-/)
  })
})
