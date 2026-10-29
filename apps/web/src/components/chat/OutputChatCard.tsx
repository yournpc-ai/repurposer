/** OutputChatCard — one exact delivered Output in its actual message row. */

import { OutputDeliveryCard } from "./OutputDeliveryCard"
import type { Output } from "@/lib/types"

export function OutputChatCard({
  output,
  onOpen,
}: {
  output: Output
  onOpen: (outputId: string) => void
}) {
  return <OutputDeliveryCard output={output} onOpen={onOpen} />
}
