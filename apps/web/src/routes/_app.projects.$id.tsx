import { Outlet, createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_app/projects/$id")({
  component: ProjectDetailLayout,
})

function ProjectDetailLayout() {
  return <Outlet />
}
