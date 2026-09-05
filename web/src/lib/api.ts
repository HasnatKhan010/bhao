/** Bhao API client. Both _en and _ur labels arrive in every response, so the
 * language switch never needs a round trip. */

export const API_BASE =
  process.env.NEXT_PUBLIC_BHAO_API_URL ?? "http://localhost:8000";

export interface Meta {
  generated_at: string;
  panel_week: string | null;
  model_version: string | null;
  is_fixture: boolean;
  rows: number | null;
  forecast_run_id?: string | null;
}

export interface City {
  city_code: string;
  city_en: string;
  city_ur: string;
  province_en: string;
  province_ur: string;
  n_items: number;
}

export interface Item {
  item_code: string;
  item_en: string;
  item_ur: string;
  unit_raw: string;
  unit_norm: string;
  qty_norm: number;
  category: string;
  is_food: boolean;
  is_administered: boolean;
}

export interface Forecast {
  city_code: string;
  item_code: string;
  item_en: string;
  item_ur: string;
  city_en: string;
  city_ur: string;
  unit_raw: string;
  target_week: string | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  last_actual: number | null;
  last_actual_week: string | null;
  direction: "up" | "down" | "flat";
  pct_change_expected: number | null;
  model_version: string | null;
  made_on: string | null;
  history: { week_ending: string; price_avg: number | null }[];
  recent_error: { mase: number | null; mase_rw?: number | null; mae: number | null; n_weeks: number };
}

export interface Mover {
  item_code: string;
  item_en: string;
  item_ur: string;
  price_avg: number | null;
  pct_change: number | null;
  rank: number;
}

export interface ScorecardRow {
  target_week: string;
  model_name: string;
  scope: string;
  city_code: string | null;
  item_code: string | null;
  mase: number | null;
  mase_rw?: number | null;
  smape: number | null;
  mae: number | null;
  coverage_80: number | null;
  bias: number | null;
  n_obs: number;
  is_backtest: boolean;
}

export interface DriftRow {
  checked_on: string;
  channel: string;
  subject: string;
  test: string;
  statistic: number | null;
  threshold: number | null;
  fired: boolean;
  severity: string;
  note: string;
}

async function get<T>(path: string): Promise<{ data: T; meta: Meta }> {
  const res = await fetch(`${API_BASE}${path}`, {
    // the API sends max-age=3600 for CDNs; the app itself must always render
    // the latest pipeline output, so the browser bypasses its own HTTP cache
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  cities: () => get<City[]>("/api/cities"),
  items: (category?: string) =>
    get<Item[]>(`/api/items${category ? `?category=${category}` : ""}`),
  forecast: async (city: string, item: string): Promise<Forecast> => {
    // /api/forecast returns the forecast object itself (Contract 3), not {data, meta}
    const res = await fetch(
      `${API_BASE}/api/forecast?city_code=${city}&item_code=${item}&history_weeks=78`,
      { cache: "no-store" },
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body?.error?.message ?? `HTTP ${res.status}`);
    }
    return res.json();
  },
  movers: (limit = 10, direction = "both") =>
    get<Mover[]>(`/api/movers?limit=${limit}&direction=${direction}`),
  scorecard: (scope = "overall", limit = 300) =>
    get<ScorecardRow[]>(`/api/scorecard?scope=${scope}&limit=${limit}`),
  drift: () => get<DriftRow[]>("/api/drift?limit=200"),
  model: () => fetch(`${API_BASE}/api/model`, { next: { revalidate: 3600 } }).then((r) => r.json()),
};

export function fmt(n: number | null | undefined, dp = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-PK", {
    maximumFractionDigits: dp,
    minimumFractionDigits: 0,
  }).format(n);
}

export function fmtRs(n: number | null | undefined, dp = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `Rs ${fmt(n, dp)}`;
}
