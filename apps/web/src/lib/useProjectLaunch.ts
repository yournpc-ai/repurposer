"use client"

import { useCallback, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { apiFetch } from "@/lib/api"
import { inferAssetType } from "@/lib/asset-type"
import { chatAttachmentFromAsset } from "@/lib/chatAttachments"
import { useAuth } from "@/lib/auth-context"
import type { ChatMention } from "@/lib/mentions"
import type { SkillOption, SkillReference } from "@/lib/skills"
import type { StagingUpload } from "@/lib/stagingUploads"

/** Create the project, attach completed uploads and hand the opening to AgentThread. */
export interface LaunchInput {
  prompt: string
  mentions: ChatMention[]
  skill?: SkillReference
  skillOption?: SkillOption
  /** Already-uploaded staging items (useStagingUploads). Launch refuses to
   * fire while any item is mid-flight or failed — Generate never waits on
   * the wire and never silently drops a file. */
  staged: StagingUpload[]
  /** Fires when the send begins (spinner on). */
  onStart?: () => void
  /** Fires right before navigating — the sender consumes its own draft
   * (mention chip law ②: send consumes, nothing lingers). */
  onSent?: () => void
}

interface CreatedProject {
  id: string
}

const URL_REGEX = /https?:\/\/[^\s<>"'）)\]]+/i
const GENERIC_SUBDOMAINS = new Set([
  "www",
  "app",
  "agent",
  "web",
  "m",
  "mobile",
  "beta",
  "docs",
  "staging",
  "dev",
  "api",
  "studio",
  "get",
  "try",
])

function deriveInitialProjectTitle(prompt: string, fallback: string): string {
  const urlMatch = URL_REGEX.exec(prompt)
  if (urlMatch) {
    try {
      const host = new URL(urlMatch[0]).hostname.toLowerCase()
      const parts = host.split(".").filter(Boolean)
      const core =
        parts.length >= 3 &&
        ["co", "com", "org", "net", "edu", "gov"].includes(parts[parts.length - 2]) &&
        parts[parts.length - 1].length === 2
          ? parts.slice(0, -2)
          : parts.length >= 2
            ? parts.slice(0, -1)
            : parts
      let start = 0
      while (core.length - start > 1 && GENERIC_SUBDOMAINS.has(core[start])) start += 1
      const stem = core[core.length - 1] ?? parts[0] ?? ""
      const brand = stem
        .split(/[-_]+/)
        .filter(Boolean)
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
      if (brand) return brand.length > 24 ? `${brand.slice(0, 23)}…` : brand
    } catch {
      // Fall back to cleaned text
    }
  }
  const firstLine = prompt.split(/\r?\n/).map((l) => l.trim()).find(Boolean) ?? ""
  const cleaned = firstLine
    .replace(URL_REGEX, " ")
    .replace(/^(?:请你?|麻烦你?|请?帮我(?:把|给)?|给我|帮我|我想(?:要)?(?:做|剪|生成|制作)?|我要(?:做|剪|制作)?|给|把)\s*/u, "")
    .replace(/^(?:please\s+|can you\s+|could you\s+|help me\s+)?(?:create|make|generate|build|cut|edit)\s+(?:a|an|me\s+a|me\s+an|the)?\s*/i, "")
    .replace(/^(?:做(?:一[支条个份部])?|制作(?:一[支条个份部])?|生成(?:一[支条个份部])?|剪(?:一[支条个份部])?)\s*/u, "")
    .replace(/\s+/g, " ")
    .replace(/[\s,，。！？!?：:；;、]+$/, "")
    .trim()
  if (!cleaned) return fallback
  return cleaned.length > 24 ? `${cleaned.slice(0, 23)}…` : cleaned
}

export function useProjectLaunch() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { requireAuth } = useAuth()
  const [launching, setLaunching] = useState(false)

  const pending = useRef(false)
  const launch = useCallback(
    async (input: LaunchInput) => {
      await requireAuth(async () => {
        const text = input.prompt.trim()
        if (!text) {
          toast.error(t("home.noPromptError"))
          return
        }
        // The staging gate: an unfinished upload blocks the send (same
        // posture as the chat dock's handleSend) — Generate never carries
        // upload time, and a failed chip is the user's call (retry or ×).
        if (input.staged.some((s) => s.status !== "done")) {
          toast.error(t("composer.uploadInProgress"))
          return
        }
        if (pending.current) return
        pending.current = true
        setLaunching(true)
        input.onStart?.()
        try {
          const title = deriveInitialProjectTitle(text, t("common.untitled"))
          const projectRes = await apiFetch("/api/v1/projects", {
            method: "POST",
            body: {
              title,
              event_name: "",
            },
          })
          if (!projectRes.ok) throw new Error("Failed to create project")
          const project = (await projectRes.json()) as CreatedProject

          // Attach only — the bytes are already in storage (Batch A). A
          // prompt-only send creates NO asset: pasted text is promoted
          // server-side in the chat plan path when it IS the user's content
          // (LLM-judged, never a length heuristic).
          const attachedAssets = await Promise.all(
            input.staged.map(async (s) => {
              const assetRes = await apiFetch(
                `/api/v1/projects/${project.id}/assets/from-staging`,
                {
                  method: "POST",
                  body: {
                    type: inferAssetType(s.file),
                    key: s.key,
                    title: s.file.name,
                    ...(s.dims ?? {}),
                  },
                },
              )
              if (!assetRes.ok) throw new Error("Failed to attach staged asset")
              return assetRes.json() as Promise<{
                id: string
                type: string
                file_url: string | null
                stream_url?: string | null
                title: string | null
              }>
            }),
          )
          const attachments = attachedAssets.map((asset, index) =>
            chatAttachmentFromAsset(asset, {
              name: input.staged[index].file.name,
              size: input.staged[index].file.size,
            }),
          )

          // Send consumes the draft (chip law ②) — the caller clears its
          // editor/state, then we hand the draft to the project's chat dock.
          input.onSent?.()

          await navigate({
            to: "/projects/$id",
            params: { id: project.id },
            state: {
              firstMessage: {
                text,
                mentions: input.mentions,
                skill: input.skill,
                skillOption: input.skillOption,
                attachments,
              },
            } as Record<string, unknown>,
          })
        } catch {
          // apiFetch already toasted the server's reason; just reset the UI.
          pending.current = false
          setLaunching(false)
        }
      })
    },
    [navigate, requireAuth, t],
  )

  return { launching, launch }
}
