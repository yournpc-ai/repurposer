import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { ArrowLeft, Wand2, Save, Trash2, FileText, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription } from "@/components/ui/alert"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Speaker {
  id: string
  name: string
  title: string | null
  language: string
  avatar_url: string | null
  persona: SpeakerPersona | null
  created_at: string
  updated_at: string | null
}

interface SpeakerPersona {
  core_values: string[]
  favorite_metaphors: string[]
  sentence_style: string
  emotional_tone: "rational" | "passionate" | "gentle" | "sharp" | "humorous"
  typical_hooks: string[]
  avoid_words: string[]
}

interface Asset {
  id: string
  type: string
  file_url: string | null
  extracted_text: string | null
  processed_at: string | null
  created_at: string
}

export const Route = createFileRoute("/speakers/$id")({
  component: SpeakerDetailPage,
})

function SpeakerDetailPage() {
  const { id } = Route.useParams()
  const { t } = useTranslation()

  const [speaker, setSpeaker] = useState<Speaker | null>(null)
  const [materials, setMaterials] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")

  const [name, setName] = useState("")
  const [title, setTitle] = useState("")
  const [persona, setPersona] = useState<SpeakerPersona | null>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [speakerRes, materialsRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/speakers/${id}`),
        fetch(`${API_URL}/api/v1/speakers/${id}/assets`),
      ])
      if (!speakerRes.ok) throw new Error("Speaker not found")
      const speakerData = await speakerRes.json()
      const materialsData = await materialsRes.json()
      setSpeaker(speakerData)
      setMaterials(materialsData)
      setName(speakerData.name)
      setTitle(speakerData.title || "")
      setPersona(speakerData.persona)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load speaker")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [id])

  const handleUpdateSpeaker = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError("")
    setMessage("")
    try {
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, title, persona }),
      })
      if (!res.ok) throw new Error("Failed to update speaker")
      setMessage(t("speakerDetail.msgUpdated"))
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed")
    } finally {
      setSaving(false)
    }
  }

  const handleGeneratePersona = async () => {
    setGenerating(true)
    setError("")
    setMessage("")
    try {
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}/persona/generate`, {
        method: "POST",
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || "Generation failed")
      setPersona(data)
      setMessage(t("speakerDetail.msgGenerated"))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed")
    } finally {
      setGenerating(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError("")
    setMessage("")
    try {
      const formData = new FormData()
      formData.append("file", file)
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}/assets`, {
        method: "POST",
        body: formData,
      })
      if (!res.ok) throw new Error("Upload failed")
      setMessage(t("speakerDetail.msgUploaded"))
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setUploading(false)
      e.target.value = ""
    }
  }

  const handleDeleteMaterial = async (assetId: string) => {
    if (!confirm(t("speakerDetail.deleteConfirm"))) return
    try {
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}/assets/${assetId}`, {
        method: "DELETE",
      })
      if (!res.ok) throw new Error("Delete failed")
      setMessage(t("speakerDetail.msgDeleted"))
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed")
    }
  }

  const updatePersonaField = <K extends keyof SpeakerPersona>(
    field: K,
    value: SpeakerPersona[K]
  ) => {
    setPersona((prev) => (prev ? { ...prev, [field]: value } : null))
  }

  const updateListField = (field: keyof SpeakerPersona, value: string) => {
    updatePersonaField(field, value.split("\n").filter((s) => s.trim()))
  }

  if (loading && !speaker) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="text-muted-foreground">{t("common.loading")}</div>
      </div>
    )
  }

  if (!speaker) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <Alert variant="destructive">
          <AlertDescription>{error || t("speakerDetail.notFound")}</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" size="icon" render={<Link to="/speakers" />}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{speaker.name}</h1>
          {speaker.title && <p className="text-muted-foreground">{speaker.title}</p>}
        </div>
      </div>

      {(message || error) && (
        <Alert variant={error ? "destructive" : "default"} className="mb-6">
          <AlertDescription>{error || message}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="persona" className="flex-1">
        <TabsList className="mb-6">
          <TabsTrigger value="persona">{t("speakerDetail.tabPersona")}</TabsTrigger>
          <TabsTrigger value="materials">
            {t("speakerDetail.tabMaterials", { count: materials.length })}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="persona" className="space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4" />
                  {t("speakerDetail.personaTitle")}
                </CardTitle>
                <CardDescription>{t("speakerDetail.personaDesc")}</CardDescription>
              </div>
              <Button
                onClick={handleGeneratePersona}
                disabled={generating || materials.length === 0}
              >
                <Wand2 className="mr-2 h-4 w-4" />
                {generating ? t("speakerDetail.generating") : t("speakerDetail.generate")}
              </Button>
            </CardHeader>
            <CardContent>
              {persona ? (
                <form onSubmit={handleUpdateSpeaker} className="space-y-6">
                  <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="tone">{t("speakerDetail.tone")}</Label>
                      <Select
                        value={persona.emotional_tone}
                        onValueChange={(v) =>
                          updatePersonaField(
                            "emotional_tone",
                            v as SpeakerPersona["emotional_tone"]
                          )
                        }
                      >
                        <SelectTrigger id="tone">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(["rational", "passionate", "gentle", "sharp", "humorous"] as const).map((tName) => (
                            <SelectItem key={tName} value={tName}>
                              {t(`speakerDetail.tones.${tName}`)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="sentence_style">{t("speakerDetail.sentenceStyle")}</Label>
                      <Input
                        id="sentence_style"
                        value={persona.sentence_style}
                        onChange={(e) => updatePersonaField("sentence_style", e.target.value)}
                      />
                    </div>
                  </div>

                  <Separator />

                  {([
                    { key: "core_values", rows: 4 },
                    { key: "favorite_metaphors", rows: 3 },
                    { key: "typical_hooks", rows: 4 },
                    { key: "avoid_words", rows: 3 },
                  ] as const).map((item) => {
                    const label = t(`speakerDetail.fields.${item.key}` as const)
                    return (
                      <div key={item.key} className="space-y-2">
                        <Label>{label}</Label>
                        <Textarea
                          value={(persona[item.key as keyof SpeakerPersona] as string[]).join("\n")}
                          onChange={(e) => updateListField(item.key as keyof SpeakerPersona, e.target.value)}
                          rows={item.rows}
                          placeholder={t("speakerDetail.fieldPlaceholder", { label })}
                        />
                      </div>
                    )
                  })}

                  <div className="flex justify-end">
                    <Button type="submit" disabled={saving}>
                      <Save className="mr-2 h-4 w-4" />
                      {saving ? t("common.saving") : t("speakerDetail.saveChanges")}
                    </Button>
                  </div>
                </form>
              ) : (
                <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16">
                  <Sparkles className="mb-4 h-8 w-8 text-muted-foreground" />
                  <p className="text-muted-foreground">{t("speakerDetail.emptyPersona")}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="materials" className="space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>{t("speakerDetail.pastMaterials")}</CardTitle>
                <CardDescription>{t("speakerDetail.pastMaterialsDesc")}</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  type="file"
                  onChange={handleFileUpload}
                  disabled={uploading}
                  accept=".txt,.md,.pdf"
                  className="w-auto"
                />
              </div>
            </CardHeader>
            <CardContent>
              {materials.length === 0 ? (
                <div className="rounded-lg border border-dashed py-12 text-center">
                  <FileText className="mx-auto mb-4 h-8 w-8 text-muted-foreground" />
                  <p className="text-muted-foreground">{t("speakerDetail.noMaterials")}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {materials.map((asset) => (
                    <div
                      key={asset.id}
                      className="flex items-start justify-between rounded-lg border p-4"
                    >
                      <div className="flex items-start gap-3 min-w-0">
                        <FileText className="mt-0.5 h-5 w-5 text-muted-foreground" />
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {asset.file_url?.split("/").pop() || t("common.untitled")}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {asset.extracted_text
                              ? t("speakerDetail.charsExtracted", { count: asset.extracted_text.length })
                              : t("speakerDetail.noText")}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {t("speakerDetail.uploadedAt", { date: new Date(asset.created_at).toLocaleString() })}
                          </p>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteMaterial(asset.id)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
