import type { ComponentProps, ReactNode } from "react"

import { Message, MessageContent } from "@/components/ui/message"
import { MessageScrollerItem } from "@/components/ui/message-scroller"
import type { Output } from "@/lib/types"

import { AnchorCards } from "../AnchorCards"
import { RunTaskList } from "../RunTaskList"
import { AssistantResponse } from "./AssistantResponse"

interface RunBlockProps extends ComponentProps<typeof RunTaskList> {
  /** Only the gated zero-delivery fallback uses this Run-level display seat. */
  opening?: ReactNode
  children?: ReactNode
  pendingSnapshot?: boolean
  outputs?: Output[]
  onOpen?: (outputId: string) => void
}

/** The single Run work surface for attached and detached adapters. Message-
 * owned deliveries render their own cards; this optional surface exists only
 * when the current Run has no delivery message and review has settled. */
export function RunBlock({ outputs, onOpen, opening, children, pendingSnapshot = false, ...props }: RunBlockProps) {
  const fallback = outputs && onOpen ? <AnchorCards outputs={outputs} onOpen={onOpen} /> : null
  return (
    <AssistantResponse data-slot="run-response">
      {opening}
      {!props.cancelled && !pendingSnapshot ? (
        <MessageScrollerItem>
          <Message align="start">
            <MessageContent>
              <RunTaskList {...props} />
              {fallback}
            </MessageContent>
          </Message>
        </MessageScrollerItem>
      ) : fallback}
      {children}
    </AssistantResponse>
  )
}
