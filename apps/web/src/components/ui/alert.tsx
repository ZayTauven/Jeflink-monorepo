// Message d'état : icône + texte (le sens n'est jamais porté par la couleur seule). Bordure 1 px,
// fond `surface`, couleur de statut sur l'icône et la bordure gauche seulement.
import type { ReactNode } from "react";

import { AlertIcon, CheckIcon, InfoIcon } from "./icons";

type Tone = "error" | "info" | "success";

const tones: Record<Tone, { border: string; icon: string; Icon: typeof AlertIcon }> = {
  error: { border: "border-l-danger", icon: "text-danger", Icon: AlertIcon },
  info: { border: "border-l-info", icon: "text-info", Icon: InfoIcon },
  success: { border: "border-l-success", icon: "text-success", Icon: CheckIcon },
};

export function Alert({
  tone,
  children,
  action,
  id,
}: {
  tone: Tone;
  children: ReactNode;
  action?: ReactNode;
  /** Relie l'alerte à un champ par aria-describedby. */
  id?: string | undefined;
}) {
  const { border, icon, Icon } = tones[tone];
  return (
    <div
      id={id}
      role={tone === "error" ? "alert" : "status"}
      className={`flex gap-3 rounded-card border border-line border-l-4 bg-surface p-4 ${border}`}
    >
      <Icon className={`mt-0.5 size-5 shrink-0 ${icon}`} />
      <div className="flex flex-col gap-3 text-base leading-relaxed text-ink">
        <div>{children}</div>
        {action}
      </div>
    </div>
  );
}
