import { useTranslation } from "react-i18next";
import { apiUrl, usePaged, type Championship } from "../api";
import { L, useLocale, useQuery } from "../components/L";
import { PlayerName } from "../components/StandingsTable";
import { ModeTag, PagedList, StatusBadge, editionTitle } from "../components/ui";
import { dateOnly, lastMoment, num } from "../format";

export default function Championships() {
  const { t } = useTranslation();
  const locale = useLocale();
  const { get, set, reset, any } = useQuery();
  const [mode, status, year, q] = [get("mode"), get("status"), get("year"), get("q")];
  const list = usePaged<Championship>(apiUrl("/championships", { mode, status, year, q, limit: 25 }));
  const years = Array.from({ length: new Date().getFullYear() - 2015 + 1 }, (_, i) => String(new Date().getFullYear() - i));
  return (
    <>
      <div className="page-head">
        <h1>{t("archive.title")}</h1>
        <p className="lede">{t("archive.lede")}</p>
      </div>
      <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
        <label>{t("filter.mode")}
          <select value={mode} onChange={(e) => set("mode", e.target.value)}>
            <option value="">{t("filter.allModes")}</option>
            {(["grade", "limit", "gcup"] as const).map((m) => <option key={m} value={m}>{t(`mode.${m}.name`)}</option>)}
          </select>
        </label>
        <label>{t("filter.status")}
          <select value={status} onChange={(e) => set("status", e.target.value)}>
            <option value="">{t("filter.any")}</option>
            {(["open", "finalizing", "final", "upcoming"] as const).map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
          </select>
        </label>
        <label>{t("filter.year")}
          <select value={year} onChange={(e) => set("year", e.target.value)}>
            <option value="">{t("filter.any")}</option>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label className="grow">{t("filter.search")}
          <input type="search" value={q} placeholder={t("archive.searchHint")} onChange={(e) => set("q", e.target.value)} maxLength={40} />
        </label>
        {any && <button type="button" className="btn btn-ghost" onClick={reset}>{t("filter.reset")}</button>}
      </form>
      <PagedList list={list} lines={6} empty={t("archive.none")}>
        {(items) => (
        <div className="table-wrap">
          <table className="list">
            <caption className="sr-only">{t("archive.title")}</caption>
            <thead><tr>
              <th scope="col">{t("archive.edition")}</th><th scope="col" className="hide-sm">{t("archive.dates")}</th>
              <th scope="col">{t("filter.status")}</th><th scope="col" className="num">{t("archive.entrants")}</th>
              <th scope="col" className="hide-sm">{t("archive.winner")}</th>
            </tr></thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td><ModeTag mode={c.mode} /> <L to={`/championships/${c.id}`} className="strong">{editionTitle(t, c)}</L>
                    {c.mode === "gcup" && c.cup?.name && <span className="muted"> · {c.cup.name}</span>}</td>
                  <td className="hide-sm">{dateOnly(c.starts_at, locale, c.utc_offset_minutes)} – {dateOnly(lastMoment(c.ends_at), locale, c.utc_offset_minutes)}</td>
                  <td><StatusBadge status={c.status} /></td>
                  <td className="num">{num(c.entrants, locale)}</td>
                  <td className="hide-sm">{c.winner ? <PlayerName id={c.winner.id} name={c.winner.name} /> : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </PagedList>
    </>
  );
}
