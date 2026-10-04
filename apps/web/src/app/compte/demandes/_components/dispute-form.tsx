"use client";

// Signalement d'un problème après la mission (spec 004, web 3). Question métier : « Je ne suis pas
// satisfait : que puis-je faire, et que va-t-il se passer ? ». Motif de la liste fermée, texte de
// 10 à 1 000 caractères, jusqu'à l'échéance. L'écran dit ce que Jeflink fait (examine et décide)
// et ce qu'il ne fait pas encore (pas de remboursement), avant l'envoi.
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Choice, Field, Fieldset, describedBy, inputClass } from "@/components/ui/form";
import { DISPUTE_MAX, DISPUTE_MIN, DISPUTE_REASONS, validateDispute } from "@/lib/bookings/dispute";

import { disputeAction } from "../finish-actions";
import { ActionError } from "./action-error";
import { useBookingAction } from "./use-booking-action";

export function DisputeForm({
  bookingId,
  deadlineText,
  supportHref,
  onCancel,
}: {
  bookingId: string;
  /** Échéance en heure de Dakar, déjà formatée (« 14 h 30 » ou « 5 oct. · 14 h 30 »). */
  deadlineText: string;
  supportHref: string | null;
  onCancel: () => void;
}) {
  const t = useTranslations("bookings.dispute");
  const uid = useId();
  const action = useBookingAction();
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<"reason" | "description" | null>(null);
  const textId = `${uid}-text`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (action.pending) return;
    const found = validateDispute(reason, text);
    setProblem(found);
    if (found) return;
    // Au succès, la page se rafraîchit : l'écran de litige prend la place du formulaire.
    await action.run(() => disputeAction({ bookingId, reason, description: text }));
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      className="flex flex-col gap-5 rounded-card border border-line-strong p-4 sm:p-5"
    >
      <p className="text-base leading-relaxed text-ink">{t("until", { when: deadlineText })}</p>

      <Fieldset
        id={`${uid}-reason`}
        legend={t("reasonLegend")}
        error={problem === "reason" ? t("reasonError") : undefined}
      >
        <div className="flex flex-col gap-2">
          {DISPUTE_REASONS.map((code) => (
            <Choice
              key={code}
              name={`${uid}-reason`}
              value={code}
              checked={reason === code}
              onChange={() => {
                setReason(code);
                setProblem(null);
              }}
            >
              {t(`reasons.${code}`)}
            </Choice>
          ))}
        </div>
      </Fieldset>

      <Field
        id={textId}
        label={t("textLabel")}
        hint={t("textHint", { min: DISPUTE_MIN })}
        error={problem === "description" ? t("textError", { min: DISPUTE_MIN }) : undefined}
      >
        <textarea
          id={textId}
          rows={5}
          maxLength={DISPUTE_MAX}
          value={text}
          aria-invalid={problem === "description" ? true : undefined}
          aria-describedby={describedBy(textId, { hint: true, error: problem === "description" })}
          onChange={(event) => {
            setText(event.target.value);
            setProblem(null);
          }}
          className={inputClass}
        />
      </Field>

      <p className="rounded-card bg-sand p-4 text-base font-medium leading-relaxed text-ink">
        {t("decision")}
      </p>

      {action.error ? <ActionError error={action.error} supportHref={supportHref} /> : null}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="submit" disabled={action.pending} aria-busy={action.pending}>
          {action.pending ? t("sending") : t("send")}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={action.pending}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
