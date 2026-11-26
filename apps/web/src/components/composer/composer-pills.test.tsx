// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { toast } from "sonner"
import { Plus } from "@/components/ui/icons"
import { createRef } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ComposerIconButton } from "./ComposerIconButton"
import { ComposerPanelButton } from "./ComposerPanelButton"
import { ComposerSendButton } from "./ComposerSendButton"
import { HomeComposer } from "@/components/home/HomeComposer"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/chat/MessageScroller"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { returnObjects?: boolean }) =>
      opts?.returnObjects ? ["Make a product launch trailer"] : key,
  }),
}))

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn(), message: vi.fn() },
}))

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: false, loginOpen: false }),
}))

const launch = vi.hoisted(() => vi.fn())
vi.mock("@/lib/useProjectLaunch", () => ({
  useProjectLaunch: () => ({ launching: false, launch }),
}))

vi.mock("@/lib/stagingUploads", () => ({
  useStagingUploads: () => ({
    staged: [],
    addFiles: vi.fn(),
    removeStaged: vi.fn(),
    retryStaged: vi.fn(),
    clearStaged: vi.fn(),
  }),
}))

vi.mock("@/components/settings/settings-dialog-context", () => ({
  useSettingsDialog: () => ({ modalOpen: false }),
}))

afterEach(() => {
  cleanup()
})

describe("Full-radius composer and scroll-to-bottom controls", () => {
  it("renders ComposerSendButton, ComposerIconButton, and ComposerPanelButton as rounded-full pills", () => {
    render(
      <div>
        <ComposerIconButton icon={Plus} label="Attach" />
        <ComposerSendButton label="Send" />
        <ComposerSendButton label="Stop" stop />
        <ComposerPanelButton
          icon={Plus}
          label="Assets"
          open={false}
          onOpenChange={() => {}}
        >
          <div>Panel</div>
        </ComposerPanelButton>
      </div>,
    )

    for (const name of ["Attach", "Send", "Stop", "Assets"]) {
      const btn = screen.getByRole("button", { name })
      expect(btn.className).toContain("rounded-full")
      expect(btn.style.getPropertyValue("--radius")).toBe("9999px")
    }
    const stopBtn = screen.getByRole("button", { name: "Stop" })
    expect(stopBtn.getAttribute("data-variant")).toBe("secondary")
    expect(stopBtn.style.getPropertyValue("--ui-icbc-icon")).toBe("#ef4444")
  })

  it("renders HomeComposer shell with pill corners and circular + / ↑ buttons", () => {
    const originalMatchMedia = window.matchMedia
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    try {
      const editorRef = createRef<MentionEditorHandle | null>()
      const { container } = render(
        <HomeComposer
          prompt=""
          onPromptChange={() => {}}
          mentions={[]}
          onMentionsChange={() => {}}
          selectedSkill={null}
          onSkillChange={() => {}}
          editorRef={editorRef}
        />,
      )

      const shell = container.querySelector('[data-slot="home-composer"]') as HTMLElement | null
      expect(shell).toBeTruthy()
      expect(shell?.className).toContain("rounded-[22px]")
      expect(shell?.style.getPropertyValue("--ui-crdc-radius")).toBe("22px")

      const assetsBtn = screen.getByRole("button", { name: "composer.assets" })
      const sendBtn = screen.getByRole("button", { name: "chat.send" })
      expect(assetsBtn.className).toContain("rounded-full")
      expect(sendBtn.className).toContain("rounded-full")
    } finally {
      window.matchMedia = originalMatchMedia
    }
  })

  it("focuses the missing required field on send, then launches with only the completed text", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
    try {
      const editorRef = createRef<MentionEditorHandle>()
      render(<HomeComposer prompt="Draft" onPromptChange={() => {}} mentions={[]} onMentionsChange={() => {}}
        selectedSkill={null} onSkillChange={() => {}} editorRef={editorRef} />)
      act(() => { editorRef.current!.insertBrief("Animate: [Copy]\\nPacing: [optional:Any changes]") })
      const send = screen.getByRole("button", { name: "chat.send" })
      fireEvent.click(screen.getByText("[Any changes]"))
      fireEvent.click(send)
      expect(launch).not.toHaveBeenCalled()
      expect(toast.message).toHaveBeenCalledWith("recipes.shelf.requiredSlot")
      expect(window.getSelection()?.toString()).toBe("[Copy]")
      const range = window.getSelection()!.getRangeAt(0)
      range.deleteContents()
      range.insertNode(document.createTextNode("Moonrise"))
      fireEvent.input(screen.getByRole("textbox"))
      fireEvent.click(send)
      expect(launch).toHaveBeenCalledWith(expect.objectContaining({ prompt: "Animate: Moonrise\\nPacing: " }))
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("renders MessageScrollerButton as a circular monochrome floating pill when scrolled up", () => {
    const originalRO = globalThis.ResizeObserver
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver

    try {
      const { container } = render(
        <MessageScrollerProvider>
          <MessageScroller>
            <MessageScrollerViewport>
              <MessageScrollerContent>
                <div>Tall content</div>
              </MessageScrollerContent>
            </MessageScrollerViewport>
            <MessageScrollerButton />
          </MessageScroller>
        </MessageScrollerProvider>,
      )

      const viewport = container.querySelector('[data-slot="message-scroller-viewport"]') as HTMLElement
      Object.defineProperty(viewport, "scrollHeight", { value: 1200, configurable: true })
      Object.defineProperty(viewport, "clientHeight", { value: 400, configurable: true })
      Object.defineProperty(viewport, "scrollTop", { value: 100, writable: true, configurable: true })
      fireEvent.scroll(viewport)

      const jumpBtn = container.querySelector('[data-slot="message-scroller-button"]') as HTMLElement | null
      expect(jumpBtn).toBeTruthy()
      expect(jumpBtn?.className).toContain("rounded-full")
      expect(jumpBtn?.className).toContain("size-8")
      expect(jumpBtn?.style.getPropertyValue("--radius")).toBe("9999px")
    } finally {
      globalThis.ResizeObserver = originalRO
    }
  })
})
