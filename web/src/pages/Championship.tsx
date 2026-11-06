import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { apiUrl, useApi, usePaged, type Championship, type Entry, type Standing, type StandingsResponse, type View } from "../api";
import { speciesName, useCatalog } from "../catalog";
import { L, useLocale, useQuery } from "../components/L";
import { MonsterPortrait, TeamStrip } from "../components/monsters";
import { RulesBlock } from "../components/Rules";
import { PlayerName, StandingsTable } from "../components/StandingsTable";
import { Async, CopyLink, Countdown, Coverage, EditionDates, Empty, EntrySummary, Facts, FollowButton, Meter, ModeName, ModeTag,
  PagedList, Segmented, Stat, StatusBadge, Tabs, editionTitle } from "../components/ui";
import { day, num, percent, relative } from "../format";

type Tab = "standings" | "results" | "teams" | "stats";

function StandingsPanel({ c }: { c: Championship }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const { get, set } = useQuery();
  const views = c.views ?? [];
  const view = (get("view") as View) || views[0];
  const q = get("q");
  const base = apiUrl(`/championships/${c.id}/standings`, { view, q, limit: 50 });
  const list = usePaged<Standing>(base, "rows");
  const meta = list.data as unknown as StandingsResponse | undefined;
  const exportUrl = (format: string) => apiUrl(`/championships/${c.id}/standings`, { view, q, format });
  return (
    <section aria-label={t("tab.standings")}>
      <div className="toolbar">
        {views.length > 1 && (
          <Segmented label={t("standings.view")} value={view} onChange={(v) => set("view", v)}
                     options={views.map((v) => ({ key: v, label: t(`view.${v}`) }))} />
        )}
        <label className="grow inline">{t("standings.search")}
          <input type="search" value={q} maxLength={40} onChange={(e) => set("q", e.target.value)} placeholder={t("standings.searchHint")} />
        </label>
        <span className="exports">{t("export.label")} <a href={exportUrl("csv")} download>CSV</a> · <a href={exportUrl("json")} download>JSON</a></span>
      </div>
      <p className="view-note muted">
        {view === "published" && meta?.cutoff_day && t("view.publishedNote", { day: day(meta.cutoff_day, locale) })}
        {view === "provisional" && t("view.provisionalNote")}
        {view === "final" && t("view.finalNote", { revision: meta?.revision ?? c.revision })}
        {view === "live" && t("view.liveNote")}
      </p>
      {meta?.first_day ? <Empty>{t("standings.firstDay")}</Empty> : (
        <PagedList list={list} lines={8}
                   empty={q ? t("standings.noMatch") : c.status === "upcoming" ? t("standings.upcoming") : t("standings.empty")}>
          {(rows) => <StandingsTable rows={rows} mode={c.mode} caption={t("standings.caption", { edition: editionTitle(t, c) })} />}
        </PagedList>
      )}
      {meta && <p className="muted small">{t("standings.total", { count: meta.total })}</p>}
    </section>
  );
}

function ResultsPanel({ c }: { c: Championship }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const list = usePaged<Entry>(apiUrl(`/championships/${c.id}/results`, { limit: 25 }));
  return (
    <section aria-label={t("tab.results")}>
      <PagedList list={list} empty={t("results.none")}>
        {(items) => (
          <ul className="feed">
            {items.map((e) => (
              <li key={e.id}>
                <PlayerName id={e.player.id} name={e.player.name} />
                <EntrySummary e={e} />
                {e.kind === "gp" && <TeamStrip team={e.team} size={22} />}
                <L to={`/results/${e.id}`} className="feed-time">{e.contest_day ? day(e.contest_day, locale) : relative(e.received_at, locale)}</L>
              </li>
            ))}
          </ul>
        )}
      </PagedList>
    </section>
  );
}

function TeamsPanel({ c }: { c: Championship }) {
  const { t } = useTranslation();
  const view = (c.views ?? [])[0];
  const list = usePaged<Standing>(c.mode === "gcup" ? null : apiUrl(`/championships/${c.id}/standings`, { view, limit: 50 }), "rows");
  if (c.mode === "gcup") return <Empty>{t("teams.gcup")}</Empty>;
  return (
    <section aria-label={t("tab.teams")}>
      <p className="muted">{t("teams.note")}</p>
      <PagedList list={list} empty={t("standings.empty")}>
        {(rows) => (
          <ul className="team-grid">
            {rows.map((r) => (
              <li key={r.position}>
                <span className="rank">{r.rank}</span>
                <PlayerName id={r.player.id} name={r.player.name} />
                <TeamStrip team={r.team} size={40} />
              </li>
            ))}
          </ul>
        )}
      </PagedList>
    </section>
  );
}

interface Stats {
  entrants: number; entries: number; rounds: number; rounds_won: number; signed: number; best_time: string | null;
  per_day: { day: string; entries: number; players: number }[];
  usage?: { unit: string; teams: number; species: { species: number; teams: number }[] };
}

function StatsPanel({ c }: { c: Championship }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const cat = useCatalog();
  const state = useApi<Stats>(apiUrl(`/championships/${c.id}/stats`));
  return (
    <Async state={state}>
      {(s) => {
        const max = Math.max(1, ...s.per_day.map((d) => d.entries));
        return (
          <section aria-label={t("tab.stats")}>
            <Facts>
              <Stat label={t("stats.entrants")} value={num(s.entrants, locale)} />
              <Stat label={c.mode === "gcup" ? t("stats.attempts") : t("stats.entries")} value={num(s.entries, locale)} />
              {c.mode !== "gcup" && <Stat label={t("stats.roundsWon")} value={`${num(s.rounds_won, locale)} / ${num(s.rounds, locale)}`} />}
              {c.mode === "gcup" && <Stat label={t("stats.bestAttempt")} value={s.best_time ?? "—"} />}
            </Facts>
            {s.per_day.length > 0 && (
              <>
                <h2 className="h3">{t("stats.perDay")}</h2>
                <table className="bars">
                  <caption className="sr-only">{t("stats.perDay")}</caption>
                  <thead className="sr-only"><tr><th>{t("stats.day")}</th><th>{t("stats.entries")}</th><th>{t("stats.entrants")}</th></tr></thead>
                  <tbody>
                    {s.per_day.map((d) => (
                      <tr key={d.day}>
                        <th scope="row">{day(d.day, locale)}</th>
                        <td><Meter value={d.entries} max={max}>{num(d.entries, locale)}</Meter></td>
                        <td className="muted">{t("stats.players", { count: d.players })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            {s.usage && (
              <>
                <h2 className="h3">{t("stats.usage")}</h2>
                <p className="muted">{t("stats.usageNote", { count: s.usage.teams })}</p>
                {s.usage.species.length === 0 ? <Empty>{t("stats.noTeams")}</Empty> : (
                  <ol className="usage">
                    {s.usage.species.map((u) => (
                      <li key={u.species}>
                        <MonsterPortrait species={u.species} size={32} />
                        <L to={`/monsters/${u.species}`}>{speciesName(cat, u.species, locale)}</L>
                        <Meter value={u.teams} max={s.usage!.teams}>
                          {percent(u.teams, s.usage!.teams, locale)} <span className="muted small">{t("stats.teamsOf", { n: u.teams, total: s.usage!.teams })}</span>
                        </Meter>
                      </li>
                    ))}
                  </ol>
                )}
              </>
            )}
          </section>
        );
      }}
    </Async>
  );
}

export default function ChampionshipPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const { get, reset, set } = useQuery();
  const state = useApi<Championship>(apiUrl(`/championships/${encodeURIComponent(id)}`), 60000);
  const tab = (get("tab") as Tab) || "standings";
  // A tab starts without the other tabs' filters
  const setTab = (k: Tab) => (k === "standings" ? reset() : set("tab", k, ["view", "q"]));
  return (
    <Async state={state} lines={6}>
      {(c) => (
        <>
          <nav className="crumbs" aria-label={t("nav.breadcrumb")}><L to="/championships">{t("nav.championships")}</L> › <ModeName mode={c.mode} /></nav>
          <div className="page-head">
            <div>
              <h1><ModeTag mode={c.mode} /> {editionTitle(t, c)} <StatusBadge status={c.status} /></h1>
              {c.mode === "gcup" && c.cup?.name && <p className="subtitle">{c.cup.name}</p>}
              <EditionDates c={c} />
              {c.status === "open" && <p><Countdown to={c.ends_at} /></p>}
              {c.status === "finalizing" && <p className="notice notice-warn">{t("status.finalizingNote")}</p>}
            </div>
            <div className="head-actions">
              <FollowButton item={{ id: c.id, name: `${t(`mode.${c.mode}.short`)} ${editionTitle(t, c)}`, kind: "championship" }} />
              <CopyLink />
            </div>
          </div>
          <div className="edition-layout">
            <div>
              <Tabs<Tab> label={t("tab.label")} value={tab} onChange={setTab} tabs={[
                { key: "standings", label: t("tab.standings") }, { key: "results", label: t("tab.results") },
                ...(c.mode !== "gcup" ? [{ key: "teams" as Tab, label: t("tab.teams") }] : []), { key: "stats", label: t("tab.stats") }]} />
              <div className="tab-body">
                {tab === "standings" && <StandingsPanel c={c} />}
                {tab === "results" && <ResultsPanel c={c} />}
                {tab === "teams" && <TeamsPanel c={c} />}
                {tab === "stats" && <StatsPanel c={c} />}
              </div>
            </div>
            <aside className="edition-side">
              <Facts>
                <Stat label={t("stats.entrants")} value={c.entrants ?? 0} />
                {c.revision && <Stat label={t("edition.revision")} value={c.revision} />}
              </Facts>
              <RulesBlock c={c} />
              <Coverage coverage={c.coverage} provenance={c.definition_provenance} />
              <nav className="edition-nav" aria-label={t("edition.neighbours")}>
                {c.previous && <L to={`/championships/${c.previous}`}>← {t("edition.previous")}</L>}
                {c.next && <L to={`/championships/${c.next}`}>{t("edition.next")} →</L>}
              </nav>
            </aside>
          </div>
        </>
      )}
    </Async>
  );
}
