// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    globalThis.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
})

const { navigateMock, apiFetchMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  apiFetchMock: vi.fn(),
}))

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (opts: unknown) => opts,
  useNavigate: () => navigateMock,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}:${JSON.stringify(opts)}` : key,
    i18n: { language: "en" },
  }),
}))

vi.mock("@/lib/api", () => ({
  apiFetch: apiFetchMock,
}))

import { AssetsPage } from "./_app.assets"

const SAMPLE_LIBRARY = {
  projects: [
    {
      id: "proj-1",
      title: "OxValue Launch",
      upload_count: 1,
      export_count: 1,
      total_count: 2,
      latest_at: "2026-11-26T10:00:00Z",
    },
    {
      id: "proj-2",
      title: "Hiring Teaser",
      upload_count: 1,
      export_count: 0,
      total_count: 1,
      latest_at: "2026-11-25T10:00:00Z",
    },
  ],
  uploads: [
    {
      id: "asset-1",
      title: "hero-demo.mp4",
      type: "video",
      project_id: "proj-1",
      project_title: "OxValue Launch",
      stream_url: "https://cdn.example/hero-demo.mp4",
      duration_seconds: 22,
      size_bytes: 5_242_880,
      width: 1920,
      height: 1080,
      processing_status: "completed",
      created_at: "2026-11-26T09:00:00Z",
    },
    {
      id: "asset-2",
      title: "team-photo.png",
      type: "image",
      project_id: "proj-2",
      project_title: "Hiring Teaser",
      stream_url: "https://cdn.example/team-photo.png",
      duration_seconds: null,
      size_bytes: 420_000,
      width: 1600,
      height: 900,
      processing_status: "completed",
      created_at: "2026-11-25T09:00:00Z",
    },
  ],
  exports: [
    {
      id: "out-1",
      title: "OxValue Final Cut",
      project_id: "proj-1",
      project_title: "OxValue Launch",
      composition_id: "comp-1",
      composition_version_id: "ver-1",
      composition_version_number: 4,
      video_url: "https://cdn.example/exports/out-1.mp4",
      poster_url: "https://cdn.example/exports/out-1.jpg",
      duration_seconds: 30,
      width: 1920,
      height: 1080,
      created_at: "2026-11-26T10:00:00Z",
    },
  ],
  audio: [
    {
      id: "music-1",
      kind: "music",
      title: "Obsidian Pulse",
      subtitle: "Dark minimal electronic",
      stream_url: "/api/v1/music/music-1/stream",
      duration_seconds: 40,
      size_bytes: 800_000,
      tags: ["electronic"],
      use_count: 1,
      created_at: "2026-11-24T10:00:00Z",
    },
  ],
  skills: [
    {
      skill_id: "sk-1",
      skill_version_id: "sv-1",
      name: "OxValue Blueprint",
      description: "5-act launch promo",
      version_number: 1,
      act_count: 5,
      slot_count: 9,
      duration_s: 28,
      style_preset: "institutional_dark",
      created_at: "2026-11-23T10:00:00Z",
    },
  ],
}

afterEach(() => {
  cleanup()
  navigateMock.mockReset()
  apiFetchMock.mockReset()
})

describe("AssetsPage (/assets)", () => {
  it("loads project folders and filters library items by project folder and category", async () => {
    apiFetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => SAMPLE_LIBRARY,
    })

    render(<AssetsPage />)

    await waitFor(() => {
      expect(screen.getByText("hero-demo.mp4")).toBeTruthy()
    })

    expect(screen.getByText("OxValue Final Cut")).toBeTruthy()
    expect(screen.getByText("team-photo.png")).toBeTruthy()
    expect(screen.getByText("Obsidian Pulse")).toBeTruthy()
    expect(screen.getByText("OxValue Blueprint")).toBeTruthy()

    // Click the "Hiring Teaser" project folder button to filter down to its asset only
    const hiringFolderBtn = screen.getByRole("button", {
      name: /Hiring Teaser/i,
      pressed: false,
    })
    fireEvent.click(hiringFolderBtn)

    expect(screen.getByText("team-photo.png")).toBeTruthy()
    expect(screen.queryByText("hero-demo.mp4")).toBeNull()
    expect(screen.queryByText("OxValue Final Cut")).toBeNull()

    // Clear project filter brings everything back
    fireEvent.click(screen.getByRole("button", { name: /assetsPage.clearProjectFilter/i }))
    expect(screen.getByText("hero-demo.mp4")).toBeTruthy()
  })

  it("requests presigned download endpoint for uploads and hands off @asset mention to /home", async () => {
    apiFetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          projects: [SAMPLE_LIBRARY.projects[0]],
          uploads: [SAMPLE_LIBRARY.uploads[0]],
          exports: [],
          audio: [],
          skills: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          url: "https://tos.example/presigned/hero-demo.mp4",
          expires_in: 300,
        }),
      })

    render(<AssetsPage />)

    await waitFor(() => {
      expect(screen.getByText("hero-demo.mp4")).toBeTruthy()
    })

    fireEvent.click(screen.getByRole("button", { name: "assetsPage.download" }))
    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/assets/asset-1/download")
    })

    fireEvent.click(screen.getByRole("button", { name: "assetsPage.useInNewChat" }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: "/home",
      state: {
        prefillMention: {
          type: "asset",
          id: "asset-1",
          label: "hero-demo.mp4",
        },
      },
    })
  })
})
