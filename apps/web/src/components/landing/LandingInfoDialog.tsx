import { useTranslation } from "react-i18next"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

/** Community preview until the real community destination is connected. */
export function LandingInfoDialog({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <Dialog>
      <DialogTrigger className={className}>
        {t("landing.entry.community")}
      </DialogTrigger>
      <DialogContent className="rounded-lg sm:max-w-md">
        <DialogHeader>
          <p className="text-xs text-muted-foreground">{t("landing.entry.preview")}</p>
          <DialogTitle>{t("landing.entry.communityTitle")}</DialogTitle>
          <DialogDescription>{t("landing.entry.communityDescription")}</DialogDescription>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">{t("landing.entry.communityNote")}</p>
      </DialogContent>
    </Dialog>
  )
}
