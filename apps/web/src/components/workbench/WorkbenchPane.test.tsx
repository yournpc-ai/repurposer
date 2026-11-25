// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  }
})

import { AssistantText } from "@/components/chat/rows/AssistantText"
import { AsyncJobStrip } from "@/components/workbench/AsyncJobStrip"
import {
  parseWorkbenchHref,
  WorkbenchProvider,
  useWorkbench,
} from "@/components/workbench/WorkbenchContext"
import { WorkbenchPane } from "@/components/workbench/WorkbenchPane"
import type { ChatMention } from "@/lib/mentions"
import type { WorkbenchData } from "@/lib/workbench"

vi.mock("./VisualPresetGalleryPanel", () => ({ default: ({ kind }: { kind: string }) => <div>{kind}</div> }))
vi.mock("./SoundLabPanel", () => ({ default: () => <div>Sound Lab</div> }))

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => false,
}))

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(async (url: string) => {
    if (url.includes("/storyboard")) {
      return {
        ok: true,
        json: async () => ({
          composition_id: "comp-1",
          composition_version_id: "ver-2",
          version: 2,
          content_digest: "d".repeat(64),
          storyboard: {
            duration_seconds: 15,
            scenes: [
              { scene_id: "scn-1", label: "开场主张幕", duration_seconds: 5, description: "产品核心定位" },
              { scene_id: "scn-2", label: "数据对比幕", duration_seconds: 10, description: "三组关键指标" },
            ],
          },
        }),
      }
    }
    if (url.includes("/workbench")) {
      return {
        ok: true,
        json: async () => sampleWorkbench,
      }
    }
    return { ok: true, json: async () => ({}) }
  }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.version != null
        ? `${key}:v${opts.version}`
        : opts?.count != null
          ? `${key}:${opts.count}`
          : key,
    i18n: { language: "zh" },
  }),
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

afterEach(() => {
  cleanup()
})

const sampleWorkbench: WorkbenchData = {
  project: {
    id: "proj-1",
    title: "Rookie Cut Demo",
    language: "zh",
    status: "active",
    updated_at: "2026-11-24T12:00:00Z",
  },
  compositions: [
    {
      composition_id: "comp-1",
      name: "旗舰宣传片",
      current_version_id: "ver-2",
      versions: [
        {
          version_id: "ver-2",
          version: 2,
          duration_seconds: 15,
          style_preset: "vox_editorial",
          is_head: true,
          created_at: "2026-11-24T12:00:00Z",
        },
        {
          version_id: "ver-1",
          version: 1,
          duration_seconds: 12,
          style_preset: "institutional_dark",
          is_head: false,
          created_at: "2026-11-24T11:50:00Z",
        },
      ],
    },
  ],
  outputs: [],
  assets: [
    {
      id: "asset-img-1",
      type: "image",
      title: "首页截图.png",
      file_url: "https://example.com/hero.png",
      processing_status: "completed",
      meta: {},
      created_at: "2026-11-24T11:40:00Z",
    },
  ],
  active_jobs: [
    {
      job_id: "job-1",
      kind: "export",
      status: "running",
      label_key: "workbench.job.export",
      conversation_id: "conv-1",
      receipt_id: "msg-1",
      target_version_id: "ver-2",
      created_at: new Date(Date.now() - 18_000).toISOString(),
    },
  ],
  skills: [],
}

function WorkbenchStateProbe() {
  const { isOpen, activeTab, selectedVersionId, selectedAssetId } = useWorkbench()
  return (
    <div
      data-testid="wb-probe"
      data-open={String(isOpen)}
      data-tab={activeTab}
      data-version={selectedVersionId ?? ""}
      data-asset={selectedAssetId ?? ""}
    />
  )
}

describe("Studio WorkbenchPane & Markdown artifact links", () => {
  it("parses #workbench:* internal links and ignores external URLs", () => {
    expect(parseWorkbenchHref("#workbench:version/ver-2")).toEqual({
      tab: "player",
      versionId: "ver-2",
    })
    expect(parseWorkbenchHref("#workbench:output/out-9")).toEqual({
      tab: "player",
      outputId: "out-9",
    })
    expect(parseWorkbenchHref("#workbench:asset/asset-1")).toEqual({
      tab: "inspector",
      assetId: "asset-1",
    })
    expect(parseWorkbenchHref("#workbench:skill/skv-1")).toEqual({
      tab: "slots",
      skillVersionId: "skv-1",
    })
    expect(parseWorkbenchHref("https://example.com")).toBeNull()
  })

  it("opens right WorkbenchPane from Markdown artifact chips and preserves safe external links", async () => {
    render(
      <WorkbenchProvider projectId="proj-1" initialData={sampleWorkbench}>
        <WorkbenchStateProbe />
        <AssistantText
          text="已更新 [v2 宣传片草稿](#workbench:version/ver-2)，可对比 [首页截图](#workbench:asset/asset-img-1) 或访问 [官网](https://example.com)。"
          hydrated
        />
        <WorkbenchPane />
      </WorkbenchProvider>,
    )

    expect(screen.getByTestId("wb-probe").getAttribute("data-open")).toBe("false")

    // External link keeps target=_blank + rel=noopener noreferrer
    const extLink = screen.getByRole("link", { name: "官网" })
    expect(extLink.getAttribute("target")).toBe("_blank")
    expect(extLink.getAttribute("rel")).toContain("noopener")

    // Clicking Markdown #workbench:version/ver-2 chip slides open WorkbenchPane on Player tab
    const versionChip = screen.getByRole("button", { name: "v2 宣传片草稿" })
    fireEvent.click(versionChip)
    expect(screen.getByTestId("wb-probe").getAttribute("data-open")).toBe("true")
    expect(screen.getByTestId("wb-probe").getAttribute("data-tab")).toBe("player")
    expect(screen.getByTestId("wb-probe").getAttribute("data-version")).toBe("ver-2")

    await waitFor(() => {
      expect(screen.getByText("开场主张幕")).toBeTruthy()
    })

    // Clicking Markdown #workbench:asset/asset-img-1 switches to Inspector tab
    const assetChip = screen.getByRole("button", { name: "首页截图" })
    fireEvent.click(assetChip)
    expect(screen.getByTestId("wb-probe").getAttribute("data-tab")).toBe("inspector")
    expect(screen.getByTestId("wb-probe").getAttribute("data-asset")).toBe("asset-img-1")
  })

  it("switches across four tabs, cites an asset and opens each preset library", async () => {
    const onCite = vi.fn<(mention: ChatMention) => void>()
    render(
      <WorkbenchProvider
        projectId="proj-1"
        initialData={sampleWorkbench}
        defaultOpen
        onCiteMention={onCite}
      >
        <WorkbenchStateProbe />
        <WorkbenchPane />
      </WorkbenchProvider>,
    )

    // Switch to Inspector tab
    fireEvent.click(screen.getByRole("tab", { name: /workbench\.tabs\.inspector/ }))
    expect(screen.getByTestId("wb-probe").getAttribute("data-tab")).toBe("inspector")

    // Click Cite in chat
    fireEvent.click(screen.getByRole("button", { name: "workbench.inspector.citeInChat" }))
    expect(onCite).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "asset",
        id: "asset-img-1",
        label: "首页截图.png",
      }),
    )

    // Switch to Slots tab (renders EmptyState when no skills)
    fireEvent.click(screen.getByRole("tab", { name: /workbench\.tabs\.slots/ }))
    expect(screen.getByText("workbench.slots.emptyTitle")).toBeTruthy()

    expect(screen.getAllByRole("tab")).toHaveLength(4)
    fireEvent.click(screen.getByRole("tab", { name: "workbench.tabs.presets" }))
    expect(await screen.findByText("block")).toBeTruthy()
    fireEvent.click(screen.getByRole("radio", { name: "visualGallery.text" }))
    expect(screen.getByText("text_preset")).toBeTruthy()
    fireEvent.click(screen.getByRole("radio", { name: "visualGallery.sounds" }))
    expect(await screen.findByText("Sound Lab")).toBeTruthy()
    expect(screen.getByTestId("wb-probe").getAttribute("data-tab")).toBe("sounds")

    // Close pane
    fireEvent.click(screen.getByRole("button", { name: "workbench.close" }))
    expect(screen.getByTestId("wb-probe").getAttribute("data-open")).toBe("false")
  })

  it("renders AsyncJobStrip for active jobs and opens WorkbenchPane on click", () => {
    render(
      <WorkbenchProvider projectId="proj-1" initialData={sampleWorkbench}>
        <WorkbenchStateProbe />
        <AsyncJobStrip />
        <WorkbenchPane />
      </WorkbenchProvider>,
    )

    const jobButton = screen.getByRole("button", { name: /workbench\.job\.export/ })
    expect(jobButton).toBeTruthy()
    fireEvent.click(jobButton)
    expect(screen.getByTestId("wb-probe").getAttribute("data-open")).toBe("true")
    expect(screen.getByTestId("wb-probe").getAttribute("data-tab")).toBe("player")
  })
})
