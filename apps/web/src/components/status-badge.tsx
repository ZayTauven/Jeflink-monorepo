// Statut d'une demande : mot + icône, la couleur ne porte jamais le sens seule (DESIGN.md).
import { AlertIcon, CheckIcon, ClockIcon, InfoIcon } from "@/components/ui/icons";
import type { Tone } from "@/lib/requests/status";

const tones: Record<Tone, { Icon: typeof CheckIcon; icon: string }> = {
  success: { Icon: CheckIcon, icon: "text-success" },
  info: { Icon: ClockIcon, icon: "text-info" },
  warning: { Icon: AlertIcon, icon: "text-warning" },
  neutral: { Icon: InfoIcon, icon: "text-ink-muted" },
};

export function StatusBadge({ tone, children }: { tone: Tone; children: string }) {
  const { Icon, icon } = tones[tone];
  return (
    <span className="inline-flex items-center gap-2 rounded-pill border border-line bg-surface px-3 py-1 text-sm font-medium text-ink">
      <Icon className={`size-4 shrink-0 ${icon}`} />
      {children}
    </span>
  );
}
