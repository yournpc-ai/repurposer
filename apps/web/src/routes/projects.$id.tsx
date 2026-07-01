import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toPng } from 'html-to-image'
import {
  ArrowLeft,
  Upload,
  Wand2,
  FileText,
  Trash2,
  Play,
  Download,
  Pencil,
  RotateCw,
  X,
  FileArchive,
  SlidersHorizontal,
  ChevronDown,
  Check,
} from 'lucide-react'

import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const OUTPUT_LANGUAGE_CODES = ['en', 'zh', 'fr', 'de', 'es', 'it'] as const

// Outputs the unified background generation can produce, in display order.
const OUTPUT_KINDS = ['clips', 'linkedin', 'quote_cards', 'carousel', 'summary', 'blog'] as const

interface Project {
  id: string
  title: string
  event_name: string | null
  status: string
  language: string
  speaker_id: string | null
  created_at: string
}

interface Speaker {
  id: string
  name: string
  persona: {
    emotional_tone: string
    sentence_style: string
  } | null
}

interface Asset {
  id: string
  type: string
  file_url: string | null
  extracted_text: string | null
  processing_status: string
  processing_error: string | null
  created_at: string
}

interface Shot {
  time_range: string
  visual: string
  subtitle: string
  mood: string
}

interface ClipScript {
  hook: string
  duration_seconds: number
  shots: Shot[]
  title_options: string[]
  music_mood: string
  virality_score: number | null
}

interface Clip {
  id: string
  hook: string
  script: ClipScript
  title_options: string[]
  music_mood: string
  status: string
  video_url: string | null
  render_spec: unknown | null
  render_status: string | null
  duration: number
  created_at: string
  updated_at: string | null
}

interface Derivative {
  id: string
  type: string
  content: {
    content?: string
    hashtags?: string[]
    quotes?: { quote: string; attribution: string }[]
    slides?: { title: string; body?: string }[]
    tldr?: string
    key_points?: string[]
    full?: string
    title?: string
  }
  language: string
  created_at: string
  updated_at: string | null
}

interface Job {
  id: string
  status: string
  current_step: string | null
  progress: number
  error: string | null
}

interface BrandConfig {
  captionColor?: string
  logoUrl?: string
  cta?: string
}

/** Renders a quote as a downloadable PNG card, styled by the brand template. */
function QuoteCardArt({
  quote,
  attribution,
  brand,
  downloadLabel,
}: {
  quote: string
  attribution: string
  brand: BrandConfig | null
  downloadLabel: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const accent = brand?.captionColor || '#facc15'

  const download = async () => {
    if (!ref.current) return
    const dataUrl = await toPng(ref.current, { pixelRatio: 3, cacheBust: true })
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = 'quote-card.png'
    a.click()
  }

  return (
    <div className="space-y-2">
      <div
        ref={ref}
        className="flex aspect-[4/5] flex-col justify-between overflow-hidden rounded-xl bg-gradient-to-br from-zinc-800 to-zinc-950 p-7"
      >
        {brand?.logoUrl ? (
          <img src={brand.logoUrl} alt="" className="h-7 w-auto self-start object-contain" />
        ) : (
          <div className="h-7" />
        )}
        <p className="text-2xl font-bold leading-snug text-white">
          <span style={{ color: accent }}>“</span>
          {quote}
          <span style={{ color: accent }}>”</span>
        </p>
        <div>
          <div className="mb-3 h-0.5 w-10" style={{ backgroundColor: accent }} />
          <p className="text-sm font-medium text-white">{attribution}</p>
          {brand?.cta && <p className="mt-1 text-xs text-white/60">{brand.cta}</p>}
        </div>
      </div>
      <Button variant="outline" size="sm" className="w-full gap-2" onClick={download}>
        <Download className="h-4 w-4" />
        {downloadLabel}
      </Button>
    </div>
  )
}

function CarouselSlideArt({
  index,
  title,
  body,
  brand,
  label,
  downloadLabel,
}: {
  index: number
  title: string
  body: string
  brand: BrandConfig | null
  label: string
  downloadLabel: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const accent = brand?.captionColor || '#facc15'

  const download = async () => {
    if (!ref.current) return
    const dataUrl = await toPng(ref.current, { pixelRatio: 3, cacheBust: true })
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = `carousel-${index}.png`
    a.click()
  }

  return (
    <div className="w-56 shrink-0 space-y-2">
      <div
        ref={ref}
        className="flex aspect-[4/5] flex-col justify-between overflow-hidden rounded-xl bg-gradient-to-br from-zinc-800 to-zinc-950 p-6"
      >
        <div className="flex items-center justify-between">
          {brand?.logoUrl ? (
            <img src={brand.logoUrl} alt="" className="h-6 w-auto object-contain" />
          ) : (
            <div className="h-6" />
          )}
          <span className="text-xs font-medium text-white/50">{label}</span>
        </div>
        <div className="space-y-2">
          <p className="text-xl font-bold leading-snug text-white">{title}</p>
          {body && <p className="text-sm leading-snug text-white/80">{body}</p>}
        </div>
        <div className="h-0.5 w-10" style={{ backgroundColor: accent }} />
      </div>
      <Button variant="outline" size="sm" className="w-full gap-2" onClick={download}>
        <Download className="h-4 w-4" />
        {downloadLabel}
      </Button>
    </div>
  )
}

export const Route = createFileRoute('/projects/$id')({
  component: ProjectDetailPage,
})

function ProjectDetailPage() {
  const { id } = Route.useParams()
  const { t } = useTranslation()

  const [project, setProject] = useState<Project | null>(null)
  const [speaker, setSpeaker] = useState<Speaker | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [derivatives, setDerivatives] = useState<Derivative[]>([])
  const [brand, setBrand] = useState<BrandConfig | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [outputs, setOutputs] = useState<string[]>(['clips', 'linkedin', 'quote_cards'])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [targetLanguage, setTargetLanguage] = useState('en')
  const [exporting, setExporting] = useState(false)

  // Inline editing state
  const [editingClipId, setEditingClipId] = useState<string | null>(null)
  const [editClipHook, setEditClipHook] = useState('')
  const [editClipTitles, setEditClipTitles] = useState('')
  const [editingDerivativeId, setEditingDerivativeId] = useState<string | null>(null)
  const [editDerivativeContent, setEditDerivativeContent] = useState('')

  const fetchData = async () => {
    setLoading(true)
    try {
      const projectRes = await fetch(`${API_URL}/api/v1/projects/${id}`)
      if (!projectRes.ok) throw new Error('Project not found')
      const projectData = await projectRes.json()
      setProject(projectData)

      const [speakerRes, assetsRes, clipsRes, derivativesRes, jobsRes, brandRes] =
        await Promise.all([
          projectData.speaker_id
            ? fetch(`${API_URL}/api/v1/speakers/${projectData.speaker_id}`)
            : Promise.resolve(new Response('null')),
          fetch(`${API_URL}/api/v1/projects/${id}/assets`),
          fetch(`${API_URL}/api/v1/projects/${id}/clips`),
          fetch(`${API_URL}/api/v1/projects/${id}/derivatives`),
          fetch(`${API_URL}/api/v1/projects/${id}/jobs`),
          fetch(`${API_URL}/api/v1/brand-templates`),
        ])

      if (projectData.speaker_id && speakerRes.ok) setSpeaker(await speakerRes.json())
      else
        setSpeaker({
          id: '',
          name: t('composer.styleDefault'),
          persona: null,
        })
      if (assetsRes.ok) setAssets(await assetsRes.json())
      if (clipsRes.ok) setClips(await clipsRes.json())
      if (derivativesRes.ok) setDerivatives(await derivativesRes.json())
      if (jobsRes.ok) {
        const jobs: Job[] = await jobsRes.json()
        setJob(jobs[0] ?? null)
      }
      if (brandRes.ok) {
        const templates: Array<{ config: BrandConfig }> = await brandRes.json()
        setBrand(templates[0]?.config ?? null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [id])

  // Poll the active job until it finishes, then refresh results.
  const jobActive = job?.status === 'pending' || job?.status === 'running'
  useEffect(() => {
    if (!job || (job.status !== 'pending' && job.status !== 'running')) return
    const jobId = job.id
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/projects/${id}/jobs/${jobId}`)
        if (!res.ok) return
        const updated: Job = await res.json()
        setJob(updated)
        if (updated.status === 'completed' || updated.status === 'failed') {
          clearInterval(timer)
          fetchData()
        }
      } catch {
        /* transient network error — keep polling */
      }
    }, 2500)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.status, id])

  // While any asset is still being processed, poll the asset list until all
  // assets reach a terminal state (completed / failed).
  const assetsPending = assets.some(
    (a) => a.processing_status === 'pending' || a.processing_status === 'processing'
  )
  useEffect(() => {
    if (!assetsPending) return
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/projects/${id}/assets`)
        if (res.ok) setAssets(await res.json())
      } catch {
        /* transient network error — keep polling */
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [assetsPending, id])

  // Map an uploaded file to its backend AssetType. Voice samples are never
  // inferred (voice cloning isn't built yet — don't promise it).
  const inferAssetType = (file: File): string => {
    const m = file.type
    if (m.startsWith('video/')) return 'video'
    if (m.startsWith('audio/')) return 'audio'
    if (m.startsWith('image/')) return 'image'
    return 'transcript' // pdf / txt / md / unknown -> text extraction
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, type?: string) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    setMessage('')
    try {
      const formData = new FormData()
      formData.append('type', type ?? inferAssetType(file))
      formData.append('file', file)
      const res = await fetch(`${API_URL}/api/v1/projects/${id}/assets`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error('Upload failed')
      setMessage(t('projectDetail.msgUploaded'))
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDeleteAsset = async (assetId: string) => {
    if (!confirm(t('projectDetail.deleteConfirm'))) return
    try {
      const res = await fetch(`${API_URL}/api/v1/projects/${id}/assets/${assetId}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('Delete failed')
      setMessage(t('projectDetail.msgDeleted'))
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const handleReprocessAsset = async (assetId: string) => {
    setError('')
    try {
      const res = await fetch(
        `${API_URL}/api/v1/projects/${id}/assets/${assetId}/reprocess`,
        { method: 'POST' }
      )
      if (!res.ok) throw new Error('Reprocess failed')
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reprocess failed')
    }
  }

  const handleGenerate = async () => {
    if (outputs.length === 0) return
    setGenerating(true)
    setError('')
    setMessage('')
    try {
      const res = await fetch(`${API_URL}/api/v1/projects/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_count: 3,
          outputs,
          target_language: targetLanguage,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Generation failed')
      // Start tracking the background job; the polling effect takes over.
      setJob({ id: data.job_id, status: 'pending', current_step: 'queued', progress: 0, error: null })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const handleExport = async () => {
    if (!clips.length && !derivatives.length) {
      setError(t('projectDetail.noContentToExport'))
      return
    }
    setExporting(true)
    setError('')
    setMessage('')
    try {
      const res = await fetch(`${API_URL}/api/v1/projects/${id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ formats: ['text'] }),
      })
      if (!res.ok) throw new Error(t('projectDetail.exportFailed'))
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const disposition = res.headers.get('content-disposition')
      const filename = disposition?.match(/filename="?([^"]+)"?/)?.[1] || 'export.zip'
      a.download = filename
      a.click()
      window.URL.revokeObjectURL(url)
      setMessage(t('projectDetail.exportSuccess'))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('projectDetail.exportFailed'))
    } finally {
      setExporting(false)
    }
  }

  const startEditClip = (clip: Clip) => {
    setEditingClipId(clip.id)
    setEditClipHook(clip.hook)
    setEditClipTitles((clip.title_options || []).join('\n'))
  }

  const cancelEditClip = () => {
    setEditingClipId(null)
    setEditClipHook('')
    setEditClipTitles('')
  }

  const saveClip = async (clipId: string) => {
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/v1/clips/${clipId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hook: editClipHook,
          title_options: editClipTitles
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      })
      if (!res.ok) throw new Error('Save failed')
      setMessage(t('projectDetail.msgSaved'))
      setEditingClipId(null)
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  const startEditDerivative = (d: Derivative) => {
    setEditingDerivativeId(d.id)
    setEditDerivativeContent(d.content.content || '')
  }

  const cancelEditDerivative = () => {
    setEditingDerivativeId(null)
    setEditDerivativeContent('')
  }

  const saveDerivative = async (derivativeId: string) => {
    setError('')
    try {
      const d = derivatives.find((x) => x.id === derivativeId)
      const res = await fetch(`${API_URL}/api/v1/derivatives/${derivativeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: { ...d?.content, content: editDerivativeContent },
        }),
      })
      if (!res.ok) throw new Error('Save failed')
      setMessage(t('projectDetail.msgSaved'))
      setEditingDerivativeId(null)
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  const linkedinPosts = derivatives.filter((d) => d.type === 'linkedin_post')
  const quoteCardSets = derivatives.filter((d) => d.type === 'quote_card')
  const carouselSets = derivatives.filter((d) => d.type === 'carousel')
  const summaries = derivatives.filter((d) => d.type === 'summary')
  const blogs = derivatives.filter((d) => d.type === 'blog')

  if (loading && !project) {
    return <div className="p-8 text-muted-foreground">{t('common.loading')}</div>
  }

  if (!project) {
    return <div className="p-8 text-destructive">{error || t('projectDetail.notFound')}</div>
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('projectDetail.back')}
            render={<Link to="/projects" />}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{project.title}</h1>
            {project.event_name && (
              <p className="text-sm text-muted-foreground">{project.event_name}</p>
            )}
          </div>
        </div>
        <Button
          variant="outline"
          className="h-9 gap-2"
          disabled={exporting || (!clips.length && !derivatives.length)}
          onClick={handleExport}
        >
          {exporting ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <FileArchive className="h-4 w-4" />
          )}
          {exporting ? t('projectDetail.exporting') : t('projectDetail.exportAll')}
        </Button>
      </div>

      {/* Status banner */}
      {(message || error) && (
        <div
          className={cn(
            'rounded-lg border px-4 py-3 text-sm',
            error
              ? 'border-destructive/30 bg-destructive/10 text-destructive'
              : 'border-border bg-muted text-foreground'
          )}
        >
          {error || message}
        </div>
      )}

      {/* Active job progress */}
      {jobActive && (
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">
              {t('projectDetail.jobRunning')}
              {job?.current_step ? ` · ${job.current_step}` : ''}
            </span>
            <span className="text-muted-foreground">{job?.progress ?? 0}%</span>
          </div>
          <Progress value={job?.progress ?? 0} className="mt-2" />
        </div>
      )}
      {job?.status === 'failed' && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {t('projectDetail.jobFailed')}
          {job.error ? `: ${job.error}` : ''}
        </div>
      )}

      {/* Meta card */}
      <div className="rounded-xl bg-card p-6 ring-1 ring-border">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('projectDetail.status')}
            </p>
            <Badge variant="secondary" className="mt-1.5 capitalize">
              {project.status}
            </Badge>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('projectDetail.speaker')}
            </p>
            <p className="mt-1.5 text-sm">{speaker?.name || t('projectDetail.unknown')}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('projectDetail.persona')}
            </p>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {speaker?.persona?.emotional_tone || t('projectDetail.notGenerated')}
            </p>
          </div>
        </div>
      </div>

      {/* Source materials + generation */}
      <div className="space-y-4 rounded-xl bg-card p-6 ring-1 ring-border">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{t('projectDetail.sourceMaterials')}</h2>
          <div className="flex flex-wrap items-center gap-2">
            <Popover>
              <PopoverTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-3 text-sm"
                  >
                    <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
                    <span>{t('composer.outputsLabel')}</span>
                    <Badge variant="secondary" className="ml-1 px-1.5 text-[10px]">
                      {outputs.length}
                    </Badge>
                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                }
              />
              <PopoverContent align="end" className="w-56 space-y-1 p-2">
                {OUTPUT_KINDS.map((key) => {
                  const active = outputs.includes(key)
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() =>
                        setOutputs((prev) =>
                          active ? prev.filter((o) => o !== key) : [...prev, key]
                        )
                      }
                      className={cn(
                        'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors',
                        active ? 'bg-accent text-foreground' : 'hover:bg-accent/50'
                      )}
                    >
                      {t(`composer.outputOptions.${key}`)}
                      {active && <Check className="h-4 w-4" />}
                    </button>
                  )
                })}
              </PopoverContent>
            </Popover>
            <Select value={targetLanguage} onValueChange={(v) => setTargetLanguage(v ?? 'en')}>
              <SelectTrigger className="h-9 w-auto gap-2 rounded-md text-sm">
                <span className="text-muted-foreground">{t('projectDetail.outputLanguage')}</span>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OUTPUT_LANGUAGE_CODES.map((code) => (
                  <SelectItem key={code} value={code}>
                    {t(`languages.${code}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              className="h-9 gap-2"
              disabled={jobActive || generating || assets.length === 0 || outputs.length === 0}
              onClick={handleGenerate}
            >
              <Wand2 className="h-4 w-4" />
              {jobActive || generating
                ? t('projectDetail.generating')
                : t('projectDetail.generate')}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-muted px-3 text-sm transition-colors hover:bg-accent">
            <Upload className="h-4 w-4" />
            {uploading ? t('projectDetail.uploading') : t('projectDetail.uploadTranscript')}
            <input
              type="file"
              onChange={(e) => handleFileUpload(e)}
              disabled={uploading}
              accept=".txt,.md,.pdf,video/*,audio/*,image/*"
              className="hidden"
            />
          </label>
          <span className="text-sm text-muted-foreground">{t('projectDetail.uploadHint')}</span>
        </div>

        {assets.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            {t('projectDetail.noMaterials')}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {assets.map((asset) => {
              const isProcessing =
                asset.processing_status === 'pending' ||
                asset.processing_status === 'processing'
              const isFailed = asset.processing_status === 'failed'
              return (
                <div key={asset.id} className="flex items-start justify-between gap-4 py-4">
                  <div className="flex min-w-0 items-start gap-3">
                    <FileText className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {asset.file_url?.split('/').pop() || t('common.untitled')}
                      </p>
                      {isProcessing ? (
                        <p className="flex items-center gap-2 text-sm text-muted-foreground">
                          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          {t('projectDetail.processing')}
                        </p>
                      ) : isFailed ? (
                        <p className="text-sm text-destructive">
                          {t('projectDetail.processingFailed')}
                          {asset.processing_error ? `: ${asset.processing_error}` : ''}
                        </p>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          {asset.extracted_text
                            ? t('projectDetail.charsExtracted', {
                                count: asset.extracted_text.length,
                              })
                            : t('projectDetail.noText')}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground/70">
                        {t('projectDetail.uploadedAt', {
                          type: asset.type,
                          date: new Date(asset.created_at).toLocaleString(),
                        })}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {isFailed && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1"
                        onClick={() => handleReprocessAsset(asset.id)}
                      >
                        <RotateCw className="h-3.5 w-3.5" />
                        {t('projectDetail.retry')}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={t('common.delete')}
                      onClick={() => handleDeleteAsset(asset.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Clips */}
      {clips.length > 0 && (
        <div className="space-y-4 rounded-xl bg-card p-6 ring-1 ring-border">
          <h2 className="text-lg font-semibold">
            {t('projectDetail.generatedClips', { count: clips.length })}
          </h2>
          <div className="space-y-4">
            {clips.map((clip, index) => {
              const isEditing = editingClipId === clip.id
              return (
                <Card key={clip.id} className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-muted-foreground">
                          #{index + 1}
                        </span>
                        {isEditing ? (
                          <Input
                            value={editClipHook}
                            onChange={(e) => setEditClipHook(e.target.value)}
                            className="h-9 flex-1"
                          />
                        ) : (
                          <h3 className="text-lg font-semibold">{clip.hook}</h3>
                        )}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                        <span>{clip.duration}s</span>
                        <span>·</span>
                        <span>{t('projectDetail.bgm')}: {clip.music_mood}</span>
                        <span>·</span>
                        <span>{t('projectDetail.score')}: {clip.script.virality_score ?? '-'}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      {isEditing ? (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9"
                            onClick={() => saveClip(clip.id)}
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9"
                            onClick={cancelEditClip}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1"
                          onClick={() => startEditClip(clip)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          {t('projectDetail.edit')}
                        </Button>
                      )}
                      {clip.render_spec ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1 text-primary"
                          render={
                            <Link
                              to="/projects/$id/clips/$clipId"
                              params={{ id, clipId: clip.id }}
                            />
                          }
                        >
                          <Play className="h-4 w-4" />
                          {t('projectDetail.openEditor')}
                        </Button>
                      ) : null}
                    </div>
                  </div>

                  {clip.title_options.length > 0 && (
                    <div className="mt-4">
                      <p className="mb-2 text-sm font-medium">
                        {t('projectDetail.titleOptions')}
                      </p>
                      {isEditing ? (
                        <Textarea
                          value={editClipTitles}
                          onChange={(e) => setEditClipTitles(e.target.value)}
                          className="min-h-[80px]"
                          placeholder={t('projectDetail.titlePerLine')}
                        />
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {clip.title_options.map((title, i) => (
                            <Badge key={i} variant="secondary">
                              {title}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="mt-4">
                    <p className="mb-2 text-sm font-medium">{t('projectDetail.scriptShots')}</p>
                    <div className="space-y-2">
                      {clip.script.shots.map((shot, i) => (
                        <div key={i} className="rounded-md bg-muted p-3">
                          <div className="mb-1 flex items-center gap-2 text-sm text-muted-foreground">
                            <span className="font-medium">{shot.time_range}</span>
                            <span>·</span>
                            <span>{shot.mood}</span>
                          </div>
                          <p className="text-foreground">{shot.subtitle}</p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            {t('projectDetail.visual', { value: shot.visual })}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* LinkedIn posts */}
      {linkedinPosts.length > 0 && (
        <div className="space-y-4 rounded-xl bg-card p-6 ring-1 ring-border">
          <h2 className="text-lg font-semibold">
            {t('projectDetail.linkedinPosts')} ({linkedinPosts.length})
          </h2>
          {linkedinPosts.map((d) => (
            <EditableDerivative
              key={d.id}
              derivative={d}
              isEditing={editingDerivativeId === d.id}
              content={editDerivativeContent}
              onContentChange={setEditDerivativeContent}
              onStartEdit={() => startEditDerivative(d)}
              onCancel={cancelEditDerivative}
              onSave={() => saveDerivative(d.id)}
              t={t}
            >
              <p className="whitespace-pre-wrap text-sm">{d.content.content}</p>
              {d.content.hashtags && d.content.hashtags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {d.content.hashtags.map((h, i) => (
                    <Badge key={i} variant="secondary">
                      #{h.replace(/^#/, '')}
                    </Badge>
                  ))}
                </div>
              )}
            </EditableDerivative>
          ))}
        </div>
      )}

      {/* Quote cards */}
      {quoteCardSets.length > 0 && (
        <div className="space-y-4 rounded-xl bg-card p-6 ring-1 ring-border">
          <h2 className="text-lg font-semibold">{t('projectDetail.quoteCards')}</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {quoteCardSets.flatMap((d) =>
              (d.content.quotes ?? []).map((q, i) => (
                <QuoteCardArt
                  key={`${d.id}-${i}`}
                  quote={q.quote}
                  attribution={q.attribution}
                  brand={brand}
                  downloadLabel={t('projectDetail.downloadCard')}
                />
              ))
            )}
          </div>
        </div>
      )}

      {/* Carousel */}
      {carouselSets.length > 0 && (
        <div className="space-y-4 rounded-xl bg-card p-6 ring-1 ring-border">
          <h2 className="text-lg font-semibold">{t('projectDetail.carousel')}</h2>
          {carouselSets.map((d) => {
            const slides = d.content.slides ?? []
            return (
              <div key={d.id} className="flex gap-4 overflow-x-auto pb-2">
                {slides.map((s, i) => (
                  <CarouselSlideArt
                    key={`${d.id}-${i}`}
                    index={i + 1}
                    title={s.title}
                    body={s.body ?? ''}
                    brand={brand}
                    label={t('projectDetail.slideLabel', { index: i + 1, total: slides.length })}
                    downloadLabel={t('projectDetail.downloadCard')}
                  />
                ))}
              </div>
            )
          })}
        </div>
      )}

      {/* Summary */}
      {summaries.length > 0 && (
        <div className="space-y-4 rounded-xl bg-card p-6 ring-1 ring-border">
          <h2 className="text-lg font-semibold">{t('projectDetail.summary')}</h2>
          {summaries.map((d) => (
            <EditableDerivative
              key={d.id}
              derivative={d}
              isEditing={editingDerivativeId === d.id}
              content={editDerivativeContent}
              onContentChange={setEditDerivativeContent}
              onStartEdit={() => startEditDerivative(d)}
              onCancel={cancelEditDerivative}
              onSave={() => saveDerivative(d.id)}
              t={t}
            >
              {d.content.tldr && <p className="font-medium">{d.content.tldr}</p>}
              {d.content.key_points && d.content.key_points.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {d.content.key_points.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              )}
              {d.content.full && (
                <p className="whitespace-pre-wrap text-sm">{d.content.full}</p>
              )}
            </EditableDerivative>
          ))}
        </div>
      )}

      {/* Blog */}
      {blogs.length > 0 && (
        <div className="space-y-4 rounded-xl bg-card p-6 ring-1 ring-border">
          <h2 className="text-lg font-semibold">{t('projectDetail.blog')}</h2>
          {blogs.map((d) => (
            <EditableDerivative
              key={d.id}
              derivative={d}
              isEditing={editingDerivativeId === d.id}
              content={editDerivativeContent}
              onContentChange={setEditDerivativeContent}
              onStartEdit={() => startEditDerivative(d)}
              onCancel={cancelEditDerivative}
              onSave={() => saveDerivative(d.id)}
              t={t}
            >
              {d.content.title && (
                <h3 className="text-base font-semibold">{d.content.title}</h3>
              )}
              <p className="whitespace-pre-wrap text-sm">{d.content.content}</p>
            </EditableDerivative>
          ))}
        </div>
      )}
    </div>
  )
}

function EditableDerivative({
  derivative,
  isEditing,
  content,
  onContentChange,
  onStartEdit,
  onCancel,
  onSave,
  t,
  children,
}: {
  derivative: Derivative
  isEditing: boolean
  content: string
  onContentChange: (v: string) => void
  onStartEdit: () => void
  onCancel: () => void
  onSave: () => void
  t: (key: string) => string
  children: React.ReactNode
}) {
  return (
    <Card className="p-4">
      {isEditing ? (
        <div className="space-y-3">
          <Textarea
            value={content}
            onChange={(e) => onContentChange(e.target.value)}
            className="min-h-[160px]"
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onCancel}>
              {t('projectDetail.cancel')}
            </Button>
            <Button size="sm" onClick={onSave}>
              {t('projectDetail.save')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {children}
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground/70">
              {new Date(derivative.created_at).toLocaleString()} · {derivative.language}
            </p>
            <Button variant="ghost" size="sm" className="gap-1" onClick={onStartEdit}>
              <Pencil className="h-3.5 w-3.5" />
              {t('projectDetail.edit')}
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}
