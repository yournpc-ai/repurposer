import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowLeft,
  FileText,
  Fingerprint,
  Pencil,
  Save,
  Trash2,
  Upload,
  Wand2,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { apiFetch } from "@/lib/api"
import { SkinEditor } from "@/components/persona/skin-editor"
import { VoiceSection, type VoiceBlock } from "@/components/persona/voice-section"

interface Persona {
  id: string
  name: string
  title: string | null
  language: string
  avatar_url: string | null
  core_values: string[]
  favorite_metaphors: string[]
  sentence_style: string
  emotional_tone: "rational" | "passionate" | "gentle" | "sharp" | "humorous"
  typical_hooks: string[]
  avoid_words: string[]
  voice: VoiceBlock
  brand: Record<string, unknown> | null
  audience: string | null
  guidelines: string | null
  cta: string | null
  created_at: string
  updated_at: string | null
}

interface Asset {
  id: string
  type: string
  file_url: string | null
  title: string | null
  extracted_text: string | null
  processed_at: string | null
  created_at: string
}

export const Route = createFileRoute("/_app/personas/$id")({
  component: PersonaDetailPage,
})

function PersonaDetailPage() {
  const { id } = Route.useParams()
  const { t } = useTranslation()

  const [persona, setPersona] = useState<Persona | null>(null)
  const [materials, setMaterials] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)

  const [renameTarget, setRenameTarget] = useState<Asset | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [renameBusy, setRenameBusy] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Asset | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState("")
  const [title, setTitle] = useState("")
  const [coreValues, setCoreValues] = useState("")
  const [favoriteMetaphors, setFavoriteMetaphors] = useState("")
  const [sentenceStyle, setSentenceStyle] = useState("")
  const [emotionalTone, setEmotionalTone] = useState<Persona["emotional_tone"]>("rational")
  const [typicalHooks, setTypicalHooks] = useState("")
  const [avoidWords, setAvoidWords] = useState("")
  const [audience, setAudience] = useState("")
  const [guidelines, setGuidelines] = useState("")
  const [cta, setCta] = useState("")
  // Controlled tabs: the skin editor needs a wider canvas than the form.
  const [tab, setTab] = useState("persona")

  const fetchData = async () => {
    setLoading(true)
    try {
      // Page-level load failure renders the not-found placeholder below, so
      // these calls stay silent (toast: false) to avoid double reporting.
      const [personaRes, materialsRes] = await Promise.all([
        apiFetch(`/api/v1/personas/${id}`, { toast: false }),
        apiFetch(`/api/v1/personas/${id}/assets`, { toast: false }),
      ])
      if (!personaRes.ok) throw new Error("Persona not found")
      const personaData: Persona = await personaRes.json()
      const materialsData = await materialsRes.json()
      setPersona(personaData)
      setMaterials(materialsData)
      setName(personaData.name)
      setTitle(personaData.title || "")
      setCoreValues(personaData.core_values.join("\n"))
      setFavoriteMetaphors(personaData.favorite_metaphors.join("\n"))
      setSentenceStyle(personaData.sentence_style)
      setEmotionalTone(personaData.emotional_tone)
      setTypicalHooks(personaData.typical_hooks.join("\n"))
      setAvoidWords(personaData.avoid_words.join("\n"))
      setAudience(personaData.audience || "")
      setGuidelines(personaData.guidelines || "")
      setCta(personaData.cta || "")
    } catch {
      setPersona(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [id])

  const assetTitle = (asset: Asset) =>
    asset.title || asset.file_url?.split("/").pop() || t("common.untitled")

  const handleUpdatePersona = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const res = await apiFetch(`/api/v1/personas/${id}`, {
        method: "PUT",
        body: {
          name,
          title,
          core_values: coreValues.split("\n").filter((s) => s.trim()),
          favorite_metaphors: favoriteMetaphors.split("\n").filter((s) => s.trim()),
          sentence_style: sentenceStyle,
          emotional_tone: emotionalTone,
          typical_hooks: typicalHooks.split("\n").filter((s) => s.trim()),
          avoid_words: avoidWords.split("\n").filter((s) => s.trim()),
          audience: audience || null,
          guidelines: guidelines || null,
          cta: cta || null,
        },
        toast: t("personaDetail.msgUpdated"),
      })
      if (res.ok) fetchData()
    } finally {
      setSaving(false)
    }
  }

  const handleGeneratePersona = async () => {
    setGenerating(true)
    try {
      const res = await apiFetch(`/api/v1/personas/${id}/generate`, {
        method: "POST",
        toast: t("personaDetail.msgGenerated"),
      })
      if (!res.ok) return
      const data: Persona = await res.json()
      setCoreValues(data.core_values.join("\n"))
      setFavoriteMetaphors(data.favorite_metaphors.join("\n"))
      setSentenceStyle(data.sentence_style)
      setEmotionalTone(data.emotional_tone)
      setTypicalHooks(data.typical_hooks.join("\n"))
      setAvoidWords(data.avoid_words.join("\n"))
      setAudience(data.audience || "")
      setGuidelines(data.guidelines || "")
      setCta(data.cta || "")
    } finally {
      setGenerating(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    setUploading(true)
    try {
      const urlRes = await apiFetch(`/api/v1/personas/${id}/assets/upload-url`, {
        method: "POST",
        body: {
          filename: file.name,
          content_type: file.type || undefined,
        },
      })
      if (!urlRes.ok) return
      const { key, upload_url } = (await urlRes.json()) as {
        key: string
        upload_url: string
      }

      // Straight PUT to the presigned storage URL — outside apiFetch, so a
      // failure here needs its own toast.
      const putRes = await fetch(upload_url, {
        method: "PUT",
        body: file,
        headers: file.type ? { "Content-Type": file.type } : {},
      })
      if (!putRes.ok) {
        toast.error(t("common.requestFailed"))
        return
      }

      const res = await apiFetch(`/api/v1/personas/${id}/assets`, {
        method: "POST",
        body: { key, title: file.name },
        toast: t("personaDetail.msgUploaded"),
      })
      if (res.ok) fetchData()
    } finally {
      setUploading(false)
    }
  }

  const openRename = (asset: Asset) => {
    setRenameValue(assetTitle(asset))
    setRenameTarget(asset)
  }

  const handleRename = async () => {
    if (!renameTarget) return
    const nextTitle = renameValue.trim()
    if (!nextTitle || renameBusy) return
    if (nextTitle === assetTitle(renameTarget)) {
      setRenameTarget(null)
      return
    }
    setRenameBusy(true)
    try {
      const res = await apiFetch(
        `/api/v1/personas/${id}/assets/${renameTarget.id}`,
        { method: "PUT", body: { title: nextTitle } }
      )
      if (res.ok) {
        setRenameTarget(null)
        fetchData()
      }
    } finally {
      setRenameBusy(false)
    }
  }

  const handleDeleteMaterial = async () => {
    if (!deleteTarget || deleteBusy) return
    setDeleteBusy(true)
    try {
      const res = await apiFetch(`/api/v1/personas/${id}/assets/${deleteTarget.id}`, {
        method: "DELETE",
        toast: t("personaDetail.msgDeleted"),
      })
      if (res.ok) {
        setDeleteTarget(null)
        fetchData()
      }
    } finally {
      setDeleteBusy(false)
    }
  }

  if (loading && !persona) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-muted-foreground">{t("common.loading")}</p>
      </div>
    )
  }

  if (!persona) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <p className="text-muted-foreground">{t("personaDetail.notFound")}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col p-6 md:p-8">
      {/* Header + tab bar hold a constant 4xl column; each tab's content sets
          its own width (skin editor breathes to 6xl) so page chrome never
          jumps sideways on tab switch. */}
      <div className="mx-auto w-full max-w-4xl">
        <div className="mb-6 flex items-center gap-3">
          <Button variant="ghost" size="icon" nativeButton={false} render={<Link to="/personas" />}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{persona.name}</h1>
            {persona.title && (
              <p className="truncate text-sm text-muted-foreground">{persona.title}</p>
            )}
          </div>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="flex-1">
        <div className="mx-auto w-full max-w-4xl">
          <TabsList className="mb-6">
            <TabsTrigger value="persona">{t("personaDetail.tabPersona")}</TabsTrigger>
            <TabsTrigger value="materials">
              {t("personaDetail.tabMaterials", { count: materials.length })}
            </TabsTrigger>
            <TabsTrigger value="skin">{t("personaDetail.tabSkin")}</TabsTrigger>
          </TabsList>
        </div>

        <div className="mx-auto w-full max-w-4xl">
          <TabsContent value="persona">
            <Card className="shadow-lg">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Fingerprint className="h-4 w-4" />
                    {t("personaDetail.personaTitle")}
                  </CardTitle>
                  <CardDescription>{t("personaDetail.personaDesc")}</CardDescription>
                </div>
                <Button
                  onClick={handleGeneratePersona}
                  disabled={generating || materials.length === 0}
                >
                  <Wand2 className="mr-2 h-4 w-4" />
                  {generating ? t("personaDetail.generating") : t("personaDetail.generate")}
                </Button>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleUpdatePersona} className="space-y-6">
                  <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="tone">{t("personaDetail.tone")}</Label>
                      <Select
                        value={emotionalTone}
                        onValueChange={(v) => setEmotionalTone(v as Persona["emotional_tone"])}
                      >
                        <SelectTrigger id="tone">
                          <SelectValue>
                            {(value: string) => t(`personaDetail.tones.${value}`)}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {(["rational", "passionate", "gentle", "sharp", "humorous"] as const).map(
                            (tName) => (
                              <SelectItem key={tName} value={tName}>
                                {t(`personaDetail.tones.${tName}`)}
                              </SelectItem>
                            )
                          )}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="sentence_style">{t("personaDetail.sentenceStyle")}</Label>
                      <Input
                        id="sentence_style"
                        value={sentenceStyle}
                        onChange={(e) => setSentenceStyle(e.target.value)}
                      />
                    </div>
                  </div>

                  {([
                    { key: "core_values", value: coreValues, setter: setCoreValues, rows: 4 },
                    { key: "favorite_metaphors", value: favoriteMetaphors, setter: setFavoriteMetaphors, rows: 3 },
                    { key: "typical_hooks", value: typicalHooks, setter: setTypicalHooks, rows: 4 },
                    { key: "avoid_words", value: avoidWords, setter: setAvoidWords, rows: 3 },
                  ] as const).map((item) => {
                    const label = t(`personaDetail.fields.${item.key}` as const)
                    return (
                      <div key={item.key} className="space-y-2">
                        <Label>{label}</Label>
                        <Textarea
                          value={item.value}
                          onChange={(e) => item.setter(e.target.value)}
                          rows={item.rows}
                          placeholder={t("personaDetail.fieldPlaceholder", { label })}
                        />
                      </div>
                    )
                  })}

                  <div className="space-y-2">
                    <CardTitle className="text-base">{t("personaDetail.contentStrategyTitle")}</CardTitle>
                    <CardDescription className="text-xs">
                      {t("personaDetail.contentStrategyDesc")}
                    </CardDescription>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="audience">{t("personaDetail.audience")}</Label>
                    <Input
                      id="audience"
                      value={audience}
                      onChange={(e) => setAudience(e.target.value)}
                      placeholder={t("personaDetail.audiencePlaceholder")}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="cta">{t("personaDetail.cta")}</Label>
                    <Input
                      id="cta"
                      value={cta}
                      onChange={(e) => setCta(e.target.value)}
                      placeholder={t("personaDetail.ctaPlaceholder")}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="guidelines">{t("personaDetail.guidelines")}</Label>
                    <Textarea
                      id="guidelines"
                      value={guidelines}
                      onChange={(e) => setGuidelines(e.target.value)}
                      rows={4}
                      placeholder={t("personaDetail.guidelinesPlaceholder")}
                    />
                  </div>

                  <div className="flex justify-end">
                    <Button type="submit" disabled={saving}>
                      <Save className="mr-2 h-4 w-4" />
                      {saving ? t("common.saving") : t("personaDetail.saveChanges")}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <div className="mt-6">
              <VoiceSection
                persona={persona}
                onSaved={(voice) => setPersona((p) => (p ? { ...p, voice } : p))}
              />
            </div>
          </TabsContent>

          <TabsContent value="materials">
            <Card className="shadow-lg">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>{t("personaDetail.pastMaterials")}</CardTitle>
                  <CardDescription>{t("personaDetail.pastMaterialsDesc")}</CardDescription>
                </div>
                <Button onClick={() => fileRef.current?.click()} disabled={uploading}>
                  <Upload className="mr-2 h-4 w-4" />
                  {uploading ? t("personaDetail.uploading") : t("common.upload")}
                </Button>
                <input
                  ref={fileRef}
                  type="file"
                  className="hidden"
                  accept=".txt,.md,.pdf"
                  onChange={handleFileUpload}
                />
              </CardHeader>
              <CardContent>
                {materials.length === 0 ? (
                  <div className="rounded-lg bg-muted py-12 text-center">
                    <FileText className="mx-auto mb-4 h-8 w-8 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">{t("personaDetail.noMaterials")}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {materials.map((asset) => (
                      <div
                        key={asset.id}
                        className="flex items-start justify-between gap-3 rounded-lg bg-muted p-4"
                      >
                        <div className="flex min-w-0 items-start gap-3">
                          <FileText className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
                          <div className="min-w-0">
                            <p className="truncate font-medium">{assetTitle(asset)}</p>
                            <p className="text-sm text-muted-foreground">
                              {asset.extracted_text
                                ? t("personaDetail.charsExtracted", {
                                    count: asset.extracted_text.length,
                                  })
                                : t("personaDetail.noText")}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {t("personaDetail.uploadedAt", {
                                date: new Date(asset.created_at).toLocaleString(),
                              })}
                            </p>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t("personaDetail.rename")}
                            onClick={() => openRename(asset)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t("common.delete")}
                            onClick={() => setDeleteTarget(asset)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </div>

        <div className="mx-auto w-full max-w-6xl">
          <TabsContent value="skin">
            <SkinEditor
              key={persona.id}
              personaId={persona.id}
              brand={persona.brand}
              onSaved={(brand) => setPersona((p) => (p ? { ...p, brand } : p))}
            />
          </TabsContent>
        </div>
      </Tabs>

      {/* Rename */}
      <Dialog
        open={renameTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRenameTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("personaDetail.renameTitle")}</DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleRename()
            }}
            placeholder={t("personaDetail.renamePlaceholder")}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button disabled={!renameValue.trim() || renameBusy} onClick={handleRename}>
              {renameBusy ? t("common.saving") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("personaDetail.deleteConfirm")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {deleteTarget && t("personaDetail.deleteDesc", { title: assetTitle(deleteTarget) })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={deleteBusy} onClick={handleDeleteMaterial}>
              {deleteBusy ? t("common.loading") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
