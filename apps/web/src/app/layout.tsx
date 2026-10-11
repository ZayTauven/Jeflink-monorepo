import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { CraftoScripts } from "@/components/crafto-scripts";

export const metadata: Metadata = {
  title: {
    default: "Jeflink — le bon pro, au bon prix, travail garanti",
    template: "%s · Jeflink",
  },
  description:
    "Plombiers, électriciens, frigoristes, équipes de ménage : des pros vérifiés à Dakar, avec un devis clair avant chaque intervention.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

// Feuilles de style du template Crafto (copiées par scripts/sync-crafto.mjs), puis nos ajouts.
const STYLESHEETS = [
  "/crafto/css/vendors.min.css",
  "/crafto/css/icon.min.css",
  "/crafto/css/style.min.css",
  "/crafto/css/responsive.min.css",
  "/crafto/demos/marketing-strategy/marketing-strategy.css",
  "/jeflink.css",
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr" className="no-js">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" crossOrigin="" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {STYLESHEETS.map((href) => (
          <link key={href} rel="stylesheet" href={href} />
        ))}
      </head>
      <body
        data-smooth-scroll="true"
        data-smooth-scroll-ease="0.08"
        data-mobile-nav-style="classic"
        className="custom-cursor bg-narvik overflow-x-hidden"
      >
        <div className="cursor-page-inner">
          <div className="circle-cursor circle-cursor-inner" />
          <div className="circle-cursor circle-cursor-outer" />
        </div>
        {children}
        <CraftoScripts />
      </body>
    </html>
  );
}
