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
  head: (ctx) => {
    // Meta follows the SSR language (root loader's cookie read) so crawlers
    // and share cards get the same language the user would see. Client-side
    // re-runs fall back to EN — crawlers only ever read the SSR payload.
    // ctx.matches is typed to this route alone; widen to reach the root match.
    const matches = ctx.matches as ReadonlyArray<{
      routeId: string
      loaderData?: { lang?: string | null }
    }>
    const rootLoaderData = matches.find((m) => m.routeId === "__root__")
      ?.loaderData
    const zh = rootLoaderData?.lang === "zh"
    const copy = zh ? LANDING_META.zh : LANDING_META.en
    return {
      meta: [
        { title: copy.title },
        { name: "description", content: copy.description },
        { property: "og:type", content: "website" },
        { property: "og:url", content: SITE_URL },
        { property: "og:title", content: copy.title },
        { property: "og:description", content: copy.ogDescription },
        { property: "og:image", content: `${SITE_URL}/og.png` },
        { property: "og:image:width", content: "1200" },
        { property: "og:image:height", content: "630" },
        { property: "og:locale", content: zh ? "zh_CN" : "en_US" },
        { name: "twitter:card", content: "summary_large_image" },
        { name: "twitter:title", content: copy.title },
        { name: "twitter:description", content: copy.ogDescription },
        { name: "twitter:image", content: `${SITE_URL}/og.png` },
      ],
      links: [
        { rel: "canonical", href: SITE_URL },
        // The locale rides a cookie, not the URL — alternates point at the
        // same page so crawlers know both languages live here.
        { rel: "alternate", hreflang: "en", href: SITE_URL },
        { rel: "alternate", hreflang: "zh", href: SITE_URL },
        { rel: "alternate", hreflang: "x-default", href: SITE_URL },
      ],
    }
  },
  component: LandingPage,
})

const SITE_URL = "https://repurposer.ai"

const LANDING_META = {
  en: {
    title: "Repurposer — You focus on your craft; we handle the rest",
    description:
      "Repurposer is an AI assistant that turns your existing material — talks, reports, podcasts, transcripts — into the content you name: LinkedIn posts, short clips, articles, newsletters, in the languages your audience speaks. GDPR-ready.",
    ogDescription:
      "An AI assistant that turns your existing material into the content you name — LinkedIn posts, clips, articles, newsletters, in the languages your audience speaks.",
  },
  zh: {
    title: "Repurposer——你讲完了，剩下的交给我们",
    description:
      "Repurposer 是一个 AI 助手，把你现有的素材——演讲、报告、播客、文字稿——变成你点名的内容：LinkedIn 帖子、短片、文章、newsletter，用你受众的语言。GDPR 就绪。",
    ogDescription:
      "一个 AI 助手，把你现有的素材变成你点名的内容——LinkedIn 帖子、短片、文章、newsletter，用你受众的语言。",
  },
}

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
