import type { Output } from "@/lib/types"

/** The text product's full body as ONE copyable string (title + body +
 * hashtags) — the composition every surface agrees on (the canvas card's
 * text region, the factsbar's Copy action), so what lands on the clipboard
 * is always exactly what the card shows. */
export function outputFullText(output: Output): string {
  const title =
    output.publishing.title ?? (output.payload.title as string | undefined) ?? null
  const body = (output.payload.content as string | undefined) ?? ""
  const hashtags =
    (output.publishing.hashtags as string[] | undefined) ??
    (output.payload.hashtags as string[] | undefined) ??
    []
  return [
    title,
    body,
    hashtags.length > 0 ? hashtags.map((h) => `#${h}`).join(" ") : null,
  ]
    .filter(Boolean)
    .join("\n\n")
}
