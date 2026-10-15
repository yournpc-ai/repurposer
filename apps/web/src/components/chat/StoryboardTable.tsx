"use client"

import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronDown, Clapperboard, Mic } from "lucide-react"

import type { StoryboardPayload } from "@/lib/chatStreamFrames"

type Scene = StoryboardPayload["storyboard"]["scenes"][number]

/** 分镜表消息块 (ADR-120 §1): the film plan's reviewable storyboard in the
 * message flow — one quiet table: 幕 × 形式 × 时长 × 屏上内容. Every fact
 * is the grounding-validated draft verbatim (世界自证 — the world shows
 * itself, never a code-composed summary). The latest version renders the
 * full table; superseded versions fold to a chip (PlanVersionChip 同律). */

const SCENE_TYPE_KEYS: Record<string, string> = {
  words: "words",
  hero: "hero",
  ui: "ui",
  divider: "divider",
  plate: "plate",
  reveal: "reveal",
  end: "end",
}

function sceneCopy(scene: Scene, hostFor: (page: number) => string | null): string {
  const strs = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
  switch (scene.type) {
    case "words":
      return strs(scene.lines).join(" / ")
    case "hero":
      return [scene.word, scene.sub].filter((x): x is string => typeof x === "string").join(" — ")
    case "ui": {
      const captions = strs(
        (Array.isArray(scene.captions) ? scene.captions : []).map(
          (c) => (c as Record<string, unknown>).text,
        ),
      )
      const host = typeof scene.page === "number" ? hostFor(scene.page) : null
      const lead = captions.length > 0 ? captions.join(" / ") : (host ?? "")
      return lead
    }
    case "divider":
      return [scene.label, ...strs(scene.roll)].filter(Boolean).join(" · ")
    case "plate": {
      const cards = Array.isArray(scene.cards) ? scene.cards : []
      const bits = cards.map((c) => {
        const r = c as Record<string, unknown>
        return [r.big, r.label].filter((x): x is string => typeof x === "string").join(" ")
      })
      return [scene.title, ...bits].filter((x): x is string => typeof x === "string" && x !== "").join(" · ")
    }
    case "reveal":
      return [scene.lead, scene.word].filter((x): x is string => typeof x === "string").join(" — ")
    case "end":
      return [scene.name, scene.tagline].filter((x): x is string => typeof x === "string").join(" — ")
    default:
      return ""
  }
}

export function StoryboardTable({
  payload,
  superseded,
}: {
  payload: StoryboardPayload
  superseded: boolean
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const scenes = payload.storyboard.scenes
  const totalSeconds = scenes.reduce((acc, s) => acc + (typeof s.seconds === "number" ? s.seconds : 0), 0)
  const pages = payload.pages ?? []
  const hostFor = (page: number) => pages[page] ?? null

  const title = payload.storyboard.name?.trim() || t("storyboard.untitled")
  const metaLine = t("storyboard.meta", {
    version: payload.version,
    count: scenes.length,
    seconds: Math.round(totalSeconds),
  })
  // 参数行 (ADR-120 E2/E3): the reviewed plan's film levers as header chips —
  // aspect always; voiceover only when off (on is the default); the mood
  // only when the plan named one; the narration language when pinned or
  // declared (data chip, like the aspect — never a translated label).
  const paramChips: string[] = [payload.aspect ?? "16:9"]
  if (payload.voiceover === false) paramChips.push(t("storyboard.voiceOff"))
  if (payload.music_mood) paramChips.push(t("storyboard.music", { mood: payload.music_mood }))
  if (payload.language) paramChips.push(payload.language.toUpperCase())

  if (superseded && !expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="flex w-fit items-center gap-1.5 rounded-md bg-muted px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <Clapperboard className="size-3.5" />
        <span>
          {title} · {metaLine} · {paramChips.join(" · ")}
        </span>
        <ChevronDown className="size-3.5" />
      </button>
    )
  }

  return (
    <div className="w-full max-w-2xl overflow-hidden rounded-lg bg-card ring-1 ring-foreground/10">
      <div className="flex items-center gap-2 px-3 py-2.5">
        <Clapperboard className="size-4 flex-none text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
          {title}
        </span>
        <span className="flex-none text-[11px] text-meta-foreground">
          {metaLine} · {paramChips.join(" · ")}
        </span>
      </div>
      <div className="divide-y divide-foreground/5">
        {scenes.map((scene, i) => (
          <div key={i} className="flex items-baseline gap-3 px-3 py-2">
            <span className="w-6 flex-none text-[11px] tabular-nums text-meta-foreground">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="w-14 flex-none text-[11px] text-muted-foreground">
              {t(`storyboard.sceneTypes.${SCENE_TYPE_KEYS[scene.type] ?? "words"}`)}
            </span>
            <span className="w-10 flex-none text-[11px] tabular-nums text-muted-foreground">
              {typeof scene.seconds === "number" ? `${scene.seconds}s` : ""}
            </span>
            <span className="min-w-0 flex-1 text-xs leading-relaxed text-foreground">
              {sceneCopy(scene, hostFor)}
              {/* 配音词 (ADR-120 E2): the scene's spoken line — reviewed
                  here, synthesized at run time; never on-screen. */}
              {typeof scene.narration === "string" && scene.narration ? (
                <span className="mt-0.5 flex items-start gap-1 text-[11px] leading-relaxed text-muted-foreground">
                  <Mic className="mt-px size-3 flex-none" />
                  {scene.narration}
                </span>
              ) : null}
            </span>
          </div>
        ))}
      </div>
      {pages.length > 0 ? (
        <div className="px-3 py-2 text-[11px] text-meta-foreground">
          {t("storyboard.source", { pages: pages.join(" · ") })}
        </div>
      ) : null}
      {superseded ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="flex w-full items-center justify-center gap-1 px-3 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent"
        >
          <ChevronDown className="size-3 rotate-180" />
          {t("storyboard.collapse")}
        </button>
      ) : null}
    </div>
  )
}
