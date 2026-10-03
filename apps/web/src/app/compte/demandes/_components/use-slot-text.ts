"use client";

// Créneau en langage courant (« Demain matin », « Mardi après-midi »), calculé en heure de Dakar
// à partir d'un `now` fourni par le serveur : même texte au rendu serveur et dans le navigateur.
import { useLocale, useTranslations } from "next-intl";

import { slotLabel } from "@/lib/requests/format";

export function useSlotText(now: string) {
  const t = useTranslations("requests.quote");
  const locale = useLocale();
  return (startIso: string, endIso: string): { text: string; range: string } => {
    const label = slotLabel(startIso, endIso, now, locale);
    if (!label) return { text: "", range: "" };
    const period = t(`period.${label.period}`);
    let text: string;
    if (label.day.kind === "today") text = t("slotDay", { day: t("today"), period });
    else if (label.day.kind === "tomorrow") text = t("slotDay", { day: t("tomorrow"), period });
    else if (label.day.kind === "weekday") text = t("slotDay", { day: label.day.text, period });
    else text = t("slotDate", { date: label.day.text, period });
    return { text, range: t("slotRange", { from: label.from, to: label.to }) };
  };
}
