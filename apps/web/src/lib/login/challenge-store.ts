// Challenge OTP reprenable sur le web (spec 001, « Code » : le web garde le challenge en
// `sessionStorage`). Rouvrir l'onglet ramène à l'écran code tant que le challenge vit. Le
// stockage de session meurt avec l'onglet ; il n'est jamais partagé avec un autre onglet.

export const CHALLENGE_KEY = "jf-otp-challenge";

export type StoredChallenge = {
  challenge_id: string;
  challenge_secret: string;
  phone_display: string;
  code_length: number;
  expires_at: string;
  resend_available_at: string;
  deliveries_remaining: number;
};

type Storage = Pick<globalThis.Storage, "getItem" | "setItem" | "removeItem">;

function isChallenge(value: unknown): value is StoredChallenge {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.challenge_id === "string" &&
    typeof v.challenge_secret === "string" &&
    v.challenge_secret.length > 0 &&
    typeof v.phone_display === "string" &&
    typeof v.code_length === "number" &&
    typeof v.expires_at === "string" &&
    typeof v.resend_available_at === "string" &&
    typeof v.deliveries_remaining === "number"
  );
}

export function saveChallenge(storage: Storage | undefined, challenge: StoredChallenge): void {
  try {
    storage?.setItem(CHALLENGE_KEY, JSON.stringify(challenge));
  } catch {
    // stockage bloqué : le challenge ne survivra pas à un rechargement, rien de plus
  }
}

/** Challenge encore vivant, ou null (absent, illisible ou expiré : alors effacé). */
export function loadChallenge(storage: Storage | undefined, now: number): StoredChallenge | null {
  try {
    const raw = storage?.getItem(CHALLENGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (isChallenge(parsed) && Date.parse(parsed.expires_at) > now) return parsed;
  } catch {
    // illisible : effacé ci-dessous
  }
  clearChallenge(storage);
  return null;
}

export function clearChallenge(storage: Storage | undefined): void {
  try {
    storage?.removeItem(CHALLENGE_KEY);
  } catch {
    // stockage bloqué : rien à effacer
  }
}
