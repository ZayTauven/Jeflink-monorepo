# apps/web — site public, espace client/pro et console

Deux groupes de routes, chacun avec son layout racine : `src/app/(site)` (Crafto, règles ci-dessous) et `src/app/(console)` (console d'administration, voir la fin de ce fichier). URL inconnue : `src/app/global-not-found.tsx`.

Next.js (App Router), **template Crafto « Marketing strategy » pris tel quel** : mêmes balisages, classes, CSS, JS jQuery et images ; seul le récit est adapté. Lire `docs/DESIGN.md`.

- `public/crafto/` est copié depuis `references/crafto` par `scripts/sync-crafto.mjs` (lancé par `pnpm dev`/`build`, ou `pnpm --filter web crafto`). Jamais versionné, jamais modifié à la main : nos ajouts vont dans `public/jeflink.css`.
- Les scripts Crafto sont chargés **après** l'hydratation React (`components/crafto-scripts.tsx`), qui rejoue `window.load`. Conséquences :
  - navigation par `<a href>` (rechargement complet), jamais `next/link` ;
  - pas de `router.refresh()` ni de Server Action qui re-rendrait une page déjà animée par Crafto ;
  - un bouton d'envoi n'a jamais la classe `submit` (main.js l'intercepte).
- Pour porter une section Crafto : partir du HTML du template, garder les classes et `data-*` à l'identique, utiliser les petits composants de `components/crafto.tsx` (`SwitchLink`, `Pill`, `ArrowSwipe`, animations `data-anime`…).
- Données : Server Components + `lib/api.ts` (serveur uniquement). Le jeton DRF vit dans le cookie httpOnly `jeflink_token` ; il n'atteint jamais le navigateur.
- Formulaires : `<ActionForm action="/act/…">` (client) → route handler dans `src/app/act/` → API Django → JSON (avec JS) ou redirection 303 (sans JS).
- Pages : `/`, `/a-propos`, `/services` (comment ça marche), `/metiers`, `/metiers/[slug]`, `/contact`, `/connexion`, `/inscription`, `/espace`, `/espace/profil` (identité, comment me joindre, mes adresses ou profil pro), `/espace/demandes/nouvelle` (`<AddressPicker>` : mes adresses en un geste, `?adresse=` sans JavaScript), `/espace/demandes/[id]`.
- Montants via `formatXOF`, dates via `formatDate` (heure de Dakar).
- Quartiers : `zonesByCity()` (`lib/zones.ts`) ; regroupés par ville (optgroup, intitulés) seulement quand plusieurs villes sont ouvertes.
- Code promo : champ « J'ai un code promo » à la publication (pré-rempli par `?code=`, que posent les bandeaux de campagne), carte « Code promo » sur la demande ouverte, prix après remise sur chaque devis (`with_code`).
- Images envoyées : `<ImageInput>` (`components/image-input.tsx`, site et console) réduit la photo dans le navigateur (`shrinkImage`, WebP) avant l'envoi et montre l'aperçu. Site : `/act/photo` (Mon espace, envoi dès la photo choisie) ; console : un champ fichier dans `ActionForm` fait partir l'action en multipart. `/media/…` est relayé vers l'API (`next.config.ts`).
- Documents des pros : section « Mes documents » de `/espace/profil` (`/act/documents`), fichier ouvert par `/documents/[id]` (route qui relaie l'API avec le jeton ; l'API décide de l'accès) ; examen dans la console, carte « Documents » de la fiche pro.
- Badges d'un pro : `<ProBadges>` et `<BadgesExplained>` (« Que veulent dire ces badges ? ») dans `components/pro-badges.tsx`, sur les devis et la page d'un métier.
- Jef : `components/jef-assistant.tsx` (client, au-dessus du formulaire de nouvelle demande) appelle `/act/jef` puis `/act/jef/[id]` en JSON, puis remplit les champs du formulaire et `jef_session` ; sans JavaScript, le formulaire classique reste disponible.

## Console (`/console`)

- Template **vireo** habillé Crafto (`docs/DESIGN.md › Console d'administration`). `src/vireo/` est copié depuis `references/vireo` par `scripts/sync-vireo.mjs` (lancé par `pnpm dev`/`build`/`typecheck`) : jamais versionné, jamais modifié. Nos fichiers : `src/console/` (`console.css`, `shell.tsx`, `ui.tsx`, `kit.tsx`, `modal.tsx`, `toaster.tsx`, `skeletons.tsx`, `charts.tsx`, `nav.ts`, `types.ts`…).
- Tailwind v4 n'est chargé que par `console.css` (le site garde ses feuilles Crafto). Navigation par `next/link`.
- Accès : `requireStaff()` (`lib/api.ts`) dans `(console)/console/layout.tsx` ; données via `/api/console/…` (permissions par rubrique : `ConsoleSection` / `section()` dans `console/permissions.py`).
- Menu = `src/console/nav.ts` : chaque section déclare sa rubrique (`section`), le menu et la recherche sont filtrés par `me.console_sections` ; une page refusée par l'API renvoie au tableau de bord avec un message. Une rubrique avec `lot` affiche une page « bientôt » (`[...section]/page.tsx`) tant qu'elle n'est pas construite.
- Listes = cartes (`src/console/cards.tsx`, `CardGrid`), comme les litiges ; formulaires = `src/console/forms.tsx` (`Field`, `Check` = interrupteur qui envoie « 0 » éteint, `TagsField` pour une liste de courts textes). Long formulaire (Réglages, Commissions) : `<SaveBar>` autour du bouton (« Modifications non enregistrées », Annuler). Bouton-icône : `<Tip label>` (infobulle). Message ponctuel côté navigateur : `toast()` (`toaster.tsx`), ex. `CopyCode`.
- Lecture : `consoleGet()` (`src/console/data.ts`) dans chaque page (revérifie l'accès). Filtres = `<AutoFilters base>` (`filters.tsx`) : formulaire GET appliqué tout seul (au changement, ou après une pause de frappe), bouton « Filtrer » gardé pour le cas sans JavaScript ; sous lui, `<ActiveFilters>` (une puce par filtre, `kit.tsx`) et `CardGrid clear=` pour l'état vide filtré. Tri = `<SortField>` dans les filtres (paramètre `tri`, transmis à l'API en `sort`, liste blanche côté API ; pas une puce). Onglets = liens (`kit.tsx`).
- Écriture : Server Actions permises ici (pas de Crafto). Une seule action, `consoleAction` (`src/console/actions.ts`) : `<ActionForm endpoint back ok>` poste vers une action de l'API console (liste blanche), invalide la page (`revalidatePath`), puis revient dessus avec `?ok=` ou `?erreur=`. Avec JavaScript, `ActionForm` (client, `action-form.tsx`) passe par `submitConsoleAction` : une erreur s'affiche dans le formulaire sans recharger la page (la saisie et la fenêtre restent). Le message s'affiche en toast (`Toaster`, monté par la coque, qui retire le paramètre de l'adresse) ; `<Flash>` ne sert plus que sans JavaScript. Action risquée = `<ReasonAction>` : fenêtre de confirmation, motif obligatoire. Un champ nommé `nom[]` part en tableau (cases à cocher multiples, `Picks`).
- Fenêtres : `<Modal trigger title>` (`src/console/modal.tsx`, `<dialog>` natif, fond flouté) pour toute confirmation, tout ajout ou toute modification hors page ; elle se referme au retour de l'action. Sans JavaScript, son bouton déplie le contenu en dessous. Jamais de `<details>` en panneau flottant.
- Chargement : chaque dossier de page a son `loading.tsx` (squelette `ListSkeleton`, `DetailSkeleton` ou `DashboardSkeleton`, `src/console/skeletons.tsx`). Liens qui ne changent que l'adresse (onglets, pages, période) : `<LinkPending />` dedans (barre en haut de l'écran).
- Exports CSV : `(console)/console/export/[name]/route.ts` relaie l'API avec le jeton (exports et filtres connus seulement, jamais depuis un autre site).
- Une `page.tsx` n'exporte que sa page et ses métadonnées : les aides partagées vont dans `src/console/` (`coupons.ts`, `money.ts`, `text.ts`).

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
