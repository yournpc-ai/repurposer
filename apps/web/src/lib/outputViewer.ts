import type { ChatOutputEntry, Output } from "@/lib/types"

/** Preserve server order and id identity; only a not-yet-projected opened item
 * is appended temporarily, never inserted by timestamp or card position. */
export function outputViewerItems(
  entries: ChatOutputEntry[] | null,
  selectedId: string,
  selectedOutput: Output | null,
): ChatOutputEntry[] {
  const seen = new Set<string>()
  const items = (entries ?? []).filter((entry) => {
    if (seen.has(entry.output_id)) return false
    seen.add(entry.output_id)
    return true
  })
  if (!seen.has(selectedId) && selectedOutput) {
    items.push({ output_id: selectedId, output: selectedOutput })
  }
  return items
}
