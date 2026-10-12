import { getCampaigns } from "@/lib/api";
import { formatDate, formatXOF } from "@/lib/format";
import type { Campaign } from "@/lib/types";

/** Conditions en clair : le client sait à quoi s'attendre avant de choisir un devis. */
function terms(c: Campaign): string {
  const t = c.terms;
  const parts: string[] = [];
  if (t.min_amount) parts.push(`Devis d'au moins ${formatXOF(t.min_amount)}.`);
  if (t.max_discount) parts.push(`Remise de ${formatXOF(t.max_discount)} au maximum.`);
  if (t.first_order_only) parts.push("Première mission sur Jeflink seulement.");
  if (t.ends_on) parts.push(`Jusqu'au ${formatDate(t.ends_on)}.`);
  if (c.coupon_code) parts.push("Saisissez le code au moment de choisir votre devis.");
  return parts.join(" ");
}

/** Lien interne seulement (même règle que l'API) : jamais « //autre-site » ni « javascript: ». */
function internal(url: string): boolean {
  return url.startsWith("/") && !url.startsWith("//") && !url.startsWith("/\\");
}

/**
 * Bandeau des campagnes en cours (console › Campagnes), dans l'esprit Crafto : carte sombre,
 * code promo en pointillés orange, bouton orange. Rien n'est rendu sans campagne en ligne.
 */
export async function CampaignBanner({
  placement,
  className = "",
}: {
  placement: "home" | "request";
  className?: string;
}) {
  const campaigns = await getCampaigns(placement);
  if (campaigns.length === 0) return null;
  const banners = (
    <>
      {campaigns.map((c) => {
        const conditions = terms(c);
        return (
          <aside
            key={c.id}
            className="jf-campaign bg-dark-gray border-radius-20px p-30px sm-p-25px mb-20px d-flex flex-column flex-md-row align-items-md-center gap-3"
            aria-label={c.title}
          >
            <div className="flex-grow-1">
              <span className="d-block alt-font fs-22 fw-500 ls-minus-05px text-white mb-5px">
                {c.title}
              </span>
              <p className="mb-0 text-white opacity-8">{c.message}</p>
              {conditions && <p className="mb-0 mt-5px fs-14 text-white opacity-6">{conditions}</p>}
            </div>
            {c.coupon_code && (
              <span className="jf-campaign__code">
                <span className="visually-hidden">Code promo&nbsp;: </span>
                {c.coupon_code}
              </span>
            )}
            {c.cta_label && internal(c.cta_url) && (
              <a
                href={c.cta_url}
                className="btn btn-medium btn-base-color btn-rounded btn-box-shadow align-self-start align-self-md-center"
              >
                {c.cta_label}
              </a>
            )}
          </aside>
        );
      })}
    </>
  );
  // Section de page (accueil) : même gabarit que les autres sections Crafto.
  if (!className) return banners;
  return (
    <section className={className}>
      <div className="container-fluid">{banners}</div>
    </section>
  );
}
