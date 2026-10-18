/** QuestionDock — the pending question's home, docked above the input.
 *
 * The message list is the record of *decided* things; the dock holds the
 * one *pending* decision (the ask_user machinery — at most one at a time). The kind
 * selects the form (NAMING N-19: the use lives in `question.kind`, the
 * mechanism is the dock — no per-kind dock components):
 * - task_book: RETIRED (ADR-111, 2026-10-08 — the confirm dock card
 *   family is gone: the plan's review face is the canvas's draft nodes,
 *   the total estimate rides the dock echo's code-composed tail), and the
 *   confirm gesture is the user's own words — start_run via sendChat,
 *   口头确认律 ADR-092).
 * - question (形态律 ADR-053 R1, 阻塞形态 2026-09-04 用户拍板翻回): * - question (形态律 ADR-053 R1, 阻塞形态 2026-09-04 用户拍板翻回):
 *   while an OPTIONS question is pending the chat input row and the
 *   disclaimer HIDE — the dock IS the question (FLORA/Opus 双参照同款：两家
 *   的选项问都接管输入): the question line (the right-side × is the bail
 *   channel — the blocking state's exit), its options as full-width ROWS
 *   (letter badges mirror the deterministic autoResume mapping — typing "a"
 *   picks option a; long labels wrap, never overflow), and the tail pencil
 *   row for a freeform answer rendered as ONE MORE ITEM ROW (the pencil in
 *   the same badge tile — FLORA / Opus "Something else…" 同款解剖; Enter
 *   settles through the answer endpoint — a number/letter/label hit
 *   converts pre-post to the option pick, anything else records
 *   kind="freeform"). No default-path line anywhere (ADR-103: 散文零宣告
 *   ——跳过语义由 × 承担，可见面画蛇添足用户拍板取消). 作答反馈座 = 点中
 *   的行本身（accent 填充 + 行尾 inline spinner，Opus 选中行解剖；作答失败
 *   自动复位），卡底不再另置孤 spinner（同日拍板）. The morph governs
 *   OPTIONS questions only: a text question (options-empty) is plain flow
 *   speech with the input live.
 * Answering collapses the question into an answered-question block in the
 * flow.
 */

import { useState } from "react"
import { Loader2, Pencil, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

/** One option on a structured question (mirrors the API's Option). */
export interface DockOption {
  id: string
  label: string
  /** 一问拍一体化 (2026-09-27): the option's one-line reason, rendered
   * muted under the label. Absent on legacy rows / code-built options. */
  description?: string
}

interface OptionDockProps {
  kind: "question"
  /** The question's human text (LLM-written user data, shown as-is). */
  question: string
  options: DockOption[]
  /** 推荐标记 (2026-09-27 一问拍一体化): at most one option id the agent
   * recommends — its row carries the muted 推荐 suffix. */
  recommendedId?: string | null
  onAnswer: (optionId: string) => void
  answering: boolean
  /** Bail affordance — the question line's × (ADR-051): for an interrupt
   * question it stops the parked run; for a plain chat ask it skips the
   * question. A graceful exit, never an error path. */
  onBail?: () => void
  /** The ×'s aria-label — the caller knows the context (stop vs skip). */
  bailLabel?: string
  /** 尾行铅笔手输入 (ADR-053 R1 阻塞形态): Enter settles a freeform answer
   * through the ANSWER endpoint (kind="freeform") — the same settlement
   * machine as an option click; a typed letter/number/label hit converts
   * pre-post to the option pick (client mirror of the server's autoResume
   * mapping), zero LLM. */
  onFreeform?: (text: string) => void
  freeformDisabled?: boolean
  /** Bare child of the floating question pill (2026-09-02 拆粘): no fill /
   * rounding / margin of its own — the pill owns the chrome. */
  plain?: boolean
}

function OptionForm({
  question,
  options,
  recommendedId,
  onAnswer,
  answering,
  onBail,
  bailLabel,
  onFreeform,
  freeformDisabled,
  plain,
}: OptionDockProps) {
  const { t } = useTranslation()
  const [freeform, setFreeform] = useState("")
  /** The clicked option's id — the picked row itself is the loading seat
   * (2026-09-04 用户拍板: feedback lives where the action happened — the
   * Opus selected-row anatomy — not a lone spinner at the card's bottom).
   * The highlight + inline spinner are gated on `answering`, so a failed
   * answer POST clears both honestly (nothing was picked server-side). */
  const [pickedId, setPickedId] = useState<string | null>(null)
  const submitFreeform = () => {
    const text = freeform.trim()
    if (!text || !onFreeform || freeformDisabled || answering) return
    onFreeform(text)
    setFreeform("")
  }
  return (
    <div className={plain ? "px-4 py-2.5" : "mb-2 rounded-lg bg-muted px-4 py-2.5"}>
      {/* Question line — no ✓ (ADR-051); the × on the right IS the bail
          channel. */}
      <div className="flex items-start gap-2 text-sm">
        <span className="min-w-0 flex-1 break-words">{question}</span>
        {onBail ? (
          <Button
            variant="ghost"
            size="icon"
            className="-mr-1 -mt-1 h-6 w-6 shrink-0"
            aria-label={bailLabel ?? t("questionDock.bail")}
            disabled={answering}
            onClick={onBail}
          >
            <X className="size-3.5" />
          </Button>
        ) : null}
      </div>
      {options.length > 0 ? (
        // Full-width rows, not pills: long option labels must wrap inside
        // the card (the old button row let them bleed past the right edge).
        // 行距 (2026-09-28 用户走查): gap 收紧到 4px——行自养 py-2 已给足
        // 触控面与 hover 底, 行间只留一道视觉分组缝.
        <div className="mt-2 flex flex-col gap-1">
          {options.map((option, index) => (
            <Button
              key={option.id}
              variant="ghost"
              disabled={answering}
              onClick={() => {
                setPickedId(option.id)
                onAnswer(option.id)
              }}
              className={cn(
                "h-auto w-full items-start justify-start gap-2.5 whitespace-normal rounded-md px-3 py-2 text-left hover:bg-accent",
                answering && pickedId === option.id
                  ? "bg-accent disabled:opacity-100"
                  : "bg-card"
              )}
            >
              {/* The badge is the POSITIONAL NUMBER (1/2/3…), never the raw
                  option id — the id is a transport fact the LLM may spell as
                  a slug ("tech_innovation"), which used to overflow this 20px
                  tile and bleed across the card (2026-09-10). The number is
                  also the typed-answer channel: _match_option resolves it
                  positionally server-side. ADR-081 (2026-09-17): the badge
                  went a/b/c → 1/2/3 — one option grammar for every source
                  (plan / ask_user / trigger). self-start (2026-09-28 对齐走
                  查): the badge pins itself to the title's 20px line box —
                  per-item alignment that holds regardless of which align
                  class the row container carries. */}
              <span className="flex h-5 w-5 shrink-0 items-center justify-center self-start rounded bg-muted text-[11px] font-medium text-muted-foreground">
                {index + 1}
              </span>
              <span className="min-w-0 break-words leading-5">
                {option.label}
                {recommendedId === option.id ? (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    · {t("questionDock.recommended")}
                  </span>
                ) : null}
                {/* 一问拍一体化 (2026-09-27): the reason line rides UNDER the
                    label (Claude-Card parity) — muted, wrapping with the
                    row, never a second color of text. */}
                {option.description ? (
                  <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">
                    {option.description}
                  </span>
                ) : null}
              </span>
              {answering && pickedId === option.id ? (
                <Loader2 className="ml-auto h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
              ) : null}
            </Button>
          ))}
          {/* 尾行铅笔手输入 (ADR-053 R1 阻塞形态) — the freeform channel
              while the input row is morphed away (freeform 恒在, 判词 5),
              rendered as ONE MORE ITEM ROW (2026-09-04 用户拍板, FLORA /
              Opus "Something else…" 同款解剖): the pencil sits in the same
              badge tile as the option numbers, the input aligns with the
              option labels. Enter settles through the answer endpoint —
              the client-side number/letter/label mapping (the server's
              autoResume mirror) converts a hit to the option pick,
              anything else records kind="freeform". */}
          {onFreeform ? (
            <div className="flex w-full items-center gap-2.5 rounded-md bg-card px-3 py-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground">
                <Pencil className="h-3 w-3" />
              </span>
              {/* dark:bg-transparent is NOT redundant with bg-transparent:
                  the Input base carries bg-input/20 + dark:bg-input/30, and
                  a bare bg-transparent loses to the dark variant (the
                  variant-pairing law, same trap as hover) — without it the
                  "Something else…" field shows a filled box on the dark
                  theme (2026-09-04 用户拍板). */}
              <Input
                value={freeform}
                onChange={(e) => setFreeform(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    submitFreeform()
                  }
                }}
                placeholder={t("chat.choicePlaceholder")}
                aria-label={t("chat.choicePlaceholder")}
                disabled={answering || freeformDisabled}
                className="h-5 min-w-0 flex-1 border-0 bg-transparent px-0 py-0 text-sm shadow-none focus-visible:ring-0 dark:bg-transparent"
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function QuestionDock(props: OptionDockProps) {
  return <OptionForm {...props} />
}
