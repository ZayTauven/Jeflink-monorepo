// « Votre quartier » : formulaire GET, sans JS, vers /recherche (spec 006). Libellé visible et
// exemple. Le texte tapé reste dans la requête : il n'est ni enregistré, ni journalisé, ni recopié
// dans le message WhatsApp (il pourrait contenir une adresse ou un numéro).
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";
import { SITE_PATHS } from "@/lib/site/paths";

/** Longueur maximale du texte tapé ; `/recherche` la revérifie côté serveur. */
export const ZONE_QUERY_MAX_LENGTH = 40;

export async function ZoneSearchForm({
  tradeSlug,
  id = "quartier",
  className = "",
}: {
  /** Slug du métier courant, transmis en champ caché (`metier`) ; absent sur la 404 générale. */
  tradeSlug?: string | null;
  /** `id` du champ : unique sur la page. */
  id?: string;
  className?: string;
}) {
  const t = await getTranslations("site.search");
  const hintId = `${id}-exemple`;
  return (
    <form action={SITE_PATHS.search} method="get" className={className}>
      {tradeSlug ? <input type="hidden" name="metier" value={tradeSlug} /> : null}
      <label htmlFor={id} className="block text-base font-medium text-ink">
        {t("label")}
      </label>
      <p id={hintId} className="mt-1 text-sm text-ink-muted">
        {t("example")}
      </p>
      <div className="mt-2 flex flex-col gap-3 sm:flex-row">
        <input
          id={id}
          name="quartier"
          type="search"
          required
          maxLength={ZONE_QUERY_MAX_LENGTH}
          autoComplete="off"
          enterKeyHint="search"
          spellCheck={false}
          aria-describedby={hintId}
          className="min-h-12 w-full rounded-card border border-line-strong bg-surface px-4 text-base text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong sm:max-w-sm"
        />
        <Button type="submit" variant="secondary">
          {t("submit")}
        </Button>
      </div>
    </form>
  );
}
