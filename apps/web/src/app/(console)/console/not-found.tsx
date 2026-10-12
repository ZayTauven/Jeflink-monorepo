import Link from "next/link";

import { PageHead } from "@/console/ui";

export default function ConsoleNotFound() {
  return (
    <>
      <PageHead
        title="Rubrique introuvable"
        subtitle="Ce lien ne mène à aucune page de la console."
      />
      <Link href="/console" className="ax-btn ax-btn--primary">
        Retour au tableau de bord
      </Link>
    </>
  );
}
