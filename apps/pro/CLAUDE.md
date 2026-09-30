# apps/pro — app Pro (prestataire + technicien)

Un seul binaire, plusieurs rôles : `owner` (artisan solo ou patron), `technician` (employé assigné). L'artisan solo est son propre technicien : aucune notion d'« entreprise » imposée.

- **Hors-ligne d'abord** : file d'actions locale (statuts, photos, code de fin) rejouée à la reconnexion, avec l'horodatage d'origine.
- Littératie variable : icônes + libellés courts, note vocale possible partout où il y a un champ texte, boutons ≥ 48 px, confirmations explicites.
- Photos avant/après obligatoires pour clôturer ; le code de fin donné par le client déclenche la clôture.
- Copilote Pro (V2) : note vocale → brouillon de devis éditable ; résumé de la demande ; traduction fr ↔ wo. Jamais envoyé sans validation du pro.
- Portefeuille : solde, commissions dues sur les missions payées en cash, versements. Solde négatif au-delà du seuil = nouvelles missions suspendues (message clair, non punitif).
- Notification critique (nouvelle mission) : push + SMS de repli.
