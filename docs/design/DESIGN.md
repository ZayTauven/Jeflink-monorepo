# Jeflink — Direction visuelle

**Crafto donne la voix, Vireo donne l'ossature, Jeflink donne l'âme.**

## Web public — ce qu'on prend à Crafto

Page de référence (décision Zay, 2026-09-30) : **`references/crafto/demo-marketing-strategy.html`** (+ `demos/marketing-strategy/marketing-strategy.css`). Les pages sœurs `demo-marketing-strategy-*.html` (services, about-us, contact, portfolio) servent de référence pour les pages équivalentes. `references/` est local et non versionné.

- Typographie éditoriale : très grands titres, interlignage serré, beaucoup d'air entre sections.
- Gros chiffres en preuve sociale (« 1 200 missions garanties », « 4,8/5 »).
- Bandeau défilant de métiers, cartes à grandes images arrondies, CTA en pilule.
- Sections numérotées (01, 02, 03) pour expliquer le fonctionnement.

**On remplace** : toutes les illustrations et photos par des scènes réelles au Sénégal (artisans, intérieurs, quartiers de Dakar). La copie « agence marketing » par un ton direct et chaleureux. La vidéo hero lourde par une image forte (vidéo en lecture à la demande).

## Console — dé-vibecoder Vireo

Référence locale : `references/vireo/` (Next 15, Tailwind v4, langage « Aurora » sur tokens `--ax-*`). On y lit la structure ; l'habillage Aurora et ses tokens ne sont pas repris.

On garde : la structure (sidebar + header + contenu), la command palette ⌘K, les tables denses, les pages d'auth, les états vides.

**Interdit** (c'est ce qui donne l'effet « vibecodé ») :

- Glassmorphism, fonds « aurora », blobs et dégradés décoratifs.
- Texte en dégradé, halos, lueurs.
- Emojis décoratifs dans l'interface (« Welcome back 👋 »).
- Avatars et images de remplissage (pravatar, picsum) : utiliser des initiales.
- Rangées de 6+ cartes KPI avec pourcentages verts/rouges sans contexte.
- Badges « New », « Hot » gratuits ; une icône devant chaque titre.
- Customizer de thème exposé à l'utilisateur ; 17 variantes de dashboard.
- Ombres multiples empilées ; rayons de bordure incohérents.
- Animations sans fonction ; loaders plein écran.
- Copie générique (« Supercharge your workflow », « Unlock insights »).
- Gris clair sur gris : tout texte respecte le contraste AA.

**Règles** :

- Un seul accent de couleur ; le reste en neutres.
- Bordures 1 px plutôt qu'ombres ; une seule élévation pour les overlays.
- Un écran = une question métier ; les tables d'abord, les graphiques quand ils répondent à une question.
- Montants : `25 000 F CFA` ; dates en français (`12 oct. · 14 h 30`) ; heure `Africa/Dakar`.
- États vides utiles : ils expliquent et proposent l'action suivante.

## Mobile

- Cibles tactiles ≥ 48 px ; icône + libellé (jamais d'icône seule pour une action clé).
- Bouton micro de premier rang sur tout écran de saisie.
- Statuts de mission lisibles d'un coup d'œil (couleur + mot + icône).
- Pas de dépendance à la couleur seule.

## Tokens

Source unique : `packages/ui-tokens`. Accent et polices **validés** (direction Crafto « marketing-strategy », 2026-09-30) ; neutres et statuts à confirmer avec la charte complète. Tous les ratios ci-dessous sont calculés (WCAG 2.1).

### Couleur

| Token                | Valeur    | Usage                                                                                      | Contraste vérifié                                                  |
| -------------------- | --------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ |
| `--jf-ink`           | `#14171C` | texte principal                                                                            | 15,2:1 sur `sand`                                                  |
| `--jf-ink-muted`     | `#5B6270` | texte secondaire                                                                           | 5,8:1 sur `paper` · 5,2:1 sur `sand`                               |
| `--jf-paper`         | `#FAF8F4` | fond clair chaud                                                                           | —                                                                  |
| `--jf-sand`          | `#EDECE3` | fond de section alterné (le « narvik » de Crafto)                                          | —                                                                  |
| `--jf-surface`       | `#FFFFFF` | cartes                                                                                     | —                                                                  |
| `--jf-line`          | `#E6E1D8` | bordures 1 px                                                                              | —                                                                  |
| `--jf-accent`        | `#FF6600` | **l'accent** : fond du CTA principal, pastilles, icônes, surlignage, flèche du logo        | ne jamais l'utiliser comme couleur de texte sur fond clair (2,9:1) |
| `--jf-on-accent`     | `#14171C` | libellé posé sur `accent`                                                                  | 6,1:1 ✓                                                            |
| `--jf-accent-strong` | `#B84800` | texte et liens orange sur fond clair, état pressé, anneau de focus, bouton à libellé blanc | 5,3:1 sur blanc · 5,0:1 sur `paper`                                |
| `--jf-success`       | `#15803D` | statuts uniquement (+ mot + icône)                                                         | 5,0:1 sur blanc                                                    |
| `--jf-warning`       | `#A16207` | statuts uniquement ; volontairement jaune-brun pour ne pas se confondre avec l'accent      | 4,9:1 sur blanc                                                    |
| `--jf-danger`        | `#B91C1C` | statuts uniquement                                                                         | 6,5:1 sur blanc                                                    |
| `--jf-info`          | `#1D6FB8` | statuts uniquement                                                                         | 5,2:1 sur blanc                                                    |

Pourquoi `#FF6600` et pas le `#F55608` de Crafto : c'est l'orange exact du logo (flèche orange de `references/assets-originaux/Jeflink-illustrations (2).png`). Même direction, une seule couleur de marque.

**Piège AA** : l'orange vif avec un libellé blanc (2,9:1) échoue. Le CTA principal est donc soit `accent` + libellé `on-accent` (sombre, écho au logo noir + orange), soit `accent-strong` + libellé blanc. Choisir l'un des deux et s'y tenir partout.

Mode sombre (console uniquement) : mêmes noms de tokens redéfinis. `accent` reste `#FF6600` (5,6:1 sur `#1B1F26`, utilisable en texte), `ink-muted` devient `#A3A9B5` (7,0:1). Jamais de couleur en dur dans un composant.

### Typographie

| Rôle    | Police                                                   | Détail                                                                                                                                              |
| ------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Display | **Funnel Display** (Google Fonts, OFL, variable 300–800) | titres web et grands titres mobiles, jamais sous 20 px ; interlignage serré ~1,05–1,1 ; letter-spacing légèrement négatif sur les très grands corps |
| Texte   | **Inter** (Google Fonts, OFL)                            | tout le reste : corps, UI, formulaires, tables, console                                                                                             |

- Web : `next/font/google` (auto-hébergé, `display: swap`, sous-ensembles `latin` + `latin-ext`), uniquement les poids utilisés.
- Mobile : fichiers embarqués via `expo-font`. Inter 400/500/600 + Funnel Display 600.
- Couverture vérifiée pour le wolof et le français : `ŋ Ŋ ë é à ó ñ ç ’ « »` présents dans les deux polices.
- **Espaces dans les montants** : Funnel Display n'a pas l'espace fine insécable U+202F, que `Intl.NumberFormat('fr')` insère dans « 25 000 ». Les helpers de formatage (`formatXof`, `money.format_xof`) utilisent U+00A0, présent dans les deux polices.

### Forme

| Token              | Valeur  | Usage                   |
| ------------------ | ------- | ----------------------- |
| `--jf-radius`      | `10px`  | cartes, champs, images  |
| `--jf-radius-pill` | `999px` | boutons, puces, filtres |

Aucune autre valeur de rayon. Bordures 1 px `line` ; une seule ombre, réservée aux overlays.
