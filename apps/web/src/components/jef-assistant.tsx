"use client";

import { useEffect, useId, useRef, useState } from "react";

import type { JefSession } from "@/lib/types";

import { JefFacts } from "./jef-facts";

type Reply = { ok: true; session: JefSession } | { ok: false; error: string };
type Step = "describe" | "questions" | "brief" | "done";

/** Débuts de phrase pour qui écrit peu : un toucher remplit le champ, le client complète. */
const STARTERS = [
  "J'ai une fuite d'eau",
  "Je n'ai plus de courant",
  "Ma clim ne refroidit plus",
  "Mon frigo ne marche plus",
];

/** Au-delà, on rend la main : sur réseau mobile, mieux vaut le formulaire qu'une attente. */
const TIMEOUT_MS = 30_000;

async function post(url: string, body: unknown): Promise<Reply> {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    return (await res.json()) as Reply;
  } catch (err) {
    const slow = err instanceof DOMException && err.name === "TimeoutError";
    return {
      ok: false,
      error: slow
        ? "Jef met trop de temps à répondre. Réessayez, ou remplissez le formulaire directement."
        : "Connexion impossible. Vérifiez votre réseau et réessayez.",
    };
  }
}

/** Remplit un champ du formulaire de demande (rendu par le serveur, juste en dessous). */
function fill(id: string, value: string) {
  const el = document.getElementById(id) as HTMLInputElement | HTMLTextAreaElement | null;
  if (el) el.value = value;
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <span className="d-block fw-500 text-dark-gray mb-5px">{title}</span>
      <ul className="jf-jef-list mb-15px">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </>
  );
}

/**
 * Jef, l'assistant de réservation : le client raconte son souci avec ses mots, répond à quelques
 * questions à choix, et Jef remplit le formulaire (titre, description, métier, urgence) avec une
 * fiche pour le pro. Sans JavaScript, le formulaire classique reste disponible.
 */
export function JefAssistant() {
  const uid = useId();
  const [step, setStep] = useState<Step>("describe");
  const [open, setOpen] = useState(true);
  const [text, setText] = useState("");
  const [session, setSession] = useState<JefSession | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const panel = useRef<HTMLElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const moved = useRef(false);

  // Après chaque étape (et pas au premier rendu), le focus va sur le début de l'étape.
  useEffect(() => {
    if (moved.current) panel.current?.querySelector<HTMLElement>("[data-focus]")?.focus();
  }, [step]);

  async function run(url: string, body: unknown, next: Step) {
    if (pending) return;
    setPending(true);
    setError("");
    const reply = await post(url, body);
    setPending(false);
    if (!reply.ok) {
      setError(reply.error);
      return;
    }
    setSession(reply.session);
    moved.current = true;
    setStep(next);
  }

  function ask() {
    if (text.trim().length < 10) {
      setError("Écrivez quelques mots de plus pour que Jef comprenne (10 caractères au moins).");
      field.current?.focus();
      return;
    }
    const trade = (document.getElementById("trade") as HTMLSelectElement | null)?.value ?? "";
    run("/act/jef", { text, trade }, "questions");
  }

  function start(starter: string) {
    setText(`${starter} `);
    field.current?.focus();
  }

  function use() {
    const brief = session?.brief;
    if (!session || !brief) return;
    fill("title", brief.title);
    fill("description", brief.description);
    fill("jef_session", String(session.id));
    if (session.trade) fill("trade", session.trade.slug);
    const urgent = document.querySelector<HTMLInputElement>('input[name="is_urgent"]');
    if (urgent) urgent.checked = brief.urgent;
    setStep("done");
    document.getElementById("zone")?.focus();
  }

  function restart() {
    setStep("describe");
    setSession(null);
    setAnswers({});
    setError("");
    fill("jef_session", "");
    moved.current = true;
  }

  if (!open) {
    return (
      <p className="mb-25px">
        <button type="button" className="btn btn-link p-0 fw-500" onClick={() => setOpen(true)}>
          <i className="bi bi-stars text-base-color me-5px" aria-hidden="true" />
          Me faire aider par Jef
        </button>
      </p>
    );
  }

  const status = pending
    ? step === "questions"
      ? "Jef prépare la demande…"
      : "Jef réfléchit…"
    : step === "done"
      ? "Le formulaire est rempli. Choisissez votre quartier, relisez, puis publiez."
      : "";

  return (
    <section
      ref={panel}
      className="jf-jef jf-form border-radius-20px p-30px sm-p-25px mb-30px"
      aria-labelledby={`${uid}-title`}
    >
      <div className="d-flex align-items-center gap-2 mb-10px">
        <span className="jf-jef__badge" aria-hidden="true">
          <i className="bi bi-stars" />
        </span>
        <h2 id={`${uid}-title`} className="alt-font fs-22 fw-500 ls-minus-05px mb-0">
          Jef vous aide à décrire votre souci
        </h2>
      </div>

      {error && (
        <div className="alert alert-danger mb-20px" role="alert">
          {error}
        </div>
      )}
      <div className="visually-hidden" aria-live="polite">
        {status}
      </div>

      {step === "describe" && (
        <>
          <div className="jf-checks mb-15px" role="group" aria-label="Pour commencer">
            {STARTERS.map((starter) => (
              <button
                key={starter}
                type="button"
                className="jf-jef__starter"
                onClick={() => start(starter)}
              >
                {starter}
              </button>
            ))}
          </div>
          <label htmlFor={`${uid}-text`} className="mb-5px">
            Racontez ce qui se passe, avec vos mots
          </label>
          <textarea
            ref={field}
            id={`${uid}-text`}
            className="form-control mb-5px"
            rows={3}
            maxLength={2000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ex. : l'eau coule sous l'évier depuis ce matin"
            aria-describedby={`${uid}-aide`}
            data-focus
          />
          <div className="hint mb-20px" id={`${uid}-aide`}>
            Depuis quand, où, ce que vous voyez. Vous pouvez dicter avec le micro du clavier. Ne
            mettez ni numéro ni adresse&nbsp;: le pro les reçoit à la réservation.
          </div>
          <div className="d-flex flex-wrap align-items-center gap-3">
            <button
              type="button"
              className="btn btn-medium btn-dark-gray btn-rounded btn-box-shadow"
              onClick={ask}
              aria-disabled={pending}
            >
              {pending ? "Jef réfléchit…" : "Demander à Jef"}
            </button>
            <button
              type="button"
              className="btn btn-link p-0 fs-15 fw-500 text-dark-gray"
              onClick={() => setOpen(false)}
            >
              Je remplis moi-même
            </button>
          </div>
          <p className="hint mt-15px mb-0">
            Jef est un assistant automatique&nbsp;: il pose quelques questions et prépare la
            demande, vous la relisez avant de publier.
          </p>
        </>
      )}

      {step === "questions" && session && (
        <>
          {session.safety.length > 0 && (
            <div className="alert alert-warning mb-20px" role="alert">
              <span className="d-block fw-600 mb-5px">D&apos;abord, votre sécurité&nbsp;:</span>
              <ul className="jf-jef-list mb-0">
                {session.safety.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="mb-20px" tabIndex={-1} data-focus>
            {session.trade ? (
              <>
                Métier retenu&nbsp;:{" "}
                <span className="fw-600 text-dark-gray">{session.trade.name}</span>.{" "}
              </>
            ) : (
              <>Jef n&apos;a pas reconnu le métier&nbsp;: choisissez-le dans le formulaire. </>
            )}
            Quelques précisions pour le pro&nbsp;:
          </p>
          {session.questions.map((q) => (
            <fieldset key={q.id} className="border-0 p-0 mb-20px">
              <legend id={`${uid}-${q.id}`} className="fs-16 fw-500 text-dark-gray mb-10px">
                {q.question}
              </legend>
              {q.choices.length > 0 ? (
                <div className="jf-checks">
                  {q.choices.map((choice) => (
                    <label key={choice}>
                      <input
                        type="radio"
                        name={`${uid}-${q.id}`}
                        value={choice}
                        checked={answers[q.id] === choice}
                        onChange={() => setAnswers({ ...answers, [q.id]: choice })}
                      />
                      <span>{choice}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <input
                  className="form-control"
                  aria-labelledby={`${uid}-${q.id}`}
                  maxLength={200}
                  value={answers[q.id] ?? ""}
                  onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                />
              )}
            </fieldset>
          ))}
          <div className="d-flex flex-wrap align-items-center gap-3">
            <button
              type="button"
              className="btn btn-medium btn-dark-gray btn-rounded btn-box-shadow"
              onClick={() => run(`/act/jef/${session.id}`, { answers }, "brief")}
              aria-disabled={pending}
            >
              {pending ? "Jef prépare la demande…" : "Préparer ma demande"}
            </button>
            <button
              type="button"
              className="btn btn-link p-0 fs-15 fw-500 text-dark-gray"
              onClick={restart}
            >
              Recommencer
            </button>
          </div>
          <p className="hint mt-15px mb-0">Vous pouvez laisser une question sans réponse.</p>
        </>
      )}

      {step === "brief" && session?.brief && (
        <>
          <p className="mb-15px" tabIndex={-1} data-focus>
            Voici la demande préparée par Jef. Relisez-la avant de l&apos;utiliser.
          </p>
          <div className="bg-white border-radius-15px p-25px mb-20px">
            {session.brief.urgent && (
              <span className="status-pill status-open mb-10px d-inline-block">Urgent</span>
            )}
            <span className="d-block alt-font fs-20 fw-500 text-dark-gray mb-10px">
              {session.brief.title}
            </span>
            <p className="mb-0 jf-pre-line">{session.brief.description}</p>
          </div>
          <List title={"En attendant le pro :"} items={session.brief.client_tips} />
          {(session.brief.pro_summary ||
            session.brief.pro_details.length > 0 ||
            session.brief.pro_bring.length > 0) && (
            <details className="mb-20px">
              <summary className="fw-500 text-dark-gray jf-summary">Ce que le pro verra</summary>
              <div className="mt-10px">
                {session.brief.pro_summary && (
                  <p className="mb-10px">{session.brief.pro_summary}</p>
                )}
                <JefFacts lines={session.brief.pro_details} />
                <List
                  title={"À prévoir (suggestion, à confirmer sur place) :"}
                  items={session.brief.pro_bring}
                />
              </div>
            </details>
          )}
          <div className="d-flex flex-wrap align-items-center gap-3">
            <button
              type="button"
              className="btn btn-medium btn-base-color btn-rounded btn-box-shadow"
              onClick={use}
            >
              Utiliser cette demande
            </button>
            <button
              type="button"
              className="btn btn-link p-0 fs-15 fw-500 text-dark-gray"
              onClick={restart}
            >
              Recommencer
            </button>
          </div>
          {session.mode === "ai" && (
            <p className="hint mt-15px mb-0">
              Jef est un assistant IA&nbsp;: il peut se tromper, vous pouvez tout modifier.
            </p>
          )}
        </>
      )}

      {step === "done" && (
        <p className="mb-0">
          <i className="bi bi-check-circle text-base-color me-5px" aria-hidden="true" />
          C&apos;est rempli. Choisissez votre quartier, relisez, puis publiez. Le pro recevra aussi
          la fiche de Jef.{" "}
          <button
            type="button"
            className="btn btn-link p-0 fw-500 align-baseline"
            onClick={restart}
          >
            Recommencer avec Jef
          </button>
        </p>
      )}
    </section>
  );
}
