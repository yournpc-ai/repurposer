import { Outlet, createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_app/speakers")({
  component: SpeakersLayout,
})

function SpeakersLayout() {
  return <Outlet />
}
