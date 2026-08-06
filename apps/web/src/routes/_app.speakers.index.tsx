import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Mic2, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
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

interface Speaker {
  id: string
  name: string
  title: string | null
  language: string
  emotional_tone: "rational" | "passionate" | "gentle" | "sharp" | "humorous"
  created_at: string
}

export const Route = createFileRoute("/_app/speakers/")({
  component: SpeakersPage,
})

function SpeakersPage() {
  const { t, i18n } = useTranslation()
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [name, setName] = useState("")
  const [title, setTitle] = useState("")
  const [language, setLanguage] = useState("en")
  const [open, setOpen] = useState(false)

  const fetchSpeakers = async () => {
    const res = await apiFetch("/api/v1/speakers")
    setSpeakers(await res.json())
  }

  useEffect(() => {
    fetchSpeakers()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await apiFetch("/api/v1/speakers", {
      method: "POST",
      body: { name, title, language },
    })
    setName("")
    setTitle("")
    setLanguage("en")
    setOpen(false)
    fetchSpeakers()
  }

  return (
    <div className="flex flex-1 flex-col p-6 md:p-8">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-8 flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              {t("speakers.title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t("speakers.subtitle")}
            </p>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger
              render={
                <Button>
                  <Plus className="mr-2 h-4 w-4" />
                  {t("speakers.new")}
                </Button>
              }
            />
            <DialogContent className="sm:max-w-md">
              <form onSubmit={handleSubmit}>
                <DialogHeader>
                  <DialogTitle>{t("speakers.dialogTitle")}</DialogTitle>
                  <DialogDescription>{t("speakers.dialogDesc")} </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid gap-2">
                    <Label htmlFor="name">{t("speakers.labelName")}</Label>
                    <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="title">{t("speakers.labelTitle")}</Label>
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

        {speakers.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg bg-muted py-20 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
              <Mic2 className="h-6 w-6 text-primary" />
            </div>
            <p className="font-medium">{t("speakers.emptyTitle")}</p>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {t("speakers.emptyDesc")}
            </p>
            <Button className="mt-6" onClick={() => setOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t("speakers.new")}
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {speakers.map((speaker) => (
              <Link
                key={speaker.id}
                to="/speakers/$id"
                params={{ id: speaker.id }}
                className="group rounded-xl bg-card p-5 shadow-sm transition-all hover:shadow-md dark:hover:bg-muted"
              >
                <div className="flex items-center gap-3">
                  <Avatar className="h-11 w-11">
                    <AvatarFallback className="bg-primary/10 text-sm font-medium text-primary">
                      {speaker.name.charAt(0).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{speaker.name}</p>
                    {speaker.title && (
                      <p className="truncate text-sm text-muted-foreground">
                        {speaker.title}
                      </p>
                    )}
                  </div>
                </div>
                <div className="mt-4 flex items-center gap-2">
                  <Badge variant="secondary" className="rounded-md">
                    {t(`speakerDetail.tones.${speaker.emotional_tone}`)}
                  </Badge>
                  <Badge
                    variant="secondary"
                    className="rounded-md uppercase"
                  >
                    {speaker.language}
                  </Badge>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {formatRelativeTime(speaker.created_at, i18n.language)}
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
