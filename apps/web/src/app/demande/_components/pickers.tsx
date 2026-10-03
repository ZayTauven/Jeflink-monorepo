"use client";

// Choix du métier (et du service) et du quartier. La recherche se fait hors ligne, dans le
// navigateur, avec la règle de l'API (`@jeflink/api-client/search`) : elle marche sans réseau
// une fois la page chargée. Les listes sont des groupes de radios natifs, sans bibliothèque.
import { useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";

import { Choice, Field, Fieldset, describedBy, inputClass } from "@/components/ui/form";
import {
  type TradeOption,
  type ZoneOption,
  searchTrades,
  searchZones,
} from "@/lib/requests/search";

const MAX_SHOWN = 8;

function SearchBox({
  id,
  label,
  placeholder,
  value,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field id={id} label={label}>
      <input
        id={id}
        type="search"
        inputMode="search"
        autoComplete="off"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={inputClass}
      />
    </Field>
  );
}

export function TradePicker({
  trades,
  tradeSlug,
  serviceSlug,
  onChange,
  error,
}: {
  trades: TradeOption[];
  tradeSlug: string;
  serviceSlug: string;
  onChange: (value: { tradeSlug: string; serviceSlug: string }) => void;
  error: string | undefined;
}) {
  const t = useTranslations("requests.form");
  const id = useId();
  const [query, setQuery] = useState("");
  const results = useMemo(() => searchTrades(query, trades), [query, trades]);
  const selected = trades.find((trade) => trade.slug === tradeSlug);
  const shown = results.slice(0, MAX_SHOWN);
  if (selected && !shown.some((trade) => trade.slug === selected.slug)) shown.unshift(selected);

  return (
    <div className="flex flex-col gap-4">
      <SearchBox
        id={`${id}-search`}
        label={t("trade.search")}
        placeholder={t("trade.placeholder")}
        value={query}
        onChange={setQuery}
      />
      <Fieldset id={id} legend={t("trade.legend")} error={error}>
        <div className="flex flex-col gap-2" data-field="trade">
          {shown.map((trade) => (
            <Choice
              key={trade.slug}
              name={`${id}-trade`}
              value={trade.slug}
              checked={trade.slug === tradeSlug}
              onChange={() => onChange({ tradeSlug: trade.slug, serviceSlug: "" })}
            >
              {trade.name}
            </Choice>
          ))}
        </div>
        <p role="status" className="text-sm text-ink-muted">
          {shown.length === 0 ? t("trade.empty") : ""}
        </p>
      </Fieldset>

      {selected && selected.services.length > 0 ? (
        <Fieldset id={`${id}-service`} legend={t("service.legend")}>
          <div className="flex flex-col gap-2">
            {selected.services.map((service) => (
              <Choice
                key={service.slug}
                name={`${id}-service`}
                value={service.slug}
                checked={service.slug === serviceSlug}
                onChange={() => onChange({ tradeSlug, serviceSlug: service.slug })}
              >
                {service.name}
              </Choice>
            ))}
            <Choice
              name={`${id}-service`}
              value=""
              checked={serviceSlug === ""}
              onChange={() => onChange({ tradeSlug, serviceSlug: "" })}
            >
              {t("service.none")}
            </Choice>
          </div>
        </Fieldset>
      ) : null}
    </div>
  );
}

export function ZonePicker({
  zones,
  zoneSlug,
  otherZone,
  zoneText,
  onChange,
  error,
}: {
  zones: ZoneOption[];
  zoneSlug: string;
  otherZone: boolean;
  zoneText: string;
  onChange: (value: { zoneSlug: string; otherZone: boolean; zoneText: string }) => void;
  error: string | undefined;
}) {
  const t = useTranslations("requests.form.zone");
  const id = useId();
  const [query, setQuery] = useState("");
  const results = useMemo(() => searchZones(query, zones), [query, zones]);
  const selected = zones.find((zone) => zone.slug === zoneSlug);
  const shown = results.slice(0, MAX_SHOWN);
  if (selected && !otherZone && !shown.some((zone) => zone.slug === selected.slug)) {
    shown.unshift(selected);
  }
  const textId = `${id}-text`;

  return (
    <div className="flex flex-col gap-4">
      <SearchBox
        id={`${id}-search`}
        label={t("search")}
        placeholder={t("placeholder")}
        value={query}
        onChange={setQuery}
      />
      <Fieldset id={id} legend={t("legend")} error={error}>
        <div className="flex flex-col gap-2" data-field="zone">
          {shown.map((zone) => (
            <Choice
              key={zone.slug}
              name={`${id}-zone`}
              value={zone.slug}
              checked={!otherZone && zone.slug === zoneSlug}
              onChange={() => onChange({ zoneSlug: zone.slug, otherZone: false, zoneText: "" })}
            >
              {zone.name}
            </Choice>
          ))}
          <Choice
            name={`${id}-zone`}
            value=""
            checked={otherZone}
            onChange={() => onChange({ zoneSlug: "", otherZone: true, zoneText })}
          >
            {t("other")}
          </Choice>
        </div>
        <p role="status" className="text-sm text-ink-muted">
          {shown.length === 0 ? t("empty") : ""}
        </p>
      </Fieldset>

      {otherZone ? (
        <Field id={textId} label={t("otherLabel")} hint={t("otherHint")}>
          <input
            id={textId}
            type="text"
            maxLength={80}
            autoComplete="off"
            value={zoneText}
            placeholder={t("otherPlaceholder")}
            aria-describedby={describedBy(textId, { hint: true })}
            onChange={(event) =>
              onChange({ zoneSlug: "", otherZone: true, zoneText: event.target.value })
            }
            className={inputClass}
          />
        </Field>
      ) : null}
    </div>
  );
}
