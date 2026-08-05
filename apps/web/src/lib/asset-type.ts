/** Shared upload-file → asset-type inference (composer and overlay chat both
 * upload source materials). Falls back to "transcript" for documents/text. */
export function inferAssetType(file: File): string {
  if (file.type.startsWith("video/")) return "video"
  if (file.type.startsWith("audio/")) return "audio"
  if (file.type.startsWith("image/")) return "image"
  return "transcript"
}
