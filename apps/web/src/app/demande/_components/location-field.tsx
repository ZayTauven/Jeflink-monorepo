"use client";

// Position facultative (géolocalisation du navigateur). Elle vit dans l'état du formulaire,
// jamais dans le brouillon stocké : elle part dans le seul POST de la demande.
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { Location } from "@/lib/requests/payload";

type Phase = "idle" | "locating" | "denied" | "unsupported";

export function LocationField({
  location,
  onChange,
}: {
  location: Location | null;
  onChange: (location: Location | null) => void;
}) {
  const t = useTranslations("requests.form.location");
  const [phase, setPhase] = useState<Phase>("idle");

  const locate = () => {
    if (!("geolocation" in navigator)) {
      setPhase("unsupported");
      return;
    }
    setPhase("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        // 5 décimales : environ un mètre, assez pour trouver la porte, pas plus.
        onChange({
          lat: Number(position.coords.latitude.toFixed(5)),
          lon: Number(position.coords.longitude.toFixed(5)),
        });
        setPhase("idle");
      },
      () => setPhase("denied"),
      { enableHighAccuracy: false, timeout: 15_000, maximumAge: 60_000 },
    );
  };

  return (
    <section className="flex flex-col gap-3 rounded-card border border-line bg-sand p-4">
      <h3 className="text-base font-medium text-ink">{t("title")}</h3>
      <p className="text-sm leading-relaxed text-ink-muted">{t("lead")}</p>
      {location ? (
        <>
          <Alert tone="success">{t("set")}</Alert>
          <Button variant="secondary" onClick={() => onChange(null)} className="self-start">
            {t("remove")}
          </Button>
        </>
      ) : (
        <Button
          variant="secondary"
          onClick={locate}
          disabled={phase === "locating"}
          aria-busy={phase === "locating"}
          className="self-start"
        >
          {phase === "locating" ? t("locating") : t("use")}
        </Button>
      )}
      {phase === "denied" ? <Alert tone="info">{t("denied")}</Alert> : null}
      {phase === "unsupported" ? <Alert tone="info">{t("unsupported")}</Alert> : null}
    </section>
  );
}
