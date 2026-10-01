import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), payment=(), usb=()" },
  ...(process.env.NODE_ENV === "production"
    ? [{ key: "Strict-Transport-Security", value: "max-age=31536000" }]
    : []),
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Django exige la barre finale : un 308 de Next casserait les POST du BFF. Les pages, elles,
  // sont ramenées à leur forme sans barre par src/proxy.ts (une seule URL par page).
  skipTrailingSlashRedirect: true,
  // Paquets du monorepo publiés en TypeScript source.
  transpilePackages: ["@jeflink/api-client", "@jeflink/ui-tokens"],
  headers: async () => [
    { source: "/:path*", headers: securityHeaders },
    // `/connexion?next=…` : le chemin de retour ne part jamais vers un autre site (spec 001, web 1).
    {
      source: "/connexion/:path*",
      headers: [{ key: "Referrer-Policy", value: "same-origin" }],
    },
  ],
};

export default withNextIntl(nextConfig);
