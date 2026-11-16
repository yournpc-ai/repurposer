import { downloadFile } from "@/lib/api"
import type { Output } from "@/lib/types"

export function downloadOutput(output: Output): void {
  if (output.type !== "video") return
  const url = output.files.video
  if (!url) return
  const title = output.publishing.title || output.payload.name || output.type
  downloadFile(url, `${title}.mp4`).catch((error) => {
    console.error("Download failed", error)
  })
}
