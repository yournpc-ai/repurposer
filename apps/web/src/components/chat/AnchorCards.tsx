/** AnchorCards — exact delivered Outputs under their terminal receipt row.
 * Each cover opens the Chat-hosted shared viewer by output_id; there is no
 * row-local lightbox, DOM gallery, inline player or aggregate card. */

import { OutputDeliveryCard } from "./OutputDeliveryCard"
import type { Output } from "@/lib/types"

export function AnchorCards({
  outputs,
  onOpen,
}: {
  outputs: Output[]
  onOpen: (outputId: string) => void
}) {
  if (outputs.length === 0) return null
  return (
    <div className="flex flex-wrap items-start gap-4 pt-3">
      {outputs.map((output) => (
        <OutputDeliveryCard key={output.id} output={output} onOpen={onOpen} />
      ))}
    </div>
  )
}
