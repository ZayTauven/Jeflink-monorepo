"use client";

// Îlot client n° 1 du site public : le menu mobile (spec 006, accessibilité).
// - Sans JS (et avant l'hydratation) : un simple lien vers le pied de page, qui porte tous les liens.
// - Avec JS : un bouton qui ouvre un `<dialog>` plein écran. `showModal()` donne le piège à focus,
//   la fermeture par Échap et le retour du focus au bouton ; `aria-expanded` suit l'état.
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import { buttonClass } from "@/components/ui/button";
import { CloseIcon, MenuIcon } from "@/components/ui/icons";
import { Logo } from "@/components/ui/logo";
import { SITE_PATHS } from "@/lib/site/paths";

export type MenuLink = { href: string; label: string };

const trigger =
  "inline-flex min-h-12 items-center gap-2 rounded-pill border border-line-strong bg-surface px-5 " +
  "text-base font-medium text-ink hover:border-ink focus-visible:outline-2 " +
  "focus-visible:outline-offset-2 focus-visible:outline-accent-strong";

export function MobileMenu({
  links,
  space,
  request,
}: {
  links: readonly MenuLink[];
  /** « Mon espace » : toujours le même lien, aucune lecture de session. */
  space: MenuLink;
  request: MenuLink;
}) {
  const t = useTranslations("site.menu");
  const dialogId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const [ready, setReady] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => setReady(true), []);

  if (!ready) {
    return (
      <a href={SITE_PATHS.footer} className={trigger}>
        <MenuIcon className="size-5" />
        {t("open")}
      </a>
    );
  }

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={expanded}
        aria-controls={dialogId}
        className={trigger}
        onClick={() => {
          dialog.current?.showModal();
          setExpanded(true);
        }}
      >
        <MenuIcon className="size-5" />
        {t("open")}
      </button>
      <dialog
        ref={dialog}
        id={dialogId}
        aria-label={t("title")}
        onClose={() => setExpanded(false)}
        onClick={(event) => {
          // Un lien suivi referme le menu : le layout reste monté d'une page à l'autre.
          if ((event.target as HTMLElement).closest("a")) dialog.current?.close();
        }}
        className="m-0 h-dvh max-h-none w-dvw max-w-none overflow-y-auto bg-sand p-0 text-ink"
      >
        <div className="mx-auto flex min-h-full max-w-6xl flex-col px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <Logo />
            <button type="button" className={trigger} onClick={() => dialog.current?.close()}>
              <CloseIcon className="size-5" />
              {t("close")}
            </button>
          </div>
          <nav aria-label={t("title")} className="mt-10 flex flex-col">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="flex min-h-14 items-center border-b border-line py-3 font-display text-3xl tracking-tight text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
              >
                {link.label}
              </a>
            ))}
            <a
              href={space.href}
              className="flex min-h-14 items-center py-3 text-base font-medium text-accent-strong underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
            >
              {space.label}
            </a>
          </nav>
          <a href={request.href} className={buttonClass("primary", "mt-auto mb-6 w-full")}>
            {request.label}
          </a>
        </div>
      </dialog>
    </>
  );
}
