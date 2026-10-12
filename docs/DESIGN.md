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
- **On prouve, on ne réclame pas** : jamais « faites-nous confiance » ni « pros de confiance ». On montre la preuve : « pros vérifiés », « prix écrit dans le devis », « avis après mission ».

## Logo

Logo **provisoire** dessiné d'après `references/assets-originaux/concept logo jeflink.jpg` : un toit dont l'avancée devient une étincelle à quatre branches, avec une petite étincelle évidée au centre. Composant `apps/web/src/components/logo.tsx` (SVG, prend la couleur du texte), favicon `apps/web/public/icon.svg`. À remplacer par le logo définitif quand il existera. Aucun logo tiers (Orange Money, Wave…) ne représente Jeflink.

## Hero : le « main show » Jeflink

La boule blanche animée de Crafto est une vidéo non livrée avec le template. Jeflink a la sienne, `apps/web/src/components/hero-show.tsx` : une sphère de disques blancs empilés dont les bords ondulent et tournent lentement (l'esprit de la boule Crafto), posée sur la lueur orange du concept de logo, avec l'étincelle Jeflink en orbite. Canvas 2D, aucune dépendance, image fixe si `prefers-reduced-motion`, pause hors écran. Idées puisées sur 21st.dev (sphères en lignes de latitude, isolignes).

## Images

- **Décors du template** (objets 3D, pastilles tournantes, laurier) : gardés tels quels.
- **Visuels d'ambiance** (abstraits sombres ou clairs) : gardés quand ils servent le récit.
- **Photos de personnes et de métiers** : remplacées par les images Jeflink (`references/assets-originaux`), produites par `apps/web/scripts/build-images.py` dans `apps/web/public/images/` (WebP aux tailles du template, provenance ligne par ligne dans `PLAN`). Les photos phares reçoivent le traitement « anneaux orange » du template (fonction `anneaux`).
- Exception voulue par Zay : la page Contact garde pour l'instant ses photos Crafto.
- **Cartes empilées de l'accueil** : rendus Gemini générés d'après nos prompts (objet unique, studio sombre, accent orange), recomposés par `carte()` dans `build-images.py` (sujet à droite, fondu et voile à gauche pour le texte blanc). Les shootings photo réels et la DA définitive les remplaceront.
- **Cartes métier claires** : dégradé sombre en bas (`bas()`) pour la lisibilité du titre blanc.

## Mobile et poids

- **Hero** : sur mobile, la sphère quitte l'arrière-plan du texte et prend sa place entre le bouton et le séparateur (`.jf-hero-stage`).
- **Barre d'actions** (`components/mobile-actions.tsx`) sous 768 px : « Faire une demande » + WhatsApp (numéro lu côté serveur dans `SUPPORT_WHATSAPP_NUMBER`, bouton masqué s'il manque). Masquée dans l'espace connecté.
- **Bandeaux défilants** : bouton pause (`components/marquee-pause.tsx`, WCAG 2.2.2), arrêtés d'office si `prefers-reduced-motion`.
- **Images Crafto** : servies en WebP par l'optimiseur de Next via `opt()` (`components/crafto.tsx`). Accueil 1,2 Mo → 0,3 Mo d'images.
- **JS Crafto** (~260 Ko gzippés) : gardé tel quel. Retirer les plugins inutiles du `vendors.min.js` minifié ne fait gagner que ~8 % pour une chirurgie fragile ; le vrai allègement passera par une reconstruction des plugins avant la production.

## À peaufiner (incohérences connues)

1. **Logos de marques** (bandeaux de l'accueil et de l'À propos) : gardés pour l'instant, à remplacer par les vrais partenaires de Jeflink.
2. **JS Crafto** : reconstruire un bundle avec les seuls plugins utilisés avant la production.

## Banque d'images

Banque locale de Zay : `C:\Users\moham\Pictures\Banque` (lire son `CLAUDE.md`, chercher dans `_catalogue/INDEX.tsv`, regarder les planches). Scènes réelles au Sénégal d'abord (`photos/metiers-services`, `photos/personnes`, `photos/immobilier`…). Copier l'image retenue dans `apps/web/public/images/`, convertie en WebP aux tailles affichées. Interdits : `photos/equipes-projets/`, un logo qui suggère un partenariat inexistant. Les visages de `assets-originaux/Faces` servent d'avatars aux **comptes de démo** uniquement ; avant toute mise en ligne, seuls de vrais clients et pros, avec leur accord, apparaissent.
