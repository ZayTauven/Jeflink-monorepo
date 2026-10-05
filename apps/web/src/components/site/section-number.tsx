// Numéro de section « 01 », « 02 » (Crafto, spec 006). Décoratif : l'ordre est déjà porté par la
// liste ordonnée qui l'entoure (`<ol>`), d'où `aria-hidden`.
export function SectionNumber({
  number,
  className = "",
}: {
  /** Position de la section, à partir de 1. */
  number: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`font-display text-5xl leading-none tracking-tight text-accent-strong ${className}`}
    >
      {String(Math.max(0, Math.trunc(number))).padStart(2, "0")}
    </span>
  );
}
