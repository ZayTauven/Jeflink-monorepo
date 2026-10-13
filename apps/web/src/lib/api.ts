import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type {
  Me,
  Pro,
  PublicReview,
  ServiceRequest,
  SiteSettings,
  Campaign,
  Stats,
  Trade,
  Zone,
} from "./types";

export const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";
export const TOKEN_COOKIE = "jeflink_token";

export type ApiError = { ok: false; status: number; error: string; fields: Record<string, string> };
export type ApiResult<T> = { ok: true; status: number; data: T } | ApiError;

/** Appel serveur → Django. Le jeton ne quitte jamais le serveur Next (cookie httpOnly). */
export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown; token?: string | null } = {},
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (init.token) headers.Authorization = `Token ${init.token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
    });
  } catch {
    return {
      ok: false,
      status: 503,
      error: "L'API Jeflink ne répond pas. Est-elle lancée (make api) ?",
      fields: {},
    };
  }
  if (res.status === 204) return { ok: true, status: 204, data: undefined as T };
  const data: unknown = await res.json().catch(() => null);
  if (res.ok) return { ok: true, status: res.status, data: data as T };
  return { ok: false, status: res.status, ...readErrors(data) };
}

/** Erreurs DRF ({detail}, {champ: [..]}, [..]) → un message général + un message par champ. */
function readErrors(data: unknown): { error: string; fields: Record<string, string> } {
  const first = (v: unknown): string =>
    Array.isArray(v) ? first(v[0]) : typeof v === "string" ? v : "";
  if (Array.isArray(data)) return { error: first(data), fields: {} };
  if (!data || typeof data !== "object") return { error: "Une erreur est survenue.", fields: {} };
  const fields: Record<string, string> = {};
  let error = "";
  for (const [key, value] of Object.entries(data)) {
    const message = first(value);
    if (key === "detail" || key === "non_field_errors") error = message;
    else fields[key] = message;
  }
  return { error: error || (Object.keys(fields).length ? "Vérifiez le formulaire." : ""), fields };
}

// --- Session ---------------------------------------------------------------------------------

export async function getToken(): Promise<string | null> {
  return (await cookies()).get(TOKEN_COOKIE)?.value ?? null;
}

export async function getMe(): Promise<Me | null> {
  const token = await getToken();
  if (!token) return null;
  const res = await api<Me>("/api/auth/me/", { token });
  return res.ok ? res.data : null;
}

/** Page réservée aux comptes connectés : sinon, connexion puis retour ici. */
export async function requireMe(here: string): Promise<{ me: Me; token: string }> {
  const token = await getToken();
  const me = token ? await getMe() : null;
  if (!me || !token) redirect(`/connexion?suite=${encodeURIComponent(here)}`);
  return { me, token };
}

/** Console : réservée à l'équipe Jeflink (comptes `is_staff`). Les autres retournent à leur espace. */
export async function requireStaff(here: string): Promise<{ me: Me; token: string }> {
  const session = await requireMe(here);
  if (!session.me.is_staff) redirect("/espace");
  return session;
}

// --- Lecture publique (vitrine) : une API arrêtée donne une page vide, pas une erreur ---------

async function publicList<T>(path: string): Promise<T[]> {
  const res = await api<T[]>(path);
  return res.ok ? res.data : [];
}

export const getTrades = () => publicList<Trade>("/api/trades/");
export const getZones = () => publicList<Zone>("/api/zones/");
export const getPros = (query = "") => publicList<Pro>(`/api/pros/${query}`);
export const getReviews = () => publicList<PublicReview>("/api/reviews/");

export async function getTrade(slug: string): Promise<Trade | null> {
  const res = await api<Trade>(`/api/trades/${encodeURIComponent(slug)}/`);
  return res.ok ? res.data : null;
}

/** Réglages publics (console › Réglages) ; API arrêtée → valeurs par défaut, le site reste lisible. */
export async function getSite(): Promise<SiteSettings> {
  const res = await api<SiteSettings>("/api/site/");
  if (res.ok) return res.data;
  return {
    accepting_requests: true,
    closed_message: "",
    support_whatsapp: "",
    support_email: "",
    max_quotes: 3,
    jef_enabled: false,
  };
}

/** Campagnes en cours pour un emplacement ; API arrêtée → aucune. */
export async function getCampaigns(placement: "home" | "request"): Promise<Campaign[]> {
  const res = await api<Campaign[]>(`/api/campaigns/?placement=${placement}`);
  return res.ok ? res.data : [];
}

export async function getStats(): Promise<Stats | null> {
  const res = await api<Stats>("/api/stats/");
  return res.ok ? res.data : null;
}

export async function getRequest(id: string, token: string): Promise<ServiceRequest | null> {
  if (!/^\d+$/.test(id)) return null;
  const res = await api<ServiceRequest>(`/api/requests/${id}/`, { token });
  return res.ok ? res.data : null;
}
