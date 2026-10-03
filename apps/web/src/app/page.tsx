import { getTranslations } from "next-intl/server";

// Accueil provisoire : le site public (direction Crafto) fait l'objet de sa propre spec.
export default async function HomePage() {
  const t = await getTranslations("home");
  return (
    <main className="mx-auto max-w-3xl px-6 py-24">
      <h1 className="font-display text-5xl leading-[1.05] tracking-tight">{t("title")}</h1>
      <p className="mt-6 text-lg text-ink-muted">{t("lead")}</p>
    </main>
  );
}
