"use client"

import { useCallback, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { apiFetch } from "@/lib/api"
import { inferAssetType } from "@/lib/asset-type"
import { useAuth } from "@/components/AuthProvider"
import type { ChatMention } from "@/lib/mentions"

/**
 * useProjectLaunch — the composer's send mechanism, shared (2026-08-08, D6
 * 二次修订): **one launchpad, two parking spots**. HomeComposer and the recipe
 * inspect overlay's launch zone ride the SAME path: create an empty project →
 * upload staged files (direct-to-storage) → navigate to
 * `/projects/$id?overlay=chat` with the draft handed over via router state —
 * the overlay chat sends it as the first `/chat` message (mentions and the
 * persona choice ride along — the single identity payload, ADR-038).
 *
 * Boundaries (unchanged doctrine): the launcher never infers intent, never
 * builds a prior, never runs generation — intent recognition lives in the
 * chat plan path. A recipe launch is just its prompt template (2026-08-11
 * ruling — 配方 = 提示词): the card's identity stays in the frontend.
 * An overlay hosting this mechanism is NOT the rejected A-form;
 * the A-form is a modal that runs generation itself.
 */

export interface LaunchInput {
  prompt: string
  mentions: ChatMention[]
  files: File[]
  /** undefined = auto persona. */
  personaId?: string
  /** Fires when the send begins (spinner on). */
  onStart?: () => void
  /** Fires right before navigating — the sender consumes its own draft
   * (mention chip law ②: send consumes, nothing lingers). */
  onSent?: () => void
}

interface CreatedProject {
  id: string
}

export function useProjectLaunch() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { requireAuth } = useAuth()
  const [launching, setLaunching] = useState(false)

  const launch = useCallback(
    async (input: LaunchInput) => {
      await requireAuth(async () => {
        // Prompt is required — the pipeline's intent step derives the task
        // book (outputs / language / clip count) from it server-side.
        const text = input.prompt.trim()
        if (!text) {
          toast.error(t("home.noPromptError"))
          return
        }
        setLaunching(true)
        input.onStart?.()
        try {
          // Project title = a 15-char split of the user's prompt + "…" — the
          // chat-app convention (a conversation is named from the user's own
          // words), NEVER the material's filename.
          const promptLine = text.replace(/\s+/g, " ")
          const title =
            (promptLine.length > 15 ? `${promptLine.slice(0, 15)}…` : promptLine) ||
            t("common.untitled")
          const projectRes = await apiFetch("/api/v1/projects", {
            method: "POST",
            body: {
              title,
              event_name: "",
              persona_id: input.personaId || undefined,
            },
          })
          if (!projectRes.ok) throw new Error("Failed to create project")
          const project = (await projectRes.json()) as CreatedProject

          // Only real user files upload. A prompt-only send creates NO asset:
          // pasted text is promoted server-side in the chat plan path when it
          // IS the user's content (LLM-judged, never a length heuristic).
          await Promise.all(
            input.files.map(async (material) => {
              const type = inferAssetType(material)

              const urlRes = await apiFetch(
                `/api/v1/projects/${project.id}/assets/upload-url`,
                {
                  method: "POST",
                  body: {
                    filename: material.name,
                    content_type: material.type || undefined,
                  },
                },
              )
              if (!urlRes.ok) throw new Error("Failed to get upload URL")
              const { key, upload_url } = (await urlRes.json()) as {
                key: string
                upload_url: string
              }

              const putRes = await fetch(upload_url, {
                method: "PUT",
                body: material,
                headers: material.type ? { "Content-Type": material.type } : {},
              })
              // Direct-to-storage PUT bypasses apiFetch, so toast here.
              if (!putRes.ok) {
                toast.error(t("composer.uploadFailed"))
                throw new Error("Failed to upload file")
              }

              const assetRes = await apiFetch(
                `/api/v1/projects/${project.id}/assets`,
                {
                  method: "POST",
                  body: { type, key, title: material.name },
                },
              )
              if (!assetRes.ok) throw new Error("Failed to create asset")
            }),
          )

          // Send consumes the draft (chip law ②) — the caller clears its
          // editor/state, then we hand the draft to the overlay chat.
          input.onSent?.()

          navigate({
            to: "/projects/$id",
            params: { id: project.id },
            search: { overlay: "chat" },
            state: {
              firstMessage: {
                text,
                mentions: input.mentions,
                personaId: input.personaId || undefined,
              },
            } as Record<string, unknown>,
          })
        } catch {
          // apiFetch already toasted the server's reason; just reset the UI.
          setLaunching(false)
        }
      })
    },
    [navigate, requireAuth, t],
  )

  return { launching, launch }
}
