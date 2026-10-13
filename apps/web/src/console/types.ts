import type { RequestStatus } from "@/lib/types";

/** Réponses de l'API console (`/api/console/…`). Montants en F CFA entiers. */

export type Badges = {
  pros_pending: number;
  stale_requests: number;
  /** Missions dont le client a demandé l'annulation : le support doit le rappeler. */
  cancel_requests: number;
  contact_unhandled: number;
  disputes_active: number;
};

export type Person = { id: number; name: string; photo: string };

export type PeriodStats = {
  requests: number;
  booking_rate: number | null;
  volume: number;
  first_quote_hours: number | null;
  rating: number | null;
  reviews: number;
};

export type Overview = {
  period_days: number;
  current: PeriodStats;
  previous: PeriodStats;
  counts: Badges & {
    pros: number;
    pros_verified: number;
    clients: number;
    open_requests: number;
  };
  status_breakdown: { status: RequestStatus; label: string; count: number }[];
  daily: { date: string; created: number; booked: number }[];
  by_trade: { slug: string; name: string; icon: string; requests: number; volume: number }[];
  by_zone: { slug: string; name: string; requests: number }[];
  top_pros: (Person & {
    trades: string[];
    missions: number;
    volume: number;
    rating: { average: number | null; count: number };
  })[];
  activity: {
    id: number;
    request_id: number;
    title: string;
    status: RequestStatus;
    status_label: string;
    note: string;
    actor: Person | null;
    created_at: string;
  }[];
  alerts: {
    pending_pros: (Person & { trades: string[]; joined_at: string })[];
    stale_requests: {
      id: number;
      title: string;
      trade: string;
      zone: string;
      created_at: string;
    }[];
    low_reviews: {
      request_id: number;
      rating: number;
      comment: string;
      pro: Person | null;
      client: Person;
      created_at: string;
    }[];
  };
};

// --- Lot 1 : listes et fiches -----------------------------------------------------------------

export type Page<T, F = Record<string, number>> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
  facets: F;
};

export type Ref = { id: number; name: string };
export type Contact = Ref & { email: string; phone: string; role: "client" | "pro" };

export type RequestRow = {
  id: number;
  title: string;
  status: RequestStatus;
  status_label: string;
  is_urgent: boolean;
  trade: { slug: string; name: string; icon: string };
  zone: { slug: string; name: string };
  client: Ref;
  pro: Ref | null;
  quotes_count: number;
  quotes_max: number;
  amount: number | null;
  open_disputes: number;
  created_at: string;
  updated_at: string;
};

export type DisputeStatus = "open" | "investigating" | "resolved" | "dismissed";

export type DisputeRow = {
  id: number;
  request: { id: number; title: string; status: RequestStatus };
  reason: string;
  reason_label: string;
  description: string;
  status: DisputeStatus;
  status_label: string;
  resolution: string;
  opened_by: Contact;
  handled_by: Ref | null;
  client: Contact;
  pro: Contact | null;
  created_at: string;
  closed_at: string | null;
};

export type ReviewRow = {
  id: number;
  request: { id: number; title: string; trade: string };
  rating: number;
  comment: string;
  is_hidden: boolean;
  hidden_reason: string;
  client: Ref;
  pro: Ref | null;
  created_at: string;
};

export type RequestDetail = Omit<RequestRow, "client" | "pro"> & {
  client: Contact;
  pro: Contact | null;
  description: string;
  landmark: string;
  preferred_date: string | null;
  quotes: {
    id: number;
    pro: Ref;
    amount: number;
    message: string;
    status: "pending" | "accepted" | "declined";
    status_label: string;
    created_at: string;
  }[];
  events: {
    id: number;
    status: RequestStatus;
    status_label: string;
    note: string;
    actor: Ref | null;
    created_at: string;
  }[];
  review: ReviewRow | null;
  disputes: DisputeRow[];
  staff_note: string;
  can_cancel: boolean;
  can_open_dispute: boolean;
  /** Motif donné par le client ; `awaiting_call` : annulation à confirmer par téléphone. */
  cancellation: {
    reason: string;
    reason_label: string;
    note: string;
    awaiting_call: boolean;
  } | null;
};

export type Account = {
  id: number;
  name: string;
  email: string;
  phone: string;
  photo: string;
  is_active: boolean;
  suspension_reason: string;
  date_joined: string;
  last_login: string | null;
};

export type ProRow = {
  account: Account;
  headline: string;
  photo: string;
  years_experience: number;
  trades: string[];
  zones: string[];
  is_verified: boolean;
  verified_at: string | null;
  verification_note: string;
  missions_done: number;
  rating: { average: number | null; count: number };
};

export type ProDetail = ProRow & {
  bio: string;
  stats: { quotes_sent: number; quotes_accepted: number; volume: number };
  missions: RequestRow[];
  reviews: ReviewRow[];
  disputes: DisputeRow[];
};

export type ClientRow = Account & {
  requests_count: number;
  spent: number;
  last_request_at: string | null;
};

export type ClientDetail = ClientRow & {
  requests: RequestRow[];
  reviews: ReviewRow[];
  disputes: DisputeRow[];
};

export type ContactRow = {
  id: number;
  name: string;
  email: string;
  message: string;
  is_handled: boolean;
  handled_at: string | null;
  handled_by: Ref | null;
  created_at: string;
};

export type AuditRow = {
  id: number;
  action: string;
  action_label: string;
  actor: Ref | null;
  target_type: "pro" | "client" | "request" | "review" | "contact" | "dispute";
  target_id: number;
  target_label: string;
  details: string;
  created_at: string;
};

// --- Lot 2 : catalogue, réglages, équipe ------------------------------------------------------

export type TradeAdmin = {
  id: number;
  slug: string;
  name: string;
  tagline: string;
  description: string;
  services: string[];
  starting_price: number | null;
  icon: string;
  image: string;
  position: number;
  is_active: boolean;
  pros_verified: number;
  requests_30d: number;
  requests_total: number;
};

export type ZoneAdmin = {
  id: number;
  slug: string;
  name: string;
  city: string;
  position: number;
  is_active: boolean;
  pros_count: number;
  requests_30d: number;
};

export type PlatformSettings = {
  max_quotes: number;
  stale_after_hours: number;
  accepting_requests: boolean;
  closed_message: string;
  support_whatsapp: string;
  support_email: string;
  jef_enabled: boolean;
  updated_at: string;
  updated_by: Ref | null;
};

/** Un échange avec Jef, relu par l'équipe (rubrique Jef). */
export type JefExchange = {
  id: number;
  client: Ref | null;
  trade: string;
  mode: "ai" | "guide";
  mode_label: string;
  text: string;
  questions: { id: string; question: string; choices: string[] }[];
  answers: Record<string, string>;
  brief: {
    title: string;
    description: string;
    urgent: boolean;
    client_tips: string[];
    pro_summary: string;
    pro_details: string[];
    pro_bring: string[];
  } | null;
  request: { id: number; title: string; status: string } | null;
  created_at: string;
};

export type JefOverview = {
  status: { enabled: boolean; ai: boolean; model: string; daily_limit: number };
  stats: { sessions: number; briefs: number; published: number; ai: number; requests: number };
};

export type StaffRole = "super" | "ops" | "marketing" | "finance";

export type Member = {
  id: number;
  name: string;
  email: string;
  role: StaffRole;
  role_label: string;
  is_active: boolean;
  is_superuser: boolean;
  last_login: string | null;
  date_joined: string;
};

// --- Lot 3 : marketing et finances --------------------------------------------------------------

export type CouponState = "active" | "scheduled" | "expired" | "exhausted" | "off";

export type CouponAdmin = {
  id: number;
  code: string;
  description: string;
  kind: "percent" | "fixed";
  kind_label: string;
  value: number;
  max_discount: number | null;
  min_amount: number | null;
  starts_on: string | null;
  ends_on: string | null;
  max_uses: number | null;
  max_uses_per_client: number;
  first_order_only: boolean;
  trades: { slug: string; name: string }[];
  zones: { slug: string; name: string }[];
  is_active: boolean;
  uses: number;
  discount_total: number;
  state: CouponState;
};

export type CampaignAdmin = {
  id: number;
  title: string;
  message: string;
  cta_label: string;
  cta_url: string;
  coupon_code: string;
  placement: "home" | "request" | "both";
  placement_label: string;
  starts_on: string | null;
  ends_on: string | null;
  is_active: boolean;
  is_live: boolean;
};

export type Commissions = {
  default_commission_percent: number;
  trades: {
    id: number;
    name: string;
    icon: string;
    is_active: boolean;
    commission_percent: number | null;
    effective: number;
  }[];
};

export type Totals = {
  count: number;
  volume: number;
  discount: number;
  commission: number;
  client_paid: number;
  net: number;
};

export type Transaction = {
  id: number;
  title: string;
  status: RequestStatus;
  status_label: string;
  trade: string;
  zone: string;
  client: Ref;
  pro: Ref | null;
  price: number;
  discount: number;
  coupon: string;
  commission_rate: number;
  commission: number;
  client_pays: number;
  net: number;
  updated_at: string;
};

export type BalanceRow = {
  pro: { id: number; name: string; phone: string; photo: string };
  missions_done: number;
  due: number;
  settled: number;
  balance: number;
};

export type Settlement = {
  id: number;
  direction: "to_jeflink" | "to_pro";
  direction_label: string;
  amount: number;
  method: string;
  method_label: string;
  reference: string;
  note: string;
  recorded_by: Ref | null;
  created_at: string;
};

export type BalanceDetail = BalanceRow & { missions: Transaction[]; settlements: Settlement[] };

export type MonthReport = Totals & {
  month: string;
  requests: number;
  booked: number;
  coupons_used: number;
};

export type Reports = {
  months: MonthReport[];
  month: string;
  by_trade: {
    trade: string;
    icon: string;
    count: number;
    volume: number;
    discount: number;
    commission: number;
    net: number;
  }[];
};
