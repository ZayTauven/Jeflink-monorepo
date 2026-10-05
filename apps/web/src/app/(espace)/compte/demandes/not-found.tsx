import { getTranslations } from "next-intl/server";

import { PageShell } from "@/components/page-shell";
import { ButtonLink } from "@/components/ui/button";

export default async function RequestNotFound() {
  const t = await getTranslations("requests.notFound");
  return (
    <PageShell>
      <section className="flex flex-col items-start gap-4">
        <h1 className="font-display text-balance text-4xl leading-[1.05] tracking-tight">
          {t("title")}
        </h1>
        <p className="text-lg leading-relaxed text-ink-muted">{t("lead")}</p>
        <ButtonLink href="/compte/demandes" variant="primary">
          {t("back")}
        </ButtonLink>
      </section>
    </PageShell>
  );
}
