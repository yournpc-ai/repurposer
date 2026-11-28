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

export type WorkbenchTab =
  | "player"
  | "storyboard"
  | "inspector"
  | "slots"
  | "presets"
  | "sounds"

export type WorkbenchPresetKind = "block" | "text_preset" | "music" | "voices" | "sounds"

export type WorkbenchArtifact =
  | {
      key: string
      kind: "output"
      outputId: string
      title?: string
      selectRegion?: boolean
      seekSeconds?: number
      seekNonce?: number
    }
  | {
      key: string
      kind: "version"
      versionId: string
      title?: string
      startSeconds?: number
      endSeconds?: number
    }
  | {
      key: string
      kind: "storyboard"
      versionId: string
      title?: string
    }
  | {
      key: string
      kind: "asset"
      assetId: string
      title?: string
    }
  | {
      key: string
      kind: "skill"
      skillVersionId: string
      title?: string
    }
  | {
      key: string
      kind: "markdown"
      id: string
      title: string
      content: string
      subtitle?: string
    }
  | {
      key: "presets"
      kind: "presets"
      presetTab?: WorkbenchPresetKind
      title?: string
    }

export type WorkbenchOpenTarget =
  | {
      tab: "player"
      versionId?: string
      outputId?: string
      title?: string
      startSeconds?: number
      endSeconds?: number
    }
  | { tab: "storyboard"; versionId: string; title?: string }
  | { tab: "inspector"; assetId?: string; outputId?: string; title?: string }
  | { tab: "slots"; skillVersionId?: string; title?: string }
  | { tab: "presets"; presetTab?: WorkbenchPresetKind; title?: string }
  | { tab: "sounds"; title?: string }

export interface WorkbenchContextValue {
  projectId: string
  workbench: WorkbenchData | null
  loading: boolean
  refresh: () => Promise<void>
  isOpen: boolean
  /** Open artifact tabs currently pinned in the right-hand viewer. */
  openArtifacts: WorkbenchArtifact[]
  activeArtifactKey: string | null
  activeArtifact: WorkbenchArtifact | null
  openArtifact: (artifact: WorkbenchArtifact) => void
  closeArtifact: (key: string) => void
  activateArtifact: (key: string) => void
  /** Legacy / convenience projections kept synced with activeArtifact. */
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
  /** Registered desktop pane width (px) so outer header tabs align flush over the pane. */
  paneWidth: number
  setPaneWidth: (width: number) => void
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
export function parseWorkbenchHref(
  href: string | undefined | null,
): WorkbenchOpenTarget | null {
  if (!href) return null
  const trimmed = href.trim()
  if (/^#workbench:presets$/i.test(trimmed)) {
    return { tab: "presets", presetTab: "block" }
  }
  if (/^#workbench:sounds$/i.test(trimmed)) {
    return { tab: "sounds" }
  }
  const match =
    /^#workbench:(version|output|asset|skill|storyboard)\/([^/?#\s]+)$/i.exec(
      trimmed,
    )
  if (!match) return null
  const kind = match[1].toLowerCase()
  const id = decodeURIComponent(match[2])
  if (!id) return null
  switch (kind) {
    case "version":
      return { tab: "player", versionId: id }
    case "output":
      return { tab: "player", outputId: id }
    case "storyboard":
      return { tab: "storyboard", versionId: id }
    case "asset":
      return { tab: "inspector", assetId: id }
    case "skill":
      return { tab: "slots", skillVersionId: id }
    default:
      return null
  }
}

function firstExternalSkillVersionId(
  data: WorkbenchData | null | undefined,
): string | null {
  for (const s of data?.skills ?? []) {
    if (s.reference.kind === "external" && s.reference.skill_version_id) {
      return s.reference.skill_version_id
    }
  }
  return null
}

function hasPlayableVideoOutput(
  files: Record<string, string | null | undefined> | undefined,
): boolean {
  if (!files) return false
  for (const key of ["video", "mp4", "stream", "url", "final"]) {
    const val = files[key]
    if (typeof val === "string" && val.trim()) return true
  }
  return Object.values(files).some(
    (v): v is string =>
      typeof v === "string" && /\.(mp4|webm|mov)(\?|$)/i.test(v),
  )
}

function pickPrimaryArtifact(data: WorkbenchData | null): WorkbenchArtifact | null {
  if (!data) return null
  const headComp = data.compositions[0]
  const headVersionId =
    headComp?.current_version_id ?? headComp?.versions[0]?.version_id ?? null

  // Prefer the rendered 1080p MP4 matching the current head, or the latest delivered video.
  const playableOutputs = data.outputs.filter((o) =>
    hasPlayableVideoOutput(o.files),
  )
  const headOutput =
    (headVersionId
      ? playableOutputs.find((o) => o.composition_version_id === headVersionId)
      : null) ?? playableOutputs[0] ?? null

  if (headOutput) {
    return {
      key: `output:${headOutput.id}`,
      kind: "output",
      outputId: headOutput.id,
      title: headComp?.name ?? undefined,
    }
  }
  if (headVersionId) {
    return {
      key: `version:${headVersionId}`,
      kind: "version",
      versionId: headVersionId,
      title: headComp?.name ?? undefined,
    }
  }
  const visualAsset = data.assets.find(
    (a) =>
      a.file_url &&
      (a.type === "image" || a.type === "video" || a.type === "web_page"),
  )
  if (visualAsset) {
    return {
      key: `asset:${visualAsset.id}`,
      kind: "asset",
      assetId: visualAsset.id,
      title: visualAsset.title ?? undefined,
    }
  }
  return null
}

function artifactToTab(artifact: WorkbenchArtifact | null): WorkbenchTab {
  if (!artifact) return "player"
  switch (artifact.kind) {
    case "output":
    case "version":
      return "player"
    case "storyboard":
    case "markdown":
      return "storyboard"
    case "asset":
      return "inspector"
    case "skill":
      return "slots"
    case "presets":
      return artifact.presetTab === "sounds" ? "sounds" : "presets"
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
  const [paneWidth, setPaneWidth] = useState(480)
  const [openArtifacts, setOpenArtifacts] = useState<WorkbenchArtifact[]>(() => {
    if (!defaultOpen) return []
    const primary = pickPrimaryArtifact(initialData)
    return primary ? [primary] : []
  })
  const [activeArtifactKey, setActiveArtifactKey] = useState<string | null>(() => {
    if (!defaultOpen) return null
    return pickPrimaryArtifact(initialData)?.key ?? null
  })
  const [selectedVersionId, setSelectedVersionIdState] = useState<string | null>(
    () =>
      initialData?.compositions[0]?.current_version_id ??
      initialData?.compositions[0]?.versions[0]?.version_id ??
      null,
  )
  const [selectedOutputId, setSelectedOutputIdState] = useState<string | null>(
    () => initialData?.outputs[0]?.id ?? null,
  )
  const [selectedAssetId, setSelectedAssetIdState] = useState<string | null>(
    () => {
      const visual = initialData?.assets.find(
        (a) =>
          a.file_url &&
          (a.type === "image" || a.type === "video" || a.type === "web_page"),
      )
      return visual?.id ?? initialData?.assets[0]?.id ?? null
    },
  )
  const [selectedSkillVersionId, setSelectedSkillVersionIdState] = useState<
    string | null
  >(() => {
    const first = initialData?.skills.find(
      (s) => s.reference.kind === "external" && s.reference.skill_version_id,
    )
    return first && first.reference.kind === "external"
      ? first.reference.skill_version_id
      : null
  })

  const mentionHandlerRef = useRef<((mention: ChatMention) => void) | null>(null)
  const textRef = useRef<((text: string) => void) | null>(null)
  const registerTextHandler = useCallback(
    (handler: ((text: string) => void) | null) => {
      textRef.current = handler
    },
    [],
  )
  const citeText = useCallback((text: string) => {
    if (!textRef.current) return false
    textRef.current(text)
    return true
  }, [])
  const propCiteRef = useRef(onCiteMention)
  propCiteRef.current = onCiteMention

  const workbenchRef = useRef<WorkbenchData | null>(workbench)
  workbenchRef.current = workbench

  const hydrateDefaults = useCallback((data: WorkbenchData) => {
    const latestVersion =
      data.compositions[0]?.current_version_id ??
      data.compositions[0]?.versions[0]?.version_id ??
      null
    setSelectedVersionIdState((prev) => {
      if (
        prev &&
        data.compositions.some((c) =>
          c.versions.some((v) => v.version_id === prev),
        )
      ) {
        return prev
      }
      return latestVersion
    })
    setSelectedOutputIdState((prev) => {
      if (prev && data.outputs.some((o) => o.id === prev)) return prev
      return data.outputs[0]?.id ?? null
    })
    setSelectedAssetIdState((prev) => {
      if (prev && data.assets.some((a) => a.id === prev)) return prev
      const visual = data.assets.find(
        (a) =>
          a.file_url &&
          (a.type === "image" || a.type === "video" || a.type === "web_page"),
      )
      return visual?.id ?? data.assets[0]?.id ?? null
    })
    setSelectedSkillVersionIdState((prev) => {
      const versionIds = data.skills
        .map((s) =>
          s.reference.kind === "external" ? s.reference.skill_version_id : null,
        )
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

  const openArtifact = useCallback((artifact: WorkbenchArtifact) => {
    setIsOpen(true)
    setOpenArtifacts((prev) => {
      const idx = prev.findIndex((item) => item.key === artifact.key)
      if (idx >= 0) {
        const existing = prev[idx]
        const merged = {
          ...existing,
          ...artifact,
          title: artifact.title ?? existing.title,
        } as WorkbenchArtifact
        const next = [...prev]
        next[idx] = merged
        return next
      }
      // Deduplicate version tabs belonging to the same composition: the player
      // already has an inline version selector, so opening v23 while v24 is open
      // should update that composition's tab in place rather than spawning two
      // identical-looking tabs.
      if (artifact.kind === "version") {
        const comps = workbenchRef.current?.compositions ?? []
        const compIdOf = (versionId: string): string | null => {
          for (const comp of comps) {
            if (
              comp.current_version_id === versionId ||
              comp.versions.some((v) => v.version_id === versionId)
            ) {
              return comp.composition_id
            }
          }
          return null
        }
        const targetCompId = compIdOf(artifact.versionId)
        const sameCompIdx = prev.findIndex((item) => {
          if (item.kind !== "version") return false
          if (targetCompId) return compIdOf(item.versionId) === targetCompId
          return Boolean(artifact.title && item.title && artifact.title === item.title)
        })
        if (sameCompIdx >= 0) {
          const existing = prev[sameCompIdx]
          const next = [...prev]
          next[sameCompIdx] = {
            ...artifact,
            title: artifact.title ?? existing.title,
          }
          return next
        }
      }
      return [...prev, artifact]
    })
    setActiveArtifactKey(artifact.key)

    if (artifact.kind === "output") {
      setSelectedOutputIdState(artifact.outputId)
      setSelectedVersionIdState(null)
    } else if (artifact.kind === "version") {
      setSelectedVersionIdState(artifact.versionId)
    } else if (artifact.kind === "storyboard") {
      setSelectedVersionIdState(artifact.versionId)
    } else if (artifact.kind === "asset") {
      setSelectedAssetIdState(artifact.assetId)
    } else if (artifact.kind === "skill") {
      setSelectedSkillVersionIdState(artifact.skillVersionId)
    }
  }, [])

  const activateArtifact = useCallback((key: string) => {
    setActiveArtifactKey(key)
    setIsOpen(true)
  }, [])

  const closeArtifact = useCallback((key: string) => {
    setOpenArtifacts((prev) => {
      const idx = prev.findIndex((item) => item.key === key)
      if (idx < 0) return prev
      const next = prev.filter((item) => item.key !== key)
      setActiveArtifactKey((curr) => {
        if (curr !== key) return curr
        if (next.length === 0) return null
        return (next[Math.min(idx, next.length - 1)] ?? next[0]).key
      })
      return next
    })
  }, [])

  const resolveDefaultArtifactForTab = useCallback(
    (tab: WorkbenchTab): WorkbenchArtifact | null => {
      const data = workbenchRef.current
      if (tab === "presets") {
        return { key: "presets", kind: "presets", presetTab: "block" }
      }
      if (tab === "sounds") {
        return { key: "presets", kind: "presets", presetTab: "sounds" }
      }
      if (tab === "inspector") {
        const assetId =
          selectedAssetId ??
          data?.assets.find(
            (a) =>
              a.file_url &&
              (a.type === "image" || a.type === "video" || a.type === "web_page"),
          )?.id ??
          data?.assets[0]?.id ??
          null
        if (assetId) {
          return { key: `asset:${assetId}`, kind: "asset", assetId }
        }
        return null
      }
      if (tab === "slots") {
        const skillVersionId =
          selectedSkillVersionId ?? firstExternalSkillVersionId(data)
        if (skillVersionId) {
          return { key: `skill:${skillVersionId}`, kind: "skill", skillVersionId }
        }
        return { key: "skill:__empty__", kind: "skill", skillVersionId: "" }
      }
      if (tab === "storyboard") {
        const vid =
          selectedVersionId ??
          data?.compositions[0]?.current_version_id ??
          data?.compositions[0]?.versions[0]?.version_id ??
          null
        return vid ? { key: `storyboard:${vid}`, kind: "storyboard", versionId: vid } : null
      }
      return pickPrimaryArtifact(data)
    },
    [selectedAssetId, selectedSkillVersionId, selectedVersionId],
  )

  const openWorkbench = useCallback(
    (target?: WorkbenchOpenTarget) => {
      if (!target) {
        setIsOpen(true)
        setOpenArtifacts((prev) => {
          if (prev.length > 0) return prev
          const primary = pickPrimaryArtifact(workbenchRef.current)
          if (primary) {
            setActiveArtifactKey(primary.key)
            return [primary]
          }
          return prev
        })
        return
      }
      if (target.tab === "player") {
        if (target.outputId) {
          openArtifact({
            key: `output:${target.outputId}`,
            kind: "output",
            outputId: target.outputId,
            title: target.title,
          })
          return
        }
        if (target.versionId) {
          openArtifact({
            key: `version:${target.versionId}`,
            kind: "version",
            versionId: target.versionId,
            title: target.title,
            startSeconds: target.startSeconds,
            endSeconds: target.endSeconds,
          })
          return
        }
        const primary = pickPrimaryArtifact(workbenchRef.current)
        if (primary) {
          openArtifact(primary)
        } else {
          setIsOpen(true)
        }
        return
      }
      if (target.tab === "storyboard") {
        openArtifact({
          key: `storyboard:${target.versionId}`,
          kind: "storyboard",
          versionId: target.versionId,
          title: target.title,
        })
        return
      }
      if (target.tab === "inspector") {
        if (target.assetId) {
          openArtifact({
            key: `asset:${target.assetId}`,
            kind: "asset",
            assetId: target.assetId,
            title: target.title,
          })
          return
        }
        if (target.outputId) {
          openArtifact({
            key: `output:${target.outputId}`,
            kind: "output",
            outputId: target.outputId,
            title: target.title,
            selectRegion: true,
          })
          return
        }
        const fallback = resolveDefaultArtifactForTab("inspector")
        if (fallback) openArtifact(fallback)
        else setIsOpen(true)
        return
      }
      if (target.tab === "slots") {
        const skillVersionId =
          target.skillVersionId ??
          selectedSkillVersionId ??
          firstExternalSkillVersionId(workbenchRef.current) ??
          ""
        openArtifact({
          key: skillVersionId ? `skill:${skillVersionId}` : "skill:__empty__",
          kind: "skill",
          skillVersionId,
          title: target.title,
        })
        return
      }
      if (target.tab === "presets") {
        openArtifact({
          key: "presets",
          kind: "presets",
          presetTab: target.presetTab ?? "block",
          title: target.title,
        })
        return
      }
      if (target.tab === "sounds") {
        openArtifact({
          key: "presets",
          kind: "presets",
          presetTab: "sounds",
          title: target.title,
        })
      }
    },
    [openArtifact, resolveDefaultArtifactForTab, selectedSkillVersionId],
  )

  const closeWorkbench = useCallback(() => setIsOpen(false), [])

  const toggleWorkbench = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev
      if (next) {
        setOpenArtifacts((existing) => {
          if (existing.length > 0) return existing
          const primary = pickPrimaryArtifact(workbenchRef.current)
          if (primary) {
            setActiveArtifactKey(primary.key)
            return [primary]
          }
          return existing
        })
      }
      return next
    })
  }, [])

  const setActiveTab = useCallback(
    (tab: WorkbenchTab) => {
      const target = resolveDefaultArtifactForTab(tab)
      if (target) openArtifact(target)
      else setIsOpen(true)
    },
    [openArtifact, resolveDefaultArtifactForTab],
  )

  const setSelectedVersionId = useCallback(
    (id: string | null) => {
      setSelectedVersionIdState(id)
      if (!id) return
      // Replace the active version tab in-place when switching versions inside the player
      setOpenArtifacts((prev) => {
        const activeIdx = prev.findIndex((a) => a.key === activeArtifactKey)
        if (activeIdx >= 0 && prev[activeIdx].kind === "version") {
          const nextKey = `version:${id}`
          // Avoid duplicate tab keys
          const dupIdx = prev.findIndex((a) => a.key === nextKey)
          if (dupIdx >= 0) {
            setActiveArtifactKey(nextKey)
            return prev
          }
          const next = [...prev]
          next[activeIdx] = { key: nextKey, kind: "version", versionId: id }
          setActiveArtifactKey(nextKey)
          return next
        }
        return prev
      })
    },
    [activeArtifactKey],
  )

  const setSelectedOutputId = useCallback((id: string | null) => {
    setSelectedOutputIdState(id)
  }, [])

  const setSelectedAssetId = useCallback(
    (id: string | null) => {
      setSelectedAssetIdState(id)
      if (!id) return
      setOpenArtifacts((prev) => {
        const activeIdx = prev.findIndex((a) => a.key === activeArtifactKey)
        if (activeIdx >= 0 && prev[activeIdx].kind === "asset") {
          const nextKey = `asset:${id}`
          const dupIdx = prev.findIndex((a) => a.key === nextKey)
          if (dupIdx >= 0) {
            setActiveArtifactKey(nextKey)
            return prev
          }
          const next = [...prev]
          next[activeIdx] = { key: nextKey, kind: "asset", assetId: id }
          setActiveArtifactKey(nextKey)
          return next
        }
        return prev
      })
    },
    [activeArtifactKey],
  )

  const setSelectedSkillVersionId = useCallback((id: string | null) => {
    setSelectedSkillVersionIdState(id)
  }, [])

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

  const activeArtifact = useMemo<WorkbenchArtifact | null>(() => {
    if (openArtifacts.length === 0) return null
    return (
      openArtifacts.find((a) => a.key === activeArtifactKey) ??
      openArtifacts[openArtifacts.length - 1] ??
      null
    )
  }, [openArtifacts, activeArtifactKey])

  const activeTab = useMemo(
    () => artifactToTab(activeArtifact),
    [activeArtifact],
  )

  // Sync active artifact's ids back to convenience selectors
  const effectiveVersionId =
    activeArtifact?.kind === "version" || activeArtifact?.kind === "storyboard"
      ? activeArtifact.versionId
      : selectedVersionId
  const effectiveOutputId =
    activeArtifact?.kind === "output"
      ? activeArtifact.outputId
      : selectedOutputId
  const effectiveAssetId =
    activeArtifact?.kind === "asset" ? activeArtifact.assetId : selectedAssetId
  const effectiveSkillVersionId =
    activeArtifact?.kind === "skill"
      ? activeArtifact.skillVersionId
      : selectedSkillVersionId

  const value = useMemo<WorkbenchContextValue>(
    () => ({
      projectId,
      workbench,
      loading,
      refresh,
      isOpen,
      openArtifacts,
      activeArtifactKey: activeArtifact?.key ?? null,
      activeArtifact,
      openArtifact,
      closeArtifact,
      activateArtifact,
      activeTab,
      selectedVersionId: effectiveVersionId,
      selectedOutputId: effectiveOutputId,
      selectedAssetId: effectiveAssetId,
      selectedSkillVersionId: effectiveSkillVersionId,
      openWorkbench,
      closeWorkbench,
      toggleWorkbench,
      setActiveTab,
      setSelectedVersionId,
      setSelectedOutputId,
      setSelectedAssetId,
      setSelectedSkillVersionId,
      paneWidth,
      setPaneWidth,
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
      paneWidth,
      openArtifacts,
      activeArtifact,
      openArtifact,
      closeArtifact,
      activateArtifact,
      activeTab,
      effectiveVersionId,
      effectiveOutputId,
      effectiveAssetId,
      effectiveSkillVersionId,
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
    ],
  )

  return (
    <WorkbenchContext.Provider value={value}>
      {children}
    </WorkbenchContext.Provider>
  )
}
