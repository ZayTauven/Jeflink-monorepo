// Tests des données structurées (spec 006, web 10) : types attendus, pas de prix sans prix saisi,
// ni LocalBusiness ni AggregateRating ni FAQPage, échappement de `<`.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  breadcrumbJsonLd,
  lowestPrice,
  organizationJsonLd,
  serializeJsonLd,
  serviceJsonLd,
  websiteJsonLd,
} from "./jsonld.ts";

const service = {
  serviceType: "Plomberie",
  name: "Plombier à Ouakam",
  url: "https://jeflink.sn/plombier/ouakam",
  providerName: "Jeflink",
  providerUrl: "https://jeflink.sn",
  area: { name: "Ouakam", city: "Dakar" },
};

describe("serviceJsonLd", () => {
  it("Service avec fournisseur, zone desservie dans sa ville, prix de départ en XOF", () => {
    const data = serviceJsonLd({ ...service, minPriceXof: 5000 }) as Record<string, any>;
    assert.equal(data["@type"], "Service");
    assert.equal(data.provider["@type"], "Organization");
    assert.equal(data.areaServed["@type"], "Place");
    assert.equal(data.areaServed.containedInPlace.name, "Dakar");
    assert.equal(data.offers.priceSpecification.minPrice, 5000);
    assert.equal(data.offers.priceSpecification.priceCurrency, "XOF");
  });

  it("sans prix saisi : aucune offre", () => {
    for (const price of [null, undefined, 0, Number.NaN]) {
      assert.ok(!("offers" in serviceJsonLd({ ...service, minPriceXof: price })), String(price));
    }
  });

  it("page métier sans quartier : pas de zone desservie", () => {
    assert.ok(!("areaServed" in serviceJsonLd({ ...service, area: null })));
  });
});

describe("autres blocs", () => {
  it("Organization : contactPoint seulement avec un numéro ; jamais LocalBusiness ni note", () => {
    const base = { name: "Jeflink", url: "https://jeflink.sn", description: "x" };
    const without = organizationJsonLd(base);
    assert.ok(!("contactPoint" in without));
    const withPhone = organizationJsonLd({ ...base, phone: "+221330000001" });
    assert.ok("contactPoint" in withPhone);
    for (const data of [without, withPhone, websiteJsonLd(base), serviceJsonLd(service)]) {
      const text = JSON.stringify(data);
      assert.doesNotMatch(text, /LocalBusiness|AggregateRating|FAQPage|aggregateRating/);
    }
  });

  it("BreadcrumbList : positions à partir de 1", () => {
    const data = breadcrumbJsonLd([
      { name: "Accueil", url: "https://jeflink.sn/" },
      { name: "Plombier", url: "https://jeflink.sn/plombier" },
    ]) as Record<string, any>;
    assert.deepEqual(
      data.itemListElement.map((item: { position: number }) => item.position),
      [1, 2],
    );
  });

  it("serializeJsonLd échappe « < » (aucune fermeture de script possible)", () => {
    const text = serializeJsonLd({ name: "</script><script>alert(1)</script>" });
    assert.ok(!text.includes("<"));
    assert.deepEqual(JSON.parse(text), { name: "</script><script>alert(1)</script>" });
  });
});

describe("lowestPrice", () => {
  it("le plus petit prix saisi, ou null", () => {
    assert.equal(lowestPrice([null, 8000, 5000, undefined, 0]), 5000);
    assert.equal(lowestPrice([null, undefined]), null);
    assert.equal(lowestPrice([]), null);
  });
});
