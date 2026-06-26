import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  FileText,
  Mic2,
  FolderKanban,
  Search,
  ExternalLink,
  Sparkles,
  Play,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Speaker {
  id: string
  name: string
  title: string | null
}

interface Project {
  id: string
  title: string
  status: string
  speaker_id: string
}

interface Asset {
  id: string
  type: string
  file_url: string | null
  extracted_text: string | null
  created_at: string
  speaker_id?: string
  project_id?: string
}

interface Clip {
  id: string
  hook: string
  duration: number
  created_at: string
  project_id: string
}

export const Route = createFileRoute("/library")({
  component: LibraryPage,
})

function LibraryPage() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState("all")
  const [query, setQuery] = useState("")
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [clips, setClips] = useState<Clip[]>([])

  useEffect(() => {
    const load = async () => {
      const [speakersRes, projectsRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/speakers`),
        fetch(`${API_URL}/api/v1/projects`),
      ])
      const speakersData: Speaker[] = await speakersRes.json()
      const projectsData: Project[] = await projectsRes.json()
      setSpeakers(speakersData)
      setProjects(projectsData)

      const allAssets: Asset[] = []
      const allClips: Clip[] = []

      await Promise.all(
        speakersData.map(async (s) => {
          const res = await fetch(`${API_URL}/api/v1/speakers/${s.id}/assets`)
          if (!res.ok) return
          const data: Asset[] = await res.json()
          allAssets.push(...data.map((a) => ({ ...a, speaker_id: s.id })))
        })
      )

      await Promise.all(
        projectsData.map(async (p) => {
          const [assetsRes, clipsRes] = await Promise.all([
            fetch(`${API_URL}/api/v1/projects/${p.id}/assets`),
            fetch(`${API_URL}/api/v1/projects/${p.id}/clips`),
          ])
          if (assetsRes.ok) {
            const data: Asset[] = await assetsRes.json()
            allAssets.push(...data.map((a) => ({ ...a, project_id: p.id })))
          }
          if (clipsRes.ok) {
            const data: Clip[] = await clipsRes.json()
            allClips.push(...data.map((c) => ({ ...c, project_id: p.id })))
          }
        })
      )

      setAssets(allAssets)
      setClips(allClips)
    }
    load()
  }, [])

  const speakerMap = Object.fromEntries(speakers.map((s) => [s.id, s]))
  const projectMap = Object.fromEntries(projects.map((p) => [p.id, p]))

  const filteredAssets = assets.filter((a) => {
    const fileName = a.file_url?.split("/").pop() || ""
    const text = a.extracted_text || ""
    return (
      fileName.toLowerCase().includes(query.toLowerCase()) ||
      text.toLowerCase().includes(query.toLowerCase())
    )
  })

  const speakerAssets = filteredAssets.filter((a) => a.speaker_id)
  const projectAssets = filteredAssets.filter((a) => a.project_id)

  const filteredClips = clips.filter((c) =>
    c.hook.toLowerCase().includes(query.toLowerCase())
  )

  const AssetList = ({ items }: { items: Asset[] }) => (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {items.map((asset) => {
        const source = asset.speaker_id
          ? {
              label: speakerMap[asset.speaker_id]?.name || "Speaker",
              to: "/speakers/$id" as const,
              params: { id: asset.speaker_id },
            }
          : asset.project_id
            ? {
                label: projectMap[asset.project_id]?.title || "Project",
                to: "/projects/$id" as const,
                params: { id: asset.project_id },
              }
            : null

        return (
          <Card key={asset.id} className="overflow-hidden">
            <CardHeader className="flex flex-row items-start gap-3 pb-3">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <FileText className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <CardTitle className="truncate text-sm font-medium">
                  {asset.file_url?.split("/").pop() || "Untitled"}
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  {asset.type} · {new Date(asset.created_at).toLocaleDateString()}
                </p>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="line-clamp-3 text-xs text-muted-foreground">
                {asset.extracted_text || "No extracted text"}
              </p>
              {source && (
                <div className="flex items-center justify-between">
                  <Badge variant="secondary" className="text-xs">
                    {source.label}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    render={<Link to={source.to} params={source.params} />}
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )

  return (
    <div className="flex min-h-screen flex-col p-8">
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("library.title")}</h1>
          <p className="text-muted-foreground">{t("library.subtitle")}</p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("library.searchPlaceholder")}
            className="pl-9"
          />
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="mb-6">
          <TabsTrigger value="all">
            {t("library.tabAll")}
            <Badge variant="secondary" className="ml-2 text-[10px]">
              {filteredAssets.length + filteredClips.length}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="speakers">
            <Mic2 className="mr-1.5 h-3.5 w-3.5" />
            {t("library.tabSpeakers")}
            <Badge variant="secondary" className="ml-2 text-[10px]">
              {speakerAssets.length}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="projects">
            <FolderKanban className="mr-1.5 h-3.5 w-3.5" />
            {t("library.tabProjects")}
            <Badge variant="secondary" className="ml-2 text-[10px]">
              {projectAssets.length}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="clips">
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            {t("library.tabClips")}
            <Badge variant="secondary" className="ml-2 text-[10px]">
              {filteredClips.length}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="space-y-6">
          {filteredAssets.length === 0 && filteredClips.length === 0 ? (
            <EmptyState />
          ) : (
            <>
              {filteredAssets.length > 0 && (
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold text-muted-foreground">{t("library.sectionAssets")}</h2>
                  <AssetList items={filteredAssets} />
                </section>
              )}
              {filteredClips.length > 0 && (
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold text-muted-foreground">{t("library.sectionClips")}</h2>
                  <ClipList clips={filteredClips} />
                </section>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="speakers">
          {speakerAssets.length === 0 ? <EmptyState /> : <AssetList items={speakerAssets} />}
        </TabsContent>

        <TabsContent value="projects">
          {projectAssets.length === 0 ? <EmptyState /> : <AssetList items={projectAssets} />}
        </TabsContent>

        <TabsContent value="clips">
          {filteredClips.length === 0 ? <EmptyState /> : <ClipList clips={filteredClips} />}
        </TabsContent>
      </Tabs>
    </div>
  )
}

function ClipList({ clips }: { clips: Clip[] }) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {clips.map((clip) => (
        <Card key={clip.id} className="overflow-hidden">
          <CardHeader className="flex flex-row items-start gap-3 pb-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Play className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <CardTitle className="truncate text-sm font-medium">{clip.hook}</CardTitle>
              <p className="text-xs text-muted-foreground">
                {clip.duration}s · {new Date(clip.created_at).toLocaleDateString()}
              </p>
            </div>
          </CardHeader>
          <CardContent>
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              render={<Link to="/projects/$id" params={{ id: clip.project_id }} />}
            >
              {t("library.viewProject")}
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function EmptyState() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed py-20">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
        <FileText className="h-6 w-6 text-primary" />
      </div>
      <p className="text-muted-foreground">{t("library.emptyTitle")}</p>
      <p className="text-xs text-muted-foreground">{t("library.emptyDesc")}</p>
    </div>
  )
}
