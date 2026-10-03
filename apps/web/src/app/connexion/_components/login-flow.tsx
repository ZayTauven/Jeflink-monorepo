"use client";

// Parcours de connexion web (spec 001, web 2) : téléphone → code → [autres appareils] →
// [compte dormant] → [nom] → retour à `next`. Tous les appels passent par le client généré et
// le BFF (cookies httpOnly) ; aucun jeton n'est lisible ici. Le challenge est gardé en
// sessionStorage : rouvrir l'onglet ramène à l'écran code tant qu'il vit.
import {
  type AuthConfig,
  type OtherSession,
  type OtpVerifyResponse,
  authConfig,
  authOtpRequest,
  authOtpResend,
  authOtpVerify,
  meFreshStart,
  meSessionsRevokeOthers,
  meUpdate,
  resetApiClientSession,
} from "@jeflink/api-client";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  type StoredChallenge,
  clearChallenge,
  loadChallenge,
  saveChallenge,
} from "@/lib/login/challenge-store";
import { webDeviceLabel } from "@/lib/login/device-label";
import { type LoginError, describeLoginError } from "@/lib/login/errors";
import { phoneForApi } from "@/lib/login/phone";

import { DormantStep, NameStep, OthersStep, RegionStep, StaffStep } from "./after-steps";
import { CodeStep } from "./code-step";
import { PhoneStep } from "./phone-step";
import { LoginErrorAlert, SupportNumber } from "./support";

type Next = { kind: "others"; sessions: OtherSession[] } | { kind: "name" };
type Step =
  | { kind: "phone" }
  | { kind: "code"; challenge: StoredChallenge }
  | { kind: "others"; sessions: OtherSession[] }
  | { kind: "dormant" }
  | { kind: "name" }
  | { kind: "region" }
  | { kind: "staff" }
  | { kind: "done" };

const DEFAULT_DIAL_CODE = "+221";
const GENERIC: LoginError = {
  code: "generic",
  key: "generic",
  support: true,
  restart: false,
  region: false,
};

function sessionStore(): Storage | undefined {
  try {
    return window.sessionStorage;
  } catch {
    return undefined; // stockage bloqué : le challenge ne survivra pas au rechargement
  }
}

function newKey(): string {
  return crypto.randomUUID();
}

/** Étapes qui suivent une connexion réussie (autres appareils, puis nom d'un nouveau compte). */
function followUps(result: OtpVerifyResponse): Next[] {
  const steps: Next[] = [];
  if (result.other_sessions?.length)
    steps.push({ kind: "others", sessions: result.other_sessions });
  if (result.is_new_user && !result.user?.display_name) steps.push({ kind: "name" });
  return steps;
}

export function LoginFlow({
  initialConfig,
  next,
  retryHref,
  supportWhatsapp,
}: {
  initialConfig: AuthConfig | null;
  next: string;
  retryHref: string | null;
  supportWhatsapp: string | null;
}) {
  const t = useTranslations("connexion");
  const [config, setConfig] = useState(initialConfig);
  const [configFailed, setConfigFailed] = useState(false);
  const [step, setStep] = useState<Step>({ kind: "phone" });
  const [queue, setQueue] = useState<Next[]>([]);
  const [phone, setPhone] = useState("");
  const [dialCode, setDialCode] = useState(
    initialConfig?.regions[0]?.dial_code ?? DEFAULT_DIAL_CODE,
  );
  const [pending, setPending] = useState(false);
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const [error, setError] = useState<LoginError | null>(null);
  const [moved, setMoved] = useState(false); // focus du titre seulement après un changement
  // Une clé par saisie : un nouvel appui après une coupure ne renvoie pas de SMS (T1).
  const idempotencyKey = useRef<string>("");

  const go = useCallback((target: Step) => {
    setError(null);
    setResent(false);
    setMoved(true);
    setStep(target);
  }, []);

  // Configuration (indicatifs, longueur du code, version des conditions) si la page ne l'a pas.
  const loadConfig = useCallback(() => {
    setConfigFailed(false);
    authConfig()
      .then((response) => {
        setConfig(response.data);
        setDialCode(response.data.regions[0]?.dial_code ?? DEFAULT_DIAL_CODE);
      })
      .catch(() => setConfigFailed(true));
  }, []);
  useEffect(() => {
    if (!initialConfig) loadConfig();
  }, [initialConfig, loadConfig]);

  // Challenge reprenable : retour direct à l'écran code.
  useEffect(() => {
    const stored = loadChallenge(sessionStore(), Date.now());
    if (stored) setStep({ kind: "code", challenge: stored });
  }, []);

  const finish = useCallback(() => {
    setStep({ kind: "done" });
    // Navigation complète : les Server Components lisent les nouveaux cookies.
    window.location.replace(next);
  }, [next]);

  const advance = useCallback(
    (steps: Next[]) => {
      const [first, ...rest] = steps;
      setQueue(rest);
      if (first) go(first);
      else finish();
    },
    [finish, go],
  );

  const restart = useCallback(
    (reason: LoginError) => {
      clearChallenge(sessionStore());
      idempotencyKey.current = newKey();
      go({ kind: "phone" });
      setError(reason);
    },
    [go],
  );

  const requestCode = useCallback(async () => {
    if (!idempotencyKey.current) idempotencyKey.current = newKey();
    setPending(true);
    setError(null);
    try {
      const response = await authOtpRequest(
        { phone: phoneForApi(phone, dialCode) },
        { headers: { "Idempotency-Key": idempotencyKey.current } },
      );
      // jeflinkFetch lève sur tout statut d'erreur : seul le 202 arrive ici.
      const data = response.status === 202 ? response.data : null;
      if (!data?.challenge_secret) {
        setError(GENERIC);
        return;
      }
      const challenge: StoredChallenge = {
        challenge_id: data.challenge_id,
        challenge_secret: data.challenge_secret,
        phone_display: data.phone_display,
        code_length: data.code_length,
        expires_at: data.expires_at,
        resend_available_at: data.resend_available_at,
        deliveries_remaining: data.deliveries_remaining,
      };
      saveChallenge(sessionStore(), challenge);
      go({ kind: "code", challenge });
    } catch (caught) {
      const described = describeLoginError(caught);
      if (described.region) go({ kind: "region" });
      else setError(described);
    } finally {
      setPending(false);
    }
  }, [phone, dialCode, go]);

  const resendCode = useCallback(async () => {
    if (step.kind !== "code") return;
    const { challenge } = step;
    setResending(true);
    setError(null);
    setResent(false);
    try {
      const response = await authOtpResend({
        challenge_id: challenge.challenge_id,
        challenge_secret: challenge.challenge_secret,
      });
      if (response.status !== 202) throw response;
      const { data } = response;
      const updated: StoredChallenge = {
        ...challenge,
        expires_at: data.expires_at,
        resend_available_at: data.resend_available_at,
        deliveries_remaining: data.deliveries_remaining,
      };
      saveChallenge(sessionStore(), updated);
      setStep({ kind: "code", challenge: updated });
      setResent(true);
    } catch (caught) {
      const described = describeLoginError(caught);
      if (described.restart) restart(described);
      else setError(described);
    } finally {
      setResending(false);
    }
  }, [step, restart]);

  const verifyCode = useCallback(
    async (code: string) => {
      if (step.kind !== "code") return;
      if (!config) {
        setError(GENERIC);
        return;
      }
      const { challenge } = step;
      setPending(true);
      setError(null);
      try {
        const response = await authOtpVerify({
          challenge_id: challenge.challenge_id,
          challenge_secret: challenge.challenge_secret,
          code,
          terms_version: config.terms_version,
          device: { platform: "web", label: webDeviceLabel(navigator.userAgent) },
        });
        if (response.status !== 200) throw response;
        const { data } = response;
        clearChallenge(sessionStore());
        if (data.status !== "authenticated") {
          go({ kind: "staff" });
          return;
        }
        resetApiClientSession(); // aucune requête d'avant n'est rejouée sous ce compte
        if (data.restricted) go({ kind: "dormant" });
        else advance(followUps(data));
      } catch (caught) {
        const described = describeLoginError(caught);
        if (described.restart) restart(described);
        else setError(described); // la saisie reste dans le champ
      } finally {
        setPending(false);
      }
    },
    [step, config, go, advance, restart],
  );

  const answerOthers = useCallback(
    async (revoke: boolean) => {
      if (!revoke) {
        advance(queue);
        return;
      }
      setPending(true);
      setError(null);
      try {
        await meSessionsRevokeOthers();
        advance(queue);
      } catch (caught) {
        setError(describeLoginError(caught));
      } finally {
        setPending(false);
      }
    },
    [queue, advance],
  );

  const freshStart = useCallback(async () => {
    setPending(true);
    setError(null);
    try {
      const response = await meFreshStart();
      if (response.status !== 200) throw response;
      const { data } = response;
      resetApiClientSession();
      advance(followUps({ ...data, is_new_user: true }));
    } catch (caught) {
      const described = describeLoginError(caught);
      if (described.restart) restart(described);
      else setError(described);
    } finally {
      setPending(false);
    }
  }, [advance, restart]);

  const saveName = useCallback(
    async (name: string) => {
      setPending(true);
      setError(null);
      try {
        await meUpdate({ display_name: name });
        advance(queue);
      } catch (caught) {
        const described = describeLoginError(caught);
        // Erreur de format du serializer : c'est le nom qui est en cause, pas un numéro.
        setError(
          described.code === "phone_invalid"
            ? { ...described, code: "display_name_invalid", key: "display_name_invalid" }
            : described,
        );
      } finally {
        setPending(false);
      }
    },
    [queue, advance],
  );

  const changePhone = useCallback(() => {
    clearChallenge(sessionStore());
    idempotencyKey.current = newKey();
    go({ kind: "phone" });
  }, [go]);

  const onPhone = useCallback((value: string) => {
    setPhone(value);
    idempotencyKey.current = newKey(); // nouvelle saisie, nouvelle clé
  }, []);

  const onDialCode = useCallback((value: string) => {
    setDialCode(value);
    idempotencyKey.current = newKey();
  }, []);

  let content;
  switch (step.kind) {
    case "phone":
      content = (
        <PhoneStep
          regions={config?.regions ?? []}
          dialCode={dialCode}
          onDialCode={onDialCode}
          phone={phone}
          onPhone={onPhone}
          onSubmit={requestCode}
          pending={pending}
          error={error}
          retryHref={retryHref}
          focusHeading={moved}
        />
      );
      break;
    case "code":
      content = (
        <CodeStep
          key={step.challenge.challenge_id}
          challenge={step.challenge}
          onVerify={verifyCode}
          onResend={resendCode}
          onChangePhone={changePhone}
          verifying={pending}
          resending={resending}
          resent={resent}
          error={error}
        />
      );
      break;
    case "others":
      content = (
        <OthersStep
          sessions={step.sessions}
          onAnswer={answerOthers}
          pending={pending}
          error={error}
        />
      );
      break;
    case "dormant":
      content = <DormantStep onFreshStart={freshStart} pending={pending} error={error} />;
      break;
    case "name":
      content = (
        <NameStep onSave={saveName} onSkip={() => advance(queue)} pending={pending} error={error} />
      );
      break;
    case "region":
      content = <RegionStep onBack={changePhone} />;
      break;
    case "staff":
      content = <StaffStep onBack={changePhone} />;
      break;
    case "done":
      content = <Alert tone="success">{t("done")}</Alert>;
      break;
  }

  return (
    <SupportNumber.Provider value={supportWhatsapp}>
      <div className="flex flex-col gap-6">
        {configFailed && !config ? (
          <Alert
            tone="error"
            action={
              <Button variant="secondary" onClick={loadConfig} className="self-start">
                {t("phone.retry")}
              </Button>
            }
          >
            {t(navigator.onLine ? "errors.generic" : "errors.network")}
          </Alert>
        ) : null}
        {content}
      </div>
    </SupportNumber.Provider>
  );
}
