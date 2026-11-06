import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { speciesName, useCatalog } from "../catalog";
import { L, useLocale, useQuery } from "../components/L";
import { MonsterPortrait } from "../components/monsters";
import { Empty, Loading } from "../components/ui";
import { RANK_LETTERS } from "../format";

const PAGE = 120;

export default function Monsters() {
  const { t } = useTranslation();
  const locale = useLocale();
  const cat = useCatalog();
  const query = useQuery();
  const [q, family, rank] = [query.get("q"), query.get("family"), query.get("rank")];
  const shown = Number(query.get("n")) || PAGE;
  const set = (k: string, v: string) => query.set(k, v, ["n"]); // a new filter starts from the first page
  const list = useMemo(() => {
    if (!cat) return [];
    const key = q.normalize("NFKC").toLowerCase().trim();
    return cat.species.filter((s) => s.art && !s.story_copy
      && (!family || String(s.family) === family) && (!rank || String(s.rank) === rank)
      && (!key || String(s.id) === key || Object.values(s.names).some((n) => n?.normalize("NFKC").toLowerCase().includes(key))));
  }, [cat, q, family, rank]);
  return (
    <>
      <div className="page-head"><h1>{t("monsters.title")}</h1><p className="lede">{t("monsters.lede")}</p></div>
      <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
        <label className="grow">{t("filter.search")}<input type="search" value={q} maxLength={40} onChange={(e) => set("q", e.target.value)} placeholder={t("monsters.searchHint")} /></label>
        <label>{t("monster.family")}
          <select value={family} onChange={(e) => set("family", e.target.value)}>
            <option value="">{t("filter.any")}</option>
            {cat && Object.entries(cat.families).map(([k, v]) => <option key={k} value={k}>{t(`family.${v}`)}</option>)}
          </select>
        </label>
        <label>{t("monster.rank")}
          <select value={rank} onChange={(e) => set("rank", e.target.value)}>
            <option value="">{t("filter.any")}</option>
            {RANK_LETTERS.slice(1).map((r, i) => <option key={r} value={i + 1}>{r}</option>)}
          </select>
        </label>
      </form>
      {!cat ? <Loading lines={6} /> : list.length === 0 ? <Empty>{t("monsters.none")}</Empty> : (
        <>
          <p className="muted small">{t("monsters.count", { count: list.length })}</p>
          <ul className="monster-grid">
            {list.slice(0, shown).map((s) => (
              <li key={s.id}>
                <L to={`/monsters/${s.id}`}>
                  <MonsterPortrait species={s.id} size={64} />
                  <span className="monster-name">{speciesName(cat, s.id, locale)}</span>
                  <span className="muted small">{s.rank ? RANK_LETTERS[s.rank] : "—"} · {t(`family.${cat.families[String(s.family)] ?? "unknown"}`)}</span>
                </L>
              </li>
            ))}
          </ul>
          {shown < list.length && (
            <div className="load-more"><button type="button" className="btn" onClick={() => query.set("n", String(shown + PAGE))}>{t("state.more")}</button></div>
          )}
        </>
      )}
    </>
  );
}
