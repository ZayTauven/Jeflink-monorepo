export type Trade = {
  slug: string;
  name: string;
  tagline: string;
  description: string;
  services: string[];
  starting_price: number | null;
  icon: string;
  image: string;
  pros_count: number;
};

export type Zone = { slug: string; name: string; city: string; city_slug: string };

export type Rating = { average: number | null; count: number };

export type Pro = {
  id: number;
  name: string;
  headline: string;
  bio: string;
  photo: string;
  years_experience: number;
  trades: { slug: string; name: string; icon: string }[];
  zones: Zone[];
  rating: Rating;
  missions_done: number;
};

export type Stats = {
  pros: number;
  trades: number;
  zones: number;
  missions_done: number;
  average_rating: number | null;
};

export type Me = {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  photo: string;
  role: "client" | "pro";
  is_staff: boolean;
  console_role: "" | "super" | "ops" | "marketing" | "finance";
  console_sections: ConsoleSection[];
  pro_profile: {
    headline: string;
    bio: string;
    trades: string[];
    zones: string[];
    years_experience: number;
    is_verified: boolean;
    verification_note: string;
    photo: string;
  } | null;
};

export type RequestStatus = "open" | "booked" | "cancelling" | "done" | "cancelled";
export type ConsoleSection =
  "dashboard" | "operations" | "catalog" | "marketing" | "finance" | "admin";

export type SiteSettings = {
  accepting_requests: boolean;
  closed_message: string;
  support_whatsapp: string;
  support_email: string;
  max_quotes: number;
  jef_enabled: boolean;
};

/** Bandeau de campagne (console › Campagnes). */
export type Campaign = {
  id: number;
  title: string;
  message: string;
  cta_label: string;
  cta_url: string;
  coupon_code: string;
  /** Conditions du code promo (et date de fin), affichées avec le bandeau. */
  terms: {
    min_amount: number | null;
    max_discount: number | null;
    first_order_only: boolean;
    ends_on: string | null;
  };
};

/** Montants d'une mission réservée (F CFA entiers, paiement sur place). */
export type Money = {
  price: number;
  discount: number;
  coupon: string;
  client_pays: number;
  commission?: number;
  commission_rate?: number;
};

export type RequestAction = "accept" | "cancel" | "complete" | "review" | "quote" | "report";

export type DisputeStatus = "open" | "investigating" | "resolved" | "dismissed";

/** Litige vu par le client et le pro de la mission. */
export type Dispute = {
  id: number;
  reason: string;
  reason_label: string;
  description: string;
  status: DisputeStatus;
  status_label: string;
  resolution: string;
  created_at: string;
  closed_at: string | null;
};

export type Quote = {
  id: number;
  pro: { id: number; name: string };
  pro_headline: string;
  pro_rating: Rating;
  amount: number;
  message: string;
  status: "pending" | "accepted" | "declined";
  status_label: string;
  /** Pour le client : ce que donne le code promo de sa demande sur ce devis. */
  with_code:
    | { code: string; discount: number; client_pays: number }
    | { code: string; error: string }
    | null;
  created_at: string;
};

export type ServiceRequest = {
  id: number;
  title: string;
  description: string;
  landmark: string;
  preferred_date: string | null;
  is_urgent: boolean;
  status: RequestStatus;
  status_label: string;
  trade: { slug: string; name: string; icon: string };
  zone: { slug: string; name: string };
  client: { id: number; name: string };
  pro: { id: number; name: string } | null;
  contact_phone: string | null;
  quotes: Quote[];
  quotes_count: number;
  quotes_max: number;
  review: { rating: number; comment: string; created_at: string } | null;
  events: { status: RequestStatus; status_label: string; note: string; created_at: string }[];
  dispute: Dispute | null;
  money: Money | null;
  /** Fiche Jef selon le lecteur : conseils pour le client, fiche pour les pros. */
  jef:
    | ({ mode: JefMode; urgent: boolean } & Partial<
        Pick<JefBrief, "client_tips" | "pro_summary" | "pro_details" | "pro_bring">
      >)
    | null;
  /** Motif d'annulation donné par le client (visible du client seulement). */
  cancellation: { reason: string; reason_label: string; note: string } | null;
  /** Code promo ajouté à la demande (visible du client seulement). */
  promo_code: string;
  actions: RequestAction[];
  created_at: string;
};

export type PublicReview = {
  rating: number;
  comment: string;
  author: string;
  author_photo: string;
  pro: string;
  trade: string;
  created_at: string;
};

/** Jef, l'assistant de réservation : mode IA (Claude) ou questions guidées (sans clé). */
export type JefMode = "ai" | "guide";

export type JefQuestion = { id: string; question: string; choices: string[] };

/** Fiche préparée par Jef : la demande à publier et ce que le pro doit savoir. */
export type JefBrief = {
  title: string;
  description: string;
  urgent: boolean;
  client_tips: string[];
  pro_summary: string;
  pro_details: string[];
  pro_bring: string[];
};

export type JefSession = {
  id: number;
  mode: JefMode;
  trade: { slug: string; name: string } | null;
  questions: JefQuestion[];
  /** Gestes de sécurité à montrer tout de suite (vide sans danger). */
  safety: string[];
  answers: Record<string, string>;
  brief: JefBrief | null;
};
