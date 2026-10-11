# Jeflink — Document produit

> Statut : v0.1 — synthèse de cadrage. Propriétaire : Zay.

## 1. Vision

Jeflink connecte particuliers et entreprises au Sénégal avec des pros vérifiés (plomberie, électricité, froid/clim, électroménager, ménage, petits travaux…).
La promesse tient en une phrase : **le bon pro, au bon prix, travail garanti.**

Demandium est un bon inventaire fonctionnel, mais il est pensé pour un marché où l'adresse est fiable, la carte bancaire courante, le client lit et tape, et la confiance envers une marketplace va de soi. À Dakar, aucune de ces hypothèses ne tient. Jeflink part donc des réalités du terrain, pas du template.

## 2. Réalités du terrain (ce qui change tout)

| Réalité                                                                                        | Conséquence produit                                                                   |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| La confiance est le frein n°1 (pro qui ne vient pas, travail bâclé, prix qui change sur place) | Garantie, preuves photo, code de fin, avenants tracés, avis vérifiés                  |
| Adressage informel : on se repère avec des lieux connus, pas des numéros de rue                | Adresse = repère + point GPS + photo du portail + note vocale                         |
| Mobile money dominant, cash encore très présent                                                | Cash + mobile money (via WiiPay) ; commission sur cash gérée par portefeuille         |
| WhatsApp est le canal par défaut, notes vocales omniprésentes                                  | WhatsApp-first, la voix comme mode de saisie principal                                |
| Français écrit, wolof parlé ; littératie variable chez les artisans                            | Interfaces icône + libellé, voix partout, traduction fr ↔ wo                          |
| Data chère, Android d'entrée de gamme, réseau instable                                         | Apps légères, hors-ligne pour les pros, SMS de repli                                  |
| Beaucoup d'artisans indépendants, souvent informels                                            | L'artisan solo est le cas par défaut ; « entreprise avec techniciens » est une option |
| Le prix se négocie ; le devis se fait souvent sur place                                        | Devis au cœur du produit, fourchettes de prix pour ancrer la négociation              |
| Contournement : après une mission, client et artisan échangent leurs numéros                   | Rendre la plateforme plus avantageuse que le contournement                            |
| Saisonnalité forte : hivernage, fortes chaleurs, fêtes                                         | Rappels et campagnes saisonnières, entretien planifié                                 |
| Diaspora importante qui finance des travaux pour la famille                                    | Commander et payer depuis l'étranger pour un proche                                   |

## 3. Personas

- **Awa, cliente à Dakar** — veut un pro fiable vite, paie en Wave/Orange Money ou cash, commande souvent par WhatsApp.
- **Moussa, client diaspora (Paris/Milan/New York)** — finance la réparation chez ses parents, veut des preuves et un prix fixé d'avance.
- **Ibou, artisan électricien solo** — Android modeste, parle wolof, écrit peu, veut plus de clients sans paperasse.
- **Fatou, gérante d'une société de nettoyage** — 8 employées, veut planifier et suivre.
- **Cheikh, technicien salarié** — reçoit ses missions, veut l'adresse, l'itinéraire et un process de clôture simple.
- **Équipe Ops Jeflink** — valide les pros, arbitre les litiges, pilote l'offre et la demande par quartier.
- _(V3)_ **Syndic / PME** — contrats de maintenance récurrents.

## 4. Verdict sur les fonctionnalités Demandium

Légende : ✅ Garder · 🔧 Adapter · ⏳ Reporter · ❌ Abandonner

### Administration

| Fonctionnalité Demandium      | Verdict     | Version Jeflink                                                                                                                                              |
| ----------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Multi-zone                    | 🔧          | Zones = polygones PostGIS par commune/quartier (Dakar d'abord). Frais de déplacement calculés sur la distance réelle, pas un forfait par zone.               |
| Commissions / abonnements     | 🔧          | V1 : commission simple (taux à arbitrer). Abonnement « Pro+ » plus tard (visibilité, copilote avancé).                                                       |
| Validation des prestataires   | 🔧 renforcé | KYC (pièce d'identité + selfie), vérification téléphone, référence terrain, badges de niveau (Vérifié → Confirmé → Expert).                                  |
| Bannières, campagnes, coupons | 🔧 allégé   | Codes promo + parrainage en V1 ; bannières et campagnes ciblées en V2.                                                                                       |
| Rapports et analyses          | 🔧          | KPIs opérationnels : délai du 1er devis, taux de complétion, litiges, annulations. Les recherches sans résultat deviennent un signal de recrutement de pros. |
| Portefeuilles, retraits       | 🔧          | Grand livre comptable, versements vers mobile money via WiiPay, libération après la fenêtre de garantie.                                                     |
| Rôles et permissions          | ✅          | RBAC Ops fin.                                                                                                                                                |

### Prestataire

| Fonctionnalité          | Verdict      | Version Jeflink                                                                                             |
| ----------------------- | ------------ | ----------------------------------------------------------------------------------------------------------- |
| Tableau de bord         | 🔧           | 4 indicateurs maximum, orientés action (missions du jour, devis en attente, solde, note).                   |
| Catalogue et tarifs     | 🔧           | Prix « à partir de » + fourchette ; le prix final vient du devis.                                           |
| Gestion des techniciens | 🔧           | Optionnelle, activée pour les entreprises. L'artisan solo est son propre technicien.                        |
| Enchères / devis        | ✅ au centre | Devis limités à 3 par demande pour éviter la course au moins-disant ; devis sur place possible via avenant. |
| Messagerie              | 🔧           | Chat avec notes vocales et photos, notifications relayées sur WhatsApp.                                     |

### Client

| Fonctionnalité           | Verdict     | Version Jeflink                                                                                                                              |
| ------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Connexions multiples     | 🔧          | OTP téléphone (SMS/WhatsApp) en principal, Google en option. Facebook abandonné. « Invité » = OTP téléphone sans création de profil complet. |
| Recherche et filtres     | 🔧          | Recherche en langage naturel + par métier + par quartier ; adressage par repères.                                                            |
| Demandes sur mesure      | ✅ fusionné | Devient le parcours principal : la demande (texte, voix, photos) est structurée par l'IA.                                                    |
| Suivi en temps réel      | ✅          | Étapes claires ; position du technicien partagée uniquement pendant « en route ».                                                            |
| Paiements                | 🔧          | Cash + mobile money via WiiPay ; acompte possible ; séquestre avec la Garantie Jeflink.                                                      |
| Fidélité et parrainage   | 🔧          | Parrainage en V1 ; points de fidélité reportés.                                                                                              |
| Favoris                  | ✅          | « Mon plombier » : re-réserver le même pro en un geste.                                                                                      |
| Modification de commande | ✅ renforcé | Avenant au devis, validé par le client dans l'app : fin des prix qui changent sans trace.                                                    |
| Avis et notes            | 🔧          | Uniquement après mission clôturée par code ; critères (ponctualité, qualité, propreté, prix respecté) ; avis vocal possible.                 |

### Technicien

| Fonctionnalité                | Verdict        | Version Jeflink                              |
| ----------------------------- | -------------- | -------------------------------------------- |
| Tâches, détails, GPS, statuts | ✅             | Dans l'app Pro unique, avec mode hors-ligne. |
| Code OTP de fin               | ✅ obligatoire | + photos avant/après obligatoires.           |

### Transversal

| Fonctionnalité                          | Verdict     | Version Jeflink                                                                                 |
| --------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------- |
| Multi-langue                            | 🔧          | `fr` + `wo`. Le wolof passe surtout par la voix.                                                |
| RTL                                     | ❌          | Arabe non prioritaire (l'architecture i18n n'empêche pas de l'ajouter).                         |
| Mode sombre                             | 🔧          | Console uniquement en V1.                                                                       |
| SEO des services                        | ✅ renforcé | Pages métier × quartier (`/plombier/ouakam`), données structurées.                              |
| Deep linking                            | ✅          | + liens partageables sur WhatsApp avec aperçu soigné.                                           |
| Dizaines de passerelles internationales | ❌          | Un seul point d'entrée : WiiPay (+ cash). Carte internationale seulement pour la diaspora (V3). |

## 5. Innovations

### Signatures (ce qui définit Jeflink)

**S1. Garantie Jeflink.** Le paiement en ligne est bloqué jusqu'à la clôture (code de fin + photos après), puis une fenêtre de contestation de 48 h. Reprise gratuite sous 7 jours si le défaut est avéré, médiation Ops sinon.

> ⚠️ Détenir des fonds de tiers relève de la réglementation de la monnaie électronique (BCEAO). Le séquestre doit être porté par WiiPay ou un établissement agréé, pas par Jeflink directement. À valider juridiquement avant V2.

**S2. WhatsApp-first.** Un agent conversationnel sur WhatsApp Business permet de créer une demande (texte ou vocal), recevoir les devis, confirmer, payer par lien et donner son avis sans installer l'app. L'app reste le meilleur parcours, pas un passage obligé.

**S3. Diaspora.** Commander et payer depuis l'étranger pour un proche au Sénégal. Le proche reçoit le code de fin ; le payeur reçoit photos avant/après et facture. Prix fixé avant intervention.

### Couche IA

| #   | Innovation              | Pour qui            | Principe                                                                                                                                                                    |
| --- | ----------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IA1 | **Demande vocale**      | Client              | Note vocale (fr ou wo) + photos → demande structurée (métier, symptômes, urgence, questions manquantes), que le client valide.                                              |
| IA2 | **Fourchette de prix**  | Client + Pro        | À partir de la demande, des photos et de l'historique du quartier : « habituellement 15 000 – 25 000 F CFA à Ouakam ». Ancre la négociation, réduit les litiges.            |
| IA3 | **Copilote Pro**        | Artisan             | Note vocale → brouillon de devis (main d'œuvre, pièces, déplacement), résumé de la demande, traduction fr ↔ wo, facture propre générée. Toujours validé par le pro.         |
| IA4 | **Matching expliqué**   | Client + Ops        | Score multi-critères (temps de trajet réel, spécialité, fiabilité, charge, prix, favori) avec la raison affichée : « Proche de vous, 38 missions clim, arrive en ~25 min ». |
| IA5 | **Adresse par repères** | Client + Technicien | Normalise « derrière la mosquée, portail vert » + point GPS + photo en une fiche d'accès claire pour le technicien.                                                         |
| IA6 | **Copilote Ops**        | Ops                 | Résumé des litiges avec preuves (chat, photos, avenants), modération des avis, détection de faux comptes et d'avis croisés.                                                 |
| IA7 | **Demande non servie**  | Ops                 | « 30 recherches “vitrier” à Keur Massar ce mois, 0 pro » → liste de recrutement priorisée.                                                                                  |

Principes communs : l'IA propose, l'humain valide ; toujours un repli sans IA ; aucune décision financière ou de sanction prise automatiquement.

> ⚠️ La reconnaissance vocale du wolof est encore inégale. À benchmarker avant de promettre. Repli : si la confiance est faible, la note vocale originale est transmise telle quelle au pro avec un résumé partiel.

### Écosystème

- **Passeport Pro** — historique de missions vérifiées (photos, avis, ponctualité) formant un profil public crédible. Avec consentement explicite, dossier partageable avec des partenaires (microfinance, assurance). Aucune notation de crédit calculée par Jeflink.
- **Carnet d'entretien du logement** — équipements enregistrés (clim, chauffe-eau, pompe…), rappels saisonniers (avant l'hivernage, avant les fortes chaleurs), abonnements récurrents (ménage hebdo, entretien clim trimestriel).
- **Anti-contournement par la valeur** — garantie, historique, facture, Passeport Pro et re-réservation en un geste rendent la plateforme plus intéressante que l'échange de numéros. Avant réservation, les numéros partagés dans le chat sont masqués avec un rappel neutre ; aucun flicage après.
- **Commission sur cash** — le pro encaisse, la commission est inscrite comme dette dans son portefeuille, déduite des prochains paiements en ligne ou réglée en mobile money. Seuil de dette paramétrable.

## 6. Priorisation

| Élément                                                     | Impact       | Effort             | Phase                       |
| ----------------------------------------------------------- | ------------ | ------------------ | --------------------------- |
| Parcours demande → devis → réservation → code de fin → avis | Très fort    | Moyen              | V1                          |
| Adressage par repères (sans IA)                             | Fort         | Faible             | V1                          |
| App Pro hors-ligne + photos avant/après                     | Fort         | Moyen              | V1                          |
| Demande vocale IA (français)                                | Fort         | Moyen              | V1                          |
| Commission sur cash via portefeuille                        | Fort         | Moyen              | V1                          |
| SEO métier × quartier                                       | Fort         | Faible             | V1                          |
| WiiPay + Garantie (séquestre)                               | Très fort    | Fort (+ juridique) | V2                          |
| WhatsApp-first                                              | Très fort    | Fort               | V2                          |
| Fourchette de prix + Copilote Pro                           | Fort         | Moyen              | V2 (données V1 nécessaires) |
| Wolof vocal                                                 | Fort         | Incertain          | V2 après benchmark          |
| Matching expliqué                                           | Moyen        | Moyen              | V2                          |
| Diaspora                                                    | Fort         | Moyen              | V3                          |
| Passeport Pro partenaires, carnet d'entretien, B2B          | Moyen à fort | Moyen              | V3                          |

## 7. Périmètre V1 — Dakar

**Catégories de lancement (6)**, validées par Zay le 2026-09-30 : plomberie · électricité · froid & climatisation · réparation électroménager · ménage · petits travaux (peinture, menuiserie, maçonnerie légère).

**Extensible par conception.** Métiers et zones sont des **données** (`catalog`, `zones`) gérées depuis la console Ops, jamais des listes codées en dur. Ajouter un métier (vitrier, jardinier, serrurier…) ou un quartier, puis plus tard une ville, ne demande ni migration ni déploiement : c'est une saisie Ops. Les métiers sont activables par zone. Le signal « demande non servie » (IA7) indique quoi ouvrir ensuite. Conséquences : l'IA reçoit la liste des métiers actifs au moment de l'appel, les pages SEO `/[metier]/[quartier]` sont générées depuis la base, et les libellés de métiers sont traduisibles (`fr`, `wo`) en base.

**Inclus** : comptes OTP · zones Dakar · catalogue · demande (formulaire + vocal fr) · jusqu'à 3 devis · réservation · suivi · avenants · code de fin + photos · avis · chat (texte, vocal, photo) · paiement cash + mobile money déclaré manuellement · portefeuille pro et commission · console Ops (KYC, litiges, zones, catégories, pros) · console Pro web basique · app client · app Pro · site public SEO.

**Exclu de V1** : paiement en ligne intégré, séquestre, agent WhatsApp, abonnements, points de fidélité, diaspora, B2B, villes hors Dakar.

## 8. Indicateurs

- Nord : **missions terminées sans litige par semaine**.
- Délai médian jusqu'au 1er devis · taux de complétion · taux de litige · réachat à 60 jours · note moyenne · part de demandes non servies par quartier.

## 9. Questions ouvertes

1. Montage juridique du séquestre avec WiiPay (ou partenaire agréé).
2. Taux de commission et règle des frais de déplacement.
3. Solution de reconnaissance vocale wolof : benchmark à faire.
4. Fournisseur WhatsApp Business (BSP) et coût par conversation.
5. Stratégie de recrutement des 50 premiers pros (terrain, bouche-à-oreille, organisations de métiers).
6. Déclarations à la CDP (données personnelles, KYC, géolocalisation).
