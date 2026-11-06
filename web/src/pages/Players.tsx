import { useTranslation } from "react-i18next";
import { apiUrl, usePaged } from "../api";
import { useLocale, useQuery } from "../components/L";
import { PlayerName } from "../components/StandingsTable";
import { PagedList } from "../components/ui";
import { relative } from "../format";

interface PlayerItem { id: string; name: string; source: "sil" | "nex"; aliases: string[]; last_seen: string; final_standings: number }

export default function Players() {
  const { t } = useTranslation();
  const locale = useLocale();
  const { get, set } = useQuery();
  const [q, source] = [get("q"), get("source")];
  const list = usePaged<PlayerItem>(apiUrl("/players", { q, namespace: source, limit: 25 }));
  return (
    <>
      <div className="page-head"><h1>{t("players.title")}</h1><p className="lede">{t("players.lede")}</p></div>
      <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
        <label className="grow">{t("players.search")}
          <input type="search" value={q} maxLength={40} onChange={(e) => set("q", e.target.value)} placeholder={t("players.searchHint")} />
        </label>
        <label>{t("players.source")}
          <select value={source} onChange={(e) => set("source", e.target.value)}>
            <option value="">{t("filter.any")}</option>
            <option value="sil">{t("source.sil")}</option>
            <option value="nex">{t("source.nex")}</option>
          </select>
        </label>
      </form>
      <p className="muted small">{t("players.identityNote")}</p>
      <PagedList list={list} lines={6} empty={q ? t("players.none", { q }) : t("players.empty")}>
        {(items) => (
        <ul className="player-list">
          {items.map((p) => (
            <li key={p.id}>
              <PlayerName id={p.id} name={p.name} />
              <span className={`source source-${p.source}`}>{t(`source.${p.source}`)}</span>
              {p.aliases.length > 0 && <span className="muted small">{t("players.aka", { names: p.aliases.join(", ") })}</span>}
              <span className="muted small push">{t("players.finals", { count: p.final_standings })} · {relative(p.last_seen, locale)}</span>
            </li>
          ))}
        </ul>
        )}
      </PagedList>
    </>
  );
}
