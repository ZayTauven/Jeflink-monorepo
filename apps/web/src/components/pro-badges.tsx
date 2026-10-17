/**
 * Badges d'un pro : « Vérifié » (pièce d'identité contrôlée par l'équipe, condition pour
 * envoyer un devis) et « Pro confirmé » (gagné seul : missions, note, aucun litige perdu).
 */
export function ProBadges({
  verified,
  confirmed,
  onDark = false,
}: {
  verified: boolean;
  confirmed: boolean;
  onDark?: boolean;
}) {
  if (!verified && !confirmed) return null;
  return (
    <span className={`jf-badges${onDark ? " jf-badges--dark" : ""}`}>
      {verified && (
        <span className="jf-badge">
          <i className="bi bi-patch-check-fill" aria-hidden="true" />
          Vérifié
        </span>
      )}
      {confirmed && (
        <span className="jf-badge jf-badge--confirmed">
          <i className="bi bi-award-fill" aria-hidden="true" />
          Pro confirmé
        </span>
      )}
    </span>
  );
}

/** « Que veulent dire ces badges ? » : la réponse en deux lignes, dépliable. */
export function BadgesExplained({ className = "" }: { className?: string }) {
  return (
    <details className={`jf-badges-help ${className}`}>
      <summary className="fw-500 text-dark-gray jf-summary">
        Que veulent dire ces badges&nbsp;?
      </summary>
      <dl className="mt-15px mb-0">
        <dt>
          <ProBadges verified confirmed={false} />
        </dt>
        <dd>
          L&apos;équipe Jeflink a contrôlé sa pièce d&apos;identité et échangé avec ce pro au
          téléphone. Seuls les pros vérifiés peuvent vous envoyer un devis.
        </dd>
        <dt>
          <ProBadges verified={false} confirmed />
        </dt>
        <dd>
          Gagné sur Jeflink&nbsp;: au moins 10 missions terminées, une note moyenne de 4,5 ou plus
          et aucun litige perdu.
        </dd>
      </dl>
    </details>
  );
}
