/** 锚卡投影套件 (flora-parity-ui 验证仪式链): 锚卡数组渲染的纯函数半
 * 座 —— output_refs 收集（顺序 + 去重 + 读容忍）、数组平铺投影、名缺
 * 回退「类型词 · 规格」（零模板回填）、字数规格。 */

import { describe, expect, it } from "vitest"

import type { Output } from "@/lib/types"

import {
  anchorCardOf,
  anchorLabel,
  approxWordCount,
  deliveredOutputsForRefs,
  isDeliveredOutput,
} from "./anchorCards"

function output(partial: Partial<Output>): Output {
  return {
    id: "o1",
    project_id: "p1",
    type: "video",
    language: null,
    status: "done",
    provenance: "generated",
    payload: {},
    files: {},
    source_ref: null,
    render_spec: null,
    render_status: null,
    quality: null,
    publishing: {},
    created_at: "2026-10-13T00:00:00Z",
    updated_at: null,
    ...partial,
  }
}

describe("delivery-message Output refs", () => {
  it("resolves only the message's own deliverable products in ref order", () => {
    const rows = [
      output({ id: "a", type: "video", render_status: "completed", files: { video: "/a.mp4" } }),
      output({ id: "b", type: "video", render_status: "completed", files: { video: "/b.mp4" } }),
      output({ id: "pending", type: "video", render_status: "rendering" }),
      output({ id: "post", type: "audio", payload: {} }),
      output({ id: "quote", type: "audio", files: { image: "/q.png" } }),
    ]
    expect(deliveredOutputsForRefs(["b", "pending", "post", "quote", "a", "b"], rows).map((row) => row.id)).toEqual(["b", "a"])
    expect(deliveredOutputsForRefs([], rows)).toEqual([])
  })
})

describe("isDeliveredOutput — 产物卡准入", () => {
  it("render 完成且文件存在才交付 video", () => {
    expect(
      isDeliveredOutput(
        output({ type: "video", render_status: "completed", files: { video: "/v.mp4" } }),
      ),
    ).toBe(true)
    for (const render_status of [null, "pending", "rendering", "failed"]) {
      expect(isDeliveredOutput(output({ type: "video", render_status }))).toBe(false)
    }
    expect(
      isDeliveredOutput(output({ type: "video", render_status: "completed", files: {} })),
    ).toBe(false)
  })
})

describe("anchorCardOf — 单卡事实(世界自证)", () => {
  it("名来源梯: publishing.title > payload.name", () => {
    expect(
      anchorCardOf(output({ publishing: { title: " 发布短片 v1 " } })).name,
    ).toBe("发布短片 v1")
    expect(
      anchorCardOf(output({ payload: { name: "T" } })).name,
    ).toBe("T")
    expect(anchorCardOf(output({ payload: { name: "H" } })).name).toBe("H")
  })

  it("名缺 = null(零模板回填 —— 回退是渲染层的事)", () => {
    expect(anchorCardOf(output({ publishing: { title: "  " } })).name).toBeNull()
    expect(anchorCardOf(output({})).name).toBeNull()
  })

  it("时长只认保存版 payload 数字;非视频不带时长", () => {
    expect(
      anchorCardOf(output({ type: "video", payload: { duration: 26 } }))
        .durationSec,
    ).toBe(26)
    expect(
      anchorCardOf(output({ type: "audio", payload: { duration: 26 } }))
        .durationSec,
    ).toBeNull()
  })

  it("交付卡只呈现视频媒体", () => {
    const video = anchorCardOf(output({ files: { video: "/v.mp4" } }))
    expect(video.kind).toBe("video")
    expect(video.videoUrl).toBe("/v.mp4")
    expect(isDeliveredOutput(output({ type: "audio", payload: {} }))).toBe(false)
  })
})

describe("anchorLabel — 名缺回退「类型词 · 规格」", () => {
  it("有名 → 名字原样(世界自证,永不改写)", () => {
    expect(anchorLabel({ name: "发布短片 v1" }, "短片", "0:26")).toBe("发布短片 v1")
  })

  it("名缺 → 类型词 + 规格", () => {
    expect(anchorLabel({ name: null }, "短片", "0:26")).toBe("短片 · 0:26")
  })

  it("名缺且规格缺 → 类型词独存", () => {
    expect(anchorLabel({ name: null }, "长文", null)).toBe("长文")
  })
})

describe("approxWordCount — text 族的字数规格", () => {
  it("en 计空白分词,两位有效数字取约", () => {
    expect(approxWordCount(Array(937).fill("w").join(" "), "en")).toBe(940)
    expect(approxWordCount("one two three four five", "en")).toBe(5)
    expect(approxWordCount(Array(47).fill("w").join(" "), "en-US")).toBe(50)
  })

  it("zh 计非空白字符", () => {
    expect(approxWordCount("字".repeat(923), "zh")).toBe(920)
    expect(approxWordCount("短 句 一 则", "zh-CN")).toBe(4)
  })

  it("空文 → null(规格缺位,类型词独存)", () => {
    expect(approxWordCount("   ", "en")).toBeNull()
  })
})
