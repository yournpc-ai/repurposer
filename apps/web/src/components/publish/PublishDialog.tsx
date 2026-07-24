"use client"

import { useEffect, useRef, useState } from "react"
import { Check, Info, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { PlatformIcon, PLATFORM_LABELS } from "@/components/publish/PlatformIcon"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { apiPost } from "@/lib/api"
import { connectChannel, PLATFORMS, useChannels } from "@/lib/channels"
import { cn } from "@/lib/utils"

import type { ChannelAccount, ChannelPlatform, Output } from "@/lib/types"

interface PublishDialogProps {
  output: Output
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface Draft {
  title: string
  caption: string
  hashtags: string
}

function initialDraft(output: Output): Draft {
  return {
    title: output.publishing.title ?? "",
    caption: output.publishing.description ?? "",
    hashtags: (output.publishing.hashtags ?? []).join(" "),
  }
}

/** ADR-026 display rule (mirrors the backend classifier): synthetic tracks →
 * disclose. The user is informed, never asked — no checkbox. */
function needsDisclosure(output: Output): boolean {
  if (output.provenance === "generated") return true
  const spec = output.render_spec as { dub?: unknown } | null
  return Boolean(spec?.dub)
}

export function PublishDialog({ output, open, onOpenChange }: PublishDialogProps) {
  const { t } = useTranslation()
  const { activeAccountFor, isConfigured } = useChannels(open)
  const [selected, setSelected] = useState<ChannelPlatform[]>([])
  const [activeTab, setActiveTab] = useState<ChannelPlatform>("linkedin")
  // Drafts survive tab switches and channel toggles for the dialog's lifetime
  // (edit = confirm, ADR-027) — keyed by platform, never reset on select.
  const [drafts, setDrafts] = useState<Record<ChannelPlatform, Draft>>(() => ({
    linkedin: initialDraft(output),
    tiktok: initialDraft(output),
  }))
  const [submitting, setSubmitting] = useState(false)
  // One idempotency key per dialog publish intent; a double-submit or
  // accidental resubmit maps to the same publication row server-side.
  const clientKeyRef = useRef<string>("")
  const wasOpenRef = useRef(false)

  // Initialize only on the open edge (false → true). Depending on `output`
  // here would wipe drafts mid-edit whenever the parent's polling hands us a
  // new object identity.
  useEffect(() => {
    if (!open) {
      wasOpenRef.current = false
      return
    }
    if (wasOpenRef.current) return
    wasOpenRef.current = true
    clientKeyRef.current = crypto.randomUUID()
    setDrafts({ linkedin: initialDraft(output), tiktok: initialDraft(output) })
    setSubmitting(false)
  }, [open, output])

  // Pre-select every connected platform once channels load; focus the first.
  useEffect(() => {
    if (!open) return
    const connected = PLATFORMS.filter((p) => activeAccountFor(p))
    setSelected(connected)
    if (connected.length > 0) setActiveTab(connected[0])
  }, [open, activeAccountFor])

  const toggle = (platform: ChannelPlatform) => {
    if (!activeAccountFor(platform)) return
    setSelected((prev) =>
      prev.includes(platform)
        ? prev.filter((p) => p !== platform)
        : [...prev, platform]
    )
    setActiveTab(platform)
  }

  const updateDraft = (platform: ChannelPlatform, patch: Partial<Draft>) =>
    setDrafts((prev) => ({ ...prev, [platform]: { ...prev[platform], ...patch } }))

  const submit = async () => {
    const targets = selected
      .map((p) => ({ platform: p, account: activeAccountFor(p) }))
      .filter((x): x is { platform: ChannelPlatform; account: ChannelAccount } =>
        Boolean(x.account)
      )
    if (targets.length === 0) {
      toast.error(t("publish.selectChannel"))
      return
    }
    setSubmitting(true)
    const results = await Promise.all(
      targets.map(({ account, platform }) => {
        const draft = drafts[platform]
        return apiPost(
          `/api/v1/projects/${output.project_id}/publications`,
          {
            output_id: output.id,
            channel_account_id: account.id,
            overrides: {
              title: draft.title,
              caption: draft.caption,
              hashtags: draft.hashtags
                .split(/\s+/)
                .map((h) => h.replace(/^#/, "").trim())
                .filter(Boolean),
            },
            client_key: clientKeyRef.current,
          },
          { toast: false }
        )
      })
    )
    setSubmitting(false)
    if (results.every((r) => r.ok)) {
      toast.success(t("publish.queued"))
      onOpenChange(false)
    } else {
      toast.error(t("publish.failed"))
    }
  }

  const editablePlatforms = selected.filter((p) => activeAccountFor(p))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("publish.title")}</DialogTitle>
        </DialogHeader>

        {/* Channel picker */}
        <div className="space-y-2">
          <Label>{t("publish.chooseChannels")}</Label>
          <div className="grid grid-cols-2 gap-2">
            {PLATFORMS.map((platform) => {
              const account = activeAccountFor(platform)
              const configured = isConfigured(platform)
              const isSelected = selected.includes(platform)
              return (
                <div
                  key={platform}
                  className={cn(
                    "rounded-md p-3 ring-1 ring-border",
                    isSelected && "ring-2 ring-primary"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <PlatformIcon platform={platform} />
                      {PLATFORM_LABELS[platform]}
                    </div>
                    {isSelected && <Check className="h-4 w-4 text-primary" />}
                  </div>
                  <div className="mt-2">
                    {!configured ? (
                      <span className="text-xs text-muted-foreground">
                        {t("publish.comingSoon")}
                      </span>
                    ) : account ? (
                      <button
                        type="button"
                        onClick={() => toggle(platform)}
                        className="flex w-full items-center gap-2 text-left"
                      >
                        <Avatar className="h-6 w-6">
                          {account.avatar_url && (
                            <AvatarImage src={account.avatar_url} />
                          )}
                          <AvatarFallback>
                            {account.display_name.slice(0, 1).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <span className="truncate text-xs text-muted-foreground">
                          {account.display_name}
                        </span>
                      </button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => connectChannel(platform)}
                      >
                        {t("publish.connect")}
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Per-platform payload drafts (state survives tab switches) */}
        {editablePlatforms.length > 0 && (
          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as ChannelPlatform)}
            className="w-full"
          >
            <TabsList variant="line" className="w-full">
              {editablePlatforms.map((platform) => (
                <TabsTrigger key={platform} value={platform}>
                  <PlatformIcon platform={platform} className="h-3.5 w-3.5" />
                  {PLATFORM_LABELS[platform]}
                </TabsTrigger>
              ))}
            </TabsList>
            {editablePlatforms.map((platform) => (
              <TabsContent key={platform} value={platform} className="space-y-3 pt-3">
                <div className="space-y-1.5">
                  <Label htmlFor={`publish-title-${platform}`}>
                    {t("publish.titleLabel")}
                  </Label>
                  <Input
                    id={`publish-title-${platform}`}
                    value={drafts[platform].title}
                    onChange={(e) =>
                      updateDraft(platform, { title: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`publish-caption-${platform}`}>
                    {t("publish.captionLabel")}
                  </Label>
                  <Textarea
                    id={`publish-caption-${platform}`}
                    rows={5}
                    value={drafts[platform].caption}
                    onChange={(e) =>
                      updateDraft(platform, { caption: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`publish-hashtags-${platform}`}>
                    {t("publish.hashtagsLabel")}
                  </Label>
                  <Input
                    id={`publish-hashtags-${platform}`}
                    value={drafts[platform].hashtags}
                    onChange={(e) =>
                      updateDraft(platform, { hashtags: e.target.value })
                    }
                  />
                </div>
              </TabsContent>
            ))}
          </Tabs>
        )}

        {needsDisclosure(output) && (
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {t("publish.aiDisclosure")}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-9"
            onClick={() => onOpenChange(false)}
          >
            {t("publish.cancel")}
          </Button>
          <Button
            size="sm"
            className="h-9"
            disabled={submitting || editablePlatforms.length === 0}
            onClick={submit}
          >
            {submitting && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            {submitting ? t("publish.publishing") : t("publish.publishNow")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
