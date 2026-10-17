import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Site et console ont chacun leur layout racine : 404 globale dans app/global-not-found.tsx.
  experimental: {
    globalNotFound: true,
    // Formulaires de la console avec une image (8 Mo au plus côté API, plus l'enveloppe).
    serverActions: { bodySizeLimit: "9mb" },
  },
  // Images envoyées (photos de profil, métiers) : servies par l'API, sous la même adresse que le site.
  rewrites: async () => [
    {
      source: "/media/:path*",
      destination: `${process.env.API_URL ?? "http://127.0.0.1:8000"}/media/:path*`,
    },
  ],
  headers: async () => [
    {
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      ],
    },
    // Fichiers privés (photos des demandes, documents des pros) : aucune adresse transmise.
    // Après la règle générale : à clé égale, la dernière l'emporte.
    ...["/photos/:path*", "/documents/:path*"].map((source) => ({
      source,
      headers: [{ key: "Referrer-Policy", value: "no-referrer" }],
    })),
  ],
};

export default nextConfig;
