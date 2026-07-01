import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { FolderKanban, Plus, Calendar, MoreHorizontal, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Project {
  id: string
  title: string
  event_name: string | null
  status: string
  language: string
  speaker_id: string
  created_at: string
}

interface Speaker {
  id: string
  name: string
}

export const Route = createFileRoute("/projects")({
  component: ProjectsPage,
})

function ProjectsPage() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [eventName, setEventName] = useState("")
  const [speakerId, setSpeakerId] = useState("")
  const [language, setLanguage] = useState("zh")
  const [loading, setLoading] = useState(false)

  const fetchData = async () => {
    const [projectsRes, speakersRes] = await Promise.all([
      fetch(`${API_URL}/api/v1/projects`),
      fetch(`${API_URL}/api/v1/speakers`),
    ])
    setProjects(await projectsRes.json())
    setSpeakers(await speakersRes.json())
  }

  useEffect(() => {
    fetchData()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!speakerId) return
    setLoading(true)
    await fetch(`${API_URL}/api/v1/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        event_name: eventName,
        language,
        speaker_id: speakerId,
      }),
    })
    setTitle("")
    setEventName("")
    setSpeakerId("")
    setLanguage("zh")
    setOpen(false)
    setLoading(false)
    fetchData()
  }

  const handleDelete = async (id: string) => {
    if (!confirm(t("projects.deleteConfirm"))) return
    await fetch(`${API_URL}/api/v1/projects/${id}`, { method: "DELETE" })
    fetchData()
  }

  const statusVariant = (status: string) => {
    switch (status.toLowerCase()) {
      case "done":
      case "completed":
        return "default"
      case "processing":
      case "generating":
        return "secondary"
      case "error":
      case "failed":
        return "destructive"
      default:
        return "outline"
    }
  }

  return (
    <div className="flex min-h-screen flex-col p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("projects.title")}</h1>
          <p className="text-muted-foreground">{t("projects.subtitle")}</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger
            render={
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                {t("projects.new")}
              </Button>
            }
          />
          <DialogContent className="sm:max-w-md">
            <form onSubmit={handleSubmit}>
              <DialogHeader>
                <DialogTitle>{t("projects.dialogTitle")}</DialogTitle>
                <DialogDescription>{t("projects.dialogDesc")}</DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="title">{t("projects.labelTitle")}</Label>
                  <Input
                    id="title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder={t("projects.titlePlaceholder")}
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="event">{t("projects.labelEvent")}</Label>
                  <Input
                    id="event"
                    value={eventName}
                    onChange={(e) => setEventName(e.target.value)}
                    placeholder={t("projects.eventPlaceholder")}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="speaker">{t("projects.labelSpeaker")}</Label>
                  <Select value={speakerId} onValueChange={(v) => setSpeakerId(v ?? "")} required>
                    <SelectTrigger id="speaker">
                      <SelectValue placeholder={t("projects.speakerPlaceholder")} />
                    </SelectTrigger>
                    <SelectContent>
                      {speakers.map((speaker) => (
                        <SelectItem key={speaker.id} value={speaker.id}>
                          {speaker.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="language">{t("projects.labelLanguage")}</Label>
                  <Select value={language} onValueChange={(v) => setLanguage(v ?? "zh")}>
                    <SelectTrigger id="language">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="zh">{t("projects.langZh")}</SelectItem>
                      <SelectItem value="en">{t("projects.langEn")}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button type="submit" disabled={loading || !speakerId}>
                  {loading ? t("common.creating") : t("common.create")}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {projects.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
              <FolderKanban className="h-6 w-6 text-primary" />
            </div>
            <CardTitle className="mb-2">{t("projects.emptyTitle")}</CardTitle>
            <CardDescription className="mb-6 text-center">
              {t("projects.emptyDesc")}
            </CardDescription>
            <Button onClick={() => setOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t("projects.new")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Card key={project.id} className="transition-colors hover:bg-accent/50">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                      <FolderKanban className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">
                        <Link to="/projects/$id" params={{ id: project.id }} className="hover:underline">
                          {project.title}
                        </Link>
                      </CardTitle>
                      <CardDescription>
                        {project.event_name || t("projects.noEvent")}
                      </CardDescription>
                    </div>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      }
                    />
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        className="text-destructive focus:text-destructive"
                        onClick={() => handleDelete(project.id)}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {t("common.delete")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge variant={statusVariant(project.status)}>{project.status}</Badge>
                  <Badge variant="outline">{t(`languages.${project.language}`)}</Badge>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  {new Date(project.created_at).toLocaleDateString()}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
