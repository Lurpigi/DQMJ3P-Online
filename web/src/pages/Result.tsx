import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { apiUrl, useApi, type Entry } from "../api";
import { locationName, useCatalog } from "../catalog";
import { L, useLocale } from "../components/L";
import { TeamColumn } from "../components/monsters";
import { PlayerName } from "../components/StandingsTable";
import { Async, Facts, ModeName, Stat, editionTitle } from "../components/ui";
import { dateTime, day, num } from "../format";

export default function ResultPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const locale = useLocale();
  const cat = useCatalog();
  const state = useApi<Entry>(apiUrl(`/results/${encodeURIComponent(id)}`));
  return (
    <Async state={state} lines={6}>
      {(e) => {
        const c = e.championship_detail!;
        const place = locationName(cat, e.location, locale);
        return (
          <>
            <nav className="crumbs" aria-label={t("nav.breadcrumb")}>
              <L to="/championships">{t("nav.championships")}</L> › <L to={`/championships/${c.id}`}><ModeName mode={c.mode} /> {editionTitle(t, c)}</L>
            </nav>
            <div className="page-head">
              <div>
                <h1><PlayerName id={e.player.id} name={e.player.name} /></h1>
                <p className="subtitle">
                  {[t(e.kind === "gp" ? "result.gpEntry" : "result.gcupEntry"),
                    e.contest_day && t("result.countsFor", { day: day(e.contest_day, locale) }),
                    t("result.received", { when: dateTime(e.received_at, locale) }), place].filter(Boolean).join(" · ")}
                </p>
                {e.name_provenance !== "observed" && <p className="muted small">{t(`provenance.${e.name_provenance}`)}</p>}
              </div>
            </div>
            {e.kind === "gp" ? (
              <div className="result-layout">
                <section>
                  <Facts>
                    <Stat label={t("points.total")} value={num(e.points?.total, locale)} />
                    <Stat label={t("points.win")} value={num(e.points?.win, locale)} />
                    <Stat label={t("points.popularity")} value={num(e.points?.popularity, locale)} />
                    <Stat label={t("points.strength")} value={num(e.points?.strength, locale)} />
                    <Stat label={t("points.evaluation")} value={num(e.points?.evaluation, locale)} />
                  </Facts>
                  <h2>{t("result.rounds")}</h2>
                  <p className="muted small">{t("result.roundsNote")}</p>
                  <ol className="rounds">
                    {(e.round_results ?? []).map((r) => (
                      <li key={r.idx} className={r.won ? "won" : ""}>
                        <span className="round-n">{t("result.round", { n: r.idx + 1 })}</span>
                        <span>{t("result.vs")} {r.opponent?.player ? <PlayerName id={r.opponent.player.id} name={r.opponent.name || r.opponent.player.name} />
                          : <span>{r.opponent?.name || t("result.cpu")}</span>}</span>
                        <span className={`outcome ${r.won ? "outcome-won" : ""}`}>{r.won ? t("result.won") : t("result.notWon")}</span>
                        <span className="muted small">{t("result.roundPoints", { win: r.points?.win ?? 0, pop: r.points?.popularity ?? 0, str: r.points?.strength ?? 0, ev: r.points?.evaluation ?? 0 })}</span>
                      </li>
                    ))}
                  </ol>
                  {e.signature === "valid" && <p className="muted small">{t("result.signed")}</p>}
                  {e.validation !== "unverified" && <p className="notice notice-warn">{t(`validation.${e.validation}`)}</p>}
                </section>
                <section>
                  <h2>{t("result.team")}</h2>
                  <TeamColumn team={e.team ?? []} />
                </section>
              </div>
            ) : (
              <Facts>
                <Stat label={t("standings.time")} value={e.time ?? "—"} />
                <Stat label={t("result.frames")} value={num(e.frames, locale)} hint={t("result.framesNote")} />
                <Stat label={t("result.best")} value={e.improved ? t("result.yes") : t("result.no")} />
              </Facts>
            )}
            <p><L to={`/championships/${c.id}`}>← {t("result.back")}</L></p>
          </>
        );
      }}
    </Async>
  );
}
