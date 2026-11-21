import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Mic2, Plus } from "lucide-react"

import { Button } from "@/components/ui/button-clean"
import { EmptyState } from "@/components/ui/empty-state-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { Select } from "@/components/ui/select-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { Avatar } from "@/components/ui/avatar-clean"
import { Badge } from "@/components/ui/badge-clean"
import { apiFetch } from "@/lib/api"
import { formatRelativeTime } from "@/lib/utils"

interface Persona {
  id: string
  name: string
  title: string | null
  language: string
  emotional_tone: "rational" | "passionate" | "gentle" | "sharp" | "humorous"
  created_at: string
}

export const Route = createFileRoute("/_app/personas/")({
  component: PersonasPage,
})

function PersonasPage() {
  const { t, i18n } = useTranslation()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [name, setName] = useState("")
  const [title, setTitle] = useState("")
  const [language, setLanguage] = useState("en")
  const [open, setOpen] = useState(false)

  const fetchPersonas = async () => {
    const res = await apiFetch("/api/v1/personas")
    setPersonas(await res.json())
  }

  useEffect(() => {
    fetchPersonas()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await apiFetch("/api/v1/personas", {
      method: "POST",
      body: { name, title, language },
    })
    setName("")
    setTitle("")
    setLanguage("en")
    setOpen(false)
    fetchPersonas()
  }

  return (
    <div className="flex flex-1 flex-col p-6 md:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
        <div className="mb-8 flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              {t("personas.title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t("personas.subtitle")}
            </p>
          </div>
          <Dialog open={open} onOpenChange={setOpen} closeLabel={t("common.close")}
            title={t("personas.dialogTitle")} description={t("personas.dialogDesc")}
            trigger={<Button size="sm" icon={<Plus size={16} />}>{t("personas.new")}</Button>}>
              <form onSubmit={handleSubmit}>
                <div className="grid gap-4 py-4">
                  <div className="grid gap-2">
                    <label htmlFor="name">{t("personas.labelName")}</label>
                    <TextField id="name" value={name} onChange={(e) => setName(e.target.value)} required />
                  </div>
                  <div className="grid gap-2">
                    <label htmlFor="title">{t("personas.labelTitle")}</label>
                    <TextField id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
                  </div>
                  <div className="grid gap-2">
                    <label htmlFor="language">{t("common.language")}</label>
                    <Select id="language" aria-label={t("common.language")} value={language} onChange={setLanguage}
                      options={["en", "fr", "de", "es", "it", "zh"].map((value) => ({ value, label: t(`languages.${value}`) }))} />
                  </div>
                </div>
                <div className="mt-4 flex justify-end gap-2">
                  <Button type="submit" size="sm">{t("common.create")}</Button>
                </div>
              </form>

          </Dialog>
        </div>

        {personas.length === 0 ? (
          <EmptyState
            bare tall icon={<Mic2 />}
            title={t("personas.emptyTitle")}
            text={t("personas.emptyDesc")}
            action={
              <Button size="sm" onClick={() => setOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                {t("personas.new")}
              </Button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {personas.map((persona) => (
              <Link
                key={persona.id}
                to="/personas/$id"
                params={{ id: persona.id }}
                className="group rounded-xl bg-card p-5 border border-subtle transition-colors hover:bg-accent"
              >
                <div className="flex items-center gap-3">
                  <Avatar name={persona.name} size={40} />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{persona.name}</p>
                    {persona.title && (
                      <p className="truncate text-sm text-muted-foreground">
                        {persona.title}
                      </p>
                    )}
                  </div>
                </div>
                <div className="mt-4 flex items-center gap-2">
                  <Badge tone="neutral" className="rounded-md">
                    {t(`personaDetail.tones.${persona.emotional_tone}`)}
                  </Badge>
                  <Badge
                    tone="neutral"
                    className="rounded-md uppercase"
                  >
                    {persona.language}
                  </Badge>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {formatRelativeTime(persona.created_at, i18n.language)}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
