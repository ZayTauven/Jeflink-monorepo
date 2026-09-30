# apps/client — app client (Expo)

Expo Router, TanStack Query + persistance, expo-notifications, enregistrement audio, expo-location, expo-image.

- Parcours clé : demande (texte, voix, photos) → devis → réservation → suivi → code de fin → avis.
- Bouton micro visible sur l'écran de demande : la voix est un mode de saisie de premier rang, pas un gadget.
- Adresse = repère + point sur la carte + photo du portail (optionnelle) + note vocale d'itinéraire. Adresses nommées réutilisables (« Chez maman, Pikine »).
- Connexion par OTP téléphone ; Google en option. Pas de Facebook.
- Doit tourner sur Android d'entrée de gamme : pas d'animations lourdes, images compressées avant upload, reprise d'upload.
- Montants affichés : `25 000 F CFA` (espace insécable), jamais de décimales.
