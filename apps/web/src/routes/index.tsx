import { createFileRoute } from "@tanstack/react-router"

import { AppShowcase } from "@/components/landing/AppShowcase"
import { Faq } from "@/components/landing/Faq"
import { FinalCta } from "@/components/landing/FinalCta"
import { Footer } from "@/components/landing/Footer"
import { Gallery } from "@/components/landing/Gallery"
import { Channels } from "@/components/landing/Channels"
import { LandingHeader } from "@/components/landing/LandingHeader"
import { LandingHero } from "@/components/landing/LandingHero"
import { Manifesto } from "@/components/landing/Manifesto"
import { ReducedMotionProvider } from "@/components/landing/motion"
import { Pricing } from "@/components/landing/Pricing"
import { SkipToContent } from "@/components/landing/SkipToContent"
import { SmoothScroll } from "@/components/landing/SmoothScroll"
import { Testimonials } from "@/components/landing/Testimonials"
import { VideoShowcase } from "@/components/landing/VideoShowcase"

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      {
        title:
          "Repurposer — Turn one talk into posts, clips and newsletters",
      },
      {
        name: "description",
        content:
          "Repurposer is an AI agent that turns talks, podcasts and interviews into LinkedIn posts, short clips, articles and newsletters — in the languages your audience speaks. You review, it publishes. Hosted in the EU.",
      },
      { property: "og:type", content: "website" },
      {
        property: "og:title",
        content: "Repurposer — Turn one talk into posts, clips and newsletters",
      },
      {
        property: "og:description",
        content:
          "An AI agent that turns talks into LinkedIn posts, clips, articles and newsletters — in the languages your audience speaks. You review, it publishes.",
      },
      { name: "twitter:card", content: "summary_large_image" },
      {
        name: "twitter:title",
        content: "Repurposer — Turn one talk into posts, clips and newsletters",
      },
      {
        name: "twitter:description",
        content:
          "An AI agent that turns talks into LinkedIn posts, clips, articles and newsletters — in the languages your audience speaks.",
      },
    ],
  }),
  component: LandingPage,
})

function LandingPage() {
  return (
    <ReducedMotionProvider>
      <SmoothScroll>
        <div id="top" className="flex min-h-svh flex-1 flex-col">
          <SkipToContent />
          <LandingHeader />
          <main id="main-content" className="flex-1 overflow-x-clip">
            <LandingHero />
            <VideoShowcase />
            <Manifesto />
            <AppShowcase />
            <Gallery />
            <Channels />
            <Testimonials />
            <Pricing />
            <Faq />
            <FinalCta />
          </main>
          <Footer />
        </div>
      </SmoothScroll>
    </ReducedMotionProvider>
  )
}
