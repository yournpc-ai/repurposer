/** 锚卡投影 (flora-parity-ui ③ · ADR-118 §2 chat 自足律首个构造物):
 * 终态收据行下的静态产物数组 —— 只读消息载荷既有 output_refs
 * (types.ts WorkflowStep) × dock 既有 outputs 读数（零新 SSE 订阅、零
 * 新拉取）。纯函数 = vitest 缝；渲染在 AnchorCards.tsx。 */

import type { Output, WorkflowStep } from "@/lib/types"
import { outputFullText } from "@/components/results/outputText"

/** One anchor card's facts — everything the render needs, nothing live. */
export interface AnchorCardData {
  outputId: string
  /** 媒体族（指针语义 → MediaLightbox kind）: video > image > text。 */
  kind: "video" | "image" | "text"
  /** The product's output type (i18n 类型词的键 —— icon/类型词 ≠ 工具名)。 */
  type: string
  /** 世界自证名 —— null = 名缺（渲染层回退「类型词 · 规格」，零模板回
   * 填，展示文案二源律 ADR-058）。 */
  name: string | null
  videoUrl: string | null
  imageUrl: string | null
  poster: string | null
  /** clip 时长（秒）—— 视频族的规格。 */
  durationSec: number | null
  /** 服务端推导的展示画幅（"9:16" 等）—— 图像族的规格。 */
  aspect: string | null
  /** text 族的正文（lightbox 体 + 字数规格的原料）。 */
  text: string | null
  createdAt: string | null
  language: string | null
}

/** The run's produced output ids — the receipt's own payload (steps carry
 * output_refs when they land a product; order = step order, deduped). */
export function runOutputRefs(steps: WorkflowStep[]): string[] {
  return [...new Set(steps.flatMap((s) => s.output_refs ?? []))]
}

/** Whether this row may appear as a delivered product card.
 *
 * A render-contracted row is not a playable product until BOTH the render
 * completed and its video file exists. Failed / pending / half-written rows
 * stay in the run's task and failure surfaces, never in delivery cards.
 * Non-render products deliver through their ordinary payload.
 */
export function isDeliveredOutput(output: Output): boolean {
  if (output.type !== "clip" && output.type !== "film") return true
  return output.render_status === "completed" && Boolean(output.files.video)
}

/** One output row → its anchor card facts (读容忍: a row without media
 * files degrades to the text seat; a name-less row keeps null — the
 * fallback is the render's job, never a template backfill here). */
export function anchorCardOf(output: Output): AnchorCardData {
  // film carries its display name in payload.name (no hook/title fields).
  const name =
    output.publishing.title?.trim() ||
    (output.payload.title as string | undefined)?.trim() ||
    (output.payload.hook as string | undefined)?.trim() ||
    (output.payload.name as string | undefined)?.trim() ||
    null
  const videoUrl = output.files.video ?? null
  const imageUrl = output.files.image ?? null
  const kind: AnchorCardData["kind"] = videoUrl
    ? "video"
    : imageUrl
      ? "image"
      : "text"
  return {
    outputId: output.id,
    kind,
    type: output.type,
    name,
    videoUrl,
    imageUrl,
    poster: output.publishing.cover_image_url ?? null,
    durationSec:
      (output.type === "clip" || output.type === "film") &&
      typeof output.payload.duration === "number"
        ? output.payload.duration
        : null,
    aspect: output.aspect ?? null,
    text: kind === "text" ? outputFullText(output) || null : null,
    createdAt: output.created_at ?? null,
    language: output.language ?? null,
  }
}

/** The receipt's anchor array (N 产物 = 数组平铺): refs resolve against
 * the dock's outputs read; unresolved refs (the fetch still in flight)
 * simply drop out — the frame is static, never a skeleton. */
export function anchorCardsForRun(
  steps: WorkflowStep[],
  outputs: Output[],
): AnchorCardData[] {
  const byId = new Map(outputs.map((o) => [o.id, o]))
  return runOutputRefs(steps)
    .map((id) => byId.get(id))
    .filter((o): o is Output => o != null)
    .filter(isDeliveredOutput)
    .map(anchorCardOf)
}

/** 名缺回退 (零模板回填): 类型词 + 规格（时长 / 画幅 / 字数 —— 世界自
 * 证的真实数字）；两者皆缺 = 类型词独存。 */
export function anchorLabel(
  card: Pick<AnchorCardData, "name">,
  typeWord: string,
  meta: string | null,
): string {
  if (card.name) return card.name
  return meta ? `${typeWord} · ${meta}` : typeWord
}

/** 字数规格 (text 族的名缺回退): zh 计非空白字符、en 计空白分词，两位
 * 有效数字取约数（「约 900 字」/ "~900 words" —— 约数不假装精确）。 */
export function approxWordCount(text: string, locale: string): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const n = locale.toLowerCase().startsWith("zh")
    ? trimmed.replace(/\s/g, "").length
    : trimmed.split(/\s+/).length
  if (n <= 0) return null
  if (n < 10) return n
  if (n < 100) return Math.round(n / 10) * 10
  const magnitude = 10 ** Math.floor(Math.log10(n) - 1)
  return Math.round(n / magnitude) * magnitude
}
