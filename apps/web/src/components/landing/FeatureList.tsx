import { useTranslation } from "react-i18next"

import type { Resources } from "@/lib/i18n/locales/en"

export function FeatureList({ className }: { className: string }) {
  const { t } = useTranslation()
  const features = t("landing.features", { returnObjects: true }) as Resources["landing"]["features"]

  return (
    <dl className={className}>
      {features.map(({ title, description }) => (
        <div key={title}>
          <dt className="text-sm font-medium text-foreground">{title}</dt>
          <dd className="mt-1 text-sm leading-5 text-muted-foreground">{description}</dd>
        </div>
      ))}
    </dl>
  )
}
