"use client";

/** Bouton « Copier » d'un code promo (presse-papiers), confirmé par un toast. */
import { Tip } from "./tip";
import { toast } from "./toaster";

/**
 * Ancienne méthode, quand le presse-papiers moderne manque (page en http sur le réseau local)
 * ou refuse (fenêtre sans focus).
 */
function legacyCopy(text: string): boolean {
  const back = document.activeElement as HTMLElement | null;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  let done = false;
  try {
    done = document.execCommand("copy");
  } catch {
    done = false;
  }
  area.remove();
  back?.focus();
  return done;
}

export function CopyCode({ code }: { code: string }) {
  async function copy() {
    let done = false;
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(code);
        done = true;
      } catch {
        done = false;
      }
    }
    if (!done) done = legacyCopy(code);
    if (done) toast(`Code ${code} copié.`);
    else toast("Copie impossible : sélectionnez le code à la main.", "danger");
  }
  return (
    <Tip label="Copier le code">
      <button
        type="button"
        className="ax-icon-btn jf-copy"
        onClick={copy}
        aria-label={`Copier le code ${code}`}
      >
        <i className="bi bi-clipboard" aria-hidden="true" />
      </button>
    </Tip>
  );
}
