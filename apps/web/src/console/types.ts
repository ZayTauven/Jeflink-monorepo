import type { RequestStatus } from "@/lib/types";

/** Réponses de l'API console (`/api/console/…`). Montants en F CFA entiers. */

export type Badges = {
  pros_pending: number;
  stale_requests: number;
  contact_unhandled: number;
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
