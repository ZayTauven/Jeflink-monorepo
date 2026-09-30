// Génère generated/tokens.css (variables --jf-*) et generated/theme.css (Tailwind v4)
// depuis src/tokens.ts, après avoir vérifié les contrastes AA.
// `--check` : ne réécrit rien, échoue si generated/ n'est pas à jour (CI, ship-check).
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { contrastRatio } from "../src/contrast.ts";
import { contrastPairs, dark, font, light, radius, shadow } from "../src/tokens.ts";
import type { ColorToken, Palette } from "../src/tokens.ts";

const outDir = join(dirname(fileURLToPath(import.meta.url)), "..", "generated");
const header =
  "/* GÉNÉRÉ par packages/ui-tokens/scripts/build.ts depuis src/tokens.ts — ne pas éditer. */\n";

const failures: string[] = [];
for (const [themeName, palette] of [
  ["clair", light],
  ["sombre", dark],
] as const) {
  for (const { fg, bg, min } of contrastPairs) {
    const ratio = contrastRatio(palette[fg], palette[bg]);
    if (ratio < min)
      failures.push(`${themeName} : ${fg} sur ${bg} = ${ratio.toFixed(2)} (min ${min})`);
  }
}
if (failures.length > 0) {
  console.error(`Contrastes AA non tenus :\n  ${failures.join("\n  ")}`);
  process.exit(1);
}

const colorNames = Object.keys(light) as ColorToken[];
const colorVars = (palette: Palette) =>
  colorNames.map((name) => `  --jf-${name}: ${palette[name]};`).join("\n");

const tokensCss = `${header}
:root {
${colorVars(light)}
  --jf-radius: ${radius.card};
  --jf-radius-pill: ${radius.pill};
  --jf-shadow-overlay: ${shadow.overlay};
  --jf-font-display: ${font.display.stack};
  --jf-font-text: ${font.text.stack};
  color-scheme: light;
}

/* Console uniquement : <html data-theme="dark">. */
[data-theme="dark"] {
${colorVars(dark)}
  color-scheme: dark;
}
`;

// Les palettes par défaut de Tailwind sont retirées : seules les classes Jeflink existent
// (bg-accent, text-ink-muted, rounded-card…). Une couleur hors tokens ne compile pas en classe.
const themeCss = `${header}
@theme {
  --color-*: initial;
  --radius-*: initial;
  --shadow-*: initial;
  --font-*: initial;
}

@theme inline {
${colorNames.map((name) => `  --color-${name}: var(--jf-${name});`).join("\n")}
  --radius-card: var(--jf-radius);
  --radius-pill: var(--jf-radius-pill);
  --shadow-overlay: var(--jf-shadow-overlay);
  --font-display: var(--jf-font-display);
  --font-sans: var(--jf-font-text);
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
`;

const outputs = { "tokens.css": tokensCss, "theme.css": themeCss };

if (process.argv.includes("--check")) {
  const stale = Object.entries(outputs)
    .filter(([file, content]) => {
      const path = join(outDir, file);
      return !existsSync(path) || readFileSync(path, "utf8") !== content;
    })
    .map(([file]) => file);
  if (stale.length > 0) {
    console.error(
      `generated/ n'est pas à jour (${stale.join(", ")}) : lance \`pnpm --filter @jeflink/ui-tokens build\`.`,
    );
    process.exit(1);
  }
  console.log("ui-tokens : contrastes AA ok, generated/ à jour.");
} else {
  mkdirSync(outDir, { recursive: true });
  for (const [file, content] of Object.entries(outputs)) writeFileSync(join(outDir, file), content);
  console.log(`ui-tokens : contrastes AA ok, ${Object.keys(outputs).join(" + ")} générés.`);
}
