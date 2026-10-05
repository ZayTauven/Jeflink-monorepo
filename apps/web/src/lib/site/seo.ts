// Métadonnées du site public (spec 006, « SEO »). Module pur, testé seul : titre de 60 caractères
// au plus, description de 155, `og:description` de 100 (deux lignes dans l'aperçu WhatsApp),
// canonical relatif résolu par `metadataBase`, `og:locale` fr_SN. Une page non indexable porte
// `noindex, follow` et son canonical pointe vers elle-même, jamais vers une autre page.
import type { Metadata } from "next";

export const TITLE_MAX = 60;
export const DESCRIPTION_MAX = 155;
export const OG_DESCRIPTION_MAX = 100;

/** Coupe à `max` caractères, au dernier mot entier, avec « … » ; texte court : inchangé. */
export function truncate(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max - 1);
  const space = cut.lastIndexOf(" ");
  return `${(space > max / 2 ? cut.slice(0, space) : cut).replace(/[ ,.;:]+$/, "")}…`;
}

export type PageSeo = {
  /** Titre de la page (le `h1`), sans la marque. */
  title: string;
  /** Titre complet déjà composé avec la marque (« {h1} · Jeflink »). */
  fullTitle: string;
  description: string;
  ogDescription?: string;
  /** Chemin canonique de la page (`/plombier/ouakam`), avec requête éventuelle. */
  path: string;
  indexable?: boolean;
  siteName: string;
  locale: string;
};

export function pageMetadata(seo: PageSeo): Metadata {
  const title = truncate(seo.fullTitle, TITLE_MAX);
  const description = truncate(seo.description, DESCRIPTION_MAX);
  return {
    title: { absolute: title },
    description,
    alternates: { canonical: seo.path },
    openGraph: {
      type: "website",
      title,
      description: truncate(seo.ogDescription ?? seo.description, OG_DESCRIPTION_MAX),
      url: seo.path,
      siteName: seo.siteName,
      locale: seo.locale,
    },
    ...(seo.indexable === false ? { robots: { index: false, follow: true } } : {}),
  };
}
