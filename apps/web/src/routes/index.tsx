import { createFileRoute } from "@tanstack/react-router"

import { LandingFooter } from "@/components/landing/LandingFooter"
import { LandingHeader } from "@/components/landing/LandingHeader"
import { LandingHero } from "@/components/landing/LandingHero"
import { LandingPricing } from "@/components/landing/LandingPricing"
import { LandingRoadmap } from "@/components/landing/LandingRoadmap"
import { LandingTrustBand } from "@/components/landing/LandingTrustBand"
import { LandingWorkflow } from "@/components/landing/LandingWorkflow"

export const Route = createFileRoute("/")({
  component: LandingPage,
})

function LandingPage() {
  return (
    <div className="flex min-h-svh flex-1 flex-col">
      <LandingHeader />
      <main className="flex-1">
        <LandingHero />
        <LandingWorkflow />
        <LandingTrustBand />
        <LandingPricing />
        <LandingRoadmap />
      </main>
      <LandingFooter />
    </div>
  )
}
