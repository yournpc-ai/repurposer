// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { createRef } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import en from "@/lib/i18n/locales/en"
import zh from "@/lib/i18n/locales/zh"
import { TurnMinimap } from "./TurnMinimap"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.index != null ? `${key}:${opts.index}` : key,
  }),
}))

afterEach(() => {
  cleanup()
})

function collectLeafKeys(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = []
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...collectLeafKeys(v as Record<string, unknown>, path))
    } else {
      keys.push(path)
    }
  }
  return keys.sort()
}

describe("TurnMinimap", () => {
  it("stays hidden when <= 1 user turn exists or when hidden prop is set", () => {
    const viewportRef = createRef<HTMLDivElement>()
    const { rerender } = render(
      <TurnMinimap
        viewportRef={viewportRef}
        turns={[{ id: "t1", index: 1, preview: "只有一条消息" }]}
      />,
    )
    expect(screen.queryByRole("navigation")).toBeNull()

    rerender(
      <TurnMinimap
        viewportRef={viewportRef}
        hidden
        turns={[
          { id: "t1", index: 1, preview: "第一条" },
          { id: "t2", index: 2, preview: "第二条" },
        ]}
      />,
    )
    expect(screen.queryByRole("navigation")).toBeNull()
  })

  it("renders dots for > 1 turn and scrolls the target turn block into view on click", () => {
    const scrollIntoView = vi.fn()
    const viewport = document.createElement("div")
    const target1 = document.createElement("div")
    target1.setAttribute("data-turn-minimap-id", "t1")
    target1.scrollIntoView = scrollIntoView
    const target2 = document.createElement("div")
    target2.setAttribute("data-turn-minimap-id", "t2")
    const target3 = document.createElement("div")
    target3.setAttribute("data-turn-minimap-id", "t3")
    viewport.append(target1, target2, target3)
    document.body.appendChild(viewport)

    const viewportRef = { current: viewport }
    render(
      <TurnMinimap
        viewportRef={viewportRef}
        turns={[
          { id: "t1", index: 1, preview: "帮我做一个 60 秒产品宣传片", versionLabel: "v1" },
          { id: "t2", index: 2, preview: "把第二幕换成数据图表", versionLabel: "v2" },
          { id: "t3", index: 3, preview: "导出 1080p 成片" },
        ]}
      />,
    )

    const buttons = screen.getAllByRole("button")
    expect(buttons).toHaveLength(3)
    fireEvent.click(buttons[0])
    expect(scrollIntoView).toHaveBeenCalledTimes(1)
    viewport.remove()
  })
})

describe("i18n EN/ZH key parity", () => {
  it("maintains 100% key parity across en.ts and zh.ts", () => {
    const enKeys = collectLeafKeys(en as unknown as Record<string, unknown>)
    const zhKeys = collectLeafKeys(zh as unknown as Record<string, unknown>)
    expect(zhKeys).toEqual(enKeys)
  })
})
