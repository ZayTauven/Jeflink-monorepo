/**
 * Logo provisoire de Jeflink, dessiné d'après le concept (references/assets-originaux/
 * « concept logo jeflink.jpg ») : un toit et une étincelle à quatre branches. Les découpes
 * passent par un masque, le logo prend donc la couleur du texte sur fond clair comme sombre.
 */
export function LogoMark({ id, className }: { id: string; className?: string }) {
  const mask = `jl-cut-${id}`;
  return (
    <svg className={className} viewBox="0 0 600 410" aria-hidden="true" focusable="false">
      <defs>
        <mask id={mask} maskUnits="userSpaceOnUse" x="0" y="0" width="600" height="410">
          <rect width="600" height="410" fill="#fff" />
          <path
            d="M-10 248 H205 C318 248 392 176 421 86 C447 168 516 222 610 238"
            fill="none"
            stroke="#000"
            strokeWidth="26"
            strokeLinejoin="round"
          />
          <path
            d="M423 208 Q429 247 468 253 Q429 259 423 298 Q417 259 378 253 Q417 247 423 208 Z"
            fill="#000"
          />
        </mask>
      </defs>
      <path
        mask={`url(#${mask})`}
        fill="currentColor"
        d="M200 8 H437 Q446 8 448 17 C468 98 512 176 584 206 Q597 212 592 224 Q587 233 576 236 L571 253 C482 262 432 318 423 402 C414 318 356 284 232 284 H22 Q10 284 10 273 Q10 262 22 262 H40 L14 236 Q2 230 10 222 C88 176 158 104 189 17 Q192 8 200 8 Z"
      />
    </svg>
  );
}

export function Logo({ id, className = "" }: { id: string; className?: string }) {
  return (
    <span className={`jeflink-logo ${className}`}>
      <LogoMark id={id} className="jeflink-logo-mark" />
      <span className="jeflink-logo-word alt-font">jeflink</span>
    </span>
  );
}
