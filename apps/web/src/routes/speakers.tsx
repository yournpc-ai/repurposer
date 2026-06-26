import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Mic2, Plus, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Speaker {
  id: string
  name: string
  title: string | null
  language: string
  created_at: string
}

export const Route = createFileRoute("/speakers")({
  component: SpeakersPage,
})

function SpeakersPage() {
  const { t } = useTranslation()
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [name, setName] = useState("")
  const [title, setTitle] = useState("")
  const [open, setOpen] = useState(false)

  const fetchSpeakers = async () => {
    const res = await fetch(`${API_URL}/api/v1/speakers`)
    setSpeakers(await res.json())
  }

  useEffect(() => {
    fetchSpeakers()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await fetch(`${API_URL}/api/v1/speakers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, title, language: "zh" }),
    })
    setName("")
    setTitle("")
    setOpen(false)
    fetchSpeakers()
  }

  return (
    <div className="flex min-h-screen flex-col p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("speakers.title")}</h1>
          <p className="text-muted-foreground">{t("speakers.subtitle")}</p>
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
              </div>
              <DialogFooter>
                <Button type="submit">{t("common.create")}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {speakers.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
              <Mic2 className="h-6 w-6 text-primary" />
            </div>
            <CardTitle className="mb-2">{t("speakers.emptyTitle")}</CardTitle>
            <CardDescription className="mb-6 text-center">
              {t("speakers.emptyDesc")}
            </CardDescription>
            <Button onClick={() => setOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t("speakers.new")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {speakers.map((speaker) => (
            <Link key={speaker.id} to="/speakers/$id" params={{ id: speaker.id }}>
              <Card className="transition-colors hover:bg-accent/50">
                <CardHeader className="flex flex-row items-center gap-4">
                  <Avatar className="h-12 w-12">
                    <AvatarFallback className="bg-primary/10 text-primary">
                      {speaker.name.slice(0, 2)}
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <CardTitle className="text-base">{speaker.name}</CardTitle>
                    <CardDescription>{speaker.title || t("speakers.noTitle")}</CardDescription>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">{t("speakers.language", { lang: speaker.language })}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
