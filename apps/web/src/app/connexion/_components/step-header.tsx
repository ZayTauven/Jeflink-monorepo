"use client";

// En-tête d'une étape : un seul titre (h1), lu en premier, focus déplacé à chaque étape pour
// que les lecteurs d'écran annoncent le changement.
import { type ReactNode, useEffect, useRef } from "react";

export function StepHeader({
  title,
  children,
  focus = true,
}: {
  title: string;
  children?: ReactNode;
  /** Faux au premier affichage de la page : ni saut ni clavier imposé à l'arrivée. */
  focus?: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus) heading.current?.focus();
  }, [focus]);
  return (
    <header className="flex flex-col gap-3">
      <h1
        ref={heading}
        tabIndex={-1}
        className="font-display text-balance text-3xl leading-[1.1] tracking-tight text-ink outline-none sm:text-4xl"
      >
        {title}
      </h1>
      {children ? <div className="text-base leading-relaxed text-ink-muted">{children}</div> : null}
    </header>
  );
}
