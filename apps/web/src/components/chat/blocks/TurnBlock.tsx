import type { ReactNode } from "react"

/** Compact vertical rhythm shared by one turn's prose, work segments and
 * structured slots. Top-level turn spacing stays on the conversation
 * scrollport; this component adds no card, colour or second message truth. */
export function TurnBlock({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-3">{children}</div>
}
