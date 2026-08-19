import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Mic2, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
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
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger
              render={
                <Button>
                  <Plus className="mr-2 h-4 w-4" />
                  {t("personas.new")}
                </Button>
              }
            />
            <DialogContent className="sm:max-w-md">
              <form onSubmit={handleSubmit}>
                <DialogHeader>
                  <DialogTitle>{t("personas.dialogTitle")}</DialogTitle>
                  <DialogDescription>{t("personas.dialogDesc")} </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid gap-2">
                    <Label htmlFor="name">{t("personas.labelName")}</Label>
                    <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="title">{t("personas.labelTitle")}</Label>
                    <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="language">{t("common.language")}</Label>
                    <Select value={language} onValueChange={(v) => setLanguage(v || "en")}>
                      <SelectTrigger id="language">
                        <SelectValue>
                          {(value: string) => t(`languages.${value}`)}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {(["en", "fr", "de", "es", "it", "zh"] as const).map((lang) => (
                          <SelectItem key={lang} value={lang}>
                            {t(`languages.${lang}`)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter>
                  <Button type="submit">{t("common.create")}</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {personas.length === 0 ? (
          <EmptyState
            icon={Mic2}
            title={t("personas.emptyTitle")}
            description={t("personas.emptyDesc")}
            action={
              <Button onClick={() => setOpen(true)}>
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
                className="group rounded-xl bg-card p-5 shadow-sm transition-all hover:shadow-md dark:hover:bg-muted"
              >
                <div className="flex items-center gap-3">
                  <Avatar className="h-11 w-11">
                    <AvatarFallback className="bg-primary/10 text-sm font-medium text-primary">
                      {persona.name.charAt(0).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
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
                  <Badge variant="secondary" className="rounded-md">
                    {t(`personaDetail.tones.${persona.emotional_tone}`)}
                  </Badge>
                  <Badge
                    variant="secondary"
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
