import type { ComponentProps } from "react"

import { Message, MessageContent } from "@/components/ui/message"
import type { Output } from "@/lib/types"

import { AnchorCards } from "../AnchorCards"
import { RunTaskList } from "../RunTaskList"

interface RunBlockProps extends ComponentProps<typeof RunTaskList> {
  /** Only the gated zero-delivery fallback uses this Run-level display seat. */
  outputs?: Output[]
  onOpen?: (outputId: string) => void
}

/** The single Run work surface for attached and detached adapters. Message-
 * owned deliveries render their own cards; this optional surface exists only
 * when the current Run has no delivery message and review has settled. */
export function RunBlock({ outputs, onOpen, ...props }: RunBlockProps) {
  const fallback = outputs && onOpen ? <AnchorCards outputs={outputs} onOpen={onOpen} /> : null
  if (props.cancelled) return fallback
  return (
    <Message align="start">
      <MessageContent>
        <RunTaskList {...props} />
        {fallback}
      </MessageContent>
    </Message>
  )
}
