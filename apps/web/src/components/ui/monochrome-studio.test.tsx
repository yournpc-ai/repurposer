// @vitest-environment jsdom
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { cleanup, render, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ThinkingState } from "./thinking-state-clean"
import { ProjectConversationsTree } from "@/components/project/ProjectConversationsTree"

const { listConversationsMock } = vi.hoisted(() => ({
  listConversationsMock: vi.fn(),
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock("@/lib/workbench", async () => {
  const actual = await vi.importActual<typeof import("@/lib/workbench")>("@/lib/workbench")
  return {
    ...actual,
    listProjectConversations: listConversationsMock,
  }
})

afterEach(() => {
  cleanup()
  listConversationsMock.mockReset()
})

const FORBIDDEN_BLUE_GREEN_PATTERNS = [
  /#16a34a/i,
  /#4fb0fe/i,
  /#0190fe/i,
  /#0060e2/i,
  /#72a7ff/i,
  /#77d9a3/i,
  /#5fc88a/i,
  /#7dcf9f/i,
  /rgba\(\s*0,\s*96,\s*226/i,
  /rgba\(\s*79,\s*176,\s*254/i,
  /rgba\(\s*22,\s*163,\s*74/i,
  /\bbg-sky-\d+/,
  /\btext-emerald-\d+/,
]

describe("Studio monochrome UI contract", () => {
  it("keeps ThinkingState styles free of blue and green colors", () => {
    const { container } = render(
      <ThinkingState
        live={false}
        defaultOpen
        headerLabel="Worked for 15s"
        steps={[
          { id: "s1", kind: "step", label: "Audited timeline clips", status: "done" },
          { id: "s2", kind: "step", label: "Rendering preview", status: "running" },
        ]}
        stepsPlan={[
          { title: "Inspect raw footage", status: "done" },
          { title: "Build 5-act storyboard", status: "done" },
          { title: "Balance voice and SFX", status: "in_progress" },
          { title: "Export master cut", status: "pending" },
        ]}
        stepsProgressLabel="2/4 steps"
      />,
    )

    const styleEl = container.querySelector("style") ?? document.head.querySelector('style[data-href="ui-thinking-state-clean"]')
    const cssText = styleEl?.textContent ?? readFileSync(resolve(__dirname, "thinking-state-clean.tsx"), "utf8")
    for (const pattern of FORBIDDEN_BLUE_GREEN_PATTERNS) {
      expect(cssText).not.toMatch(pattern)
    }

    // Verify completed checkmark & active pulse elements render cleanly
    expect(container.querySelector(".ui-thinkc__plan-check")).toBeTruthy()
    expect(container.querySelector(".ui-thinkc__plan-pulse")).toBeTruthy()
    expect(container.querySelector(".ui-thinkc__steps-badge")).toBeTruthy()
  })

  it("renders ProjectConversationsTree active-job dot in monochrome without sky/blue utilities", async () => {
    listConversationsMock.mockResolvedValueOnce([
      {
        id: "conv-1",
        project_id: "proj-1",
        title: "Launch Cut",
        message_count: 8,
        has_active_job: true,
        compacted: false,
        compacted_at: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ])

    const { container } = render(
      <ProjectConversationsTree projectId="proj-1" activeConversationId="conv-1" />,
    )

    await waitFor(() => {
      expect(container.querySelector('[title="conversations.activeJob"]')).toBeTruthy()
    })

    const dot = container.querySelector('[title="conversations.activeJob"]')
    expect(dot?.className).toContain("bg-foreground/85")
    expect(dot?.className).not.toMatch(/\bbg-(sky|blue|emerald|green|teal|cyan)-/)
  })

  it("defines strictly monochrome global AffectUI tokens in styles.css", () => {
    const stylesSource = readFileSync(resolve(__dirname, "../../styles.css"), "utf8")
    for (const token of [
      "--aui-focus: #202020;",
      "--aui-blue: #202020;",
      "--aui-info: #202020;",
      "--aui-green: #202020;",
      "--aui-success: #202020;",
      "--aui-focus: #ededed;",
      "--aui-blue: #ededed;",
      "--aui-info: #e4e4e7;",
      "--aui-green: #d4d4d8;",
      "--aui-success: #d4d4d8;",
    ]) {
      expect(stylesSource).toContain(token)
    }
    expect(stylesSource).not.toContain("#0060e2")
    expect(stylesSource).not.toContain("#72a7ff")
    expect(stylesSource).not.toContain("#16794d")
    expect(stylesSource).not.toContain("#77d9a3")

    const avatarSource = readFileSync(resolve(__dirname, "avatar-clean.tsx"), "utf8")
    expect(avatarSource).toContain("--ui-avtc-bg-s: 0%;")
    expect(avatarSource).toContain("--ui-avtc-fg-s: 0%;")

    const voiceOrbSource = readFileSync(resolve(__dirname, "voice-orb.tsx"), "utf8")
    for (const pattern of [...FORBIDDEN_BLUE_GREEN_PATTERNS, /#2f6bff/i, /#6f9bff/i]) {
      expect(voiceOrbSource).not.toMatch(pattern)
    }
  })
})
