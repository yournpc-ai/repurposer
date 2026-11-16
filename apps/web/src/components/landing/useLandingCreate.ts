import { useNavigate } from "@tanstack/react-router"
import { useAuth } from "@/lib/auth-context"
import { stageLandingCreate } from "@/lib/landingCreate"
import type { LandingGalleryItem } from "./content"

export function useLandingCreate() {
  const { isAuthenticated, setLoginOpen } = useAuth()
  const navigate = useNavigate()
  return (item?: LandingGalleryItem) => {
    if (item) stageLandingCreate({ skill: item.skill, promptKey: `landing.gallery.items.${item.id}.prompt` })
    if (isAuthenticated) void navigate({ to: "/home" })
    else setLoginOpen(true)
  }
}
