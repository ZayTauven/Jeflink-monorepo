"use client";

import { useEffect, useRef, useState } from "react";

type SwiperLike = {
  autoplay: { start: () => void; stop: () => void };
  setTransition: (ms: number) => void;
  setTranslate: (x: number) => void;
  wrapperEl: HTMLElement;
  animating: boolean;
};

/**
 * Bouton « pause » d'un bandeau défilant Swiper du template (WCAG 2.2.2). Le bandeau s'arrête
 * net, sur place ; il est arrêté d'office si l'utilisateur préfère moins d'animations.
 */
export function MarqueePause() {
  const ref = useRef<HTMLButtonElement>(null);
  const [paused, setPaused] = useState(false);

  const swiper = () =>
    (
      ref.current?.closest("section")?.querySelector(".swiper") as
        (HTMLElement & { swiper?: SwiperLike }) | null
    )?.swiper;

  const freeze = (s: SwiperLike) => {
    const x = new DOMMatrix(getComputedStyle(s.wrapperEl).transform).m41;
    s.autoplay.stop();
    s.setTransition(0);
    s.setTranslate(x);
  };

  useEffect(() => {
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Swiper est initialisé par main.js après le chargement : on attend qu'il existe.
    let tries = 0;
    const timer = window.setInterval(() => {
      const s = swiper();
      if (s || ++tries > 40) window.clearInterval(timer);
      if (s) {
        freeze(s);
        setPaused(true);
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, []);

  const toggle = () => {
    const s = swiper();
    if (!s) return;
    if (paused) {
      // La transition interrompue par la pause n'a jamais signalé sa fin.
      s.animating = false;
      s.autoplay.start();
    } else freeze(s);
    setPaused(!paused);
  };

  return (
    <button
      ref={ref}
      type="button"
      className="jf-marquee-pause"
      onClick={toggle}
      aria-pressed={paused}
      aria-label={paused ? "Relancer le défilement" : "Mettre le défilement en pause"}
    >
      <i className={`bi ${paused ? "bi-play-fill" : "bi-pause-fill"}`} aria-hidden="true" />
    </button>
  );
}
