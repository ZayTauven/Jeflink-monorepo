// Logo Jeflink : les deux flèches (noire et orange) redessinées en SVG depuis
// references/assets-originaux/Jeflink-illustrations (2).png, plus le nom en Funnel Display.
// Vectoriel en ligne : net à toute taille, aucun fichier à télécharger.

export function LogoMark({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="60 150 400 215"
      className={className}
      fill="none"
      strokeWidth="56"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <g className="stroke-ink">
        <path d="M112 205H222V318" />
        <path d="M100 326 214 212" />
      </g>
      <g className="stroke-accent">
        <path d="M300 196V310H410" />
        <path d="M308 302 422 188" />
      </g>
    </svg>
  );
}

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark className="h-6 w-auto" />
      <span className="font-display text-2xl font-semibold tracking-tight text-ink">Jeflink</span>
    </span>
  );
}
