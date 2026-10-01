import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), payment=(), usb=()" },
  ...(process.env.NODE_ENV !== "development"
    ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]
    : []),
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Django exige la barre finale : un 308 de Next casserait les POST du BFF. Les pages, elles,
  // sont ramenées à leur forme sans barre par src/proxy.ts (une seule URL par page).
  skipTrailingSlashRedirect: true,
  experimental: {
    // Pas de cache Turbopack persistant au build : nos builds (CI, image) partent de zéro, et ce
    // cache garde un instantané de l'environnement du build (revue web 1, m-6).
    turbopackFileSystemCacheForBuild: false,
  },
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
