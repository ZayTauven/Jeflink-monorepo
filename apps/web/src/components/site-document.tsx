import type { ReactNode } from "react";

import { CraftoScripts } from "./crafto-scripts";

// Feuilles de style du template Crafto (copiées par scripts/sync-crafto.mjs), puis nos ajouts.
const STYLESHEETS = [
  "/crafto/css/vendors.min.css",
  "/crafto/css/icon.min.css",
  "/crafto/css/style.min.css",
  "/crafto/css/responsive.min.css",
  "/crafto/demos/marketing-strategy/marketing-strategy.css",
  "/jeflink.css",
];

/** Document HTML du site public (layout du groupe `(site)` et page 404 globale). */
export function SiteDocument({ children }: { children: ReactNode }) {
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
