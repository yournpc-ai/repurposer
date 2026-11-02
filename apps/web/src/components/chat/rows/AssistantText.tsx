/** Assistant prose — markdown, no bubble (Opus pattern). Streamdown parses
 * incomplete markdown safely mid-stream, so the live preview and the settled
 * message share one renderer. */

import { Streamdown } from "streamdown"

import { Message, MessageContent } from "@/components/ui/message"
import { cn } from "@/lib/utils"
import { shouldAnimateEntrance } from "../timeline/reveal"

export function AssistantText({
  text,
  streaming,
  hydrated,
}: {
  text: string
  streaming?: boolean
  hydrated?: boolean
}) {
  return (
    <Message align="start">
      <MessageContent>
        <Streamdown
          mode={streaming ? "streaming" : "static"}
          isAnimating={streaming}
          className={cn(
            "text-sm leading-relaxed",
            shouldAnimateEntrance(hydrated) &&
              "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300",
          )}
        >
          {text}
        </Streamdown>
      </MessageContent>
    </Message>
  )
}
