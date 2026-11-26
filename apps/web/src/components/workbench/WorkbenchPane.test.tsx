// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

beforeAll(() => {
  Element.prototype.scrollIntoView ??= () => {}
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

vi.mock("./VisualPresetGalleryPanel", () => ({
  default: ({ kind }: { kind: string }) => <div>{kind}</div>,
}))
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
          scenes: [
            {
              scene_id: "scn-1",
              number: 1,
              range_seconds: { start: 0, end: 5 },
              intent: "开场主张幕",
              visual_description: "产品核心定位与品牌视觉推近",
              narration: "专利和无形资产的价值，缺的是站得住的证据。",
            },
            {
              scene_id: "scn-2",
              number: 2,
              range_seconds: { start: 5, end: 15 },
              intent: "数据对比幕",
              visual_description: "三组关键指标跃升呈现",
              narration: null,
            },
          ],
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
        : opts?.title != null && opts?.number != null
          ? `${key}:${opts.number}:${opts.title}`
          : opts?.name != null
            ? `${key}:${opts.name}`
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
  const {
    isOpen,
    activeTab,
    activeArtifactKey,
    openArtifacts,
    selectedVersionId,
    selectedAssetId,
  } = useWorkbench()
  return (
    <div
      data-testid="wb-probe"
      data-open={String(isOpen)}
      data-tab={activeTab}
      data-artifact={activeArtifactKey ?? ""}
      data-artifact-count={String(openArtifacts.length)}
      data-version={selectedVersionId ?? ""}
      data-asset={selectedAssetId ?? ""}
    />
  )
}

describe("Studio WorkbenchPane focused artifact viewer & Markdown links", () => {
  it("parses #workbench:* internal links and ignores external URLs", () => {
    expect(parseWorkbenchHref("#workbench:version/ver-2")).toEqual({
      tab: "player",
      versionId: "ver-2",
    })
    expect(parseWorkbenchHref("#workbench:output/out-9")).toEqual({
      tab: "player",
      outputId: "out-9",
    })
    expect(parseWorkbenchHref("#workbench:storyboard/ver-2")).toEqual({
      tab: "storyboard",
      versionId: "ver-2",
    })
    expect(parseWorkbenchHref("#workbench:asset/asset-1")).toEqual({
      tab: "inspector",
      assetId: "asset-1",
    })
    expect(parseWorkbenchHref("#workbench:skill/skv-1")).toEqual({
      tab: "slots",
      skillVersionId: "skv-1",
    })
    expect(parseWorkbenchHref("#workbench:presets")).toEqual({
      tab: "presets",
      presetTab: "block",
    })
    expect(parseWorkbenchHref("#workbench:sounds")).toEqual({
      tab: "sounds",
    })
    expect(parseWorkbenchHref("https://example.com")).toBeNull()
  })

  it("opens focused artifact tabs from Markdown chips without permanent multi-tab clutter", async () => {
    render(
      <WorkbenchProvider projectId="proj-1" initialData={sampleWorkbench}>
        <WorkbenchStateProbe />
        <AssistantText
          text="已更新 [旗舰宣传片 v2](#workbench:version/ver-2)，可对比 [首页截图](#workbench:asset/asset-img-1)、阅读 [分镜脚本.md](#workbench:storyboard/ver-2) 或访问 [官网](https://example.com)。"
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

    // Clicking Markdown #workbench:version/ver-2 opens ONLY that 1 focused tab
    fireEvent.click(screen.getByRole("button", { name: "旗舰宣传片 v2" }))
    expect(screen.getByTestId("wb-probe").getAttribute("data-open")).toBe("true")
    expect(screen.getByTestId("wb-probe").getAttribute("data-artifact")).toBe("version:ver-2")
    expect(screen.getByRole("tab", { name: "旗舰宣传片 v2" })).toBeTruthy()
    expect(screen.getAllByRole("tab")).toHaveLength(1)

    // Backend storyboard fields (intent + visual_description + range_seconds) render cleanly
    await waitFor(() => {
      expect(screen.getByText("开场主张幕")).toBeTruthy()
      expect(screen.getByText("产品核心定位与品牌视觉推近")).toBeTruthy()
    })

    // Clicking Markdown #workbench:asset/asset-img-1 adds a second focused tab
    fireEvent.click(screen.getByRole("button", { name: "首页截图" }))
    expect(screen.getByTestId("wb-probe").getAttribute("data-artifact")).toBe("asset:asset-img-1")
    expect(screen.getAllByRole("tab")).toHaveLength(2)

    // Clicking Markdown #workbench:storyboard/ver-2 opens the readable Markdown Script viewer
    fireEvent.click(screen.getByRole("button", { name: "分镜脚本.md" }))
    expect(screen.getByTestId("wb-probe").getAttribute("data-artifact")).toBe("storyboard:ver-2")
    expect(screen.getAllByRole("tab")).toHaveLength(3)
    await waitFor(() => {
      expect(screen.getByText(/专利和无形资产的价值/)).toBeTruthy()
    })
  })

  it("defaults to full rendered MP4 when available and switches outputs via chat link", async () => {
    const outputs = ["newer", "older"].map((id) => ({
      id,
      type: "video",
      status: "completed",
      files: { video: `/${id}.mp4` },
      composition_id: "comp-1",
      composition_version_id: id === "newer" ? "ver-2" : "ver-1",
      created_at: null,
    }))
    render(
      <WorkbenchProvider
        projectId="proj-1"
        initialData={{ ...sampleWorkbench, outputs }}
        defaultOpen
      >
        <AssistantText text="对比旧版 [v1 成片](#workbench:output/older)。" hydrated />
        <WorkbenchPane />
      </WorkbenchProvider>,
    )

    // Defaults directly to the full rendered MP4 rather than a truncated 12s draft scrub
    expect(
      screen.getByRole("link", { name: "workbench.player.download" }).getAttribute("href"),
    ).toBe("/newer.mp4")

    // Clicking the older output link opens it cleanly in a second artifact tab
    fireEvent.click(screen.getByRole("button", { name: "v1 成片" }))
    expect(
      screen.getByRole("link", { name: "workbench.player.download" }).getAttribute("href"),
    ).toBe("/older.mp4")
  })

  it("cites an asset, opens presets/Sound Lab only on demand via chat link, and has no dead + or close buttons", async () => {
    const onCite = vi.fn<(mention: ChatMention) => void>()
    render(
      <WorkbenchProvider
        projectId="proj-1"
        initialData={sampleWorkbench}
        defaultOpen
        onCiteMention={onCite}
      >
        <WorkbenchStateProbe />
        <AssistantText
          text="查看 [首页截图](#workbench:asset/asset-img-1)，或在 [挑选动效与音效](#workbench:presets) 中预览。"
          hydrated
        />
        <WorkbenchPane />
      </WorkbenchProvider>,
    )

    // No dead + button or redundant close icon in the header
    expect(screen.queryByRole("button", { name: "workbench.openItemMenu" })).toBeNull()
    expect(screen.queryByRole("button", { name: "workbench.close" })).toBeNull()

    // Open asset via chat Markdown link
    fireEvent.click(screen.getByRole("button", { name: "首页截图" }))
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

    // Open Presets temporarily on demand via chat Markdown link
    fireEvent.click(screen.getByRole("button", { name: "挑选动效与音效" }))
    expect(await screen.findByText("block")).toBeTruthy()
    fireEvent.click(screen.getByRole("radio", { name: "visualGallery.text" }))
    expect(screen.getByText("text_preset")).toBeTruthy()
    fireEvent.click(screen.getByRole("radio", { name: "visualGallery.sounds" }))
    expect(await screen.findByText("Sound Lab")).toBeTruthy()
    expect(screen.getByTestId("wb-probe").getAttribute("data-tab")).toBe("sounds")

    // Closing an open artifact tab removes it cleanly
    const tabCountBefore = screen.getAllByRole("tab").length
    fireEvent.click(screen.getAllByRole("button", { name: /workbench\.closeTab/ })[0])
    expect(screen.getAllByRole("tab")).toHaveLength(tabCountBefore - 1)
  })

  it("deduplicates same-composition version tabs and allows closing the last remaining tab", async () => {
    render(
      <WorkbenchProvider projectId="proj-1" initialData={sampleWorkbench}>
        <WorkbenchStateProbe />
        <AssistantText
          text="查看 [旗舰宣传片](#workbench:version/ver-2) 或回看 [旗舰宣传片](#workbench:version/ver-1)。"
          hydrated
        />
        <WorkbenchPane />
      </WorkbenchProvider>,
    )

    const buttons = screen.getAllByRole("button", { name: "旗舰宣传片" })
    fireEvent.click(buttons[0])
    expect(screen.getByTestId("wb-probe").getAttribute("data-open")).toBe("true")
    expect(screen.getByTestId("wb-probe").getAttribute("data-artifact")).toBe("version:ver-2")
    expect(screen.getAllByRole("tab")).toHaveLength(1)

    // Opening another version of the SAME composition replaces the existing tab in place (no duplicate tab)
    fireEvent.click(buttons[1])
    expect(screen.getByTestId("wb-probe").getAttribute("data-artifact")).toBe("version:ver-1")
    expect(screen.getAllByRole("tab")).toHaveLength(1)

    // The single remaining tab still has a close button, and clicking it returns the Workbench to its empty state (keeping sidebar open)
    const closeBtn = screen.getByRole("button", { name: /workbench\.closeTab/ })
    fireEvent.click(closeBtn)
    expect(screen.getByTestId("wb-probe").getAttribute("data-open")).toBe("true")
    expect(screen.getByTestId("wb-probe").getAttribute("data-artifact-count")).toBe("0")
    expect(screen.getByText("workbench.projectFilesHeading")).toBeTruthy()
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
    expect(screen.getByTestId("wb-probe").getAttribute("data-artifact")).toBe("version:ver-2")
  })
})
