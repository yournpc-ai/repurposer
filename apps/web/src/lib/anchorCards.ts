import type { Output } from "@/lib/types"

export interface AnchorCardData {
  outputId: string
  kind: "video"
  type: string
  name: string | null
  videoUrl: string | null
  imageUrl: string | null
  poster: string | null
  durationSec: number | null
  aspect: string | null
  createdAt: string | null
  language: string | null
}

export function isDeliveredOutput(output: Output): boolean {
  if (output.type !== "video") return false
  return output.render_status === "completed" && Boolean(output.files.video)
}

export function isChatVideoOutput(output: Output): boolean {
  return isDeliveredOutput(output)
}

export function anchorCardOf(output: Output): AnchorCardData {
  const name =
    output.publishing.title?.trim() ||
    (output.payload.name as string | undefined)?.trim() ||
    null
  return {
    outputId: output.id,
    kind: "video",
    type: output.type,
    name,
    videoUrl: output.files.video ?? null,
    imageUrl: output.files.image ?? null,
    poster: output.publishing.cover_image_url ?? null,
    durationSec: output.type === "video"
      ? output.payload.duration_seconds ?? output.payload.duration ?? null
      : null,
    aspect: output.aspect ?? null,
    createdAt: output.created_at ?? null,
    language: output.language ?? null,
  }
}

export function deliveredOutputsForRefs(
  refs: readonly string[],
  outputs: Output[],
): Output[] {
  const byId = new Map(outputs.map((output) => [output.id, output]))
  return [...new Set(refs)]
    .map((id) => byId.get(id))
    .filter((output): output is Output => output != null)
    .filter(isChatVideoOutput)
}

export function anchorLabel(
  card: Pick<AnchorCardData, "name">,
  typeWord: string,
  meta: string | null,
): string {
  if (card.name) return card.name
  return meta ? `${typeWord} · ${meta}` : typeWord
}

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
