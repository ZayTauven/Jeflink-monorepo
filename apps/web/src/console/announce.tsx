"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * Message de retour après une action (page rechargée) : il prend le focus, pour être lu par
 * les lecteurs d'écran et vu au clavier, puisqu'un role="status" rendu au chargement ne l'est pas toujours.
 */
export function Announce({
  className,
  role,
  children,
}: {
  className: string;
  role: "status" | "alert";
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <div ref={ref} tabIndex={-1} className={className} role={role}>
      {children}
    </div>
  );
}
