import { useTranslation } from "react-i18next";
import { apiUrl, useApi, type Championship, type Entry, type Freshness, type Mode, type Standing } from "../api";
import { L, useLocale } from "../components/L";
import { TeamStrip } from "../components/monsters";
import { PlayerName, StandingsTable } from "../components/StandingsTable";
import { Async, Countdown, Empty, EntrySummary, ModeName, StatusBadge, editionTitle, When } from "../components/ui";
import { dateTime, num, relative } from "../format";
import { usePrefs } from "../prefs";

interface Panel {
  mode: Mode; current: Championship | null; leaders: Standing[];
  view: { view: string; cutoff_day?: string; first_day?: boolean } | null;
  previous: { championship: Championship; podium: Standing[] } | null;
}
interface OverviewData { panels: Panel[]; recent: Entry[]; freshness: Freshness[]; now: string }

function PanelCard({ p }: { p: Panel }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const c = p.current;
  return (
    <article className={`panel mode-${p.mode}`} aria-labelledby={`panel-${p.mode}`}>
      <header className="panel-head">
        <h2 id={`panel-${p.mode}`}><span className={`mode-dot mode-${p.mode}`} aria-hidden="true" /><ModeName mode={p.mode} /></h2>
        {c && <StatusBadge status={c.status} />}
      </header>
      {!c ? <Empty>{t("overview.noEdition")}</Empty> : (
        <>
          <p className="panel-edition">
            <L to={`/championships/${c.id}`} className="strong">{editionTitle(t, c)}</L>
            {c.mode === "limit" && c.rules.theme && <span className="muted"> · {c.rules.theme[locale] ?? c.rules.theme.en}</span>}
          </p>
          {c.status === "open" && <p className="panel-time"><Countdown to={c.ends_at} /> · <When iso={c.ends_at} offset={c.utc_offset_minutes} /></p>}
          <p className="muted">{t("overview.entrants", { count: c.entrants ?? 0 })}{p.view?.view === "published" && p.view.cutoff_day ? " · " + t("standings.publishedNote") : ""}</p>
          {p.view?.first_day ? <Empty>{t("standings.firstDay")}</Empty>
            : p.leaders.length ? <StandingsTable rows={p.leaders} mode={p.mode} caption={t("overview.leaders")} compact />
              : <Empty>{t("overview.noEntries")}</Empty>}
          <p className="panel-links">
            <L to={`/championships/${c.id}`}>{t("overview.fullStandings")} →</L>
            {p.previous && <> · <L to={`/championships/${p.previous.championship.id}`}>{t("overview.previous")}</L></>}
          </p>
        </>
      )}
      {p.previous && p.previous.podium.length > 0 && (
        <div className="previous">
          <h3>{t("overview.lastChampions", { edition: editionTitle(t, p.previous.championship) })}</h3>
          <ol className="podium">
            {p.previous.podium.map((s) => (
              <li key={s.position} className={`medal-${s.rank}`}>
                <span className="rank">{s.rank}</span> <PlayerName id={s.player.id} name={s.player.name} />
                <span className="muted"> {s.time ?? num(s.points?.total, locale)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </article>
  );
}

export default function Overview() {
  const { t } = useTranslation();
  const locale = useLocale();
  const [prefs] = usePrefs();
  const state = useApi<OverviewData>(apiUrl("/overview"), 60000);
  const followed = prefs.followed;
  return (
    <>
      <div className="page-head">
        <h1>{t("overview.title")}</h1>
        <p className="lede">{t("overview.lede")}</p>
      </div>
      <Async state={state} lines={8}>
        {(d) => (
          <>
            <div className="panels">{d.panels.map((p) => <PanelCard key={p.mode} p={p} />)}</div>
            {followed.length > 0 && (
              <section className="section">
                <h2>{t("follow.title")}</h2>
                <ul className="chips">
                  {followed.map((f) => (
                    <li key={f.kind + f.id}><L to={f.kind === "player" ? `/players/${f.id}` : `/championships/${f.id}`}>{f.name}</L></li>
                  ))}
                </ul>
              </section>
            )}
            <section className="section">
              <h2>{t("overview.recent")}</h2>
              {d.recent.length === 0 ? <Empty>{t("overview.noEntries")}</Empty> : (
                <ul className="feed">
                  {d.recent.map((e) => (
                    <li key={e.id}>
                      <span className={`mode-dot mode-${e.championship_mode}`} aria-hidden="true" />
                      <PlayerName id={e.player.id} name={e.player.name} />
                      <EntrySummary e={e} />
                      {e.kind === "gp" && <TeamStrip team={e.team} size={22} />}
                      <L to={`/results/${e.id}`} className="feed-time"><time dateTime={e.received_at} title={dateTime(e.received_at, locale)}>{relative(e.received_at, locale)}</time></L>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </Async>
    </>
  );
}
