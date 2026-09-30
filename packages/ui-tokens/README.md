# @jeflink/ui-tokens

Source unique des tokens Jeflink : `src/tokens.ts`. Valeurs et raisons dans `docs/design/DESIGN.md`.

| Export                          | Pour                                                                                                                              |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `@jeflink/ui-tokens`            | objets TS (`light`, `dark`, `radius`, `font`…) : apps Expo, graphiques                                                            |
| `@jeflink/ui-tokens/tokens.css` | variables `--jf-*`, thème sombre via `<html data-theme="dark">`                                                                   |
| `@jeflink/ui-tokens/theme.css`  | thème Tailwind v4 : `bg-accent`, `text-ink-muted`, `rounded-card`, `font-display`… Les palettes Tailwind par défaut sont retirées |

Côté Next : `@import "tailwindcss"; @import "@jeflink/ui-tokens/tokens.css"; @import "@jeflink/ui-tokens/theme.css";`
et `next/font` avec `variable: "--font-funnel-display"` / `"--font-inter"`.

Modifier un token : éditer `src/tokens.ts`, puis `pnpm --filter @jeflink/ui-tokens build`.
Le build refuse toute valeur qui casse une paire de contraste AA. `test` vérifie que `generated/` est à jour.
