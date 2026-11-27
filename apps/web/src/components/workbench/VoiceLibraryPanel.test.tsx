// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import VoiceLibraryPanel, { type VoiceLibraryItem } from "./VoiceLibraryPanel"

const apiFetchMock = vi.fn()
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.id ? `${key}:${String(opts.name)}:${String(opts.id)}` : key,
    i18n: { language: "zh" },
  }),
}))

const VOICES: VoiceLibraryItem[] = [
  {
    id: "834c43d7-8796-4af6-b230-fe3b2474161c",
    scope: "user",
    status: "ready",
    source_kind: "minimax_clone",
    name: "创始人男声（视频复刻）",
    description: "基于演讲原声复刻的权威男声纹",
    languages: ["zh", "en"],
    gender: "male",
    tone_tags: ["authoritative", "promo"],
    compatible_styles: ["swiss_paper"],
    provider: "minimax",
    provider_voice_id: "vcfcd2df917d6a42",
    preview_url: "/api/v1/voices/834c43d7-8796-4af6-b230-fe3b2474161c/audio",
    use_count: 0,
    is_favorite: true,
  },
  {
    id: "e4bf8870-e632-4c8c-b7fc-71a700bf2761",
    scope: "platform",
    status: "curated",
    source_kind: "minimax_design",
    name: "旗舰商业宣传女声",
    description: "现代质感商业宣传片女声",
    languages: ["zh", "en"],
    gender: "female",
    tone_tags: ["commercial", "warm"],
    compatible_styles: ["swiss_paper"],
    provider: "minimax",
    provider_voice_id: "ttv-voice-test",
    preview_url: "/api/v1/voices/e4bf8870-e632-4c8c-b7fc-71a700bf2761/audio",
    use_count: 0,
    is_favorite: true,
  },
]

describe("VoiceLibraryPanel", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => VOICES,
    })
  })

  it("renders both permanent voices and cites the selected voice instruction", async () => {
    const onUsePreset = vi.fn()
    const onCountChange = vi.fn()
    render(<VoiceLibraryPanel onUsePreset={onUsePreset} onCountChange={onCountChange} />)

    await waitFor(() => {
      expect(screen.getByText("创始人男声（视频复刻）")).toBeTruthy()
      expect(screen.getByText("旗舰商业宣传女声")).toBeTruthy()
    })
    expect(onCountChange).toHaveBeenCalledWith(2)

    const useButtons = screen.getAllByRole("button", { name: "presetsPage.usePreset" })
    fireEvent.click(useButtons[0])
    expect(onUsePreset).toHaveBeenCalledWith(
      expect.stringContaining("834c43d7-8796-4af6-b230-fe3b2474161c"),
    )
  })
})
