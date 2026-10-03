// Lien WhatsApp du support (« aucune impasse », spec 001, T3). Le message pré-rempli ne contient
// ni numéro ni donnée personnelle ; le numéro du support vient de la configuration serveur.
import { ButtonLink } from "@/components/ui/button";
import { ChatIcon } from "@/components/ui/icons";
import { whatsappUrl } from "@/lib/login/support";

export function SupportLink({
  number,
  message,
  label,
  variant = "secondary",
  className = "",
}: {
  number: string | null;
  message: string;
  label: string;
  variant?: "primary" | "secondary";
  className?: string;
}) {
  const href = whatsappUrl(number, message);
  if (!href) return null;
  return (
    <ButtonLink
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      variant={variant}
      className={className}
    >
      <ChatIcon className="size-5" />
      {label}
    </ButtonLink>
  );
}
