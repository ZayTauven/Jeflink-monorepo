// /connexion (spec 001, web 2). Question métier : « Comment entrer dans Jeflink avec mon seul
// numéro ? ». Action principale : recevoir puis saisir le code SMS.
//
// Rendu serveur : la configuration OTP (indicatifs, longueur du code, version des conditions)
// arrive avec la page, sans aller-retour de plus sur un réseau lent. La page ne redirige jamais
// d'après le témoin de session (boucle sur un refresh en 429 ou 5xx) ; `next` est revalidé.
import { type AuthConfig, authConfig } from "@jeflink/api-client";
import { safeNextPath } from "@jeflink/api-client/paths";
import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { CheckIcon } from "@/components/ui/icons";
import { Logo } from "@/components/ui/logo";
import { serverApi } from "@/lib/bff";
import { readSiteConfig } from "@/lib/site-config";

import { LoginFlow } from "./_components/login-flow";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("connexion");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function single(value: string | string[] | undefined): string | null {
  return typeof value === "string" ? value : null;
}

export default async function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const next = safeNextPath(single(params.next));
  const api = await serverApi();
  let config: AuthConfig | null = null;
  try {
    config = (await authConfig(api.options)).data;
  } catch {
    config = null; // le client réessaie lui-même
  }
  // Refresh impossible pour une raison passagère : on propose d'abord de réessayer.
  const retryHref = single(params.raison) === "indisponible" ? api.refreshPath(next) : null;
  const { supportWhatsapp } = readSiteConfig(process.env);
  const t = await getTranslations("connexion.aside");
  const tBrand = await getTranslations("brand");

  return (
    <div className="min-h-dvh bg-paper">
      <div className="mx-auto grid min-h-dvh max-w-6xl lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-8 lg:p-6">
        <aside className="hidden flex-col justify-between rounded-card bg-sand p-12 lg:flex">
          <Link
            href="/"
            aria-label={tBrand("home")}
            className="inline-flex min-h-12 items-center self-start"
          >
            <Logo />
          </Link>
          <div className="flex flex-col gap-10">
            <p className="font-display text-5xl leading-[1.05] tracking-tight text-ink">
              {t("title")}
            </p>
            <ul className="flex flex-col gap-5">
              {[t("verified"), t("price"), t("guarantee")].map((text) => (
                <li key={text} className="flex gap-4 text-lg leading-snug text-ink">
                  <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-pill bg-accent text-on-accent">
                    <CheckIcon className="size-4" />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>
        </aside>

        <main className="flex flex-col px-4 pb-12 pt-6 sm:px-10 lg:justify-center lg:py-12">
          <Link
            href="/"
            aria-label={tBrand("home")}
            className="mb-8 inline-flex min-h-12 items-center self-start lg:hidden"
          >
            <Logo />
          </Link>
          <div className="w-full max-w-md lg:mx-auto">
            <LoginFlow
              initialConfig={config}
              next={next}
              retryHref={retryHref}
              supportWhatsapp={supportWhatsapp}
            />
          </div>
        </main>
      </div>
    </div>
  );
}
