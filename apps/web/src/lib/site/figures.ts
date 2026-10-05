// Gros chiffres du site (spec 006, Q5). Trois chiffres vrais par construction (règles lues dans
// `stats.rules`, jamais recopiées ; « 0 F » de frais pour le client, confirmé en Q5). Les preuves
// réelles (`stats`) en remplacent un seulement au-delà des seuils : sous un seuil, l'API renvoie
// `null` et rien ne s'affiche à la place. Jamais un « 0 » ni un compteur vide. Module pur.

/** Forme de `GET /api/stats/` (spec 006) : seules les valeurs lues ici. */
export type PublicStats = {
  missions_completed: number | null;
  rating: { average: number; count: number } | null;
  verified_pros: number | null;
  rules: {
    max_quotes_per_request: number;
    dispute_window_hours: number;
  } | null;
};

export type Figure =
  | { kind: "quotes"; value: number }
  | { kind: "dispute"; hours: number }
  | { kind: "fees" }
  | { kind: "missions"; value: number }
  | { kind: "pros"; value: number }
  | { kind: "rating"; average: number; count: number };

const positive = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isFinite(value) && value > 0;

/** Preuves réelles disponibles, de la plus parlante à la moins parlante. */
export function availableProofs(stats: PublicStats | null | undefined): Figure[] {
  const proofs: Figure[] = [];
  if (!stats) return proofs;
  if (positive(stats.missions_completed)) {
    proofs.push({ kind: "missions", value: stats.missions_completed });
  }
  if (stats.rating && positive(stats.rating.count) && positive(stats.rating.average)) {
    proofs.push({ kind: "rating", average: stats.rating.average, count: stats.rating.count });
  }
  if (positive(stats.verified_pros)) proofs.push({ kind: "pros", value: stats.verified_pros });
  return proofs;
}

/**
 * Au plus 3 chiffres. Base : devis au plus, délai pour signaler un problème, frais nuls. Les
 * règles manquantes (API sans réponse) laissent la base réduite ; le chiffre « 0 F » reste, il ne
 * dépend d'aucune donnée. Chaque preuve disponible remplace un chiffre de règle (le délai d'abord,
 * puis le nombre de devis) ; « 0 F » reste toujours.
 */
export function chooseFigures(stats: PublicStats | null | undefined): Figure[] {
  const base: Figure[] = [];
  const rules = stats?.rules;
  if (rules && positive(rules.max_quotes_per_request)) {
    base.push({ kind: "quotes", value: rules.max_quotes_per_request });
  }
  if (rules && positive(rules.dispute_window_hours)) {
    base.push({ kind: "dispute", hours: rules.dispute_window_hours });
  }
  base.push({ kind: "fees" });

  const proofs = availableProofs(stats);
  const replaceable = [1, 0].filter((i) => i < base.length - 1 && base[i]?.kind !== "fees");
  for (const index of replaceable) {
    const proof = proofs.shift();
    if (!proof) break;
    base[index] = proof;
  }
  // Sans règles mais avec des preuves : elles complètent jusqu'à 3.
  while (base.length < 3 && proofs.length) {
    base.unshift(proofs.shift() as Figure);
  }
  return base.slice(0, 3);
}
