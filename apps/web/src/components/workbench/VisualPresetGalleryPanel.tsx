import { useEffect, useRef, useState } from "react"
import { useReducedMotion } from "motion/react"
import { Layers, MessageSquarePlus, Play, Search, Type } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getSoundRecipe } from "@repurposer/sound-engine"
import type { VideoSpec } from "@repurposer/video-spec"

import MotionPresetPlayer from "@/components/chat/video/MotionPresetPlayer"
import { Badge } from "@/components/ui/badge-clean"
import { Button } from "@/components/ui/button-clean"
import { Select } from "@/components/ui/select-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { apiFetch } from "@/lib/api"
import { useWorkbench } from "./WorkbenchContext"

type VisualKind = "block" | "text_preset"

interface VisualPreset {
  id: string
  name: string
  name_zh: string | null
  category: string
  summary: string
  recommended_sfx?: string[]
  preview_duration_s: number
  preview_spec: VideoSpec | null
}

function LivePreview({ spec, title, autoPlay, focus }: {
  spec: VideoSpec
  title: string
  autoPlay: boolean
  focus: boolean
}) {
  const host = useRef<HTMLDivElement>(null)
  const { t } = useTranslation()
  useEffect(() => {
    // The shared player exposes its transport through this play/pause button.
    const control = host.current?.querySelector<HTMLButtonElement>(":scope > button")
    if (focus && document.activeElement === document.body) control?.focus({ preventScroll: true })
    if (autoPlay && control?.ariaLabel === t("chat.candidates.playPreset", { title })) control.click()
  }, [autoPlay, focus, t, title])
  return <div ref={host} className="relative w-full grayscale">
    <MotionPresetPlayer spec={spec} title={title} />
  </div>
}

export default function VisualPresetGalleryPanel({ kind }: { kind: VisualKind }) {
  const { t, i18n } = useTranslation()
  const { citeText } = useWorkbench()
  const reducedMotion = useReducedMotion()
  const [rows, setRows] = useState<VisualPreset[]>([])
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading")
  const [retry, setRetry] = useState(0)
  const [category, setCategory] = useState("")
  const [query, setQuery] = useState("")
  const [hovered, setHovered] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const zh = i18n.language.startsWith("zh")

  useEffect(() => {
    const abort = new AbortController()
    const path = kind === "block" ? "blocks" : "text-presets"
    async function load() {
      setState("loading")
      const collected: VisualPreset[] = []
      for (let offset = 0; !abort.signal.aborted; offset += 20) {
        const response = await apiFetch(`/api/v1/catalog/${path}?limit=20&offset=${offset}`,
          { signal: abort.signal, toast: false })
        if (!response.ok) throw Error("catalog")
        const { items }: { items: VisualPreset[] } = await response.json()
        collected.push(...items)
        if (items.length < 20) break
      }
      if (!abort.signal.aborted) {
        setRows(collected)
        setState("ready")
      }
    }
    load().catch(() => { if (!abort.signal.aborted) setState("failed") })
    return () => abort.abort()
  }, [kind, retry])

  const categoryLabel = (value: string) => t(`visualGallery.categories.${value}`, { defaultValue: value })
  const categories = [...new Set(rows.map(row => row.category))].sort()
  const needle = query.trim().toLowerCase()
  const filtered = rows.filter(row => (!category || row.category === category) &&
    [row.name, row.name_zh, row.id, row.summary, categoryLabel(row.category),
      t(`visualGallery.summaries.${row.id}`, { defaultValue: row.summary })]
      .join(" ").toLowerCase().includes(needle))
  const active = hovered ?? selected
  const PreviewIcon = kind === "block" ? Layers : Type

  return <section className="flex min-h-0 flex-1 flex-col" aria-label={t(kind === "block" ? "visualGallery.blocks" : "visualGallery.text")}>
    <div className="flex shrink-0 items-center gap-2 px-3 py-3">
      <TextField size="sm" type="search" className="min-w-0 flex-1" prefix={<Search size={14} />}
        aria-label={t("visualGallery.search")} placeholder={t("visualGallery.search")}
        value={query} onChange={e => setQuery(e.target.value)} />
      <Select size="sm" aria-label={t("soundLab.category")} value={category} onChange={setCategory}
        options={[{ value: "", label: t("visualGallery.all") },
          ...categories.map(value => ({ value, label: categoryLabel(value) }))]} />
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3 thin-scroll">
      {state === "ready" && <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,18rem),1fr))] gap-2">
        {filtered.map(row => {
          const title = (zh && row.name_zh) || row.name
          const alternate = zh ? row.name : row.name_zh
          const sounds = row.recommended_sfx?.map(id => {
            const recipe = getSoundRecipe(id.replace(/^dsp_/, ""))
            return (zh ? recipe?.name_zh : recipe?.name) || id
          })
          const spec = row.preview_spec
          const playable = spec && spec.width > 0 && spec.height > 0 && spec.duration_frames > 0
          return <article key={row.id} aria-label={title}
            onMouseEnter={() => setHovered(row.id)} onMouseLeave={() => setHovered(null)}
            className="flex flex-col gap-3 rounded-xl border border-subtle bg-card p-3 text-foreground">
            <div className="flex items-start gap-3">
              <div className="relative grid aspect-video w-1/2 shrink-0 place-items-center overflow-hidden rounded-md bg-muted">
                {playable && active === row.id
                  ? <LivePreview spec={spec} title={title} autoPlay={!reducedMotion || selected === row.id} focus={selected === row.id} />
                  : playable ? <button type="button" onClick={() => setSelected(row.id)}
                      aria-label={t("chat.candidates.playPreset", { title })}
                      className="absolute inset-0 grid place-items-center text-muted-foreground focus-visible:outline-2 focus-visible:-outline-offset-2">
                      <PreviewIcon size={28} strokeWidth={1.25} /><Play className="absolute right-2 bottom-2 size-3" />
                    </button>
                    : <span className="p-2 text-xs text-muted-foreground">{t("chat.candidates.presetUnavailable")}</span>}
              </div>
              <div className="min-w-0 flex-1">
                <Badge size="sm">{categoryLabel(row.category)}</Badge>
                <h3 className="mt-1 text-sm font-semibold">{title}</h3>
                {alternate && alternate !== title && <p lang={zh ? "en" : "zh"} className="text-xs text-muted-foreground">{alternate}</p>}
                <p className="mt-2 text-xs leading-relaxed">{t(`visualGallery.summaries.${row.id}`, { defaultValue: row.summary })}</p>
              </div>
            </div>
            <div className="mt-auto flex items-center justify-between gap-2 border-t border-subtle pt-2">
              <span className="min-w-0 text-xs text-muted-foreground">
                {sounds?.length ? t("visualGallery.sound", { name: sounds.join(zh ? "、" : ", ") }) : null}
              </span>
              <Button variant="secondary" size="sm" icon={<MessageSquarePlus size={13} />} onClick={() => {
                const instruction = t(kind === "block" ? "visualGallery.blockInstruction" : "visualGallery.textInstruction",
                  { name: title, id: row.id })
                if (citeText(instruction + " ")) toast.success(t("soundLab.cited"))
                else toast.error(t("visualGallery.citeFailed"))
              }}>{t("soundLab.cite")}</Button>
            </div>
          </article>
        })}
      </div>}
      {(state !== "ready" || !filtered.length) && <div role="status" className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
        {t(state === "ready" ? "visualGallery.empty" : `visualGallery.${state}`)}
        {state === "failed" && <Button size="sm" variant="ghost" onClick={() => setRetry(v => v + 1)}>{t("soundLab.retry")}</Button>}
      </div>}
    </div>
  </section>
}
