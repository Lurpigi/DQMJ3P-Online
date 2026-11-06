import { useEffect, useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ApiError, Championship, Entry, Mode, Status } from "../api";
import { Icon } from "./Icon";
import { dateTime, duration, lastMoment, num, offsetLabel, relative } from "../format";
import { useFollow, type Followed } from "../prefs";
import { useLocale } from "./L";

export function ModeName({ mode, short }: { mode: Mode; short?: boolean }) {
  const { t } = useTranslation();
  return <>{t(short ? `mode.${mode}.short` : `mode.${mode}.name`)}</>;
}

export function ModeTag({ mode }: { mode: Mode }) {
  return <span className={`mode-tag mode-${mode}`}><ModeName mode={mode} short /></span>;
}

export function StatusBadge({ status }: { status: Status }) {
  const { t } = useTranslation();
  return <span className={`status status-${status}`}>{t(`status.${status}`)}</span>;
}

export function editionTitle(t: (k: string, o?: Record<string, unknown>) => string, c: Pick<Championship, "mode" | "edition" | "cup">) {
  if (c.mode === "gcup") return t("edition.gcup", { cup: c.cup?.number ?? (c.edition % 12) + 1, week: c.edition });
  return t("edition.gp", { n: c.edition });
}

/** What an uploaded result says, in one line of a feed. */
export function EntrySummary({ e }: { e: Entry }) {
  const { t } = useTranslation();
  const locale = useLocale();
  return (
    <span className="feed-what">
      {e.kind === "gp" ? t("feed.gp", { points: num(e.points?.total, locale), won: e.rounds_won ?? 0 })
        : t(e.improved ? "feed.gcupBest" : "feed.gcup", { time: e.time })}
      {e.validation !== "unverified" && <span className="tag tag-warn">{t(`validation.${e.validation}`)}</span>}
    </span>
  );
}

/** Rank with movement since the previous published day, as text and arrow (not only color). */
export function RankCell({ rank, previous }: { rank: number; previous?: number | null }) {
  const { t } = useTranslation();
  let move: ReactNode = null;
  if (previous !== undefined) {
    if (previous === null) move = <span className="move move-new" title={t("standings.new")}>{t("standings.newShort")}</span>;
    else if (previous > rank) move = <span className="move move-up" aria-label={t("standings.up", { n: previous - rank })}>▲{previous - rank}</span>;
    else if (previous < rank) move = <span className="move move-down" aria-label={t("standings.down", { n: rank - previous })}>▼{rank - previous}</span>;
    else move = <span className="move move-same" aria-label={t("standings.same")}>＝</span>;
  }
  const medal = rank <= 3 ? ` medal medal-${rank}` : "";
  return <span className="rank-cell"><span className={`rank${medal}`}>{rank}</span>{move}</span>;
}

/** Official time (competition zone) with the viewer's local time under it. */
export function When({ iso, offset, label }: { iso: string; offset: number; label?: string }) {
  const locale = useLocale();
  const { t } = useTranslation();
  const local = dateTime(iso, locale);
  const official = dateTime(iso, locale, offset);
  return (
    <span className="when">
      {label && <span className="when-label">{label} </span>}
      <time dateTime={iso}>{official}</time> <span className="zone">{offsetLabel(offset)}</span>
      {local !== official && <span className="local"> · {t("time.yours", { time: local })}</span>}
    </span>
  );
}

export function EditionDates({ c }: { c: Championship }) {
  const { t } = useTranslation();
  return (
    <div className="edition-dates">
      <When iso={c.starts_at} offset={c.utc_offset_minutes} label={t("edition.starts")} />
      <When iso={lastMoment(c.ends_at)} offset={c.utc_offset_minutes} label={t("edition.ends")} />
    </div>
  );
}

export function Countdown({ to }: { to: string }) {
  const { t } = useTranslation();
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(id); }, []);
  const left = (new Date(to).getTime() - now) / 1000;
  if (left <= 0) return <span className="countdown">{t("time.closed")}</span>;
  const d = duration(left);
  return <span className="countdown">{t("time.left", { d: d.days, h: d.hours, m: d.minutes })}</span>;
}

export function Loading({ lines = 3 }: { lines?: number }) {
  const { t } = useTranslation();
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="sr-only">{t("state.loading")}</span>
      {Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton" style={{ width: `${90 - i * 12}%` }} />)}
    </div>
  );
}

export function ErrorBox({ error, onRetry, stale }: { error: ApiError; onRetry?: () => void; stale?: number }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const key = error.status === 404 ? "state.notFound" : error.code === "timeout" ? "state.timeout"
    : error.status === 0 ? "state.offline" : error.status === 429 ? "state.rateLimited" : "state.error";
  return (
    <div className={`notice ${stale ? "notice-warn" : "notice-error"}`} role="alert">
      <p>{t(key)}{stale ? " " + t("state.stale", { when: relative(new Date(stale).toISOString(), locale) }) : ""}</p>
      {onRetry && error.status !== 404 && <button type="button" className="btn" onClick={onRetry}>{t("state.retry")}</button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/** Loading / error / content of one API call, keeping stale data on screen. */
export function Async<T>({ state, children, lines }: {
  state: { data: T | undefined; error: ApiError | undefined; loading: boolean; fetchedAt?: number; reload: () => void };
  children: (data: T) => ReactNode; lines?: number;
}) {
  if (state.data !== undefined) {
    return <>{state.error && <ErrorBox error={state.error} onRetry={state.reload} stale={state.fetchedAt} />}{children(state.data)}</>;
  }
  if (state.error) return <ErrorBox error={state.error} onRetry={state.reload} />;
  return <Loading lines={lines} />;
}

/** A cursor-paged list: error, first-page skeleton, empty state, items, "load more". */
export function PagedList<T>({ list, empty, lines, children }: {
  list: { items: T[]; error: ApiError | undefined; loading: boolean; fetchedAt?: number; reload: () => void; more: (() => void) | null };
  empty: ReactNode; lines?: number; children: (items: T[]) => ReactNode;
}) {
  return (
    <>
      {list.error && <ErrorBox error={list.error} onRetry={list.reload} stale={list.items.length ? list.fetchedAt : undefined} />}
      {list.loading && !list.items.length ? <Loading lines={lines} />
        : list.items.length ? children(list.items) : !list.error && <Empty>{empty}</Empty>}
      <LoadMore more={list.more} loading={list.loading} />
    </>
  );
}

/** One choice among a few, applied at once (views, competitions). */
export function Segmented<K extends string>({ options, value, onChange, label }: {
  options: { key: K; label: ReactNode }[]; value: K; onChange: (k: K) => void; label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" role="radio" aria-checked={o.key === value} onClick={() => onChange(o.key)}>{o.label}</button>
      ))}
    </div>
  );
}

/** Horizontal bar with its value; the bar is decoration, the number is the data. */
export function Meter({ value, max, children }: { value: number; max: number; children?: ReactNode }) {
  return (
    <span className="meter">
      <span className="meter-track" aria-hidden="true"><span className="meter-fill" style={{ width: `${Math.min(100, (value / Math.max(1, max)) * 100)}%` }} /></span>
      <span className="meter-value">{children ?? value}</span>
    </span>
  );
}

export function Tabs<K extends string>({ tabs, value, onChange, label }: {
  tabs: { key: K; label: ReactNode }[]; value: K; onChange: (k: K) => void; label: string;
}) {
  const id = useId();
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const n = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!n) return;
    e.preventDefault();
    const next = tabs[(i + n + tabs.length) % tabs.length];
    onChange(next.key);
    document.getElementById(`${id}-${next.key}`)?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, i) => (
        <button key={tab.key} id={`${id}-${tab.key}`} type="button" role="tab" aria-selected={tab.key === value}
                tabIndex={tab.key === value ? 0 : -1} className="tab" onClick={() => onChange(tab.key)} onKeyDown={(e) => onKey(e, i)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function LoadMore({ more, loading }: { more: (() => void) | null; loading: boolean }) {
  const { t } = useTranslation();
  if (!more) return null;
  return <div className="load-more"><button type="button" className="btn" onClick={more} disabled={loading}>{t(loading ? "state.loading" : "state.more")}</button></div>;
}

export function FollowButton({ item }: { item: Followed }) {
  const { t } = useTranslation();
  const [on, toggle] = useFollow(item);
  return (
    <button type="button" className="btn btn-ghost follow" aria-pressed={on} onClick={toggle}>
      <Icon name={on ? "star-filled" : "star"} />{t(on ? "follow.on" : "follow.off")}
    </button>
  );
}

export function CopyLink() {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(location.href); setDone(true); setTimeout(() => setDone(false), 2000); } catch { /* not allowed */ }
  };
  return (
    <button type="button" className="btn btn-ghost" onClick={copy}>
      <Icon name={done ? "check" : "link"} /><span aria-live="polite">{t(done ? "share.copied" : "share.copy")}</span>
    </button>
  );
}

export function Coverage({ coverage, provenance }: { coverage?: Record<string, string>; provenance?: string }) {
  const { t } = useTranslation();
  const notes = Object.entries(coverage ?? {}).filter(([, v]) => v !== "complete");
  if (!notes.length && provenance !== "reconstructed") return null;
  return (
    <ul className="coverage">
      {provenance === "reconstructed" && <li>{t("coverage.definition")}</li>}
      {notes.map(([k, v]) => <li key={k}>{t(`coverage.${k}.${v}`, { defaultValue: t("coverage.generic", { feature: k, level: v }) })}</li>)}
    </ul>
  );
}

/** A row of key figures. Children are <Stat>s. */
export function Facts({ children }: { children: ReactNode }) {
  return <dl className="facts">{children}</dl>;
}

export function Stat({ label, value, hint }: { label: ReactNode; value: ReactNode; hint?: ReactNode }) {
  return <div className="stat"><dt>{label}</dt><dd>{value}{hint && <span className="stat-hint">{hint}</span>}</dd></div>;
}
