import { Link, createFileRoute } from "@tanstack/react-router"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  FileText,
  Search,
  Play,
  Quote,
  Newspaper,
  Image as ImageIcon,
  Download,
  ExternalLink,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { apiFetch, toAbsoluteUrl } from "@/lib/api"

type LibraryType = "upload" | "clip" | "post" | "quotes" | "article" | "carousel"

interface LibraryItem {
  id: string
  type: LibraryType
  title: string
  project_id: string
  created_at: string
  preview: string | null
  download_url: string | null
}

type FilterTab = "all" | LibraryType

const TABS: { key: FilterTab; labelKey: string; icon: typeof FileText }[] = [
  { key: "all", labelKey: "library.tabs.all", icon: FileText },
  { key: "upload", labelKey: "library.tabs.uploads", icon: FileText },
  { key: "clip", labelKey: "library.tabs.clips", icon: Play },
  { key: "post", labelKey: "library.tabs.post", icon: FileText },
  { key: "quotes", labelKey: "library.tabs.quotes", icon: Quote },
  { key: "article", labelKey: "library.tabs.article", icon: Newspaper },
  { key: "carousel", labelKey: "library.tabs.carousel", icon: ImageIcon },
]

const TYPE_ICONS: Record<LibraryType, typeof FileText> = {
  upload: FileText,
  clip: Play,
  post: FileText,
  quotes: Quote,
  article: Newspaper,
  carousel: ImageIcon,
}

export const Route = createFileRoute("/library")({
  component: LibraryPage,
})

function LibraryPage() {
  const { t } = useTranslation()
  const [items, setItems] = useState<LibraryItem[]>([])
  const [activeTab, setActiveTab] = useState<FilterTab>("all")
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiFetch("/api/v1/library")
        if (!res.ok) throw new Error("Failed to load library")
        setItems(await res.json())
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const filtered = useMemo(() => {
    let list = items
    if (activeTab !== "all") {
      list = list.filter((i) => i.type === activeTab)
    }
    if (query.trim()) {
      const q = query.toLowerCase()
      list = list.filter(
        (i) =>
          i.title.toLowerCase().includes(q) ||
          (i.preview?.toLowerCase().includes(q) ?? false)
      )
    }
    return list
  }, [items, activeTab, query])

  const groups = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    const result: { label: string; items: LibraryItem[] }[] = [
      { label: t("library.groups.today"), items: [] },
      { label: t("library.groups.yesterday"), items: [] },
      { label: t("library.groups.earlier"), items: [] },
    ]

    for (const item of filtered) {
      const d = new Date(item.created_at)
      d.setHours(0, 0, 0, 0)
      if (d.getTime() === today.getTime()) {
        result[0].items.push(item)
      } else if (d.getTime() === yesterday.getTime()) {
        result[1].items.push(item)
      } else {
        result[2].items.push(item)
      }
    }

    return result.filter((g) => g.items.length > 0)
  }, [filtered, t])

  const counts = useMemo(() => {
    const c: Record<FilterTab, number> = {
      all: items.length,
      upload: 0,
      clip: 0,
      post: 0,
      quotes: 0,
      article: 0,
      carousel: 0,
    }
    for (const item of items) {
      c[item.type]++
    }
    return c
  }, [items])

  return (
    <div className="flex min-h-screen flex-col p-6 md:p-8">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {t("library.title")}
            </h1>
            <p className="text-sm text-muted-foreground">{t("library.subtitle")}</p>
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

        <div className="mb-6 flex flex-wrap items-center gap-2">
          {TABS.map((tab) => {
            const Icon = tab.icon
            const active = activeTab === tab.key
            return (
              <Button
                key={tab.key}
                variant={active ? "secondary" : "outline"}
                size="sm"
                onClick={() => setActiveTab(tab.key)}
                className="h-8 gap-1.5"
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{t(tab.labelKey)}</span>
                <Badge variant={active ? "default" : "secondary"} className="ml-1 text-[10px]">
                  {counts[tab.key]}
                </Badge>
              </Button>
            )
          })}
        </div>

        {loading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {t("common.loading")}
          </p>
        ) : groups.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-8">
            {groups.map((group) => (
              <section key={group.label} className="space-y-3">
                <h2 className="text-sm font-medium text-muted-foreground">
                  {group.label}
                </h2>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {group.items.map((item) => (
                    <LibraryCard key={item.id} item={item} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function LibraryCard({ item }: { item: LibraryItem }) {
  const { t } = useTranslation()
  const Icon = TYPE_ICONS[item.type]

  const handleDownload = () => {
    const url = toAbsoluteUrl(item.download_url)
    if (!url) return
    const a = document.createElement("a")
    a.href = url
    a.download = item.title
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return (
    <Card className="flex items-center gap-3 p-3 ring-1 ring-border shadow-sm transition-colors hover:bg-accent">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{item.title}</p>
        <p className="text-xs text-muted-foreground">
          {new Date(item.created_at).toLocaleString()}
        </p>
        {item.preview && (
          <p className="line-clamp-1 text-xs text-muted-foreground">
            {item.preview}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {item.download_url && (
          <Button variant="ghost" size="icon-sm" onClick={handleDownload} title={t("common.download")}>
            <Download className="h-4 w-4" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          nativeButton={false}
          render={<Link to="/projects/$id" params={{ id: item.project_id }} />}
          title={t("library.viewProject")}
        >
          <ExternalLink className="h-4 w-4" />
        </Button>
      </div>
    </Card>
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
