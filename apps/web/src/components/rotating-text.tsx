/**
 * Pastille tournante (remplace l'image « LET'S START NEW PROJECT » du template) : texte sur un
 * cercle, séparé par des étincelles. Tourne avec la classe Crafto `animation-rotation`.
 */
export function RotatingText({
  id,
  parts = ["Le bon pro", "au bon prix"],
  className = "",
}: {
  id: string;
  parts?: string[];
  className?: string;
}) {
  const path = `jf-circle-${id}`;
  const r = 76;
  const circumference = 2 * Math.PI * r;
  const n = parts.length * 2;
  return (
    <svg
      className={`jf-rotating-text ${className}`}
      viewBox="0 0 200 200"
      width={200}
      height={200}
      aria-hidden="true"
    >
      <defs>
        <path
          id={path}
          d={`M100,100 m-${r},0 a${r},${r} 0 1,1 ${2 * r},0 a${r},${r} 0 1,1 -${2 * r},0`}
        />
      </defs>
      {Array.from({ length: n }, (_, i) => {
        const start = (i / n) * circumference;
        // Le chemin part de la gauche, sens horaire : l'étincelle se place au début de chaque
        // segment, entre deux textes, juste à l'extérieur du cercle comme les lettres.
        const angle = (i / n) * 360 - 90;
        return (
          <g key={i}>
            <text>
              <textPath
                href={`#${path}`}
                startOffset={start + 14}
                textLength={circumference / n - 28}
                lengthAdjust="spacing"
              >
                {parts[i % parts.length].toUpperCase()}
              </textPath>
            </text>
            <path
              d="M0,-6 Q0.9,-0.9 6,0 Q0.9,0.9 0,6 Q-0.9,0.9 -6,0 Q-0.9,-0.9 0,-6 Z"
              transform={`rotate(${angle} 100 100) translate(100 ${100 - r - 6})`}
              fill="currentColor"
            />
          </g>
        );
      })}
    </svg>
  );
}
