import { Children, type ReactNode } from "react"
import { AssistantResponse } from "./AssistantResponse"

/** The user boundary and assistant interior have separate layout owners. */
export function TurnBlock({ user, children }: { user?: ReactNode; children?: ReactNode }) {
  return (
    <div data-slot="turn-block" className="flex min-w-0 flex-col empty:hidden gap-6">
      {user}
      {Children.toArray(children).length > 0 ? <AssistantResponse>{children}</AssistantResponse> : null}
    </div>
  )
}
