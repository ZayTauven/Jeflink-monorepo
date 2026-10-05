"use client";

// Îlot client n° 2 du site public : la pause du bandeau. Le bouton n'apparaît qu'une fois la page
// hydratée (sans JS, le bandeau est statique : rien à mettre en pause). Le CSS fait le reste
// (`data-paused`, survol, focus, mouvement réduit) : voir globals.css.
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useState } from "react";

import { PauseIcon, PlayIcon } from "@/components/ui/icons";

export function MarqueeShell({ children }: { children: ReactNode }) {
  const t = useTranslations("site.marquee");
  const [ready, setReady] = useState(false);
  const [paused, setPaused] = useState(false);
  useEffect(() => setReady(true), []);

  return (
    <div className="jf-marquee" data-paused={paused ? "true" : "false"}>
      {children}
      {ready ? (
        <button
          type="button"
          aria-pressed={paused}
          onClick={() => setPaused((value) => !value)}
          className="jf-marquee-toggle mt-4 inline-flex min-h-12 items-center gap-2 rounded-pill border border-line-strong bg-surface px-5 text-base font-medium text-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
        >
          {paused ? <PlayIcon className="size-5" /> : <PauseIcon className="size-5" />}
          {paused ? t("play") : t("pause")}
        </button>
      ) : null}
    </div>
  );
}
