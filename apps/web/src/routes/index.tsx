import { createFileRoute } from "@tanstack/react-router"

import { LandingHeader } from "@/components/landing/LandingHeader"
import { LandingHero } from "@/components/landing/LandingHero"

export const Route = createFileRoute("/")({
  component: LandingPage,
})

function LandingPage() {
  return (
    <div className="flex min-h-svh flex-1 flex-col">
      <LandingHeader />
      <main className="flex flex-1 flex-col">
        <LandingHero />
      </main>
    </div>
  )
}
