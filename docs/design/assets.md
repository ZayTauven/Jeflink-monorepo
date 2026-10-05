# Provenance des images livrées

Une ligne par image copiée depuis la banque (`C:\Users\moham\Pictures\Banque`, voir DESIGN.md › Banque d'images) ou d'ailleurs. Une image sans licence claire n'entre pas en production.

| Fichier livré                                        | Chemin dans la banque                                                     | Source / nom d'origine (catalogue)                                                 | Licence        | Tailles livrées | Ajouté le  |
| ---------------------------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------- | --------------- | ---------- |
| `apps/web/src/components/ui/logo.tsx` (SVG en ligne) | hors banque : `references/assets-originaux/Jeflink-illustrations (2).png` | logo Jeflink (deux flèches), **redessiné** en vecteur ; fidélité à valider par Zay | marque Jeflink | vectoriel       | 2026-10-01 |
| `apps/web/public/images/site/hero-1600.webp` | `photos/metiers-services/equipe-nettoyage-appartement.jpg` | `Jeflink-illustrations (79).jpg` (lot d'origine du projet) | à confirmer, dev local (non renseignée au catalogue) | 1600×2000, 82,1 ko (recadrage 4:5 ; `next/image` en tire les variantes mobiles) | 2026-10-05 |
| `apps/web/public/images/site/metier-electricity-600.webp` / `-480.webp` | `photos/metiers-services/electricienne-cablage.jpg` | `Jeflink-illustrations (96).jpg` | à confirmer, dev local | 600×450 22,9 ko · 480×360 17,2 ko | 2026-10-05 |
| `apps/web/public/images/site/metier-plumbing-600.webp` / `-480.webp` | `photos/metiers-services/compteurs-eau-plomberie.jpg` | `Jeflink-illustrations (56).jpg` | à confirmer, dev local. Objets seuls : **à remplacer** | 600×450 24,4 ko · 480×360 17,6 ko | 2026-10-05 |
| `apps/web/public/images/site/metier-cooling-600.webp` / `-480.webp` | `photos/metiers-services/climatiseur-mural-split.jpg` | `Jeflink-illustrations (66).jpg` | à confirmer, dev local. Appareil seul : **à remplacer** | 600×450 10,6 ko · 480×360 7,7 ko | 2026-10-05 |
| `apps/web/public/images/site/metier-cleaning-600.webp` / `-480.webp` | `photos/metiers-services/menage-nettoyage-table.jpg` | `Jeflink-illustrations (60).jpg` | à confirmer, dev local | 600×450 22,1 ko · 480×360 16,3 ko | 2026-10-05 |
| `apps/web/public/images/site/metier-handyman-600.webp` / `-480.webp` | `photos/metiers-services/ouvrier-poncage-mur-chantier.jpg` | `Jeflink-illustrations (95).jpg` | à confirmer, dev local | 600×450 22,3 ko · 480×360 15,0 ko | 2026-10-05 |
| `apps/web/public/images/site/pro-600.webp` | `photos/metiers-services/menuisier-tablier-etabli.jpg` | `Jeflink-illustrations (85).jpg` | à confirmer, dev local (carte « Devenir pro », sans légende nominative) | 600×450, 36,4 ko | 2026-10-05 |
| `apps/web/public/images/site/dakar-1200.webp` | `photos/culture-senegal/batiment-colonial-car-rapide-dakar.jpg` | `Sn-Dahoo-Immobilier (13).jpg` (projet Dahoo) | à confirmer, dev local | 1200×800, 117,3 ko | 2026-10-05 |

Électroménager (`appliance`) : aucune photo dans la banque, le site prend le visuel générique (aplat `sand` et pictogramme). Total livré : 13 fichiers, 412 ko. Non converties faute d'emplacement utile en V1 : les variantes de la spec (clés à molette, nettoyage de mur, rue aux taxis, séjour Dahoo, marché Pexels).
