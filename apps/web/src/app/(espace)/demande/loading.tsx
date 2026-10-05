import { getTranslations } from "next-intl/server";

import { PageShell } from "@/components/page-shell";

// Le formulaire attend le profil et le catalogue : un texte et des blocs sobres, pas de loader plein écran.
export default async function Loading() {
  const t = await getTranslations("requests.detail");
  return (
    <PageShell>
      <p role="status" className="text-lg text-ink-muted">
        {t("loading")}
      </p>
      <div aria-hidden="true" className="mt-6 flex flex-col gap-3">
        <div className="h-14 rounded-card border border-line bg-surface" />
        <div className="h-48 rounded-card border border-line bg-surface" />
      </div>
    </PageShell>
  );
}
