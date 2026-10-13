"use client";

/**
 * Fenêtre modale de la console : balisage `.ax-modal__*` de vireo sur un `<dialog>` natif
 * (focus gardé dans la fenêtre, Échap, page derrière inerte), fond voilé et flouté.
 *
 * Le contenu (souvent un formulaire `ActionForm`) est rendu côté serveur. Après l'envoi,
 * l'action revient sur la page avec un message : la fenêtre se referme et le toast prend
 * le relais. (Next remonte alors la page : en cas d'erreur, la saisie est à refaire.)
 * Sans JavaScript, le bouton reste un `<details>` qui déplie le contenu sous lui.
 */
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from "react";

export function Modal({
  trigger,
  triggerClassName = "ax-btn ax-btn--secondary ax-btn--sm",
  title,
  subtitle,
  icon,
  danger = false,
  size,
  closeOnBackdrop = false,
  children,
}: {
  trigger: ReactNode;
  triggerClassName?: string;
  title: string;
  subtitle?: ReactNode;
  /** Pastille d'icône Bootstrap à gauche du titre (ex. confirmations). */
  icon?: string;
  danger?: boolean;
  size?: "sm" | "lg";
  /** Clic sur le voile = fermer. Pour les confirmations courtes seulement : un formulaire
   * d'ajout ou de modification ne doit pas se perdre sur un clic de travers. */
  closeOnBackdrop?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const fallback = useRef<HTMLDetailsElement>(null);
  const pressedOnBackdrop = useRef(false);
  const titleId = useId();
  const pathname = usePathname();
  const params = useSearchParams();

  // Ouvre la fenêtre, le curseur dans le premier champ (sinon sur « Fermer »).
  function show() {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal();
    dialog
      .querySelector<HTMLElement>(
        ".ax-modal__body :is(input:not([type=hidden]):not([type=checkbox]), textarea, select)",
      )
      ?.focus();
  }

  // Retour de l'action (nouvelle adresse) : on referme.
  useEffect(() => {
    ref.current?.close();
  }, [pathname, params]);

  // Clic avant le chargement du JavaScript : le repli s'est déplié ; la fenêtre prend le relais.
  // (Après l'effet précédent, qui tourne aussi au montage.)
  useEffect(() => {
    if (fallback.current?.open) {
      fallback.current.open = false;
      show();
    }
  }, []);

  function open(e: MouseEvent) {
    e.preventDefault();
    show();
  }

  // Clic sur le voile (hors de la fenêtre) : on ferme, sauf si le geste a commencé dedans
  // (sélection de texte dans un champ relâchée à l'extérieur).
  function onPointerDown(e: MouseEvent<HTMLDialogElement>) {
    pressedOnBackdrop.current = e.target === e.currentTarget;
  }
  function onClick(e: MouseEvent<HTMLDialogElement>) {
    if (closeOnBackdrop && pressedOnBackdrop.current && e.target === e.currentTarget) {
      ref.current?.close();
    }
    pressedOnBackdrop.current = false;
  }

  return (
    <div className="jf-modal-host">
      <details ref={fallback} className="jf-modal-fallback" suppressHydrationWarning>
        <summary className={triggerClassName} onClick={open} aria-haspopup="dialog">
          {trigger}
        </summary>
      </details>
      <dialog
        ref={ref}
        className={`ax-modal__dialog jf-dialog${size ? ` ax-modal__dialog--${size}` : ""}`}
        aria-labelledby={titleId}
        onMouseDown={onPointerDown}
        onClick={onClick}
      >
        <div className="ax-modal__header">
          {icon && (
            <span
              className={`ax-modal__status jf-dialog__status${danger ? " ax-modal__status--danger" : ""}`}
              aria-hidden="true"
            >
              <i className={`bi ${icon}`} />
            </span>
          )}
          <div className="jf-dialog__titles">
            <h2 className="ax-modal__title" id={titleId}>
              {title}
            </h2>
            {subtitle && <p className="jf-dialog__subtitle">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="ax-modal__close"
            onClick={() => ref.current?.close()}
            aria-label="Fermer"
          >
            <i className="bi bi-x-lg" aria-hidden="true" />
          </button>
        </div>
        <div className="ax-modal__body">{children}</div>
      </dialog>
    </div>
  );
}

/** Bouton « Annuler » d'un formulaire en fenêtre : referme la fenêtre qui le contient. */
export function CloseModal({ children = "Annuler" }: { children?: ReactNode }) {
  return (
    <button
      type="button"
      className="ax-btn ax-btn--ghost ax-btn--sm jf-dialog__cancel"
      onClick={(e) => e.currentTarget.closest("dialog")?.close()}
    >
      {children}
    </button>
  );
}
