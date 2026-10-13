"use client";

/**
 * Filtres d'une liste de la console, appliqués tout seuls : une case au changement, une liste
 * déroulante ou la recherche après une courte pause (on peut parcourir les options au clavier
 * sans recharger la page à chaque flèche), ou tout de suite sur Entrée. `summary` (« 12 demandes »)
 * est lu par les lecteurs d'écran quand les résultats changent. Le filtrage
 * reste fait par l'API (listes paginées) : on change seulement l'adresse de la page.
 *
 * Les champs sont rendus par la page (Server Component) ; sans JavaScript, c'est un formulaire
 * GET ordinaire avec son bouton « Filtrer ». Quand l'adresse change ailleurs (puce retirée,
 * onglet), les champs reprennent les valeurs de l'adresse.
 */
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition, type FormEvent, type ReactNode } from "react";

import { TopBar } from "./pending";

const TYPING_MS = 400;

function isTextField(el: EventTarget | null): el is HTMLInputElement {
  return el instanceof HTMLInputElement && (el.type === "text" || el.type === "search");
}

export function AutoFilters({
  base,
  label = "Filtres",
  summary,
  children,
}: {
  base: string;
  label?: string;
  summary: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const form = useRef<HTMLFormElement>(null);
  const typing = useRef<number | undefined>(undefined);
  const applied = useRef<string | null>(null);
  const later = useRef<"push" | "replace">("replace");
  const [pending, startTransition] = useTransition();
  const [auto, setAuto] = useState(false);

  useEffect(() => {
    setAuto(true);
    return () => window.clearTimeout(typing.current);
  }, []);

  // L'adresse a changé (puce retirée, onglet, retour arrière) : les champs la suivent.
  // Si c'est notre propre recherche, on ne touche pas au champ où l'on écrit encore.
  useEffect(() => {
    const el = form.current;
    if (!el) return;
    const own = params.toString() === applied.current;
    for (const field of Array.from(el.elements)) {
      if (own && field === document.activeElement) continue;
      if (field instanceof HTMLSelectElement) {
        field.value = params.get(field.name) ?? "";
      } else if (field instanceof HTMLInputElement && field.type === "checkbox") {
        field.checked = params.get(field.name) === field.value;
      } else if (isTextField(field)) {
        field.value = params.get(field.name) ?? "";
      }
    }
    // Puce retirée : son lien a disparu, le focus serait perdu ; il revient aux filtres.
    if (!own && document.activeElement === document.body) {
      el.querySelector<HTMLElement>("input:not([type=hidden]), select")?.focus();
    }
  }, [params]);

  // Nouvelle adresse = champs remplis (sans la page : on repart de la première).
  function apply(mode: "push" | "replace") {
    window.clearTimeout(typing.current);
    later.current = "replace";
    const el = form.current;
    if (!el) return;
    const query = new URLSearchParams();
    for (const [name, value] of new FormData(el)) {
      if (typeof value === "string" && value.trim()) query.set(name, value.trim());
    }
    const search = query.toString();
    applied.current = search;
    const url = search ? `${base}?${search}` : base;
    if (url === window.location.pathname + window.location.search) return;
    startTransition(() => {
      if (mode === "push") router.push(url, { scroll: false });
      else router.replace(url, { scroll: false });
    });
  }

  // Une liste déroulante l'emporte sur la frappe : son choix doit rester dans l'historique.
  function wait(mode: "push" | "replace") {
    if (mode === "push") later.current = "push";
    window.clearTimeout(typing.current);
    typing.current = window.setTimeout(() => apply(later.current), TYPING_MS);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    apply("push");
  }

  return (
    <form
      ref={form}
      className="jf-filters"
      method="get"
      action={base}
      role="search"
      aria-label={label}
      aria-busy={pending}
      data-auto={auto ? "" : undefined}
      onSubmit={onSubmit}
      // Cases : tout de suite. Listes déroulantes et recherche : après une pause. (Le
      // « change » d'un champ texte, au départ du champ, est déjà couvert par la pause.)
      onChange={(e) => {
        if (e.target instanceof HTMLSelectElement) wait("push");
        else if (!isTextField(e.target)) apply("push");
      }}
      onInput={(e) => {
        if (isTextField(e.target)) wait("replace");
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" && isTextField(e.target)) {
          e.preventDefault();
          apply("push");
        }
      }}
    >
      {children}
      <p className="ax-visually-hidden" role="status">
        {summary}
      </p>
      {pending && <TopBar />}
    </form>
  );
}
