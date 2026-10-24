/** 锚卡投影套件 (flora-parity-ui 验证仪式链): 锚卡数组渲染的纯函数半
 * 座 —— output_refs 收集（顺序 + 去重 + 读容忍）、数组平铺投影、名缺
 * 回退「类型词 · 规格」（零模板回填）、字数规格。 */

import { describe, expect, it } from "vitest"

import type { Output, WorkflowStep } from "@/lib/types"

import {
  anchorCardOf,
  anchorCardsForRun,
  anchorLabel,
  approxWordCount,
  isDeliveredOutput,
  runOutputRefs,
} from "./anchorCards"

function step(partial: Partial<WorkflowStep>): WorkflowStep {
  return {
    id: "s1",
    kind: "render",
    status: "done",
    seq: 1,
    error: null,
    cost: null,
    started_at: null,
    finished_at: null,
    ...partial,
  }
}

function output(partial: Partial<Output>): Output {
  return {
    id: "o1",
    project_id: "p1",
    workflow_step_id: null,
    type: "clip",
    language: null,
    status: "done",
    provenance: "generated",
    payload: {},
    files: {},
    source_ref: null,
    render_spec: null,
    render_status: null,
    render_error: null,
    score: null,
    quality: null,
    publishing: {},
    created_at: "2026-10-13T00:00:00Z",
    updated_at: null,
    ...partial,
  }
}

describe("runOutputRefs — 收据载荷的 output_refs 收集", () => {
  it("按步骤顺序收集,跨步骤去重", () => {
    const steps = [
      step({ id: "a", output_refs: ["o1", "o2"] }),
      step({ id: "b", output_refs: ["o2", "o3"] }),
      step({ id: "c" }), // 无 refs 的步骤不贡献
      step({ id: "d", output_refs: [] }),
    ]
    expect(runOutputRefs(steps)).toEqual(["o1", "o2", "o3"])
  })

  it("零 refs → 零锚卡(空数组,收据行独存)", () => {
    expect(runOutputRefs([step({ id: "a" })])).toEqual([])
  })
})

describe("anchorCardsForRun — N 产物 = 数组平铺投影", () => {
  const steps = [
    step({ id: "a", output_refs: ["o1", "o2", "gone"] }),
    step({ id: "b", output_refs: ["o3"] }),
  ]
  const outputs = [
    output({ id: "o1", type: "clip", render_status: "completed", files: { video: "/v1.mp4" } }),
    output({ id: "o2", type: "quotes", files: { image: "/q1.png" } }),
    output({ id: "o3", type: "article", payload: { content: "正文" } }),
  ]

  it("refs 顺序即数组顺序;解析不到的 ref 静默掉落(拉取在途 ≠ 骨架)", () => {
    const cards = anchorCardsForRun(steps, outputs)
    expect(cards.map((c) => c.outputId)).toEqual(["o1", "o2", "o3"])
  })

  it("媒体族映射: video > image > text(读容忍降级)", () => {
    const cards = anchorCardsForRun(steps, outputs)
    expect(cards.map((c) => c.kind)).toEqual(["video", "image", "text"])
  })

  it("未交付的 film/clip 不进入产物卡;文本产物不受影响", () => {
    const deliverySteps = [
      step({ id: "delivery", output_refs: ["failed", "pending", "empty", "ready", "post"] }),
    ]
    const rows = [
      output({ id: "failed", type: "film", render_status: "failed" }),
      output({ id: "pending", type: "clip", render_status: "rendering" }),
      output({ id: "empty", type: "film", render_status: "completed", files: {} }),
      output({ id: "ready", type: "film", render_status: "completed", files: { video: "/film.mp4" } }),
      output({ id: "post", type: "post", payload: { content: "正文" } }),
    ]
    expect(anchorCardsForRun(deliverySteps, rows).map((c) => c.outputId)).toEqual([
      "ready",
      "post",
    ])
  })
})

describe("isDeliveredOutput — 产物卡准入", () => {
  it("render 完成且文件存在才交付 film/clip", () => {
    expect(
      isDeliveredOutput(
        output({ type: "film", render_status: "completed", files: { video: "/v.mp4" } }),
      ),
    ).toBe(true)
    for (const render_status of [null, "pending", "rendering", "failed"]) {
      expect(isDeliveredOutput(output({ type: "clip", render_status }))).toBe(false)
    }
    expect(
      isDeliveredOutput(output({ type: "clip", render_status: "completed", files: {} })),
    ).toBe(false)
  })
})

describe("anchorCardOf — 单卡事实(世界自证)", () => {
  it("名来源梯: publishing.title > payload.title > payload.hook", () => {
    expect(
      anchorCardOf(output({ publishing: { title: " 发布短片 v1 " } })).name,
    ).toBe("发布短片 v1")
    expect(
      anchorCardOf(output({ payload: { title: "T", hook: "H" } })).name,
    ).toBe("T")
    expect(anchorCardOf(output({ payload: { hook: "H" } })).name).toBe("H")
  })

  it("名缺 = null(零模板回填 —— 回退是渲染层的事)", () => {
    expect(anchorCardOf(output({ publishing: { title: "  " } })).name).toBeNull()
    expect(anchorCardOf(output({})).name).toBeNull()
  })

  it("clip 时长只认 payload.duration 数字;非 clip 不带时长", () => {
    expect(
      anchorCardOf(output({ type: "clip", payload: { duration: 26 } }))
        .durationSec,
    ).toBe(26)
    expect(
      anchorCardOf(output({ type: "post", payload: { duration: 26 } }))
        .durationSec,
    ).toBeNull()
  })

  it("text 族正文 = outputFullText 的一份拷贝;媒体族不带正文", () => {
    const text = anchorCardOf(
      output({ type: "article", payload: { title: "题", content: "文" } }),
    )
    expect(text.kind).toBe("text")
    expect(text.text).toBe("题\n\n文")
    const video = anchorCardOf(output({ files: { video: "/v.mp4" } }))
    expect(video.text).toBeNull()
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
