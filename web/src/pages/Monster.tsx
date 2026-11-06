import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { apiUrl, useApi, type Mode, type PlayerRef, type TeamMember } from "../api";
import { artOf, speciesName, useCatalog } from "../catalog";
import { L, useLocale } from "../components/L";
import { MonsterPortrait, TeamStrip } from "../components/monsters";
import { PlayerName } from "../components/StandingsTable";
import { Async, Empty, Facts, Loading, Meter, ModeName, ModeTag, Stat } from "../components/ui";
import { RANK_LETTERS, percent, relative } from "../format";
import { LOCALE_NAMES } from "../i18n";

interface MonsterStats {
  by_mode: Record<"grade" | "limit", { teams: number; with_species: number }>;
  recent: { entry: string; championship: string; mode: Mode; player: PlayerRef; received_at: string; points: number; team: TeamMember[] }[];
}
const STATS = ["hp", "mp", "atk", "def", "agi", "wis"] as const;
const STAT_SCALE = 2000; // bars share one scale so species compare at a glance

export default function MonsterPage() {
  const { id = "" } = useParams();
  const species = Number(id);
  const { t } = useTranslation();
  const locale = useLocale();
  const cat = useCatalog();
  const stats = useApi<MonsterStats>(Number.isInteger(species) ? apiUrl(`/monsters/${species}/stats`) : null);
  if (!cat) return <Loading />;
  const s = cat.byId.get(species);
  if (!s) return <Empty>{t("monsters.unknown", { id })}</Empty>;
  const art = artOf(cat, species);
  return (
    <>
      <nav className="crumbs" aria-label={t("nav.breadcrumb")}><L to="/monsters">{t("nav.monsters")}</L></nav>
      <div className="monster-head">
        <MonsterPortrait species={species} size={120} full />
        <div>
          <h1>{speciesName(cat, species, locale)}</h1>
          <p className="subtitle">#{s.id} · {t("monster.rank")} {s.rank ? RANK_LETTERS[s.rank] : "—"} · {t(`family.${cat.families[String(s.family)] ?? "unknown"}`)} · {t(`size.${s.size}`, { defaultValue: "—" })}</p>
          <dl className="names">
            {(["en", "it", "fr", "ja"] as const).filter((l) => s.names[l]).map((l) => <div key={l}><dt>{LOCALE_NAMES[l]}</dt><dd lang={l}>{s.names[l]}</dd></div>)}
          </dl>
        </div>
      </div>
      <section className="section">
        <h2>{t("monster.maxStats")}</h2>
        <dl className="stat-bars">
          {STATS.map((k, i) => (
            <div key={k}><dt>{t(`stat.${k}`)}</dt><dd><Meter value={s.stats[i]} max={STAT_SCALE} /></dd></div>
          ))}
        </dl>
      </section>
      <section className="section">
        <h2>{t("monster.usage")}</h2>
        <Async state={stats}>
          {(d) => (
            <>
              <Facts>
                {(["grade", "limit"] as const).map((m) => (
                  <Stat key={m} label={<ModeName mode={m} />} value={percent(d.by_mode[m].with_species, d.by_mode[m].teams, locale)}
                        hint={t("stats.teamsOf", { n: d.by_mode[m].with_species, total: d.by_mode[m].teams })} />
                ))}
              </Facts>
              <p className="muted small">{t("monster.usageNote")}</p>
              <h3>{t("monster.recent")}</h3>
              {d.recent.length === 0 ? <Empty>{t("monster.noTeams")}</Empty> : (
                <ul className="feed">
                  {d.recent.map((r) => (
                    <li key={r.entry}><ModeTag mode={r.mode} /> <PlayerName id={r.player.id} name={r.player.name} /> <TeamStrip team={r.team} size={22} />
                      <L to={`/results/${r.entry}`} className="feed-time">{relative(r.received_at, locale)}</L></li>
                  ))}
                </ul>
              )}
            </>
          )}
        </Async>
      </section>
      {art && <p className="muted small">{t("monster.artSource")}</p>}
    </>
  );
}
