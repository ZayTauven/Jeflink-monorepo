// Barre d'actions mobile : « Faire une demande » et « WhatsApp » restent en bas de l'écran, en CSS
// seul (aucun JS), sur l'accueil, `/[metier]` et `/[metier]/[quartier]`. Posée en dernier enfant de
// `<main>` : `sticky` la garde au bas de l'écran pendant la lecture, puis elle se pose au-dessus du
// pied de page sans le masquer. Zone de sécurité de l'appareil respectée ; `scroll-padding-bottom`
// (globals.css) l'empêche de masquer l'élément qui a le focus (WCAG 2.4.11). Masquée dès `lg`.
import { getTranslations } from "next-intl/server";

import { type CtaContext, CtaPair } from "./cta-pair";

export async function ActionBar(context: CtaContext) {
  const t = await getTranslations("site.cta");
  return (
    <div
      role="region"
      aria-label={t("barLabel")}
      className="jf-action-bar sticky bottom-0 z-20 border-t border-line bg-paper px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden"
    >
      <CtaPair {...context} variant="bar" />
    </div>
  );
}
