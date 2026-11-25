// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { apiFetch } from "@/lib/api"
import { createI18n } from "@/lib/i18n"
import VisualPresetGalleryPanel from "./VisualPresetGalleryPanel"

const { cite, play } = vi.hoisted(() => ({ cite: vi.fn(() => true), play: vi.fn() }))
vi.mock("./WorkbenchContext", () => ({ useWorkbench: () => ({ citeText: cite }) }))
vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }))
vi.mock("motion/react", () => ({ useReducedMotion: () => false }))
vi.mock("@/components/chat/video/MotionPresetPlayer", () => ({
  default: ({ title, spec }: { title: string; spec: { duration_frames: number } }) =>
    <button aria-label={`Play ${title}`} onClick={play} data-testid="player">{spec.duration_frames}</button>,
}))

const block = {
  name: "Logo Wall", name_zh: "标志墙", id: "logo_wall", category: "logos_partners",
  summary: "Rolling partner logos", recommended_sfx: ["dsp_velvet_pass"],
  preview_spec: { duration_frames: 90, width: 1280, height: 720 }, preview_duration_s: 3,
}
const text = { ...block, name: "Neon Pulse", name_zh: "霓虹辉光", id: "neon_pulse", category: "fx_display", recommended_sfx: [] }
const stage = { ...block, name: "Stage", name_zh: "舞台", id: "stage", category: "devices" }

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} })
  vi.mocked(apiFetch).mockImplementation(async path => {
    const url = new URL(path, "http://localhost")
    const rows = url.pathname.endsWith("/blocks") ? [stage, block] : [
      ...Array.from({ length: 20 }, (_, i) => ({ ...stage, id: "title_" + i, name: "Title " + i })), text,
    ]
    const offset = Number(url.searchParams.get("offset"))
    return Response.json({ items: rows.slice(offset, offset + Number(url.searchParams.get("limit"))) })
  })
})
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals() })

function gallery(kind: "block" | "text_preset", language: "en" | "zh" = "en") {
  return render(<I18nextProvider i18n={createI18n(language)}><VisualPresetGalleryPanel kind={kind} /></I18nextProvider>)
}

describe("visual preset galleries", () => {
  it("filters across pages by category and searches either language", async () => {
    gallery("text_preset")
    await screen.findByRole("article", { name: "Neon Pulse" })
    expect(screen.getAllByRole("article")).toHaveLength(21)
    fireEvent.click(screen.getByRole("combobox", { name: "Category" }))
    fireEvent.click(within(screen.getByRole("listbox", { hidden: true })).getByText("Display effects"))
    expect(screen.getAllByRole("article")).toHaveLength(1)
    const search = screen.getByRole("searchbox")
    for (const query of ["霓虹", "nEoN"]) {
      fireEvent.change(search, { target: { value: query } })
      expect(screen.getByRole("article", { name: "Neon Pulse" })).toBeTruthy()
    }
    fireEvent.change(search, { target: { value: "stage" } })
    expect(screen.getByRole("status").textContent).toBe("No matching presets")
  })

  it("mounts just the active shared player, loops on hover and supports explicit preview", async () => {
    gallery("block")
    const logo = await screen.findByRole("article", { name: "Logo Wall" })
    const stageCard = screen.getByRole("article", { name: "Stage" })
    expect(screen.queryByTestId("player")).toBeNull()
    fireEvent.mouseEnter(logo)
    expect(within(logo).getByTestId("player").textContent).toBe("90")
    expect(play).toHaveBeenCalledTimes(1)
    fireEvent.mouseEnter(stageCard)
    expect(within(logo).queryByTestId("player")).toBeNull()
    expect(within(stageCard).getByTestId("player")).toBeTruthy()
    fireEvent.mouseLeave(stageCard)
    expect(screen.queryByTestId("player")).toBeNull()
    fireEvent.click(within(logo).getByRole("button", { name: "Play Logo Wall" }))
    expect(document.activeElement).toBe(within(logo).getByTestId("player"))
    expect(screen.getAllByTestId("player")).toHaveLength(1)
  })

  it.each([
    ["block", "标志墙", "Logo Wall", "block_id: logo_wall"],
    ["text_preset", "霓虹辉光", "Neon Pulse", "text_preset: neon_pulse"],
  ] as const)("cites %s in Chinese and uses neutral card and control styles", async (kind, title, alternate, field) => {
    const { container } = gallery(kind, "zh")
    const card = await screen.findByRole("article", { name: title })
    expect(within(card).getByText(alternate)).toBeTruthy()
    if (kind === "block") expect(within(card).getByText(/推荐音效/)).toBeTruthy()
    fireEvent.click(within(card).getByRole("button", { name: "引用到对话" }))
    expect(cite).toHaveBeenCalledWith(expect.stringContaining(field))
    expect(cite).toHaveBeenCalledWith(expect.stringContaining(title))
    const classes = [...container.querySelectorAll("[class]")].map(el => el.getAttribute("class")).join(" ")
    expect(classes).not.toMatch(/(?:^|[\s:-])(?:slate|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d/)
  })

  it("retries a failed catalog request", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(new Response(null, { status: 503 }))
    gallery("block")
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }))
    expect(await screen.findByRole("article", { name: "Logo Wall" })).toBeTruthy()
  })
})
