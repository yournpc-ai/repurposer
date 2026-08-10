import { createFileRoute, redirect } from "@tanstack/react-router"

// Brand template module retired (ADR-038): the skin now lives on the persona
// (`persona.brand` block, edited on the persona page). Keep the old URL as a
// permanent redirect so existing links / history land on the persona list.
export const Route = createFileRoute("/_app/brand-template")({
  beforeLoad: () => {
    throw redirect({ to: "/personas", replace: true })
  },
})
