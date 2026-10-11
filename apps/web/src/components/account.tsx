import type { ReactNode } from "react";

import type { RequestStatus, ServiceRequest } from "@/lib/types";
import { formatDate } from "@/lib/format";

import { fadeUp, lines, PERSPECTIVE, Pill, SECTION_X } from "./crafto";

/** En-tête des pages de l'espace : la carte titre du template (pilule + grand titre). */
export function AccountHero({
  pill,
  title,
  children,
  aside,
}: {
  pill: string;
  title: ReactNode;
  children?: ReactNode;
  aside: ReactNode;
}) {
  return (
    <section className={`${SECTION_X} pt-0 md-pt-50px top-space-margin`}>
      <div className="container-fluid">
        <div className="row">
          <div className="col-lg-5 col-xl-4 md-mb-30px">
            <div className="bg-white border-radius-20px p-12 sm-p-7 h-100 d-flex flex-column align-items-start">
              <Pill className="text-white bg-base-color mb-50px sm-mb-30px" anime={fadeUp()}>
                {pill}
              </Pill>
              <h1
                className="h3 alt-font fw-500 ls-minus-2px mb-20px"
                style={PERSPECTIVE}
                data-anime={lines()}
              >
                {title}
              </h1>
              {children}
            </div>
          </div>
          <div className="col-lg-7 col-xl-8">{aside}</div>
        </div>
      </div>
    </section>
  );
}

export function StatusPill({ status, label }: { status: RequestStatus; label: string }) {
  return <span className={`status-pill status-${status}`}>{label}</span>;
}

export function ErrorAlert({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <div className="alert alert-danger mb-25px" role="alert">
      {message}
    </div>
  );
}

/** Carte d'une demande dans les listes du tableau de bord. */
export function RequestCard({ req, viewer }: { req: ServiceRequest; viewer: "client" | "pro" }) {
  const myQuote = viewer === "pro" ? req.quotes[0] : undefined;
  return (
    <a
      href={`/espace/demandes/${req.id}`}
      className="d-block bg-white border-radius-20px p-30px sm-p-25px mb-20px box-shadow-quadruple-large-hover text-dark-gray"
    >
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-10px">
        <span className="fs-14 text-uppercase fw-500 opacity-7">
          <i className={`bi ${req.trade.icon} text-base-color me-5px`} />
          {req.trade.name} · {req.zone.name}
        </span>
        <StatusPill status={req.status} label={req.status_label} />
      </div>
      <span className="alt-font fs-24 fw-500 ls-minus-1px d-block mb-5px">
        {req.is_urgent && <span className="text-base-color">Urgent · </span>}
        {req.title}
      </span>
      <span className="fs-15 opacity-7">
        Publiée le {formatDate(req.created_at)}
        {viewer === "client" && req.status === "open" && ` · ${req.quotes_count} devis reçu(s)`}
        {viewer === "client" && req.pro && ` · ${req.pro.name}`}
        {myQuote && ` · votre devis : ${myQuote.status_label.toLowerCase()}`}
        {viewer === "pro" && !myQuote && req.status === "open" && ` · ${req.client.name}`}
      </span>
    </a>
  );
}
