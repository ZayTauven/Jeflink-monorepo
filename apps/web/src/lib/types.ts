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

export type Zone = { slug: string; name: string; city: string };

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

export type RequestStatus = "open" | "booked" | "done" | "cancelled";
export type ConsoleSection =
  "dashboard" | "operations" | "catalog" | "marketing" | "finance" | "admin";

export type SiteSettings = {
  accepting_requests: boolean;
  closed_message: string;
  support_whatsapp: string;
  support_email: string;
  max_quotes: number;
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
