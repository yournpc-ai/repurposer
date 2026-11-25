// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AudioCandidateSurface, soundDisplayTitle } from "./AudioCandidateSurface"
import type { CandidateSurface } from "../timeline/types"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("./WaveformPlayer", () => ({
  WaveformPlayer: ({ durationSeconds, waveformKey }: {
    durationSeconds: number
    waveformKey: string
  }) => (
    <div
      data-testid="waveform-player"
      data-duration={durationSeconds}
      data-identity={waveformKey}
    />
  ),
}))

const member = {
  start: 0,
  end: 3.2,
  excerpt: "Door click.mp3",
  speaker: null,
  provider: "freesound",
  provider_id: "12345",
  title: "Door click.mp3",
  author: "field-recordist",
  duration_seconds: 3.2,
  source_url: "https://freesound.org/people/field-recordist/sounds/12345/",
  preview_url: "https://cdn.freesound.org/previews/123/12345-hq.mp3",
  license: "CC0",
  attribution: '"Door click" by field-recordist on Freesound (CC0 1.0)',
  query: "door click",
}

const surface: CandidateSurface = {
  candidateSetId: "sfx-set-1",
  topic: "door click",
  assetId: null,
  members: [member],
  selected: [],
}

describe("AudioCandidateSurface display boundary", () => {
  it("shows ordinal, extension-free title, duration and selection without provider chrome", () => {
    const { container, rerender } = render(
      <AudioCandidateSurface surface={surface} hydrated />,
    )
    expect(screen.getByText("01")).toBeTruthy()
    expect(screen.getByText("Door click")).toBeTruthy()
    expect(screen.queryByText("Door click.mp3")).toBeNull()
    expect(screen.queryByText(/field-recordist/)).toBeNull()
    expect(screen.queryByText(/CC0/)).toBeNull()
    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.getByTestId("waveform-player").getAttribute("data-duration")).toBe("3.2")
    expect(screen.getByTestId("waveform-player").getAttribute("data-identity"))
      .toBe("sfx-set-1:12345:0")

    rerender(<AudioCandidateSurface surface={{ ...surface, selected: [0] }} hydrated />)
    expect(screen.getAllByTestId("waveform-player")).toHaveLength(1)
    expect(container.querySelector(".bg-accent")).not.toBeNull()
    // The hidden provider facts remain available to the audio type guard and
    // the server import; only their user-visible chrome is gone.
    expect(surface.members[0]).toMatchObject({
      author: "field-recordist",
      license: "CC0",
      source_url: member.source_url,
    })
  })

  it("removes only the final filename extension", () => {
    expect(soundDisplayTitle("Soft.UI.Button.WAV")).toBe("Soft.UI.Button")
    expect(soundDisplayTitle("Already clean")).toBe("Already clean")
    expect(soundDisplayTitle("Version 2.0")).toBe("Version 2.0")
  })

  it("displays enriched permanent music library chips (BPM, LUFS, instrumental, styles, use count) and Use track action", () => {
    const musicSurface: CandidateSurface = {
      kind: "music_set",
      candidateSetId: "music-set-rich",
      topic: "Minimalist studio pulse",
      assetId: null,
      selected: [],
      members: [
        {
          start: 0,
          end: 94,
          excerpt: "Monolith Pulse",
          speaker: null,
          provider: "music_library",
          provider_id: "music-1",
          music_id: "music-1",
          title: "Monolith Pulse",
          author: "Rookie Studio",
          duration_seconds: 94,
          source_url: null,
          preview_url: "/api/v1/music/music-1/stream",
          license: "Library",
          attribution: "Monolith Pulse",
          query: "minimalist studio",
          bpm: 108,
          lufs: -14.8,
          instrumental: true,
          compatible_styles: ["Product Launch", "Minimal"],
          use_count: 5,
        },
      ],
    }

    const onSelect = vi.fn()
    render(
      <AudioCandidateSurface
        surface={musicSurface}
        hydrated
        onSelectCandidate={onSelect}
      />,
    )

    expect(screen.getByText("Monolith Pulse")).toBeTruthy()
    expect(screen.getByText("108 BPM")).toBeTruthy()
    expect(screen.getByText("-14.8 LUFS")).toBeTruthy()
    expect(screen.getByText("chat.candidates.instrumental")).toBeTruthy()
    expect(screen.getByText("Product Launch")).toBeTruthy()
    expect(screen.getByText("Minimal")).toBeTruthy()
    expect(screen.getByText("chat.candidates.usedCount")).toBeTruthy()
    const useBtn = screen.getByRole("button", { name: "chat.candidates.useTrack" })
    expect(useBtn.className).toContain("rounded-full")
  })
})
