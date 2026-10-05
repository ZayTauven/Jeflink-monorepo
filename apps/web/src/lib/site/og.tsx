// Image Open Graph (1 200 × 630) : le titre et le logo sur un aplat `sand`, sans photo, légère
// (100 ko au plus). Couleurs : les tokens de `@jeflink/ui-tokens` (jamais une valeur en dur).
// Police : celle de `next/og` par défaut ; un fichier OFL versionné dans l'app viendra avec le
// chantier prod (téléchargement à autoriser).
import { light } from "@jeflink/ui-tokens";
import { ImageResponse } from "next/og";

export const OG_SIZE = { width: 1200, height: 630 } as const;
export const OG_CONTENT_TYPE = "image/png";

function Mark() {
  return (
    <svg
      width="120"
      height="64"
      viewBox="60 150 400 215"
      fill="none"
      strokeWidth="56"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <g stroke={light.ink}>
        <path d="M112 205H222V318" />
        <path d="M100 326 214 212" />
      </g>
      <g stroke={light.accent}>
        <path d="M300 196V310H410" />
        <path d="M308 302 422 188" />
      </g>
    </svg>
  );
}

export function renderOg(input: {
  title: string;
  brand: string;
  subtitle?: string;
}): ImageResponse {
  const long = input.title.length > 40;
  return new ImageResponse(
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        width: "100%",
        height: "100%",
        padding: 72,
        background: light.sand,
        color: light.ink,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <Mark />
        <div style={{ fontSize: 44, fontWeight: 600 }}>{input.brand}</div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div
          style={{ fontSize: long ? 72 : 92, lineHeight: 1.05, fontWeight: 600, letterSpacing: -2 }}
        >
          {input.title}
        </div>
        {input.subtitle ? (
          <div style={{ fontSize: 34, color: light["ink-muted"] }}>{input.subtitle}</div>
        ) : null}
      </div>
      <div
        style={{
          display: "flex",
          width: 160,
          height: 12,
          background: light.accent,
          borderRadius: 6,
        }}
      />
    </div>,
    { ...OG_SIZE },
  );
}
