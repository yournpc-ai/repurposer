import type { ComponentProps } from "react"
import { cn } from "@/lib/utils"

/** A complete assistant response owns its internal rhythm. The conversation
 * only spaces whole containers; prose/work/components never negotiate gaps
 * with their neighbours outside this boundary. */
export function AssistantResponse({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="assistant-response" className={cn("flex min-w-0 flex-col empty:hidden gap-3", className)} {...props} />
}
