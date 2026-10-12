import type { Metadata } from "next";

import { SiteDocument } from "@/components/site-document";

import NotFound from "./(site)/not-found";

// URL inconnue : le site et la console ont chacun leur layout racine, Next sert donc cette page
// hors de tout layout (option experimental.globalNotFound).
export const metadata: Metadata = {
  title: "Page introuvable · Jeflink",
  icons: { icon: "/icon.svg" },
};

export default function GlobalNotFound() {
  return (
    <SiteDocument>
      <NotFound />
    </SiteDocument>
  );
}
