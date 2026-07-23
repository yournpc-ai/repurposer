import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"
import { Play, Upload, Sparkles, Mic2, Languages } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Tour, type TourStep } from "@/components/ui/tour"

/**
 * /dev/tour — Tour acceptance playground (docs/tasks/tour-component.md).
 * Covers the brief's edge cases: scrollable-container target, missing target
 * (auto-skip), viewport-edge target, mid-tour step navigation.
 */

export const Route = createFileRoute("/dev/tour")({
  component: DevTourPage,
})

const STEPS: TourStep[] = [
  {
    target: "[data-tour='demo-composer']",
    title: "Describe your talk",
    description:
      "Paste a prompt or drop your talk recording here — the agent turns one talk into two weeks of content.",
  },
  {
    target: "[data-tour='demo-actions']",
    title: "Tune the output",
    description:
      "Speaker, tone, and output types are set here. Anything you change by hand stays locked.",
    side: "top",
  },
  {
    target: "[data-tour='demo-missing']",
    title: "This step should never appear",
    description: "Its target does not exist, so the tour must skip it silently.",
  },
  {
    target: "[data-tour='demo-scrolled']",
    title: "Works inside scroll containers",
    description:
      "This card lives inside a scrollable panel — the spotlight tracks it anyway.",
    side: "right",
  },
  {
    target: "[data-tour='demo-edge']",
    title: "Viewport edges are fine",
    description:
      "The popover flips and shifts automatically when the target hugs the edge.",
    side: "top",
    align: "end",
  },
]

function DevTourPage() {
  const [open, setOpen] = useState(false)

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-10 p-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium">Tour playground</h1>
          <p className="text-sm text-muted-foreground">
            Acceptance field for docs/tasks/tour-component.md — callbacks log to
            console.
          </p>
        </div>
        <Button className="h-9" onClick={() => setOpen(true)}>
          <Play className="h-4 w-4" />
          Start tour
        </Button>
      </div>

      {/* Target 1: composer-like card */}
      <Card data-tour="demo-composer" className="py-0 ring-1 ring-border shadow-xl">
        <CardContent className="flex gap-4 p-4">
          <div className="flex h-24 w-24 flex-col items-center justify-center gap-2 rounded-md bg-muted text-muted-foreground">
            <Upload className="h-5 w-5" />
            <span className="text-xs">Drop media</span>
          </div>
          <div className="flex-1 rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
            Describe your talk, or paste a transcript…
          </div>
        </CardContent>
      </Card>

      {/* Target 2: action bar */}
      <div data-tour="demo-actions" className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="h-9">
          <Mic2 className="h-4 w-4" />
          Speaker
        </Button>
        <Button variant="outline" size="sm" className="h-9">
          <Sparkles className="h-4 w-4" />
          Tone
        </Button>
        <Button variant="outline" size="sm" className="h-9">
          <Languages className="h-4 w-4" />
          Languages
        </Button>
      </div>

      {/* Target 3: inside a scrollable container */}
      <div className="h-48 overflow-y-auto rounded-lg bg-muted/30 p-4 ring-1 ring-border">
        <div className="flex flex-col gap-3">
          {Array.from({ length: 8 }, (_, i) => (
            <div
              key={i}
              {...(i === 5 ? { "data-tour": "demo-scrolled" } : {})}
              className="rounded-md bg-card p-3 text-sm ring-1 ring-border"
            >
              Scrollable item {i + 1}
            </div>
          ))}
        </div>
      </div>

      {/* Spacer so the edge target can sit near the viewport bottom-right */}
      <div className="flex h-[60vh] items-end justify-end">
        <Card data-tour="demo-edge" className="py-0 ring-1 ring-border">
          <CardContent className="p-4 text-sm">Edge target</CardContent>
        </Card>
      </div>

      <Tour
        steps={STEPS}
        open={open}
        onOpenChange={setOpen}
        onComplete={() => console.log("[tour] complete")}
        onSkip={() => console.log("[tour] skip")}
      />
    </div>
  )
}
