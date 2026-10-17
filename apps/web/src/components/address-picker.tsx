"use client";

import type { MouseEvent } from "react";

import type { SavedAddress } from "@/lib/types";

/**
 * « Mes adresses » au-dessus du formulaire de demande : un geste remplit le quartier et le
 * repère. Avec JavaScript, sans recharger (la saisie reste) ; sans, le lien recharge la page
 * avec `?adresse=` et le serveur pré-remplit les champs.
 */
export function AddressPicker({
  addresses,
  base,
  selected,
}: {
  addresses: SavedAddress[];
  /** Adresse de la page (avec sa requête) : le lien y ajoute `adresse=`. */
  base: string;
  selected?: number;
}) {
  const hrefFor = (id: number) => `${base}${base.includes("?") ? "&" : "?"}adresse=${id}`;

  function pick(event: MouseEvent<HTMLAnchorElement>, address: SavedAddress) {
    const zone = document.getElementById("zone") as HTMLSelectElement | null;
    const landmark = document.getElementById("landmark") as HTMLInputElement | null;
    if (!zone || !landmark) return; // repli : le lien recharge la page
    event.preventDefault();
    zone.value = address.zone;
    landmark.value = address.landmark;
    const save = document.getElementById("save-address");
    if (save) {
      save.hidden = true; // déjà enregistrée
      const name = save.querySelector("input");
      if (name) name.value = ""; // un champ masqué partirait quand même : pas de doublon
    }
    event.currentTarget
      .closest("[data-addresses]")
      ?.querySelectorAll("a")
      .forEach((a) => a.setAttribute("aria-current", String(a === event.currentTarget)));
    landmark.focus();
  }

  return (
    <div className="mb-25px" data-addresses role="group" aria-labelledby="mes-adresses">
      <span id="mes-adresses" className="d-block fs-14 fw-500 text-dark-gray mb-10px">
        Mes adresses
      </span>
      <div className="jf-checks">
        {addresses.map((a) => (
          <a
            key={a.id}
            href={hrefFor(a.id)}
            className="jf-address-chip"
            aria-current={a.id === selected}
            onClick={(e) => pick(e, a)}
          >
            <i className="feather icon-feather-map-pin" aria-hidden="true" />
            <span>
              {a.label} · {a.zone_name}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
