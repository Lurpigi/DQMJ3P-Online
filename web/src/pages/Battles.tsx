import { useTranslation } from "react-i18next";
import { apiUrl, usePaged, type Mode, type PlayerRef, type TeamMember } from "../api";
import { speciesName, useCatalog } from "../catalog";
import { L, useLocale, useQuery } from "../components/L";
import { TeamStrip } from "../components/monsters";
import { PlayerName } from "../components/StandingsTable";
import { ModeTag, PagedList } from "../components/ui";
import { relative } from "../format";

interface Battle {
  entry: string; round: number; championship: string; mode: Mode; received_at: string; player: PlayerRef; team: TeamMember[];
  opponent: { name: string; player: PlayerRef | null }; won: boolean | null;
}

export default function Battles() {
  const { t } = useTranslation();
  const locale = useLocale();
  const cat = useCatalog();
  const { get, set, reset, any } = useQuery();
  const list = usePaged<Battle>(apiUrl("/battles", { mode: get("mode"), championship: get("championship"), player: get("player"),
    species: get("species"), from: get("from"), to: get("to"), limit: 30 }));
  return (
    <>
      <div className="page-head"><h1>{t("battles.title")}</h1><p className="lede">{t("battles.lede")}</p></div>
      <div className="notice notice-info"><p>{t("battles.coverage")}</p></div>
      <form className="filters" onSubmit={(e) => e.preventDefault()}>
        <label>{t("filter.mode")}
          <select value={get("mode")} onChange={(e) => set("mode", e.target.value)}>
            <option value="">{t("filter.allGp")}</option>
            <option value="grade">{t("mode.grade.name")}</option>
            <option value="limit">{t("mode.limit.name")}</option>
          </select>
        </label>
        <label>{t("filter.species")}
          <input list="species-list" value={get("species")} inputMode="numeric" onChange={(e) => set("species", e.target.value.replace(/\D/g, ""))} placeholder="#" />
        </label>
        <datalist id="species-list">{cat?.species.filter((s) => s.art && !s.story_copy).map((s) => <option key={s.id} value={s.id}>{speciesName(cat, s.id, locale)}</option>)}</datalist>
        <label>{t("filter.from")}<input type="date" value={get("from")} onChange={(e) => set("from", e.target.value)} /></label>
        <label>{t("filter.to")}<input type="date" value={get("to")} onChange={(e) => set("to", e.target.value)} /></label>
        {any && <button type="button" className="btn btn-ghost" onClick={reset}>{t("filter.reset")}</button>}
      </form>
      {get("player") && <p className="muted small">{t("battles.playerFilter")}</p>}
      <PagedList list={list} lines={8} empty={t("battles.none")}>
        {(items) => (
          <ul className="feed battles">
            {items.map((b) => (
              <li key={b.entry + "-" + b.round}>
                <span className="battle-who">
                  <ModeTag mode={b.mode} /> <PlayerName id={b.player.id} name={b.player.name} /> <TeamStrip team={b.team} size={22} />
                  <span className="muted"> {t("result.vs")} </span>
                  {b.opponent.player ? <PlayerName id={b.opponent.player.id} name={b.opponent.name || b.opponent.player.name} /> : (b.opponent.name || t("result.cpu"))}
                </span>
                <span className={`outcome ${b.won ? "outcome-won" : ""}`}>{b.won ? t("result.won") : t("result.notWon")}</span>
                <L to={`/results/${b.entry}`} className="feed-time">{t("result.round", { n: b.round })} · {relative(b.received_at, locale)}</L>
              </li>
            ))}
          </ul>
        )}
      </PagedList>
    </>
  );
}
