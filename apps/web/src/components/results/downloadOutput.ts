import { downloadFile, toAbsoluteUrl } from "@/lib/api"
import type { Output } from "@/lib/types"

/** Per-type download — the old card-face actions moved over verbatim
 * (ADR-041 D5 平移): clip → MP4, quotes → image, text types → markdown. */
export function downloadOutput(output: Output): void {
  if (output.type === "clip") {
    const url = output.files.video
    if (!url) return
    const title = output.publishing.title || output.payload.hook || "clip"
    downloadFile(url, `${title}.mp4`).catch((e) =>
      console.error("Download failed", e)
    )
    return
  }
  if (output.type === "quotes") {
    const url = toAbsoluteUrl(output.files.image)
    if (!url) return
    const a = document.createElement("a")
    a.href = url
    a.download = `quotes-${output.id}.png`
    document.body.appendChild(a)
    a.click()
    a.remove()
    return
  }
  // post / carousel / article — the text types export as one markdown file.
  let text = ""
  if (output.type === "carousel") {
    text = (output.payload.slides ?? [])
      .map((s) => [s.title, s.body].filter(Boolean).join("\n"))
      .join("\n\n---\n\n")
  } else if (output.type === "article") {
    text = [output.payload.title ?? "", output.payload.content ?? ""]
      .filter(Boolean)
      .join("\n\n")
  } else {
    const content = output.payload.content ?? ""
    const hashtags = output.payload.hashtags ?? []
    text = [content, hashtags.join(" ")].filter(Boolean).join("\n\n")
  }
  if (!text) return
  const blob = new Blob([text], { type: "text/plain" })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${output.type}-${output.id}.txt`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}
