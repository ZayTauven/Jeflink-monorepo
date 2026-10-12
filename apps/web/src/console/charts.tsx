"use client";

/**
 * Graphiques de la console, sur le composant ApexChart de vireo (src/vireo/charts).
 * Règles dataviz : un seul axe, légende + étiquettes, couleurs = jetons --ax-chart-*.
 */
import { ApexChart } from "@/vireo/charts/ApexChart";

type Day = { date: string; created: number; booked: number };

const FR = {
  name: "fr",
  options: {
    months: [
      "janvier",
      "février",
      "mars",
      "avril",
      "mai",
      "juin",
      "juillet",
      "août",
      "septembre",
      "octobre",
      "novembre",
      "décembre",
    ],
    shortMonths: [
      "janv.",
      "févr.",
      "mars",
      "avr.",
      "mai",
      "juin",
      "juil.",
      "août",
      "sept.",
      "oct.",
      "nov.",
      "déc.",
    ],
    days: ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"],
    shortDays: ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."],
  },
};

/** Au-delà d'un mois, une courbe par jour devient du bruit : on regroupe par semaine. */
function buckets(daily: Day[]): { points: Day[]; weekly: boolean } {
  if (daily.length <= 31) return { points: daily, weekly: false };
  // Semaines comptées à rebours depuis aujourd'hui : la dernière se termine ce jour.
  const points: Day[] = [];
  for (let end = daily.length; end > 0; end -= 7) {
    const week = daily.slice(Math.max(0, end - 7), end);
    points.unshift({
      date: week[0].date,
      created: week.reduce((n, d) => n + d.created, 0),
      booked: week.reduce((n, d) => n + d.booked, 0),
    });
  }
  return { points, weekly: true };
}

/** Demandes publiées et réservations : deux séries de même unité, un seul axe. */
export function ActivityChart({ daily }: { daily: Day[] }) {
  const total = daily.reduce((n, d) => n + d.created, 0);
  const booked = daily.reduce((n, d) => n + d.booked, 0);
  const { points, weekly } = buckets(daily);
  const at = (d: Day) => Date.parse(`${d.date}T00:00:00Z`);
  return (
    <>
      <div className="jf-legend" aria-hidden="true">
        <span>
          <i style={{ background: "var(--ax-chart-1)" }} />
          Demandes publiées ({total})
        </span>
        <span>
          <i style={{ background: "var(--ax-chart-2)" }} />
          Réservations ({booked})
        </span>
      </div>
      <ApexChart
        type="area"
        height={300}
        legend="none"
        ariaLabel={`Courbe ${weekly ? "hebdomadaire" : "journalière"} : ${total} demandes publiées et ${booked} réservations sur la période.`}
        series={[
          { name: "Demandes publiées", data: points.map((d) => ({ x: at(d), y: d.created })) },
          { name: "Réservations", data: points.map((d) => ({ x: at(d), y: d.booked })) },
        ]}
        apex={{
          chart: { locales: [FR], defaultLocale: "fr" },
          stroke: { width: 2, curve: "monotoneCubic" },
          fill: { type: "gradient", gradient: { opacityFrom: 0.18, opacityTo: 0 } },
          xaxis: { type: "datetime", labels: { datetimeUTC: true, format: "d MMM" } },
          yaxis: {
            min: 0,
            forceNiceScale: true,
            labels: { formatter: (v: number) => `${Math.round(v)}` },
          },
          tooltip: {
            shared: true,
            intersect: false,
            x: { format: weekly ? "'semaine du' d MMM" : "dddd d MMM" },
          },
        }}
      />
    </>
  );
}
