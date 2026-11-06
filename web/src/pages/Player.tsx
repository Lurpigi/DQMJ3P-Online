import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { apiUrl, useApi, usePaged, type Championship, type Entry, type Mode, type Standing, type TeamMember } from "../api";
import { L, useLocale, useQuery } from "../components/L";
import { TeamColumn, TeamStrip } from "../components/monsters";
import { Async, CopyLink, Empty, EntrySummary, Facts, FollowButton, Loading, ModeName, ModeTag, PagedList, RankCell, Stat,
  StatusBadge, Tabs, editionTitle } from "../components/ui";
import { dateOnly, day, num, relative } from "../format";

const RankChart = lazy(() => import("../components/RankChart"));
type Tab = "overview" | "championships" | "results" | "teams";
interface Summary { finals: number; titles: number; podiums: number; best_rank: number | null; entries: number;
  editions_entered: number; rounds: number; rounds_won: number; best_time: string | null }
interface Current { championship: Championship; view: string; entrants: number; standing: Standing | null }
interface PlayerData {
  id: string; name: string; source: "sil" | "nex"; first_seen: string; last_seen: string;
  aliases: { name: string; provenance: string; first_seen: string; last_seen: string }[];
  summary: Record<Mode, Summary>; current: Current[];
}
interface Placement { championship: { id: string; mode: Mode; edition: number; starts_at: string; cup: Championship["cup"] };
  revision: number; entrants: number; standing: Standing }

function OverviewTab({ p }: { p: PlayerData }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const places = useApi<{ items: Placement[] }>(apiUrl(`/players/${p.id}/championships`));
  const modes = (p.source === "nex" ? ["gcup"] : ["grade", "limit"]) as Mode[];
  return (
    <>
      {p.current.length > 0 && (
        <section className="section">
          <h2>{t("player.current")}</h2>
          <ul className="current-list">
            {p.current.map((c) => (
              <li key={c.championship.id}>
                <ModeTag mode={c.championship.mode} /> <L to={`/championships/${c.championship.id}`}>{editionTitle(t, c.championship)}</L>
                <StatusBadge status={c.championship.status} />
                {c.standing ? <span>{t("player.place", { rank: c.standing.rank, count: c.entrants })} · {c.standing.time ?? num(c.standing.points?.total, locale)}</span>
                  : <span className="muted">{t("player.notRanked")}</span>}
                <span className="muted small">{t(`view.${c.view}`)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {modes.map((m) => {
        const s = p.summary[m];
        const points = (places.data?.items ?? []).filter((x) => x.championship.mode === m).reverse()
          .map((x) => ({ label: editionTitle(t, x.championship), rank: x.standing.rank, entrants: x.entrants }));
        return (
          <section key={m} className="section">
            <h2><ModeName mode={m} /></h2>
            <Facts>
              <Stat label={t("player.titles")} value={s.titles} />
              <Stat label={t("player.podiums")} value={s.podiums} />
              <Stat label={t("player.bestRank")} value={s.best_rank ?? "—"} />
              <Stat label={t("player.finals")} value={s.finals} />
              {m === "gcup" ? <Stat label={t("player.bestTime")} value={s.best_time ?? "—"} />
                : <Stat label={t("standings.rounds")} value={`${s.rounds_won}/${s.rounds}`} />}
            </Facts>
            {points.length > 1 && <Suspense fallback={<Loading />}><RankChart points={points} /></Suspense>}
          </section>
        );
      })}
      {p.aliases.length > 1 && (
        <section className="section">
          <h2>{t("player.aliases")}</h2>
          <ul className="plain">
            {p.aliases.map((a) => (
              <li key={a.name + a.provenance}>{a.name} <span className="muted small">{dateOnly(a.first_seen, locale)} – {dateOnly(a.last_seen, locale)}
                {a.provenance === "reconstructed" && ` · ${t("player.reconstructed")}`}</span></li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function ChampionshipsTab({ p }: { p: PlayerData }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const state = useApi<{ items: Placement[] }>(apiUrl(`/players/${p.id}/championships`));
  return (
    <Async state={state}>
      {(d) => d.items.length === 0 ? <Empty>{t("player.noFinals")}</Empty> : (
        <div className="table-wrap">
          <table className="list">
            <caption className="sr-only">{t("tab.championships")}</caption>
            <thead><tr><th scope="col">{t("archive.edition")}</th><th scope="col" className="hide-sm">{t("archive.dates")}</th>
              <th scope="col" className="num">{t("standings.rank")}</th><th scope="col" className="num">{t("archive.entrants")}</th>
              <th scope="col" className="num">{t("standings.score")}</th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.championship.id}>
                  <td><ModeTag mode={x.championship.mode} /> <L to={`/championships/${x.championship.id}`}>{editionTitle(t, x.championship)}</L></td>
                  <td className="hide-sm">{dateOnly(x.championship.starts_at, locale)}</td>
                  <td className="num"><RankCell rank={x.standing.rank} /></td>
                  <td className="num">{x.entrants}</td>
                  <td className="num">{x.standing.time ?? num(x.standing.points?.total, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Async>
  );
}

function ResultsTab({ p }: { p: PlayerData }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const list = usePaged<Entry>(apiUrl(`/players/${p.id}/results`, { limit: 25 }));
  return (
    <>
      <PagedList list={list} empty={t("results.none")}>
        {(items) => (
          <ul className="feed">
            {items.map((e) => (
              <li key={e.id}>
                {e.championship_mode && <ModeTag mode={e.championship_mode} />}
                <EntrySummary e={e} />
                {e.kind === "gp" && <TeamStrip team={e.team} size={22} />}
                <L to={`/results/${e.id}`} className="feed-time">{e.contest_day ? day(e.contest_day, locale) : relative(e.received_at, locale)}</L>
              </li>
            ))}
          </ul>
        )}
      </PagedList>
    </>
  );
}

function TeamsTab({ p }: { p: PlayerData }) {
  const { t } = useTranslation();
  const state = useApi<{ items: { championship: Placement["championship"]; entry: string; recorded_at: string; team: TeamMember[] }[] }>(
    apiUrl(`/players/${p.id}/teams`));
  if (p.source === "nex") return <Empty>{t("teams.gcup")}</Empty>;
  return (
    <Async state={state}>
      {(d) => d.items.length === 0 ? <Empty>{t("team.none")}</Empty> : (
        <ol className="evolution">
          {d.items.map((x, i) => {
            const older = d.items[i + 1]?.team.map((m) => m.species) ?? [];
            const changed = new Set(x.team.map((m) => m.species).filter((s) => older.length && !older.includes(s)));
            return (
              <li key={x.championship.id}>
                <h2 className="h3"><ModeTag mode={x.championship.mode} /> <L to={`/championships/${x.championship.id}`}>{editionTitle(t, x.championship)}</L>
                  {" · "}<L to={`/results/${x.entry}`} className="small">{t("teams.entry")}</L></h2>
                <TeamColumn team={x.team} changed={changed} />
              </li>
            );
          })}
        </ol>
      )}
    </Async>
  );
}

export default function PlayerPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const locale = useLocale();
  const { get, set } = useQuery();
  const state = useApi<PlayerData>(apiUrl(`/players/${encodeURIComponent(id)}`));
  const tab = (get("tab") as Tab) || "overview";
  const setTab = (k: Tab) => set("tab", k === "overview" ? "" : k);
  return (
    <Async state={state} lines={6}>
      {(p) => (
        <>
          <nav className="crumbs" aria-label={t("nav.breadcrumb")}><L to="/players">{t("nav.players")}</L></nav>
          <div className="page-head">
            <div>
              <h1>{p.name || t("player.unnamed")}</h1>
              <p className="subtitle"><span className={`source source-${p.source}`}>{t(`source.${p.source}`)}</span>{" "}
                {t("player.seen", { first: dateOnly(p.first_seen, locale), last: relative(p.last_seen, locale) })}</p>
            </div>
            <div className="head-actions"><FollowButton item={{ id: p.id, name: p.name || p.id, kind: "player" }} /><CopyLink /></div>
          </div>
          <Tabs<Tab> label={t("tab.label")} value={tab} onChange={setTab} tabs={[
            { key: "overview", label: t("tab.overview") }, { key: "championships", label: t("tab.championships") },
            { key: "results", label: t("tab.results") }, { key: "teams", label: t("tab.teams") }]} />
          <div className="tab-body">
            {tab === "overview" && <OverviewTab p={p} />}
            {tab === "championships" && <ChampionshipsTab p={p} />}
            {tab === "results" && <ResultsTab p={p} />}
            {tab === "teams" && <TeamsTab p={p} />}
          </div>
          <p className="muted small">{t(p.source === "sil" ? "player.identitySil" : "player.identityNex")}</p>
        </>
      )}
    </Async>
  );
}
