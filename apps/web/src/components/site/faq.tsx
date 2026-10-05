// Questions fréquentes en `<details>` / `<summary>` natifs (Crafto remplace Bootstrap, spec 006) :
// aucun JS, clavier et lecteur d'écran gérés par le navigateur. Pas de JSON-LD `FAQPage`.
// Chaque réponse s'appuie sur une règle des specs 001 à 005, citée en commentaire à côté de sa clé.
import type { ReactNode } from "react";

import { ChevronDownIcon } from "@/components/ui/icons";

export type FaqItem = { id: string; question: string; answer: ReactNode };

export function Faq({ items, className = "" }: { items: readonly FaqItem[]; className?: string }) {
  if (items.length === 0) return null;
  return (
    <div className={`border-t border-line ${className}`}>
      {items.map((item) => (
        <details key={item.id} className="group border-b border-line">
          <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-3 font-display text-xl text-ink marker:content-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong [&::-webkit-details-marker]:hidden">
            {item.question}
            <ChevronDownIcon className="size-6 shrink-0 transition-transform group-open:rotate-180" />
          </summary>
          <div className="pb-5 pr-10 text-base text-ink-muted">{item.answer}</div>
        </details>
      ))}
    </div>
  );
}
