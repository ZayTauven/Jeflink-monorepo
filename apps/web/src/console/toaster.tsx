"use client";

/**
 * Toasts de la console (`.ax-toast` de vireo), en bas à droite.
 *
 * Une action serveur revient sur la page avec `?ok=` ou `?erreur=` : le toaster affiche le
 * message, puis retire le paramètre de l'adresse (un rechargement ne le rejoue pas).
 * Réussite : disparaît après 7 s, compte à rebours en pause au survol ou au clavier.
 * Erreur : reste jusqu'à ce qu'on la ferme (le temps de lire, WCAG 2.2.1).
 * Les messages sont insérés dans une zone `aria-live` déjà présente : ils sont lus sans
 * déplacer le focus.
 * Sans JavaScript, `<Flash>` affiche l'alerte d'origine.
 */
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

type Tone = "success" | "danger";
type Item = { id: number; tone: Tone; message: string; leaving: boolean };

const LEAVE_MS = 180;

export function Toaster() {
  const params = useSearchParams();
  const [items, setItems] = useState<Item[]>([]);
  const seen = useRef("");
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((cur) => cur.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    window.setTimeout(() => setItems((cur) => cur.filter((t) => t.id !== id)), LEAVE_MS);
  }, []);

  useEffect(() => {
    const ok = params.get("ok");
    const erreur = params.get("erreur");
    if (!ok && !erreur) {
      seen.current = "";
      return;
    }
    // Mode strict (dev) : l'effet tourne deux fois pour la même adresse.
    const key = params.toString();
    if (seen.current === key) return;
    seen.current = key;

    const tone: Tone = erreur ? "danger" : "success";
    const message = (erreur || ok) as string;
    nextId.current += 1;
    const id = nextId.current;
    setItems((cur) => [...cur.slice(-2), { id, tone, message, leaving: false }]);

    const url = new URL(window.location.href);
    url.searchParams.delete("ok");
    url.searchParams.delete("erreur");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }, [params]);

  return (
    <div className="ax-toast-region ax-toast-region--bottom-end jf-toasts" aria-live="polite">
      {items.map((t) => (
        <div
          key={t.id}
          className={`ax-toast ax-toast--${t.tone}${t.leaving ? " is-leaving" : ""}`}
        >
          <i
            className={`bi ${t.tone === "danger" ? "bi-exclamation-octagon-fill" : "bi-check-circle-fill"} ax-toast__icon`}
            aria-hidden="true"
          />
          <div className="ax-toast__content">
            <p className="ax-toast__title">{t.message}</p>
          </div>
          <button
            type="button"
            className="ax-toast__dismiss"
            onClick={() => dismiss(t.id)}
            aria-label="Fermer le message"
          >
            <i className="bi bi-x-lg" aria-hidden="true" />
          </button>
          {t.tone === "success" && (
            <span
              className="ax-toast__timer jf-toast-timer"
              aria-hidden="true"
              onAnimationEnd={() => dismiss(t.id)}
            />
          )}
        </div>
      ))}
    </div>
  );
}
