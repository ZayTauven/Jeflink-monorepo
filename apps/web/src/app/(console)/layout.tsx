import type { Metadata, Viewport } from "next";
import Script from "next/script";
import type { ReactNode } from "react";

import "@/console/console.css";
import { THEME_SCRIPT } from "@/console/theme";

export const metadata: Metadata = {
  title: { default: "Console", template: "%s · Console Jeflink" },
  icons: { icon: "/icon.svg" },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#edece3" },
    { media: "(prefers-color-scheme: dark)", color: "#121212" },
  ],
};

/** Document de la console : template vireo habillé Crafto (src/console/console.css). */
export default function ConsoleRootLayout({ children }: { children: ReactNode }) {
  return (
    // Le script de thème modifie <html> avant l'hydratation : écart voulu.
    <html lang="fr" suppressHydrationWarning>
      <head>
        <Script id="jf-console-theme" strategy="beforeInteractive">
          {THEME_SCRIPT}
        </Script>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Funnel+Display:wght@400..700&family=Inter:wght@400;500;600;700&display=swap"
        />
        {/* Police d'icônes du site (Bootstrap Icons, copiée avec Crafto). */}
        <link rel="stylesheet" href="/crafto/css/icon.min.css" />
      </head>
      <body>{children}</body>
    </html>
  );
}
