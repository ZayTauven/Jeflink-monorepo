# ADR 0010 — Demande et réservation : deux cycles de vie, la réservation naît à `accepted`

Statut : proposé · 2026-10-03 · Spec : `docs/specs/003-requests-quotes-booking.md` · Revue terrain intégrée (délai de confirmation)

## Contexte

Le diagramme d'ARCHITECTURE.md fait commencer la machine à états d'une réservation à `requested`, puis `quoted`. Or, avant le choix du client, il n'y a ni pro, ni montant, ni créneau. Il y a une demande et jusqu'à 3 devis de pros différents. Si une `Booking` portait ces deux états, elle aurait des champs vides et un « pro » multiple, et chaque devis devrait écrire dans la réservation. Le terrain impose aussi un cas courant : le pro choisi ne confirme pas, ou se désiste, et le client doit pouvoir revenir aux autres devis sans tout ressaisir.

## Décision

- **La demande (`requests.ServiceRequest`) a son propre cycle** : `needs_zone`, `open`, `quoted`, `booked`, `expired`, `cancelled`. Seul `requests.services` change son statut, à partir d'une table de transitions testée. Les horodatages (`first_quoted_at`, `closed_at`, `close_reason`) servent de journal.
- **La réservation (`bookings.Booking`) naît à `accepted`**, quand le client accepte un devis, par `bookings.services.create_from_quote()`. C'est le seul point de création. Il journalise l'événement initial (`"" → accepted`) avec la même fonction que `transition()`.
- La machine à états de la réservation est déclarée en entier, d'`accepted` à `closed`. Les transitions qu'une spec n'a pas encore activées lèvent `transition_not_enabled`.
- **Une demande peut avoir plusieurs réservations dans le temps**, mais une seule active : `Booking.request` est une FK, avec une `UniqueConstraint(request)` partielle sur les statuts non annulés. Si le pro se désiste, la demande revient à `quoted` ou à `open`.
- **Le pro confirme** (`accepted → scheduled`) dans un délai réglable : 4 h, ou 1 h si la demande est urgente, gelé de 21 h à 7 h (heure de Dakar) et borné par le début du créneau. Sans confirmation, le système annule (`pro_unconfirmed`), sans pénalité de fiabilité en V1, et le client retrouve ses autres devis.
- `requested` et `quoted` disparaissent du diagramme de la réservation dans ARCHITECTURE.md et passent dans celui de la demande.

## Conséquences

- La règle 10 (« aucune transition hors de `bookings.services.transition()` ») s'applique à un objet qui a toujours un pro, un montant et un créneau. Les contraintes en base sont simples (aucun champ nul « en attendant »).
- Les KPI « délai du 1er devis » et « demandes non servies » se lisent sur la demande, et la fiabilité des pros sur les `BookingEvent`.
- Toutes les durées (expiration, validité, confirmation, gel nocturne) sont des réglages : on les ajuste aux données réelles sans changer de code. Le délai de confirmation est une fonction pure, testée sur ses cas limites.
- − Deux tables de transitions à maintenir, dont une hors du domaine `bookings`. Les deux sont testées de façon exhaustive (chaque couple autorisé ou refusé).
- − Les écrans doivent fusionner deux statuts (« demande : réservée », « réservation : en attente de confirmation »). L'API renvoie la réservation active dans le détail de la demande.

## Alternatives écartées

- **Une `Booking` créée dès la demande, en `requested`** : pro et montant nuls jusqu'au choix, devis rattachés à la réservation, et retour aux devis compliqué après un désistement.
- **Statut `accepted` éphémère (passage direct à `scheduled` à l'acceptation)** : plus court, mais aucun engagement du pro après un délai parfois long entre son devis et le choix du client. Le « pro qui ne vient pas » est le premier frein de confiance (PRODUCT.md §2).
