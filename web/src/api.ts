// Client of the public API (server/dashboard). Responses keep their last good copy: a failed
// refresh shows the previous data with its time instead of an empty page.
import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/$/, "");
const TIMEOUT_MS = 12000;

export type Mode = "grade" | "limit" | "gcup";
export type Status = "upcoming" | "open" | "finalizing" | "final";
export type View = "final" | "live" | "published" | "provisional";
export interface PlayerRef { id: string; name: string }
export interface TeamMember { species: number; level: number | null; slot?: number; stats?: Record<string, number> }
export interface Points { total: number | null; win: number | null; popularity: number | null; strength: number | null; evaluation: number | null }
export interface LimitRule { type: number; value: number }
export interface Rules {
  kind: "open" | "limit" | "static" | "gcup";
  rules?: LimitRule[]; text?: Record<string, string>; theme?: Record<string, string>; allowed_species?: number[];
}
export interface Coins { platinum?: number; gold?: number; silver?: number; bronze?: number }
export interface Rewards {
  champion?: { item: number | null; coins: Coins | null }; top10?: { item: number | null; coins: Coins | null };
  prizes?: { from: number; to: number; coins: Coins }[];
}
export interface Cup {
  number: number; category: string; name?: string; cpu?: number[]; allowed_species?: number[]; strength?: number;
  course?: { map: number; variant: number }; event?: number;
}
export interface Championship {
  id: string; mode: Mode; edition: number; calendar_version: string; starts_at: string; ends_at: string;
  utc_offset_minutes: number; status: Status; revision: number | null; finalized_at: string | null;
  rules: Rules; rewards: Rewards; cup: Cup | null; definition_provenance: "observed" | "reconstructed";
  coverage: Record<string, string>; days?: { first: string; last: string }; entrants?: number; entries?: number;
  views?: View[]; revisions?: { revision: number; created_at: string; reason: string }[];
  previous?: string | null; next?: string | null; winner?: PlayerRef | null;
}
export interface Standing {
  position: number; rank: number; player: PlayerRef; location: number | null; points?: Points;
  rounds?: number; rounds_won?: number; entries?: number; frames?: number | null; time?: string | null;
  previous_rank?: number | null; team?: TeamMember[];
}
export interface StandingsResponse {
  championship: Championship; views: View[]; view: View; revision?: number; cutoff_day?: string; first_day?: boolean;
  as_of_entry?: string; total: number; rows: Standing[]; next_cursor: string | null;
}
export interface Entry {
  id: string; kind: "gp" | "gcup"; championship: string; championship_mode?: Mode; player: PlayerRef;
  name_provenance: string; received_at: string; validation: string; signature: string | null;
  contest_day?: string | null; location?: number | null; points?: Points; rounds?: number; rounds_won?: number;
  frames?: number | null; time?: string | null; improved?: boolean | null; team?: TeamMember[];
  round_results?: RoundResult[]; championship_detail?: Championship;
}
export interface RoundResult {
  idx: number; won: boolean | null; opponent?: { name: string; player: PlayerRef | null };
  points?: Omit<Points, "total">;
}
export interface Freshness { source: string; as_of: string | null; lag_seconds: number | null; failing: boolean }

export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}

export function apiUrl(path: string, params?: Record<string, string | number | boolean | null | undefined>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return `${API_BASE}${path}${s ? (path.includes("?") ? "&" : "?") + s : ""}`;
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(new DOMException("timeout", "TimeoutError")), TIMEOUT_MS);
  signal?.addEventListener("abort", () => ctrl.abort(signal.reason));
  try {
    const res = await fetch(url, { signal: ctrl.signal, headers: { Accept: "application/json" } });
    if (!res.ok) {
      let code = `http_${res.status}`;
      try { code = (await res.json()).error ?? code; } catch { /* not JSON */ }
      throw new ApiError(res.status, code);
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (ctrl.signal.aborted && !signal?.aborted) throw new ApiError(0, "timeout");
    if (signal?.aborted) throw e;
    throw new ApiError(0, "network");
  } finally {
    clearTimeout(timer);
  }
}

const cache = new Map<string, { data: unknown; at: number }>();

export interface ApiState<T> {
  data: T | undefined; error: ApiError | undefined; loading: boolean; fetchedAt: number | undefined; reload: () => void;
}

/** GET url (null = nothing to load); refreshes every `refreshMs` when set. */
export function useApi<T>(url: string | null, refreshMs?: number): ApiState<T> {
  const cached = url ? cache.get(url) : undefined;
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean; at?: number }>(
    { data: cached?.data as T | undefined, loading: !!url && !cached, at: cached?.at });
  const [tick, setTick] = useState(0);
  const current = useRef(url);
  current.current = url;

  useEffect(() => {
    if (!url) { setState({ loading: false }); return; }
    const hit = cache.get(url);
    setState({ data: hit?.data as T | undefined, loading: !hit, at: hit?.at });
    const ctrl = new AbortController();
    getJson<T>(url, ctrl.signal).then(
      (data) => {
        cache.set(url, { data, at: Date.now() });
        if (current.current === url) setState({ data, loading: false, at: Date.now() });
      },
      (error) => {
        if (ctrl.signal.aborted) return;
        if (current.current === url) setState((s) => ({ ...s, error: error instanceof ApiError ? error : new ApiError(0, "network"), loading: false }));
      });
    return () => ctrl.abort();
  }, [url, tick]);

  useEffect(() => {
    if (!refreshMs || !url) return;
    const id = setInterval(() => { if (document.visibilityState === "visible") setTick((t) => t + 1); }, refreshMs);
    return () => clearInterval(id);
  }, [url, refreshMs]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data: state.data, error: state.error, loading: state.loading, fetchedAt: state.at, reload };
}

/** Cursor pagination: pages are appended; a new base url starts over. */
export function usePaged<T>(base: string | null, key: "items" | "rows" = "items") {
  const [cursor, setCursor] = useState<string | null>(null);
  const [items, setItems] = useState<T[]>([]);
  useEffect(() => { setCursor(null); setItems([]); }, [base]);
  const url = base ? (cursor ? `${base}${base.includes("?") ? "&" : "?"}cursor=${encodeURIComponent(cursor)}` : base) : null;
  const page = useApi<{ next_cursor: string | null } & Record<string, unknown>>(url);
  useEffect(() => {
    if (!page.data) return;
    const got = (page.data[key] as T[] | undefined) ?? [];
    setItems((prev) => (cursor ? [...prev, ...got] : got));
  }, [page.data, cursor, key]);
  const next = page.data?.next_cursor ?? null;
  return { ...page, items, more: next ? () => setCursor(next) : null };
}
