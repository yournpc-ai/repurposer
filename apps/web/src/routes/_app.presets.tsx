import { lazy, Suspense, useCallback, useEffect, useState } from "react"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { LayoutGrid, List, Search } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"

import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { Select } from "@/components/ui/select-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { TextField } from "@/components/ui/text-field-clean"

const VisualPresetGalleryPanel = lazy(
  () => import("@/components/workbench/VisualPresetGalleryPanel"),
)
const SoundLabPanel = lazy(
  () => import("@/components/workbench/SoundLabPanel"),
)

type PresetSection = "block" | "text_preset" | "sounds"
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
      <header>
        <h1 className="text-2xl leading-8 font-medium">
          {t("presetsPage.title")}
        </h1>
        <p className="mt-1 text-[13px] leading-5 text-muted-foreground">
          {t("presetsPage.subtitle")}
        </p>
      </header>

      <section aria-labelledby="presets-library-title">
        <h2 id="presets-library-title" className="project-section-title">
          {t(
            section === "block"
              ? "visualGallery.blocks"
              : section === "text_preset"
                ? "visualGallery.text"
                : "visualGallery.sounds",
          )}
          {section !== "sounds" && count != null ? (
            <span className="tabular-nums">{count}</span>
          ) : null}
        </h2>

        <div className="project-toolbar">
          <SegmentedControl<PresetSection>
            aria-label={t("workbench.tabs.presets")}
            value={section}
            onChange={(next) => {
              setSection(next)
              setCategory("")
              setQuery("")
              setCount(null)
            }}
            variant="buttons"
            options={[
              { value: "block", label: t("visualGallery.blocks") },
              { value: "text_preset", label: t("visualGallery.text") },
              { value: "sounds", label: t("visualGallery.sounds") },
            ]}
          />

          {section !== "sounds" ? (
            <div className="project-tools">
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
              <TextField
                size="sm"
                type="search"
                prefix={<Search size={16} />}
                className="project-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label={t("visualGallery.search")}
                placeholder={t("visualGallery.search")}
              />
            </div>
          ) : null}
        </div>

        <div className="mt-4">
          <Suspense
            fallback={
              <div className="flex h-48 items-center justify-center">
                <Spinner size={18} />
              </div>
            }
          >
            {section === "sounds" ? (
              <SoundLabPanel standalone onUsePreset={handleUsePreset} />
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
