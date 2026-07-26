/** OutputChatCard — results-page cards inlined into the chat flow.
 *
 * Renders the exact card components as-is (chat button inside an inline card
 * simply opens another modal — acceptable per 2026-07-26 review: the five
 * cards stay untouched). Never duplicate card markup here.
 */

import { ArticleCard } from "@/components/results/ArticleCard"
import { CarouselCard } from "@/components/results/CarouselCard"
import { ClipCard } from "@/components/results/ClipCard"
import { PostCard } from "@/components/results/PostCard"
import { QuotesCard } from "@/components/results/QuotesCard"

import type { Output } from "@/lib/types"

export function OutputChatCard({ output }: { output: Output }) {
  switch (output.type) {
    case "clip":
      return <ClipCard output={output} />
    case "post":
      return <PostCard output={output} />
    case "quotes":
      return <QuotesCard output={output} />
    case "carousel":
      return <CarouselCard output={output} />
    case "article":
      return <ArticleCard output={output} />
    default:
      return null
  }
}
