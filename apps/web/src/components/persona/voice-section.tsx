import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Check, Mic, Upload } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { apiFetch } from "@/lib/api"

export type VoiceBlock = {
  kind: "cloned" | "stock"
  sample_asset_id?: string
  voice_id?: string
  stock_id?: string
} | null

interface VoiceSample {
  id: string
  title: string | null
  file_url: string | null
  created_at: string
}

interface PersonaVoiceCarrier {
  id: string
  voice: VoiceBlock
}

/**
 * Voice section (persona form tab): shows the persona's current voice
 * binding and re-binds the voice sample. The dub chain reads project-level
 * samples today; this block is the binding of record the chain will read
 * next — so the copy states what IS bound, never what it will do.
 */
export function VoiceSection({
  persona,
  onSaved,
}: {
  persona: PersonaVoiceCarrier
  onSaved: (voice: VoiceBlock) => void
}) {
  const { t } = useTranslation()
  const [samples, setSamples] = useState<VoiceSample[]>([])
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const loadSamples = async () => {
    try {
      const res = await apiFetch(
        `/api/v1/personas/${persona.id}/assets?type=voice_sample`,
        { toast: false }
      )
      if (res.ok) setSamples(await res.json())
    } catch {
      /* offline — keep whatever we had */
    }
  }

  useEffect(() => {
    void loadSamples()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona.id])

  const voice = persona.voice
  const boundSample =
    voice?.kind === "cloned"
      ? samples.find((s) => s.id === voice.sample_asset_id)
      : undefined

  const putVoice = async (next: VoiceBlock) => {
    if (busy) return
    setBusy(true)
    try {
      const res = await apiFetch(`/api/v1/personas/${persona.id}`, {
        method: "PUT",
        body: { voice: next },
        toast: t("personaDetail.voice.msgUpdated"),
      })
      if (res.ok) onSaved(next)
    } finally {
      setBusy(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file || busy) return
    setBusy(true)
    try {
      const urlRes = await apiFetch(`/api/v1/personas/${persona.id}/assets/upload-url`, {
        method: "POST",
        body: { filename: file.name, content_type: file.type || undefined },
      })
      if (!urlRes.ok) return
      const { key, upload_url } = (await urlRes.json()) as {
        key: string
        upload_url: string
      }

      const putRes = await fetch(upload_url, {
        method: "PUT",
        body: file,
        headers: file.type ? { "Content-Type": file.type } : {},
      })
      if (!putRes.ok) return

      const res = await apiFetch(`/api/v1/personas/${persona.id}/assets`, {
        method: "POST",
        body: { key, title: file.name, type: "voice_sample" },
      })
      if (!res.ok) return
      const asset = (await res.json()) as VoiceSample
      await putVoice({ kind: "cloned", sample_asset_id: asset.id })
      await loadSamples()
    } finally {
      setBusy(false)
    }
  }

  const sampleName = (s: VoiceSample) =>
    s.title || s.file_url?.split("/").pop() || t("common.untitled")

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="h-4 w-4" />
          {t("personaDetail.voice.title")}
        </CardTitle>
        <CardDescription>{t("personaDetail.voice.desc")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        <input
          ref={fileRef}
          type="file"
          accept="audio/*"
          className="hidden"
          onChange={handleUpload}
        />

        {/* Auto (NULL) — today's behavior: each project's own audio. */}
        <button
          type="button"
          disabled={busy}
          onClick={() => voice !== null && putVoice(null)}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left hover:bg-accent disabled:opacity-60"
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm">{t("personaDetail.voice.auto")}</p>
            <p className="text-xs text-muted-foreground">
              {t("personaDetail.voice.autoDesc")}
            </p>
          </div>
          {voice === null && <Check className="h-4 w-4 shrink-0 text-primary" />}
        </button>

        {/* My voice sample (cloned binding). */}
        <div className="flex items-center gap-3 rounded-md px-3 py-2.5">
          <div className="min-w-0 flex-1">
            <p className="text-sm">{t("personaDetail.voice.mine")}</p>
            <p className="truncate text-xs text-muted-foreground">
              {voice?.kind === "cloned"
                ? boundSample
                  ? sampleName(boundSample)
                  : t("personaDetail.voice.sampleMissing")
                : voice?.kind === "stock"
                  ? t("personaDetail.voice.stock")
                  : t("personaDetail.voice.noSample")}
            </p>
          </div>
          {voice?.kind === "cloned" && (
            <Check className="h-4 w-4 shrink-0 text-primary" />
          )}
          <Button
            variant="outline"
            size="sm"
            className="h-9 shrink-0"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="mr-2 h-4 w-4" />
            {voice?.kind === "cloned"
              ? t("personaDetail.voice.replace")
              : t("personaDetail.voice.upload")}
          </Button>
        </div>

        {/* Previously uploaded samples — click to re-bind without re-upload. */}
        {voice?.kind !== "cloned" && samples.length > 0 && (
          <div className="space-y-1 pt-1">
            {samples.map((s) => (
              <button
                key={s.id}
                type="button"
                disabled={busy}
                onClick={() => putVoice({ kind: "cloned", sample_asset_id: s.id })}
                className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-60"
              >
                <span className="truncate">{sampleName(s)}</span>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
