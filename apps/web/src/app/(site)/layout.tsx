import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SiteDocument } from "@/components/site-document";

export const metadata: Metadata = {
  title: {
    default: "Jeflink — le bon pro, au bon prix, travail garanti",
    template: "%s · Jeflink",
  },
  description:
    "Plombiers, électriciens, frigoristes, équipes de ménage : des pros vérifiés à Dakar, avec un devis clair avant chaque intervention.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function SiteLayout({ children }: { children: ReactNode }) {
  return <SiteDocument>{children}</SiteDocument>;
}
