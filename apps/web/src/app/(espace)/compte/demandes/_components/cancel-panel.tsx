"use client";

// Annulation d'une demande ou d'une réservation, avec un motif de la liste fermée (spec 003).
// Le formulaire s'ouvre dans la page ; « other » demande une note de 200 caractères au plus.
import { refreshWebSession } from "@jeflink/api-client/web";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useId, useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Choice, Field, Fieldset, describedBy, inputClass } from "@/components/ui/form";
import type { RequestError } from "@/lib/requests/errors";
import { callAction } from "@/lib/requests/result";
import { CLIENT_REASONS, MAX_NOTE, validateCancel } from "@/lib/requests/status";

import { RefreshButton } from "./refresh-button";
import { cancelAction } from "../actions";

export function CancelPanel({ kind, id }: { kind: "request" | "booking"; id: string }) {
  const t = useTranslations("requests.cancel");
  const tErr = useTranslations("requests.errors");
  const router = useRouter();
  const [, startRefresh] = useTransition();
  const uid = useId();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<"reason" | "note" | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<RequestError | null>(null);
  const noteId = `${uid}-note`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    const found = validateCancel(reason, note);
    setProblem(found);
    if (found) return;
    setPending(true);
    setError(null);
    const result = await callAction(
      () => cancelAction({ kind, id, reason, note }),
      refreshWebSession,
    );
    if (result.ok) {
      startRefresh(() => router.refresh());
      return;
    }
    setPending(false);
    if (result.error.login) {
      window.location.assign(`/connexion?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    setError(result.error);
  }

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)} aria-expanded={false}>
        {kind === "request" ? t("openRequest") : t("openBooking")}
      </Button>
    );
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      className="flex flex-col gap-5 rounded-card border border-line bg-surface p-5"
    >
      <Fieldset
        id={`${uid}-reason`}
        legend={t("title")}
        error={problem === "reason" ? t("reasonError") : undefined}
      >
        <div className="flex flex-col gap-2">
          {CLIENT_REASONS.map((code) => (
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

      {reason === "other" ? (
        <Field
          id={noteId}
          label={t("note")}
          hint={t("noteHint")}
          error={problem === "note" ? t("noteError") : undefined}
        >
          <textarea
            id={noteId}
            rows={3}
            maxLength={MAX_NOTE}
            value={note}
            aria-invalid={problem === "note" ? true : undefined}
            aria-describedby={describedBy(noteId, { hint: true, error: problem === "note" })}
            onChange={(event) => {
              setNote(event.target.value);
              setProblem(null);
            }}
            className={inputClass}
          />
        </Field>
      ) : null}

      {error ? (
        <Alert
          tone="error"
          action={
            error.code === "transition_not_allowed" || error.code === "request_closed" ? (
              <RefreshButton />
            ) : undefined
          }
        >
          {tErr(error.key, error.values)}
        </Alert>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="submit" disabled={pending} aria-busy={pending}>
          {pending ? t("confirming") : t("confirm")}
        </Button>
        <Button variant="secondary" onClick={() => setOpen(false)} disabled={pending}>
          {kind === "request" ? t("keepRequest") : t("keepBooking")}
        </Button>
      </div>
    </form>
  );
}
