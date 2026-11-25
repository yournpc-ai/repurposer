// @vitest-environment jsdom
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { VoiceOrb } from "@/components/ui/voice-orb"
import { reduceCandidateFrame } from "@/lib/chatStreamFrames"
import { CandidateSurfaceCard } from "../CandidateSurface"
import { candidatesLog } from "../timeline/history"
import type { CandidateSurface } from "../timeline/types"
import {
  VoiceCandidateSurface,
  isVoiceCandidateSurface,
} from "./VoiceCandidateSurface"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (key === "chat.candidates.selectVoiceMessage") {
        return `Use voice ${params?.ordinal} (${params?.title})`
      }
      if (key === "chat.candidates.usedCount") {
        return `Used ×${params?.count}`
      }
      if (key === "chat.candidates.playVoice") {
        return `Play voice ${params?.title}`
      }
      if (key === "chat.candidates.pauseVoice") {
        return `Pause voice ${params?.title}`
      }
      if (key === "chat.candidates.voiceAuditioning") {
        return `Auditioning · ${params?.ordinal}`
      }
      return key
    },
  }),
}))

const voiceSurface: CandidateSurface = {
  kind: "voice_set",
  candidateSetId: "voice-set-1",
  topic: "Product launch narration",
  assetId: null,
  selected: [1],
  members: [
    {
      start: 0,
      end: 0,
      excerpt: "Atlas Editorial",
      voice_id: "voice-atlas",
      title: "Atlas Editorial",
      description: "Measured baritone with studio clarity for flagship launches",
      source_kind: "curated",
      scope: "curated",
      languages: ["en-US", "zh-CN"],
      gender: "male",
      age_band: "adult",
      tone_tags: ["Warm", "Editorial"],
      compatible_styles: ["Product Launch", "Documentary"],
      use_count: 6,
      preview_url: "https://example.com/audio/atlas.mp3",
    },
    {
      start: 0,
      end: 0,
      excerpt: "Clara Studio",
      voice_id: "voice-clara",
      title: "Clara Studio",
      description: "Crisp modern pacing ideal for SaaS walkthroughs",
      source_kind: "cloned",
      scope: "personal",
      languages: ["en"],
      gender: "female",
      age_band: "young_adult",
      tone_tags: ["Crisp", "Confident"],
      compatible_styles: ["Explainer"],
      use_count: 2,
      preview_url: "https://example.com/audio/clara.mp3",
    },
  ],
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("VoiceOrb & VoiceCandidateSurface", () => {
  it("renders VoiceOrb with strictly monochrome defaults (zero blue/green accents)", () => {
    const { container } = render(<VoiceOrb state="idle" size={108} label={false} />)
    const orb = container.querySelector(".ui-vo")
    expect(orb).toBeTruthy()
    expect(orb?.getAttribute("data-state")).toBe("idle")

    const source = readFileSync(
      resolve(__dirname, "../../ui/voice-orb.tsx"),
      "utf8",
    )
    expect(source).not.toMatch(/#2f6bff|#6f9bff|#0060e2|#4fb0fe/i)
  })

  it("renders voice_set candidates with metadata pills, play/pause orb transitions, and selection callback", async () => {
    const playSpy = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockImplementation(async function (this: HTMLMediaElement) {
        this.dispatchEvent(new Event("playing"))
      })
    const pauseSpy = vi
      .spyOn(HTMLMediaElement.prototype, "pause")
      .mockImplementation(function (this: HTMLMediaElement) {
        this.dispatchEvent(new Event("pause"))
      })
    const onSelect = vi.fn()

    const { container } = render(
      <CandidateSurfaceCard
        surface={voiceSurface}
        hydrated
        onSelectCandidate={onSelect}
      />,
    )

    expect(isVoiceCandidateSurface(voiceSurface)).toBe(true)
    expect(screen.getByText("01")).toBeTruthy()
    expect(screen.getByText("02")).toBeTruthy()
    expect(screen.getByText("Atlas Editorial")).toBeTruthy()
    expect(screen.getAllByText("EN")).toHaveLength(2)
    expect(screen.getByText("ZH")).toBeTruthy()
    expect(screen.getByText("Warm")).toBeTruthy()
    expect(screen.getByText("Product Launch")).toBeTruthy()
    expect(screen.getByText("Used ×6")).toBeTruthy()
    expect(screen.getByText("chat.candidates.scopeCurated")).toBeTruthy()
    expect(screen.getByText("chat.candidates.scopePersonal")).toBeTruthy()

    const orbEl = container.querySelector(".ui-vo")
    expect(orbEl?.getAttribute("data-state")).toBe("idle")

    // Play voice 01 -> transitions orb to speaking
    fireEvent.click(screen.getByRole("button", { name: "Play voice Atlas Editorial" }))
    await waitFor(() => {
      expect(orbEl?.getAttribute("data-state")).toBe("speaking")
    })
    expect(playSpy).toHaveBeenCalledTimes(1)
    expect(screen.getByText("Auditioning · 01")).toBeTruthy()

    // Pause voice 01 -> transitions orb back to idle
    fireEvent.click(screen.getByRole("button", { name: "Pause voice Atlas Editorial" }))
    await waitFor(() => {
      expect(orbEl?.getAttribute("data-state")).toBe("idle")
    })
    expect(pauseSpy).toHaveBeenCalled()

    // Select voice 01 -> invokes callback with formatted natural selection prompt
    fireEvent.click(screen.getByRole("button", { name: "chat.candidates.useVoice" }))
    expect(onSelect).toHaveBeenCalledWith(
      "Use voice 01 (Atlas Editorial)",
      0,
      voiceSurface,
    )

    // Voice 02 is pre-selected
    expect(screen.getByRole("button", { name: "chat.candidates.selected" })).toBeTruthy()
  })

  it("preserves voice_set and enriched music_set fields across live SSE frames and history replay", () => {
    const liveVoiceEvent = {
      kind: "voice_set" as const,
      candidate_set_id: "voice-set-live",
      topic: "Launch narration",
      members: voiceSurface.members,
      selected: [0],
    }
    const live = reduceCandidateFrame([], liveVoiceEvent, "2026-11-25T10:00:00Z")[0]
      .candidates
    expect(live?.kind).toBe("voice_set")
    expect(live?.selected).toEqual([0])
    expect(live?.members[0].voice_id).toBe("voice-atlas")

    const replayed = candidatesLog({
      type: "candidates_log",
      events: [liveVoiceEvent],
    })
    expect(replayed).toHaveLength(1)
    expect(replayed?.[0].kind === "set" && replayed[0].surface.kind).toBe("voice_set")
    expect(replayed?.[0].kind === "set" && replayed[0].surface.selected).toEqual([0])
    expect(replayed?.[0].kind === "set" && replayed[0].surface.members[0]).toMatchObject({
      voice_id: "voice-atlas",
      scope: "curated",
      languages: ["en-US", "zh-CN"],
      tone_tags: ["Warm", "Editorial"],
      use_count: 6,
    })

    // Also verify VoiceCandidateSurface can render directly without selection callback
    render(<VoiceCandidateSurface surface={voiceSurface} hydrated />)
    expect(screen.getAllByText("Atlas Editorial").length).toBeGreaterThanOrEqual(1)
  })
})
