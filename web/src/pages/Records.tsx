import { useTranslation } from "react-i18next";
import { apiUrl, useApi, type Championship, type Mode, type PlayerRef } from "../api";
import { L, useLocale, useQuery } from "../components/L";
import { courseName } from "../components/Rules";
import { PlayerName } from "../components/StandingsTable";
import { Async, Empty, ModeTag, Segmented, editionTitle } from "../components/ui";
import { dateOnly, num } from "../format";

interface RecordsData {
  champions: { championship: string; mode: Mode; edition: number; starts_at: string; cup: Championship["cup"]; player: PlayerRef; points: number | null; time: string | null }[];
  podium_leaders: { player: PlayerRef; titles: number; podiums: number; finals: number }[];
  participation: { player: PlayerRef; finals: number }[];
  gcup_best_times: { course: { map: number; variant: number } | null; event: number | null; time: string; player: PlayerRef; championship: string; edition: number }[];
}

export default function Records() {
  const { t } = useTranslation();
  const locale = useLocale();
  const { get, set } = useQuery();
  const mode = get("mode");
  const state = useApi<RecordsData>(apiUrl("/records", { mode }));
  return (
    <>
      <div className="page-head"><h1>{t("records.title")}</h1><p className="lede">{t("records.lede")}</p></div>
      <div className="toolbar">
        <Segmented label={t("filter.mode")} value={mode} onChange={(m) => set("mode", m)}
                   options={[{ key: "", label: t("filter.allModes") }, ...(["grade", "limit", "gcup"] as const).map((m) => ({ key: m, label: t(`mode.${m}.name`) }))]} />
      </div>
      <Async state={state} lines={8}>
        {(d) => (
          <div className="records-layout">
            <div>
              <section className="section">
                <h2>{t("records.champions")}</h2>
                {d.champions.length === 0 ? <Empty>{t("records.none")}</Empty> : (
                  <ol className="plain hall">
                    {d.champions.map((c) => (
                      <li key={c.championship + c.player.id}>
                        <ModeTag mode={c.mode} /> <L to={`/championships/${c.championship}`}>{editionTitle(t, c)}</L>
                        <span className="muted small"> {dateOnly(c.starts_at, locale)}</span> · <PlayerName id={c.player.id} name={c.player.name} />
                        <span className="muted"> {c.time ?? num(c.points, locale)}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
              <section className="section">
                <h2>{t("records.gcupTimes")}</h2>
                <p className="muted small">{t("records.gcupNote")}</p>
                {d.gcup_best_times.length === 0 ? <Empty>{t("records.none")}</Empty> : (
                  <ul className="plain hall">
                    {d.gcup_best_times.map((r) => (
                      <li key={r.championship}>
                        <strong>{courseName(t, r.course) ?? "—"}</strong> · {t(`cup.event.${r.event ?? 0}`)}
                        <br /><span className="strong">{r.time}</span> <PlayerName id={r.player.id} name={r.player.name} />{" "}
                        <L to={`/championships/${r.championship}`} className="small">{t("edition.gcupShort", { week: r.edition })}</L>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
            <div>
              <section className="section">
                <h2>{t("records.podiums")}</h2>
                {d.podium_leaders.length === 0 ? <Empty>{t("records.none")}</Empty> : (
                  <div className="table-wrap"><table className="list compact">
                    <thead><tr><th scope="col">{t("standings.player")}</th><th scope="col" className="num">{t("player.titles")}</th>
                      <th scope="col" className="num">{t("player.podiums")}</th><th scope="col" className="num">{t("player.finals")}</th></tr></thead>
                    <tbody>{d.podium_leaders.map((r) => <tr key={r.player.id}><td><PlayerName id={r.player.id} name={r.player.name} /></td>
                      <td className="num">{r.titles}</td><td className="num">{r.podiums}</td><td className="num">{r.finals}</td></tr>)}</tbody>
                  </table></div>
                )}
              </section>
              <section className="section">
                <h2>{t("records.participation")}</h2>
                {d.participation.length === 0 ? <Empty>{t("records.none")}</Empty> : (
                  <ol className="plain columns">{d.participation.map((r) => <li key={r.player.id}><PlayerName id={r.player.id} name={r.player.name} /> <span className="muted">{t("players.finals", { count: r.finals })}</span></li>)}</ol>
                )}
              </section>
            </div>
          </div>
        )}
      </Async>
    </>
  );
}
