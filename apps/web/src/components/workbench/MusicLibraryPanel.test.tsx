// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "@/lib/i18n"
import MusicLibraryPanel, { type MusicLibraryItem } from "./MusicLibraryPanel"

const sampleTrack: MusicLibraryItem = {
  id: "11111111-1111-4111-8111-111111111111",
  mood: "promo-keynote-percussion",
  title: "Precision Tech Pulse",
  title_zh: "清透现代科技律动",
  category: "product_promo",
  genre: "Ambient Electro",
  energy: "medium",
  bpm: 112,
  format_kind: "arc_90s",
  summary: "Clean modern tech launch electronica.",
  use_for: ["Modern SaaS UI demo"],
  avoid: [],
  sections: [
    { name: "intro", label: "Intro", label_zh: "铺垫起势", start_seconds: 0, end_seconds: 20, voice_friendly: true },
    {
      name: "groove",
      label: "UI Groove",
      label_zh: "清透主律动",
      start_seconds: 20,
      end_seconds: 55,
      voice_friendly: true,
      recommended: true,
      note_zh: "30–60s 带旁白 UI 演示推荐切入",
    },
  ],
  waveform_peaks: [0.2, 0.5, 0.8, 0.6],
  url: "/api/v1/music/11111111-1111-4111-8111-111111111111/stream",
  duration_seconds: 170,
  lufs: -15.3,
  tags: ["product-promo", "voice-friendly"],
  scope: "platform",
  status: "curated",
}

const mockApiFetch = vi.fn()
vi.mock("@/lib/api", () => ({
  API_URL: "http://localhost:8000",
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}))

afterEach(() => {
  cleanup()
  mockApiFetch.mockReset()
})

describe("MusicLibraryPanel", () => {
  it("renders empty state honestly when library has no tracks", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => [] })
    render(
      <I18nextProvider i18n={createI18n("en")}>
        <MusicLibraryPanel />
      </I18nextProvider>,
    )
    expect(await screen.findByText(/Music 3\.0 library is ready/i)).toBeTruthy()
  })

  it("renders annotated sections and cites recommended source_start_seconds", async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => [sampleTrack] })
    const onUsePreset = vi.fn()
    render(
      <I18nextProvider i18n={createI18n("zh")}>
        <MusicLibraryPanel onUsePreset={onUsePreset} />
      </I18nextProvider>,
    )
    expect(await screen.findByText("清透现代科技律动")).toBeTruthy()
    expect(screen.getByText("铺垫起势")).toBeTruthy()
    expect(screen.getByText("清透主律动")).toBeTruthy()
    expect(screen.getByText("旁白友好")).toBeTruthy()

    // Renders table structure in list view with Copy and recommended cut action
    expect(screen.getByRole("table")).toBeTruthy()
    expect(screen.getByRole("button", { name: /复制/ })).toBeTruthy()

    // Clicking "从 0:20 切入" passes exact source_start_seconds: 20
    fireEvent.click(screen.getByRole("button", { name: /从 0:20 切入/ }))
    await waitFor(() => {
      expect(onUsePreset).toHaveBeenCalledTimes(1)
      expect(onUsePreset.mock.calls[0][0]).toContain("source_start_seconds: 20")
      expect(onUsePreset.mock.calls[0][0]).toContain(sampleTrack.id)
    })

    // Clicking play resolves relative /api/v1/... stream path against API_URL
    const createdUrls: string[] = []
    class FakeAudio {
      preload = ""
      currentTime = 0
      duration = 170
      constructor(src: string) {
        createdUrls.push(src)
      }
      addEventListener() {}
      pause() {}
      play() {
        return Promise.resolve()
      }
    }
    vi.stubGlobal("Audio", FakeAudio)
    try {
      fireEvent.click(screen.getByRole("button", { name: /播放 清透现代科技律动/ }))
      expect(createdUrls[0]).toBe(`http://localhost:8000${sampleTrack.url}`)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
