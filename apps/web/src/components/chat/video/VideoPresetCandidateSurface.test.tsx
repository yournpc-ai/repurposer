// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import type { VideoSpec } from "@repurposer/video-spec"
import { afterEach, describe, expect, it, vi } from "vitest"
import { I18nextProvider } from "react-i18next"
import { createI18n, type Locale } from "@/lib/i18n"
import { CandidateSurfaceCard } from "../CandidateSurface"
import { candidatesLog } from "../timeline/history"
import type { CandidateSurface } from "../timeline/types"

vi.mock("./MotionPresetPlayer", () => ({
  default: ({ spec }: { spec: VideoSpec }) => <div data-testid="player">{spec.duration_frames}</div>,
}))

const spec: VideoSpec = {
  family: "video", format: 1, fps: { num: 30, den: 1 }, duration_frames: 84, width: 1280, height: 720,
  background: "#09090B", sample_rate: 48000, fonts: [], tracks: [{ track_id: "main", role: "main", kind: "visual", order: 0, clips: [] }],
  provenance: { composition_id: "preview", composition_version_id: "demo", content_digest: "a".repeat(64) },
}
const surface: CandidateSurface = {
  kind: "video_preset_set", candidateSetId: "set", assetId: null, topic: "motion", selected: [2],
  members: ["kinetic_beat:typewriter_swap", "ui_montage:fan_slide", "text-reveal"].map((id, i) => ({
    start: 0, end: 2.8, excerpt: id, preset_id: id, duration_seconds: 2.8, title: id, preview_digest: "a".repeat(64),
    width: 1280, height: 720, aspect: "16:9", ...(i < 2 ? { preview_spec: spec } : { preview_url: "/reveal.mp4" }),
  })),
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function renderSurface(select: () => void, locale: Locale) {
  return render(<I18nextProvider i18n={createI18n(locale)}>
    <CandidateSurfaceCard surface={surface} onSelectCandidate={select} />
  </I18nextProvider>)
}

describe("motion comparison in Chat", () => {
  it("replays inline specs and MP4s and sends the chosen ordinal through Chat", async () => {
    vi.stubGlobal("FontFace", class {})
    vi.stubGlobal("CanvasRenderingContext2D", class {})
    const select = vi.fn()
    const replay = candidatesLog({ type: "candidates_log", events: [{
      kind: surface.kind, candidate_set_id: surface.candidateSetId, members: surface.members,
    }] })
    expect(replay?.[0]).toMatchObject({ kind: "set", surface: { members: [
      { preview_spec: spec }, { preview_spec: spec }, { preview_url: "/reveal.mp4" },
    ] } })
    const { container } = renderSurface(select, "en")
    expect(screen.getByText("Typewriter swap")).toBeTruthy()
    expect(await screen.findAllByTestId("player")).toHaveLength(2)
    expect(container.querySelector("video")?.getAttribute("src")).toBe("/reveal.mp4")
    const button = screen.getAllByRole("button", { name: "Use" })[1]
    expect(button.className).toContain("rounded-full")
    fireEvent.click(button)
    expect(select).toHaveBeenCalledWith("Use motion 02 (Fan slide)", 1, surface)
    expect(screen.getByRole("button", { pressed: true }).className).toContain("bg-foreground")
    expect(container.innerHTML).not.toMatch(/(?:bg|text|border)-(?:blue|green|emerald)-/)
  })

  it("keeps selection available without a canvas", () => {
    vi.stubGlobal("CanvasRenderingContext2D", undefined)
    const select = vi.fn()
    renderSurface(select, "zh")
    expect(screen.getByText("斜角横滑")).toBeTruthy()
    expect(screen.queryByTestId("player")).toBeNull()
    expect(screen.getAllByText("预览不可用")).toHaveLength(2)
    fireEvent.click(screen.getAllByRole("button", { name: "选用" })[0])
    expect(select).toHaveBeenCalledTimes(1)
  })
})
