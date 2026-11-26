import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { AudioLines, Copy, MessageSquarePlus, Play, RotateCcw, Search } from "@/components/ui/icons"
import { toast } from "sonner"
import { SOUND_RECIPES, TUNE_SCHEMA, type SoundDomain, type SoundTune } from "@repurposer/sound-engine"
import { Button } from "@/components/ui/button-clean"
import { Select } from "@/components/ui/select-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { startSoundPreview } from "@/lib/sound-preview"
import { apiFetch } from "@/lib/api"
import { useOptionalWorkbench } from "./WorkbenchContext"

interface SoundRow {
  id: string
  recipe_id?: string
  name: string
  name_zh?: string
  category: string
  moods: string[]
  use_for: string[]
  summary: string
  engine_kind: "sample" | "dsp_recipe"
  duration_ms: number
  waveform_peaks: number[]
  audio_url?: string
}

const axes = Object.keys(TUNE_SCHEMA) as (keyof SoundTune)[]
const categories = (domain: SoundDomain) =>
  [...new Set(SOUND_RECIPES.filter(r => r.domain === domain).map(r => r.category))]

export default function SoundLabPanel({
  standalone = false,
  onUsePreset,
}: {
  standalone?: boolean
  onUsePreset?: (instruction: string) => void
} = {}) {
  const { t, i18n } = useTranslation()
  const workbench = useOptionalWorkbench()
  const [domain, setDomain] = useState<SoundDomain>("interface")
  const [category, setCategory] = useState("")
  const [query, setQuery] = useState("")
  const [rows, setRows] = useState<SoundRow[]>([])
  const [selected, setSelected] = useState("")
  const [tune, setTune] = useState<SoundTune>({})
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [retry, setRetry] = useState(0)
  const [status, setStatus] = useState("")
  const ctx = useRef<AudioContext | null>(null)
  const stop = useRef<(() => void) | null>(null)
  const ticket = useRef(0)
  const cancel = () => {
    ticket.current++
    stop.current?.()
    stop.current = null
  }
  useEffect(() => () => { cancel(); void ctx.current?.close(); ctx.current = null }, [])
  useEffect(() => {
    const abort = new AbortController()
    setLoading(true)
    setFailed(false)
    setRows([])
    async function load() {
      const collected: SoundRow[] = []
      for (let offset = 0; ; offset += 20) {
        const response = await apiFetch("/api/v1/catalog/sfx?domain=" + domain + "&limit=20&offset=" + offset,
          { signal: abort.signal, toast: false })
        if (!response.ok) throw Error("catalog")
        const { items } = await response.json() as { items: SoundRow[] }
        collected.push(...items)
        if (items.length < 20) break
      }
      if (!abort.signal.aborted) setRows(collected)
    }
    load().catch(() => { if (!abort.signal.aborted) setFailed(true) })
      .finally(() => { if (!abort.signal.aborted) setLoading(false) })
    return () => abort.abort()
  }, [domain, retry])

  const label = (row: SoundRow) => i18n.language.startsWith("zh") && row.name_zh ? row.name_zh : row.name
  const filtered = rows.filter(row => (!category || category === row.category) &&
    [row.id, row.name, row.name_zh, ...row.moods, ...row.use_for, row.summary].join(" ").toLowerCase().includes(query.trim().toLowerCase()))
  const active = filtered.find(row => row.id === selected) ?? filtered[0]
  const resetSelection = () => { cancel(); setSelected(""); setTune({}); setStatus("") }

  async function preview(row: SoundRow, values: SoundTune) {
    cancel()
    const id = ticket.current
    setStatus("")
    try {
      if (row.engine_kind === "sample") {
        if (!row.audio_url) throw Error("sample URL")
        const audio = new Audio(row.audio_url)
        stop.current = () => audio.pause()
        await audio.play()
      } else {
        const audio = ctx.current ??= new AudioContext()
        if (audio.state === "suspended") await audio.resume()
        if (id !== ticket.current) return
        const source = startSoundPreview(audio, { recipeId: row.recipe_id!, tune: values })
        stop.current = () => { source.stop(); source.disconnect() }
      }
    } catch {
      if (id === ticket.current) setStatus("playbackError")
    }
  }
  function cite(row: SoundRow) {
    const changes = Object.fromEntries(axes.filter(key => tune[key] !== undefined && tune[key] !== TUNE_SCHEMA[key].default)
      .map(key => [key, tune[key]]))
    const settings = { sfx_id: row.id, ...(row.recipe_id ? { recipe_id: row.recipe_id } : { sfx_slug: row.id }),
      ...(Object.keys(changes).length ? { tune: changes } : {}) }
    const instruction = t("soundLab.instruction", { name: label(row), settings: JSON.stringify(settings) })
    if (workbench) {
      setStatus(workbench.citeText(instruction) ? "cited" : "citeFailed")
      return
    }
    if (onUsePreset) {
      onUsePreset(instruction)
      return
    }
    void navigator.clipboard?.writeText(instruction).then(() => {
      toast.success(t("common.copied"))
    })
  }

  return <section className={standalone ? "grid min-h-[28rem] grid-cols-1 overflow-hidden rounded-xl border border-subtle bg-card text-foreground lg:grid-cols-[minmax(0,1fr)_320px]" : "flex min-h-0 flex-1 flex-col overflow-y-auto bg-card text-foreground"} aria-label={t("workbench.tabs.sounds")}>
    <div className={standalone ? "flex min-h-0 flex-col lg:border-r lg:border-subtle" : "contents"}>
    <div className="grid gap-2 border-b border-subtle p-3">
      <div className="flex items-center justify-between gap-2">
        <SegmentedControl<SoundDomain> size="sm" aria-label={t("soundLab.domain")} value={domain}
          onChange={value => { resetSelection(); setCategory(""); setDomain(value) }}
          options={(["interface", "video"] as const).map(value => ({ value, label: t("soundLab." + value) }))} />
        <Select size="sm" aria-label={t("soundLab.category")} value={category || "all"}
          onChange={value => { resetSelection(); setCategory(value === "all" ? "" : value) }}
          options={[{ value: "all", label: t("soundLab.all") }, ...categories(domain).map(value => ({ value, label: t("soundLab.categories." + value) }))]} />
      </div>
      <TextField size="sm" type="search" prefix={<Search size={14} />} aria-label={t("soundLab.search")}
        placeholder={t("soundLab.search")} value={query} onChange={e => { resetSelection(); setQuery(e.target.value) }} />
    </div>
    <div className="min-h-24 flex-1 overflow-y-auto px-2 py-1 thin-scroll">
      {filtered.map(row => <button key={row.id} type="button" aria-pressed={active?.id === row.id}
        onClick={() => {
          const values = active?.id === row.id ? tune : {}
          setTune(values); setSelected(row.id); void preview(row, values)
        }}
        className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-muted aria-pressed:bg-muted">
        <Play size={13} className="shrink-0" />
        <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium">{label(row)}</span>
          <span className="block text-[10px] text-muted-foreground">{t("soundLab.categories." + row.category, { defaultValue: row.category })}</span></span>
        <span aria-hidden className="flex h-5 w-16 items-center gap-px text-muted-foreground">
          {row.waveform_peaks.map((peak, i) => <i key={i} className="flex-1 rounded-full bg-current" style={{ height: Math.max(5, peak * 100) + "%" }} />)}
        </span>
        <span className="w-14 text-right text-[11px] tabular-nums text-muted-foreground">{row.duration_ms} ms</span>
      </button>)}
      {!filtered.length && <p role="status" className="p-3 text-xs text-muted-foreground">
        {t("soundLab." + (loading ? "loading" : failed ? "failed" : "empty"))}
        {failed && <Button size="sm" variant="ghost" onClick={() => setRetry(v => v + 1)}>{t("soundLab.retry")}</Button>}
      </p>}
    </div>
    </div>
    {active && <div className={standalone ? "flex flex-col justify-between p-4" : "shrink-0 border-t border-subtle p-3"}>
      <div>
      <div className="mb-2 flex items-center gap-2 text-xs"><AudioLines size={15} />
        <strong>{active.engine_kind === "sample" ? label(active) : t("soundLab.tune")}</strong>
        {active.engine_kind === "dsp_recipe" && <><span className="truncate text-muted-foreground">{label(active)}</span>
          <Button size="sm" variant="ghost" icon={<RotateCcw size={12} />} className="ml-auto" onClick={() => { setTune({}); void preview(active, {}) }}>
            {t("soundLab.reset")}</Button></>}
      </div>
      {active.engine_kind === "dsp_recipe" && axes.map(key => {
        const axis = TUNE_SCHEMA[key]
        const value = tune[key] ?? axis.default
        return <label key={key} className="grid min-h-7 grid-cols-[4rem_1fr_5.7rem] items-center gap-2 text-xs">
          <span>{t("soundLab.axes." + key)}</span>
          <input type="range" aria-label={t("soundLab.axes." + key)} min={axis.min} max={axis.max} step={axis.step}
            value={value} className="w-full accent-current" onChange={e => setTune({ ...tune, [key]: Number(e.target.value) })}
            onPointerUp={e => void preview(active, { ...tune, [key]: Number(e.currentTarget.value) })}
            onKeyUp={e => { if (["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"].includes(e.key)) void preview(active, tune) }} />
          <output className="text-right text-[11px] tabular-nums text-muted-foreground">
            {key === "length_scale" ? value.toFixed(2) + "× · " + Math.max(25, Math.min(12000, Math.round(value * active.duration_ms))) + " ms" : value + " " + axis.unit}
          </output>
        </label>
      })}
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        <Button size="sm" variant="secondary" icon={<Play size={13} />} onClick={() => void preview(active, tune)}>{t("soundLab.preview")}</Button>
        <Button size="sm" icon={workbench ? <MessageSquarePlus size={13} /> : <Copy size={13} />} onClick={() => cite(active)}>
          {workbench ? t("soundLab.cite") : onUsePreset ? t("presetsPage.usePreset") : t("common.copy")}
        </Button>
      </div>
    </div>}
    {status && <div role="status" className="px-3 pb-2 text-xs text-muted-foreground">{t("soundLab." + status)}</div>}
  </section>
}
