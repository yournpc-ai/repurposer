"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import type { ChatMention } from "@/lib/mentions"
import {
  fetchProjectWorkbench,
  type WorkbenchData,
} from "@/lib/workbench"

export type WorkbenchTab = "player" | "inspector" | "slots" | "presets" | "sounds"

export type WorkbenchOpenTarget =
  | { tab: "player"; versionId?: string; outputId?: string }
  | { tab: "inspector"; assetId?: string; outputId?: string }
  | { tab: "slots"; skillVersionId?: string }

export interface WorkbenchContextValue {
  projectId: string
  workbench: WorkbenchData | null
  loading: boolean
  refresh: () => Promise<void>
  isOpen: boolean
  activeTab: WorkbenchTab
  selectedVersionId: string | null
  selectedOutputId: string | null
  selectedAssetId: string | null
  selectedSkillVersionId: string | null
  openWorkbench: (target?: WorkbenchOpenTarget) => void
  closeWorkbench: () => void
  toggleWorkbench: () => void
  setActiveTab: (tab: WorkbenchTab) => void
  setSelectedVersionId: (id: string | null) => void
  setSelectedOutputId: (id: string | null) => void
  setSelectedAssetId: (id: string | null) => void
  setSelectedSkillVersionId: (id: string | null) => void
  /** Register the active AgentThread composer mention-injection handler. */
  registerMentionHandler: (handler: ((mention: ChatMention) => void) | null) => void
  /** Inject a mention (+ optional region selection) into the active composer. */
  registerTextHandler: (handler: ((text: string) => void) | null) => void
  citeText: (text: string) => boolean
  citeMention: (mention: ChatMention) => boolean
}

const WorkbenchContext = createContext<WorkbenchContextValue | null>(null)

export function useOptionalWorkbench(): WorkbenchContextValue | null {
  return useContext(WorkbenchContext)
}

export function useWorkbench(): WorkbenchContextValue {
  const ctx = useContext(WorkbenchContext)
  if (!ctx) throw new Error("useWorkbench must be used inside WorkbenchProvider")
  return ctx
}

/** Parse internal Markdown artifact links (#workbench:version/<id>, etc.). */
export function parseWorkbenchHref(href: string | undefined | null): WorkbenchOpenTarget | null {
  if (!href) return null
  const trimmed = href.trim()
  const match = /^#workbench:(version|output|asset|skill)\/([^/?#\s]+)$/i.exec(trimmed)
  if (!match) return null
  const kind = match[1].toLowerCase()
  const id = decodeURIComponent(match[2])
  if (!id) return null
  switch (kind) {
    case "version":
      return { tab: "player", versionId: id }
    case "output":
      return { tab: "player", outputId: id }
    case "asset":
      return { tab: "inspector", assetId: id }
    case "skill":
      return { tab: "slots", skillVersionId: id }
    default:
      return null
  }
}

export function WorkbenchProvider({
  projectId,
  initialData = null,
  defaultOpen = false,
  onCiteMention,
  children,
}: {
  projectId: string
  initialData?: WorkbenchData | null
  defaultOpen?: boolean
  onCiteMention?: (mention: ChatMention) => void
  children: ReactNode
}) {
  const [workbench, setWorkbench] = useState<WorkbenchData | null>(initialData)
  const [loading, setLoading] = useState(initialData == null)
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const [activeTab, setActiveTab] = useState<WorkbenchTab>("player")
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [selectedOutputId, setSelectedOutputId] = useState<string | null>(null)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [selectedSkillVersionId, setSelectedSkillVersionId] = useState<string | null>(null)

  const mentionHandlerRef = useRef<((mention: ChatMention) => void) | null>(null)
  const textRef = useRef<((text: string) => void) | null>(null)
  const registerTextHandler = useCallback((handler: ((text: string) => void) | null) => { textRef.current = handler }, [])
  const citeText = useCallback((text: string) => {
    if (!textRef.current) return false
    textRef.current(text)
    return true
  }, [])
  const propCiteRef = useRef(onCiteMention)
  propCiteRef.current = onCiteMention

  const hydrateDefaults = useCallback((data: WorkbenchData) => {
    const latestVersion =
      data.compositions[0]?.current_version_id ??
      data.compositions[0]?.versions[0]?.version_id ??
      null
    setSelectedVersionId((prev) => {
      if (
        prev &&
        data.compositions.some((c) => c.versions.some((v) => v.version_id === prev))
      ) {
        return prev
      }
      return latestVersion
    })
    setSelectedOutputId((prev) => {
      if (prev && data.outputs.some((o) => o.id === prev)) return prev
      return data.outputs[0]?.id ?? null
    })
    setSelectedAssetId((prev) => {
      if (prev && data.assets.some((a) => a.id === prev)) return prev
      const visual = data.assets.find(
        (a) => a.file_url && (a.type === "image" || a.type === "video" || a.type === "web_page"),
      )
      return visual?.id ?? data.assets[0]?.id ?? null
    })
    setSelectedSkillVersionId((prev) => {
      const versionIds = data.skills
        .map((s) => (s.reference.kind === "external" ? s.reference.skill_version_id : null))
        .filter((id): id is string => Boolean(id))
      if (prev && versionIds.includes(prev)) return prev
      return versionIds[0] ?? null
    })
  }, [])

  const refresh = useCallback(async () => {
    try {
      const data = await fetchProjectWorkbench(projectId)
      setWorkbench(data)
      hydrateDefaults(data)
    } catch {
      // Best-effort refresh; keep previous projection visible
    } finally {
      setLoading(false)
    }
  }, [projectId, hydrateDefaults])

  useEffect(() => {
    if (initialData) {
      setWorkbench(initialData)
      hydrateDefaults(initialData)
      setLoading(false)
      return
    }
    setLoading(true)
    void refresh()
  }, [projectId, initialData, hydrateDefaults, refresh])

  // Poll every 3s ONLY while active_jobs.length > 0 (zero polling when idle).
  const hasActiveJobs = (workbench?.active_jobs.length ?? 0) > 0
  useEffect(() => {
    if (!hasActiveJobs) return
    const timer = window.setInterval(() => {
      void refresh()
    }, 3000)
    return () => window.clearInterval(timer)
  }, [hasActiveJobs, refresh])

  const openWorkbench = useCallback((target?: WorkbenchOpenTarget) => {
    setIsOpen(true)
    if (!target) return
    setActiveTab(target.tab)
    if (target.tab === "player") {
      if (target.versionId) setSelectedVersionId(target.versionId)
      if (target.outputId) setSelectedOutputId(target.outputId)
    } else if (target.tab === "inspector") {
      if (target.assetId) setSelectedAssetId(target.assetId)
      if (target.outputId) setSelectedOutputId(target.outputId)
    } else if (target.tab === "slots") {
      if (target.skillVersionId) setSelectedSkillVersionId(target.skillVersionId)
    }
  }, [])

  const closeWorkbench = useCallback(() => setIsOpen(false), [])
  const toggleWorkbench = useCallback(() => setIsOpen((prev) => !prev), [])

  const registerMentionHandler = useCallback(
    (handler: ((mention: ChatMention) => void) | null) => {
      mentionHandlerRef.current = handler
    },
    [],
  )

  const citeMention = useCallback((mention: ChatMention): boolean => {
    const handler = mentionHandlerRef.current ?? propCiteRef.current
    if (!handler) return false
    handler(mention)
    return true
  }, [])

  const value = useMemo<WorkbenchContextValue>(
    () => ({
      projectId,
      workbench,
      loading,
      refresh,
      isOpen,
      activeTab,
      selectedVersionId,
      selectedOutputId,
      selectedAssetId,
      selectedSkillVersionId,
      openWorkbench,
      closeWorkbench,
      toggleWorkbench,
      setActiveTab,
      setSelectedVersionId,
      setSelectedOutputId,
      setSelectedAssetId,
      setSelectedSkillVersionId,
      registerMentionHandler,
      registerTextHandler,
      citeText,
      citeMention,
    }),
    [
      projectId,
      workbench,
      loading,
      refresh,
      isOpen,
      activeTab,
      selectedVersionId,
      selectedOutputId,
      selectedAssetId,
      selectedSkillVersionId,
      openWorkbench,
      closeWorkbench,
      toggleWorkbench,
      registerMentionHandler,
      registerTextHandler,
      citeText,
      citeMention,
    ],
  )

  return (
    <WorkbenchContext.Provider value={value}>
      {children}
    </WorkbenchContext.Provider>
  )
}
