// « Votre quartier » côté serveur : les libellés viennent de i18n, les champs de ZoneSearchFields.
import { getTranslations } from "next-intl/server";

import { ZoneSearchFields } from "./zone-search-fields";

export { ZONE_QUERY_MAX_LENGTH } from "./zone-search-fields";

export async function ZoneSearchForm({
  tradeSlug,
  id,
  className,
}: {
  /** Slug du métier courant, transmis en champ caché (`metier`) ; absent sur la 404 générale. */
  tradeSlug?: string | null;
  /** `id` du champ : unique sur la page. */
  id?: string;
  className?: string;
}) {
  const t = await getTranslations("site.search");
  return (
    <ZoneSearchFields
      labels={{ label: t("label"), example: t("example"), submit: t("submit") }}
      {...(tradeSlug !== undefined ? { tradeSlug } : {})}
      {...(id !== undefined ? { id } : {})}
      {...(className !== undefined ? { className } : {})}
    />
  );
}
