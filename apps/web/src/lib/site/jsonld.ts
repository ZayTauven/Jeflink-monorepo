// Données structurées du site public (spec 006, « SEO », Q11) : Organization, WebSite, Service,
// BreadcrumbList. Ni LocalBusiness (aucune adresse ouverte au public par quartier), ni
// AggregateRating (avis sur soi-même non éligibles), ni FAQPage. Le prix n'apparaît que s'il est
// saisi. Modules purs, testés seuls ; `serializeJsonLd` échappe `<` (doc embarquée de Next).

export type JsonLd = Record<string, unknown>;

const CONTEXT = "https://schema.org";

export function organizationJsonLd(input: {
  name: string;
  url: string;
  description: string;
  /** Numéro d'appel du support (E.164), seulement s'il est configuré. */
  phone?: string | null;
}): JsonLd {
  return {
    "@context": CONTEXT,
    "@type": "Organization",
    name: input.name,
    url: input.url,
    description: input.description,
    ...(input.phone
      ? {
          contactPoint: {
            "@type": "ContactPoint",
            contactType: "customer support",
            telephone: input.phone,
            availableLanguage: ["fr", "wo"],
          },
        }
      : {}),
  };
}

export function websiteJsonLd(input: { name: string; url: string }): JsonLd {
  return { "@context": CONTEXT, "@type": "WebSite", name: input.name, url: input.url };
}

export function serviceJsonLd(input: {
  /** Nom du service rendu : le métier (« Plomberie »). */
  serviceType: string;
  /** Titre de la page (« Plombier à Ouakam »). */
  name: string;
  url: string;
  providerName: string;
  providerUrl: string;
  /** Quartier desservi et sa ville, pour un métier × quartier. */
  area?: { name: string; city: string } | null | undefined;
  /** Prix de départ en XOF entier, seulement s'il est saisi. */
  minPriceXof?: number | null | undefined;
}): JsonLd {
  const price = input.minPriceXof;
  return {
    "@context": CONTEXT,
    "@type": "Service",
    serviceType: input.serviceType,
    name: input.name,
    url: input.url,
    provider: { "@type": "Organization", name: input.providerName, url: input.providerUrl },
    ...(input.area
      ? {
          areaServed: {
            "@type": "Place",
            name: input.area.name,
            containedInPlace: { "@type": "City", name: input.area.city },
          },
        }
      : {}),
    ...(typeof price === "number" && Number.isFinite(price) && price > 0
      ? {
          offers: {
            "@type": "Offer",
            priceCurrency: "XOF",
            priceSpecification: {
              "@type": "PriceSpecification",
              minPrice: Math.trunc(price),
              priceCurrency: "XOF",
            },
          },
        }
      : {}),
  };
}

export function breadcrumbJsonLd(items: readonly { name: string; url: string }[]): JsonLd {
  return {
    "@context": CONTEXT,
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

/** Texte à poser dans la balise `<script type="application/ld+json">`. */
export function serializeJsonLd(data: JsonLd): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

/** Plus petit prix de départ saisi parmi des services, ou null si aucun n'en a. */
export function lowestPrice(prices: readonly (number | null | undefined)[]): number | null {
  const valid = prices.filter(
    (price): price is number => typeof price === "number" && Number.isFinite(price) && price > 0,
  );
  return valid.length ? Math.min(...valid) : null;
}
