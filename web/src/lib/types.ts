// Mirrors trip_planner/trip/models.py and the event schema in trip_planner/agent/service.py.

export type Place = {
  place_id: string;
  name: string;
  address?: string;
  lat?: number | null;
  lng?: number | null;
  rating?: number | null;
  user_ratings?: number | null;
  price_level?: number | null;
  types?: string[];
  maps_url?: string;
  website?: string;
  photo_url?: string;
};

export type Flight = {
  id: string;
  airline: string;
  origin: string;
  destination: string;
  depart_at: string;
  arrive_at: string;
  return_date?: string | null;
  stops: number;
  duration_min: number;
  price_usd: number;
  booking_url?: string;
};

export type Hotel = {
  id: string;
  name: string;
  address?: string;
  lat?: number | null;
  lng?: number | null;
  check_in: string;
  check_out: string;
  price_per_night_usd: number;
  total_usd: number;
  rating?: number | null;
  stars?: number | null;
  booking_url?: string;
  photo_url?: string;
};

export type Stop = {
  id: string;
  place: Place;
  start: string;
  duration_min: number;
  note?: string;
  est_cost_usd?: number | null;
  travel_from_prev_min?: number | null;
  travel_mode?: "walk" | "transit" | "drive" | null;
};

export type Day = { date: string; area?: string; notes?: string; stops: Stop[] };

export type Trip = {
  id: string;
  title: string;
  origin: string;
  destinations: string[];
  start_date?: string | null;
  end_date?: string | null;
  travelers: number;
  budget_usd?: number | null;
  tier: "budget" | "mid" | "luxury";
  pace: "relaxed" | "moderate" | "packed";
  prefs: string[];
  constraints: string[];
  flight?: Flight | null;
  hotel?: Hotel | null;
  days: Day[];
  status: "planning" | "awaiting_approval" | "approved";
};

export type Issue = { code: string; severity: "error" | "warning"; message: string; date?: string | null; stop_id?: string | null };

export type Cost = { flight: number; hotel: number; activities: number; total: number; budget: number | null; remaining: number | null };

export type TripSummary = {
  id: string; title: string; status: Trip["status"]; updated_at: string;
  destination: string; start_date?: string | null; end_date?: string | null; days: number;
  photo: string; // first stop/hotel photo, "" when none
};

export type Approval = { summary: string; total_usd: number };

export type ThreadData = {
  trip: Trip;
  messages?: { role: "user" | "assistant"; text: string }[];
  pending_approval?: Approval | null;
  issues: Issue[];
  cost: Cost;
};

export type StreamEvent =
  | { type: "text"; delta: string }
  | { type: "tool_start"; name: string; label: string }
  | { type: "tool_end"; name: string; ok: boolean; summary: string; ms: number }
  | { type: "trip"; trip: Trip; issues: Issue[]; cost: Cost }
  | ({ type: "approval" } & Approval)
  | { type: "done" }
  | { type: "error"; message: string };
