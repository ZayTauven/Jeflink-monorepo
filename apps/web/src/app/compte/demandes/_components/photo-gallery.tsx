"use client";

// Photos de la mission (spec 004, web 2). Question métier : « Le travail correspond-il à ce qui
// était prévu ? ». Réseau faible : seules les miniatures (environ 20 Ko) se chargent ; l'image pleine
// s'ouvre sur demande, dans la page. Les URL sont signées pour 10 minutes : une URL expirée se
// renouvelle en actualisant la page (la réservation est relue). « Signaler cette photo » la masque
// pour le client et le pro ; l'Ops la garde pour un litige.
import type { Photo } from "@jeflink/api-client";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { type PhotoPhase, PHOTO_PHASES, isExpired, photosOf } from "@/lib/bookings/photos";

import { reportPhotoAction } from "../booking-actions";
import { ActionError } from "./action-error";
import { RefreshButton } from "./refresh-button";
import { useBookingAction } from "./use-booking-action";

export function PhotoGallery({
  bookingId,
  photos,
  now,
  supportHref,
}: {
  bookingId: string;
  photos: readonly Photo[];
  /** Instant du rendu serveur : décide si une URL signée a déjà expiré. */
  now: string;
  supportHref: string | null;
}) {
  const t = useTranslations("bookings.photos");
  const report = useBookingAction();
  const [openId, setOpenId] = useState<string | null>(null);
  const [reporting, setReporting] = useState(false);
  const [failed, setFailed] = useState<Set<string>>(new Set());

  const groups = PHOTO_PHASES.map((phase) => ({ phase, items: photosOf(photos, phase) })).filter(
    (group) => group.items.length > 0,
  );
  if (groups.length === 0) return null;

  const opened = photos.find((photo) => photo.public_id === openId) ?? null;
  const stale = (photo: Photo) => failed.has(photo.public_id) || isExpired(photo.expires_at, now);

  async function reportOpened() {
    if (!opened) return;
    if (await report.run(() => reportPhotoAction(bookingId, opened.public_id))) {
      setOpenId(null);
      setReporting(false);
    }
  }

  return (
    <section
      aria-labelledby="photos-title"
      className="flex flex-col gap-5 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="photos-title" className="font-display text-2xl tracking-tight">
        {t("title")}
      </h2>

      {groups.map(({ phase, items }) => (
        <PhaseGroup
          key={phase}
          phase={phase}
          items={items}
          stale={stale}
          onOpen={(photo) => {
            setOpenId(photo.public_id);
            setReporting(false);
            report.clearError();
          }}
          onFail={(photo) => setFailed((current) => new Set(current).add(photo.public_id))}
          openId={openId}
        />
      ))}

      {opened ? (
        <div
          role="group"
          aria-label={t("viewerLabel")}
          className="flex flex-col gap-4 rounded-card border border-line-strong p-4"
        >
          {stale(opened) ? (
            <Alert tone="info" action={<RefreshButton />}>
              {t("expired")}
            </Alert>
          ) : (
            <Image
              src={opened.url}
              alt={t(`alt.${opened.phase}`)}
              width={opened.width}
              height={opened.height}
              unoptimized
              onError={() => setFailed((current) => new Set(current).add(opened.public_id))}
              className="h-auto w-full rounded-card bg-sand"
            />
          )}

          {report.error ? <ActionError error={report.error} supportHref={supportHref} /> : null}

          {reporting ? (
            <div className="flex flex-col gap-3">
              <p className="text-base font-medium text-ink">{t("reportTitle")}</p>
              <p className="text-base text-ink-muted">{t("reportLead")}</p>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Button onClick={reportOpened} disabled={report.pending} aria-busy={report.pending}>
                  {report.pending ? t("reporting") : t("reportYes")}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setReporting(false)}
                  disabled={report.pending}
                >
                  {t("reportNo")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button variant="secondary" onClick={() => setReporting(true)}>
                {t("report")}
              </Button>
              <Button variant="quiet" onClick={() => setOpenId(null)}>
                {t("close")}
              </Button>
            </div>
          )}
        </div>
      ) : null}

      <p className="text-sm text-ink-muted">{t("retention")}</p>
    </section>
  );
}

function PhaseGroup({
  phase,
  items,
  stale,
  onOpen,
  onFail,
  openId,
}: {
  phase: PhotoPhase;
  items: Photo[];
  stale: (photo: Photo) => boolean;
  onOpen: (photo: Photo) => void;
  onFail: (photo: Photo) => void;
  openId: string | null;
}) {
  const t = useTranslations("bookings.photos");
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-lg font-medium text-ink">
        {t(`phase.${phase}`, { count: items.length })}
      </h3>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {items.map((photo, index) => (
          <li key={photo.public_id} className="flex flex-col gap-2">
            {photo.status === "processing" ? (
              <p className="flex aspect-[4/3] items-center justify-center rounded-card border border-line bg-sand p-3 text-center text-sm text-ink-muted">
                {t("processing")}
              </p>
            ) : (
              <button
                type="button"
                onClick={() => onOpen(photo)}
                aria-expanded={openId === photo.public_id}
                className="relative aspect-[4/3] min-h-12 overflow-hidden rounded-card border border-line bg-sand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
              >
                {stale(photo) ? (
                  <span className="flex h-full items-center justify-center p-3 text-center text-sm text-ink-muted">
                    {t("expiredThumb")}
                  </span>
                ) : (
                  <Image
                    src={photo.thumb_url}
                    alt={t(`alt.${photo.phase}`)}
                    fill
                    sizes="(min-width: 640px) 200px, 45vw"
                    unoptimized
                    onError={() => onFail(photo)}
                    className="object-cover"
                  />
                )}
              </button>
            )}
            <span className="text-sm text-ink-muted">
              {t("caption", { number: index + 1 })}
              {photo.status === "processing" ? "" : ` · ${t("enlarge")}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
