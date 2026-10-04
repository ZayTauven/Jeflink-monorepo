// Note d'un pro (spec 004, web 3) : moyenne et nombre d'avis, ou « Nouveau sur Jeflink » tant que
// l'API n'en donne pas (moins de 3 avis publiés). Mot et chiffre, jamais l'étoile seule.
import type { Rating } from "@jeflink/api-client";
import { useTranslations } from "next-intl";

import { StarIcon } from "@/components/ui/icons";
import { formatAverage } from "@/lib/bookings/review";

export function RatingLine({ rating }: { rating: Rating | null | undefined }) {
  const t = useTranslations("bookings.rating");
  if (!rating) return <span className="text-sm text-ink-muted">{t("new")}</span>;
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink">
      <StarIcon filled className="size-4 text-accent" />
      <span>
        {formatAverage(rating.average)}
        <span className="sr-only"> {t("outOf")}</span>
      </span>
      <span className="font-normal text-ink-muted">{t("count", { count: rating.count })}</span>
    </span>
  );
}
