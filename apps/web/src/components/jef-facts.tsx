/**
 * Faits de la fiche Jef (« Endroit : cuisine »), en tableau libellé / valeur. Même rendu dans
 * la fiche du pro et dans l'aperçu « Ce que le pro verra » de l'assistant. Une ligne sans
 * libellé (ancienne fiche, mode IA) s'affiche telle quelle.
 */
const SEPARATOR = /\s:\s/; // espace (insécable ou non), deux-points, espace

export function JefFacts({ lines }: { lines: string[] }) {
  if (lines.length === 0) return null;
  return (
    <dl className="jf-jef-facts">
      {lines.map((line) => {
        const at = line.search(SEPARATOR);
        if (at < 0) {
          return (
            <div key={line}>
              <dd>{line}</dd>
            </div>
          );
        }
        const label = line.slice(0, at);
        const value = line.slice(at).replace(SEPARATOR, "");
        return (
          <div key={line}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        );
      })}
    </dl>
  );
}
