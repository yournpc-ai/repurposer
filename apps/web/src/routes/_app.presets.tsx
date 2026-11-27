import { lazy, Suspense, useCallback, useEffect, useState } from "react"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import {
  AudioLines,
  Layers,
  LayoutGrid,
  List,
  Mic,
  Music2,
  Search,
  Type,
} from "@/components/ui/icons"
import { useTranslation } from "react-i18next"

import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { Select } from "@/components/ui/select-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { TextField } from "@/components/ui/text-field-clean"

const VisualPresetGalleryPanel = lazy(
  () => import("@/components/workbench/VisualPresetGalleryPanel"),
)
const MusicLibraryPanel = lazy(
  () => import("@/components/workbench/MusicLibraryPanel"),
)
const VoiceLibraryPanel = lazy(
  () => import("@/components/workbench/VoiceLibraryPanel"),
)
const SoundLabPanel = lazy(
  () => import("@/components/workbench/SoundLabPanel"),
)

type PresetSection = "block" | "text_preset" | "music" | "voices" | "sounds"
type PresetView = "list" | "grid"

export const Route = createFileRoute("/_app/presets")({
  component: PresetsPage,
})

function PresetsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [section, setSection] = useState<PresetSection>("block")
  const [view, setView] = useState<PresetView>("list")
  const [query, setQuery] = useState("")
  const [category, setCategory] = useState("")
  const [categories, setCategories] = useState<{ value: string; label: string }[]>([])
  const [count, setCount] = useState<number | null>(null)

  useEffect(() => {
    try {
      const saved = localStorage.getItem("presets-view")
      if (saved === "grid" || saved === "list") setView(saved)
    } catch {
      // Storage may be unavailable
    }
  }, [])

  const handleUsePreset = useCallback(
    (instruction: string) => {
      void navigate({
        to: "/home",
        state: { prefillPrompt: instruction } as Record<string, unknown>,
      })
    },
    [navigate],
  )

  return (
    <div className="projects-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl leading-8 font-medium tracking-tight text-foreground">
            {t("presetsPage.title")}
          </h1>
          <p className="mt-1 text-[13px] leading-5 text-muted-foreground">
            {t("presetsPage.subtitle")}
          </p>
        </div>
      </header>

      <section aria-label={t("workbench.tabs.presets")} className="flex flex-col gap-5">
        <div className="flex flex-col gap-3 border-b border-subtle pb-3 sm:flex-row sm:items-center sm:justify-between">
          <SegmentedControl<PresetSection>
            kind="tabs"
            aria-label={t("workbench.tabs.presets")}
            value={section}
            onChange={(next) => {
              setSection(next)
              setCategory("")
              setQuery("")
              setCount(null)
            }}
            variant="underline"
            options={[
              {
                value: "block",
                label: t("visualGallery.blocks"),
                icon: <Layers size={15} />,
                count: section === "block" && count != null ? count : undefined,
              },
              {
                value: "text_preset",
                label: t("visualGallery.text"),
                icon: <Type size={15} />,
                count: section === "text_preset" && count != null ? count : undefined,
              },
              {
                value: "music",
                label: t("visualGallery.music"),
                icon: <Music2 size={15} />,
                count: section === "music" && count != null ? count : undefined,
              },
              {
                value: "voices",
                label: t("visualGallery.voices"),
                icon: <Mic size={15} />,
                count: section === "voices" && count != null ? count : undefined,
              },
              {
                value: "sounds",
                label: t("visualGallery.sounds"),
                icon: <AudioLines size={15} />,
              },
            ]}
          />

          {section !== "sounds" ? (
            <div className="flex flex-wrap items-center gap-2">
              {categories.length > 0 ? (
                <Select
                  size="sm"
                  aria-label={t("soundLab.category")}
                  value={category}
                  onChange={setCategory}
                  options={[
                    { value: "", label: t("visualGallery.all") },
                    ...categories,
                  ]}
                />
              ) : null}
              <TextField
                size="sm"
                type="search"
                prefix={<Search size={15} />}
                className="project-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label={t("visualGallery.search")}
                placeholder={
                  section === "music"
                    ? t("musicLibrary.search")
                    : section === "voices"
                      ? t("voiceLibrary.search")
                      : t("visualGallery.search")
                }
              />
              <SegmentedControl<PresetView>
                aria-label={t("projects.view")}
                value={view}
                variant="tray"
                onChange={(next) => {
                  setView(next)
                  try {
                    localStorage.setItem("presets-view", next)
                  } catch {
                    // Keep session choice
                  }
                }}
                options={[
                  {
                    value: "list",
                    ariaLabel: t("projects.list"),
                    icon: <List size={15} />,
                  },
                  {
                    value: "grid",
                    ariaLabel: t("projects.grid"),
                    icon: <LayoutGrid size={15} />,
                  },
                ]}
              />
            </div>
          ) : null}
        </div>

        <div>
          <Suspense
            fallback={
              <div className="flex h-48 items-center justify-center">
                <Spinner size={18} />
              </div>
            }
          >
            {section === "sounds" ? (
              <SoundLabPanel standalone onUsePreset={handleUsePreset} />
            ) : section === "music" ? (
              <MusicLibraryPanel
                view={view}
                hideToolbar
                query={query}
                category={category}
                onCategoriesChange={setCategories}
                onCountChange={setCount}
                onUsePreset={handleUsePreset}
              />
            ) : section === "voices" ? (
              <VoiceLibraryPanel
                view={view}
                hideToolbar
                query={query}
                category={category}
                onCategoriesChange={setCategories}
                onCountChange={setCount}
                onUsePreset={handleUsePreset}
              />
            ) : (
              <VisualPresetGalleryPanel
                key={section}
                kind={section}
                view={view}
                hideToolbar
                query={query}
                category={category}
                onCategoriesChange={setCategories}
                onCountChange={setCount}
                onUsePreset={handleUsePreset}
              />
            )}
          </Suspense>
        </div>
      </section>
    </div>
  )
}
