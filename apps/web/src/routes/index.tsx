import { createFileRoute } from "@tanstack/react-router"

import { CreationShowcase } from "@/components/landing/CreationShowcase"
import { CreationStory } from "@/components/landing/CreationStory"
import { LandingFaq } from "@/components/landing/LandingFaq"
import { EarlyAccess } from "@/components/landing/EarlyAccess"
import { Footer } from "@/components/landing/Footer"
import { LandingHeader } from "@/components/landing/LandingHeader"
import { LandingHero } from "@/components/landing/LandingHero"
import { ReducedMotionProvider } from "@/components/landing/motion"
import { SkipToContent } from "@/components/landing/SkipToContent"

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
        { property: "og:site_name", content: "Rookie Cut" },
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
        { rel: "alternate", hrefLang: "en", href: SITE_URL },
        { rel: "alternate", hrefLang: "zh", href: SITE_URL },
        { rel: "alternate", hrefLang: "x-default", href: SITE_URL },
      ],
    }
  },
  component: LandingPage,
})

const SITE_URL = "https://repurposer.ai"

const LANDING_META = {
  en: {
    title: "Rookie Cut — Your AI video agent",
    description: "Create videos with motion graphics, rich animation, and precise editing—all through conversation.",
    ogDescription: "Your AI video agent. Create videos with motion graphics, rich animation, and precise editing—all through conversation.",
  },
  zh: {
    title: "Rookie Cut — 你的 AI 视频 Agent",
    description: "通过对话，轻松制作融合动态图形、丰富动画与精细剪辑的视频。",
    ogDescription: "你的 AI 视频 Agent。通过对话，轻松制作融合动态图形、丰富动画与精细剪辑的视频。",
  },
}

function LandingPage() {
  return (
    <ReducedMotionProvider>
      <div
        id="top"
        className="landing-surface min-h-svh bg-background"
      >
        <SkipToContent />
        <LandingHeader />
        <main id="main-content">
          <LandingHero />
          <CreationShowcase />
          <CreationStory />
          <LandingFaq />
          <EarlyAccess />
        </main>
        <Footer />
      </div>
    </ReducedMotionProvider>
  )
}
