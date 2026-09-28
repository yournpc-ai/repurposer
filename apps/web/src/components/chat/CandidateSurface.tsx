/** CandidateSurfaceCard — the chat's candidate surface (Workspace 合同 v4.2
 * C8-c, 2026-09-26 封板): the exploration chain's candidates live HERE, in
 * the message flow — never on the canvas (chat 决策永不成节点).
 *
 * Anatomy (合同 Seg C 同构): ordinal as the visual address (「第二个」 speaks
 * to it — two-digit, 01-based) + the source range (mm:ss–mm:ss) + the
 * source-faithful excerpt (C4 锚链: every range/excerpt anchors the SOURCE
 * evidence, never the editable transcript) + the speaker when the ASR
 * named one. Default three recommendations + expand-all (推荐样本，不是只能
 * 选 3 个). Selection state = the row highlight only (bg-accent token step)
 * — the rows are display, never buttons: selection rides chat language
 * (「第二个」「都做」), the surface just reflects it. No playback (候选试听
 * 无此能力, v4.2 事实校正).
 *
 * The card is self-contained (its payload carries every rendered fact), so
 * a deleted source asset leaves nothing dangling — an off-shape payload
 * simply never reaches here (historyReplay's read tolerance). Data chain:
 * live SSE `assistant.candidates` frames + the candidates_log intent dump
 * (record_candidates_log) — message-borne end to end, no endpoint. */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronDown } from "lucide-react"

import { Message, MessageContent } from "@/components/ui/message"
import { cn } from "@/lib/utils"
import type { CandidateSurface } from "./historyReplay"

/** 默认 3 推荐 + 全量可展开 (C8-c: a recommended SAMPLE, never a cap). */
const VISIBLE_COUNT = 3

/** mm:ss–mm:ss — the source range's one display form (the contract mock's). */
function formatRange(start: number, end: number): string {
  const stamp = (s: number) => {
    const t = Math.max(0, Math.round(s))
    return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`
  }
  return `${stamp(start)}–${stamp(end)}`
}

export function CandidateSurfaceCard({ surface }: { surface: CandidateSurface }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const members = surface.members
  const overflow = members.length - VISIBLE_COUNT
  const shown = expanded ? members : members.slice(0, VISIBLE_COUNT)

  return (
    <Message align="start">
      <MessageContent>
        {/* Register parity with AnsweredQuestion: an in-flow bg-muted block
            hugging its content (fill-first — no ring, no shadow), the same
            entrance beat. */}
        <div className="w-fit max-w-[85%] rounded-lg bg-muted py-1.5 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
          <div
            className={cn(
              "flex flex-col",
              expanded && "max-h-64 overflow-y-auto thin-scroll",
            )}
          >
            {shown.map((member, index) => {
              const selected = surface.selected.includes(index)
              return (
                <div
                  key={index}
                  className={cn(
                    "flex items-start gap-2.5 rounded-md px-3 py-1.5",
                    // 选择态 = 行高亮 (C8-c): the --accent step, one token
                    // both themes — never a drawn stroke.
                    selected && "bg-accent",
                  )}
                >
                  {/* ordinal 是地址: the two-digit visual address the user's
                      「第二个」 speaks to. */}
                  <span
                    className={cn(
                      "mt-0.5 shrink-0 tabular-nums text-xs",
                      selected ? "text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0">
                    {/* One clamped line-block: the range prefix rides INSIDE
                        the clamp (line-clamp needs the box) so a two-line
                        excerpt keeps its range attached. */}
                    <span className="line-clamp-2 text-sm leading-relaxed">
                      <span className="mr-1.5 text-xs tabular-nums text-muted-foreground">
                        {formatRange(member.start, member.end)}
                      </span>
                      {member.speaker ? (
                        <span className="text-muted-foreground">
                          {member.speaker} ·{" "}
                        </span>
                      ) : null}
                      {member.excerpt}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
          {overflow > 0 ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-0.5 flex w-full items-center gap-1.5 rounded-md px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <ChevronDown
                className={cn(
                  "size-3.5 transition-transform",
                  expanded && "rotate-180",
                )}
              />
              {expanded
                ? t("chat.candidates.less")
                : t("chat.candidates.more", { count: overflow })}
            </button>
          ) : null}
        </div>
      </MessageContent>
    </Message>
  )
}
