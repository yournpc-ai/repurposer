import { createFileRoute } from "@tanstack/react-router"

import { AppShowcase } from "@/components/landing/AppShowcase"
import { Faq } from "@/components/landing/Faq"
import { FinalCta } from "@/components/landing/FinalCta"
import { Footer } from "@/components/landing/Footer"
// import { Gallery } from "@/components/landing/Gallery" — hidden, see main
import { Channels } from "@/components/landing/Channels"
import { LandingHeader } from "@/components/landing/LandingHeader"
import { LandingHero } from "@/components/landing/LandingHero"
import { Manifesto } from "@/components/landing/Manifesto"
import { ReducedMotionProvider } from "@/components/landing/motion"
import { Pricing } from "@/components/landing/Pricing"
import { SkipToContent } from "@/components/landing/SkipToContent"
import { SmoothScroll } from "@/components/landing/SmoothScroll"
// import { Testimonials } from "@/components/landing/Testimonials" — hidden, see main
import { VideoShowcase } from "@/components/landing/VideoShowcase"

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      {
        title:
          "Repurposer — You focus on your craft; we handle the rest",
      },
      {
        name: "description",
        content:
          "Repurposer is an AI assistant that turns your existing material — talks, reports, podcasts, transcripts — into the content you name: LinkedIn posts, short clips, articles, newsletters, in the languages your audience speaks. GDPR-ready.",
      },
      { property: "og:type", content: "website" },
      {
        property: "og:title",
        content: "Repurposer — You focus on your craft; we handle the rest",
      },
      {
        property: "og:description",
        content:
          "An AI assistant that turns your existing material into the content you name — LinkedIn posts, clips, articles, newsletters, in the languages your audience speaks.",
      },
      { name: "twitter:card", content: "summary_large_image" },
      {
        name: "twitter:title",
        content: "Repurposer — You focus on your craft; we handle the rest",
      },
      {
        name: "twitter:description",
        content:
          "An AI assistant that turns your existing material into the content you name — LinkedIn posts, clips, articles, newsletters, in the languages your audience speaks.",
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
            {/* Gallery ("Made from one source") and Testimonials ("In
                their own words") stay hidden pending narrative rework —
                their #gallery / #reviews anchors are removed from the
                header dropdown and footer; restore by uncommenting. */}
            {/* <Gallery /> */}
            <Channels />
            {/* <Testimonials /> */}
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
