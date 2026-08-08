import { Outlet, createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_app/personas")({
  component: PersonasLayout,
})

function PersonasLayout() {
  return <Outlet />
}
