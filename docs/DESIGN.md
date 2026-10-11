# Jeflink — Direction visuelle

## Principe (décision Zay, 2026-10-11)

Le site reprend **tel quel** le template Crafto « Marketing strategy » (`references/crafto/demo-marketing-strategy*.html`) : architecture des pages, balisage, classes, CSS, JavaScript (jQuery, Swiper, anime.js, Skrollr…) et images. Seul le **récit** est réécrit pour Jeflink. Les points incohérents sont listés plus bas et seront peaufinés ensuite, un par un.

| Page Crafto                  | Page Jeflink                              |
| ---------------------------- | ----------------------------------------- |
| `demo-marketing-strategy`    | `/` accueil                               |
| `…-about-us`                 | `/a-propos`                               |
| `…-services`                 | `/services` (comment ça marche)           |
| `…-portfolio`                | `/metiers` (un métier = un projet)        |
| `…-single-project-slider`    | `/metiers/[slug]`                         |
| `…-contact`                  | `/contact` (formulaire fonctionnel)       |
| (cartes titre + formulaires) | `/connexion`, `/inscription`, `/espace/…` |

## Règles de fidélité

- Partir du HTML Crafto ; garder classes, `data-anime`, `data-slider-options`, `data-parallax-*` à l'identique. Les sections répétitives deviennent des `.map()` sur des données, sans changer le balisage produit.
- Couleurs, typographies, rayons : ceux du template (`--base-color: #f55608`, Funnel Display + Inter, rayons 20 px). On ne crée pas de nouveau système de tokens.
- Ce qui manque au template (logo, statuts de demande, cases à cocher, étoiles) va dans `apps/web/public/jeflink.css`, dans l'esprit Crafto.
- Copie : ton direct, chaleureux, concret ; montants `15 000 F CFA` ; espace insécable avant `? ! : ;`.

## Logo

Logo **provisoire** dessiné d'après `references/assets-originaux/concept logo jeflink.jpg` : un toit dont l'avancée devient une étincelle à quatre branches, avec une petite étincelle évidée au centre. Composant `apps/web/src/components/logo.tsx` (SVG, prend la couleur du texte), favicon `apps/web/public/icon.svg`. À remplacer par le logo définitif quand il existera. Aucun logo tiers (Orange Money, Wave…) ne représente Jeflink.

## À peaufiner (incohérences connues, par priorité)

1. **Logos de vraies marques** présentés comme clients (bandeaux de l'accueil et de l'À propos : Thumbtack, Nextdoor, Eventbrite…) et **badges de notes Trustpilot / Clutch** (4,9 et 4,8) dans l'accroche : à retirer ou remplacer avant toute diffusion, ce sont de faux partenariats et de fausses notes.
2. **Photos** : scènes de bureau occidentales et objets 3D abstraits du template. À remplacer par des artisans et intérieurs au Sénégal (banque d'images ci-dessous ; l'ancienne version avait déjà des visuels métier optimisés au tag `archive/avant-simplification`, `apps/web/public/images/site/`).
3. **Pastille tournante** (`demo-marketing-strategy-08.png`) et vignette « avatars » (`…-about-08.png`) : textes et visages du template.
4. **Vidéo de l'accueil** : le template n'est livré qu'avec l'image d'attente ; les boutons « lecture » mènent vers `/services` ou l'inscription pro.
5. **Mobile** : barre d'actions « Faire une demande » + WhatsApp, bandeaux défilants avec pause (WCAG 2.2.2), animations réduites si `prefers-reduced-motion`.
6. **Poids** : le JS Crafto (~0,6 Mo de plugins) et les JPG non optimisés ne conviennent pas à un réseau faible ; à alléger avant la production.

## Banque d'images

Banque locale de Zay : `C:\Users\moham\Pictures\Banque` (lire son `CLAUDE.md`, chercher dans `_catalogue/INDEX.tsv`, regarder les planches). Scènes réelles au Sénégal d'abord (`photos/metiers-services`, `photos/personnes`, `photos/immobilier`…). Copier l'image retenue dans `apps/web/public/images/`, convertie en WebP aux tailles affichées. Interdits : `photos/equipes-projets/`, un portrait présenté comme un vrai client ou un vrai pro, un logo qui suggère un partenariat inexistant.
