/** 消息 copy 套件 (flora-parity-ui 验证仪式链): 纯客户端剪贴板 —— 成
 * 功逐字落地、失败静默（reject 不外抛,无 toast 半座可测）。 */

import { describe, expect, it } from "vitest"

import { copyMessageText } from "./messageCopy"

describe("copyMessageText — 纯客户端剪贴板(静默档)", () => {
  it("成功: 文本逐字交给剪贴板,回报 true", async () => {
    let written: string | null = null
    const ok = await copyMessageText("短片好了，就在下面。", async (s) => {
      written = s
    })
    expect(ok).toBe(true)
    expect(written).toBe("短片好了，就在下面。")
  })

  it("失败(剪贴板被拒): 静默回报 false,永不外抛", async () => {
    const ok = await copyMessageText("x", async () => {
      throw new Error("denied")
    })
    expect(ok).toBe(false)
  })
})
