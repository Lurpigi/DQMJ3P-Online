import { useTranslation } from "react-i18next";
import { apiUrl, useApi, type Freshness, type Mode, type Status } from "../api";
import { L, useLocale } from "../components/L";
import { Async, ModeName, StatusBadge } from "../components/ui";
import { dateTime, relative } from "../format";

interface StatusData {
  status: "ok" | "degraded"; now: string; sources: Freshness[]; finalizing: string[];
  current: Record<Mode, { id: string; status: Status; ends_at: string } | null>; catalog_version: string | null;
  gp_signature_checks: { valid: number; invalid: number };
}

export default function StatusPage() {
  const { t } = useTranslation();
  const locale = useLocale();
  const state = useApi<StatusData>(apiUrl("/status"), 30000);
  return (
    <>
      <div className="page-head"><h1>{t("statusPage.title")}</h1></div>
      <Async state={state}>
        {(d) => (
          <>
            <p className={`notice ${d.status === "ok" ? "notice-info" : "notice-warn"}`}>{t(`statusPage.${d.status}`)}</p>
            <h2>{t("statusPage.sources")}</h2>
            <div className="table-wrap"><table className="list">
              <thead><tr><th scope="col">{t("statusPage.source")}</th><th scope="col">{t("statusPage.asOf")}</th><th scope="col">{t("statusPage.state")}</th></tr></thead>
              <tbody>{d.sources.map((s) => (
                <tr key={s.source}><td>{t(`statusPage.src.${s.source}`, { defaultValue: s.source })}</td>
                  <td>{s.as_of ? <time dateTime={s.as_of} title={dateTime(s.as_of, locale)}>{relative(s.as_of, locale)}</time> : "—"}</td>
                  <td>{s.failing ? t("statusPage.failing") : t("statusPage.healthy")}</td></tr>))}</tbody>
            </table></div>
            <h2>{t("statusPage.current")}</h2>
            <ul className="plain">
              {(Object.entries(d.current) as [Mode, StatusData["current"][Mode]][]).map(([m, c]) => (
                <li key={m}><ModeName mode={m} />: {c ? <><L to={`/championships/${c.id}`}>{c.id}</L> <StatusBadge status={c.status} /> · {t("edition.ends")} {dateTime(c.ends_at, locale)}</> : "—"}</li>
              ))}
            </ul>
            {d.finalizing.length > 0 && <><h2>{t("status.finalizing")}</h2><ul className="plain">{d.finalizing.map((id) => <li key={id}><L to={`/championships/${id}`}>{id}</L></li>)}</ul></>}
            <h2>{t("statusPage.checks")}</h2>
            <p className="muted">{t("statusPage.signatures", { valid: d.gp_signature_checks.valid, invalid: d.gp_signature_checks.invalid })}</p>
            <p className="muted small">{t("statusPage.catalog", { version: d.catalog_version ?? "—" })}</p>
          </>
        )}
      </Async>
    </>
  );
}
