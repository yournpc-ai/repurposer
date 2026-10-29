import { useTranslation } from "react-i18next"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

/** Preview destinations until the real community and public roadmap are connected. */
export function LandingInfoDialog({ kind, className }: {
  kind: "community" | "roadmap"
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <Dialog>
      <DialogTrigger className={className}>
        {t(`landing.entry.${kind}`)}
      </DialogTrigger>
      <DialogContent className="rounded-lg sm:max-w-md">
        <DialogHeader>
          <p className="text-xs text-muted-foreground">{t("landing.entry.preview")}</p>
          <DialogTitle>{t(`landing.entry.${kind}Title`)}</DialogTitle>
          <DialogDescription>{t(`landing.entry.${kind}Description`)}</DialogDescription>
        </DialogHeader>
        {kind === "roadmap" && (
          <ol className="space-y-4 py-2">
            {(["create", "publish", "improve"] as const).map((stage) => (
              <li key={stage}>
                <p className="text-sm font-medium">{t(`landing.entry.${stage}`)}</p>
                <p className="mt-1 text-sm text-muted-foreground">{t(`landing.entry.${stage}Description`)}</p>
              </li>
            ))}
          </ol>
        )}
        <p className="text-xs text-muted-foreground">{t(`landing.entry.${kind}Note`)}</p>
      </DialogContent>
    </Dialog>
  )
}
