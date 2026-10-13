/** AnchorCards — 锚卡 (flora-parity-ui ③ · ADR-118 单一渲染面律修订注):
 * 终态收据帧 —— 静态、零订阅，挂在终态收据行之下、归收据所有（收据行
 * = 唯一父座）。N 产物 = 数组平铺（flex-wrap 小卡，禁合集卡组件）；
 * 无内联播放钮，点击 = 开 MediaLightbox（指针语义 —— 唯一展开目标，
 * lightbox 的声音互斥全局已接）。渲染 ⟺ !canvas_visible —— 环境分支由
 * ChatDock 的挂载点把守（lib/canvasVisibility 单源），组件自身不读环
 * 境。名缺 → 「类型词 · 规格」回退（anchorLabel，零模板回填）。 */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Clock,
  FileText,
  Languages,
  RectangleHorizontal,
  RectangleVertical,
  Square,
} from "lucide-react"

import { toAbsoluteUrl } from "@/lib/api"
import { formatDuration } from "@/lib/utils"
import {
  MediaLightbox,
  type MediaChip,
  type MediaLightboxData,
} from "@/components/results/MediaLightbox"

import {
  anchorLabel,
  approxWordCount,
  type AnchorCardData,
} from "@/lib/anchorCards"

export function AnchorCards({ cards }: { cards: AnchorCardData[] }) {
  const { t, i18n } = useTranslation()
  const [lightbox, setLightbox] = useState<MediaLightboxData | null>(null)
  if (cards.length === 0) return null

  const openCard = (
    card: AnchorCardData,
    title: string,
    typeWord: string,
  ) => {
    // Chips = the card's own facts (the ResultsCanvas vocabulary: type /
    // language / aspect / duration — never a model name).
    const chips: MediaChip[] = []
    if (card.language) {
      chips.push({
        Icon: Languages,
        label: t(`languages.${card.language}`, { defaultValue: card.language }),
      })
    }
    if (card.aspect === "1:1" || card.aspect === "16:9" || card.aspect === "9:16") {
      chips.push({
        Icon:
          card.aspect === "1:1"
            ? Square
            : card.aspect === "16:9"
              ? RectangleHorizontal
              : RectangleVertical,
        label: card.aspect,
      })
    }
    if (card.durationSec != null) {
      chips.push({ Icon: Clock, label: formatDuration(card.durationSec) })
    }
    setLightbox({
      kind: card.kind,
      url: toAbsoluteUrl(card.videoUrl ?? card.imageUrl) ?? undefined,
      poster: card.poster ? toAbsoluteUrl(card.poster) : null,
      title,
      createdAt: card.createdAt,
      text: card.text ?? undefined,
      chips,
      downloadName: card.videoUrl ? `${title || typeWord}.mp4` : undefined,
    })
  }

  return (
    <>
      <div className="flex flex-wrap gap-2 pt-2">
        {cards.map((card) => {
          const typeWord = t(`chat.anchorCards.types.${card.type}`, {
            defaultValue: card.type,
          })
          // 规格 = 世界自证的真实数字: 视频时长 / 图像画幅 / 文本约字数。
          const meta =
            card.kind === "video" && card.durationSec != null
              ? formatDuration(card.durationSec)
              : card.kind === "image" && card.aspect
                ? card.aspect
                : card.kind === "text" && card.text
                  ? (() => {
                      const n = approxWordCount(card.text, i18n.language)
                      return n != null
                        ? t("chat.anchorCards.words", { count: n })
                        : null
                    })()
                  : null
          const label = anchorLabel(card, typeWord, meta)
          // 名缺时 label 已带规格,副行让位(零重复);有名时副行 = 规格 · 类型词。
          const sub = card.name
            ? [meta, typeWord].filter(Boolean).join(" · ") || null
            : null
          const thumbUrl = toAbsoluteUrl(card.imageUrl)
          return (
            <button
              key={card.outputId}
              type="button"
              aria-label={t("chat.anchorCards.view", { name: label })}
              onClick={() => openCard(card, label, typeWord)}
              className="flex max-w-full items-center gap-2 rounded-lg bg-muted px-2 py-1.5 text-left ring-1 ring-foreground/10 transition-colors hover:bg-accent"
            >
              <span className="relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-md bg-background">
                {card.kind === "video" && card.videoUrl ? (
                  <>
                    <video
                      src={toAbsoluteUrl(card.videoUrl) ?? undefined}
                      poster={thumbUrl ?? undefined}
                      muted
                      playsInline
                      preload="metadata"
                      className="h-full w-full object-cover"
                    />
                    {card.durationSec != null ? (
                      <span className="absolute right-0.5 bottom-0.5 rounded-sm bg-black/70 px-1 font-mono text-[9px] leading-3 text-white">
                        {formatDuration(card.durationSec)}
                      </span>
                    ) : null}
                  </>
                ) : card.kind === "image" && thumbUrl ? (
                  <img src={thumbUrl} alt="" className="h-full w-full object-cover" />
                ) : (
                  <FileText className="h-4 w-4 text-muted-foreground" />
                )}
              </span>
              <span className="min-w-0">
                <span className="block max-w-44 truncate text-xs font-medium text-foreground">
                  {label}
                </span>
                {sub ? (
                  <span className="block text-[11px] text-meta-foreground">
                    {sub}
                  </span>
                ) : null}
              </span>
            </button>
          )
        })}
      </div>
      <MediaLightbox
        data={lightbox}
        onOpenChange={(open) => {
          if (!open) setLightbox(null)
        }}
      />
    </>
  )
}
