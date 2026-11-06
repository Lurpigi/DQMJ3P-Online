import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TeamMember } from "../api";
import { artOf, speciesName, useCatalog } from "../catalog";
import { RANK_LETTERS } from "../format";
import { L, useLocale } from "./L";

const IMG_BASE = `${import.meta.env.BASE_URL}monsters/`;
const FAMILY_BASE = `${import.meta.env.BASE_URL}families/`;
const FAMILY_ICONS = new Set(["slime", "dragon", "beast", "nature", "demon", "undead", "material", "corrupted", "unknown"]);

/** Localized family name with its in-game style icon (public/families/<key>.png, 16 px pixel art). */
export function FamilyName({ family }: { family: number | null | undefined }) {
  const cat = useCatalog();
  const { t } = useTranslation();
  const key = (family && cat?.families[String(family)]) || "unknown";
  return (
    <span className="family">
      {FAMILY_ICONS.has(key) && <img className="family-icon" src={`${FAMILY_BASE}${key}.png`} alt="" width={16} height={16} />}
      {t(`family.${key}`)}
    </span>
  );
}

/** Portrait of a species. icon = the first tile (square), full = every tile stacked, as in the
 *  game's party list (large monsters take 2-4 tiles). Unknown species or missing artwork get a
 *  neutral placeholder: decorative art never stands in for a team that was not recorded. */
export function MonsterPortrait({ species, size = 40, full = false }: { species: number; size?: number; full?: boolean }) {
  const cat = useCatalog();
  const locale = useLocale();
  const [failed, setFailed] = useState(false);
  const art = artOf(cat, species);
  const name = speciesName(cat, species, locale);
  const tiles = full && art ? art.tiles : 1;
  if (!art || failed) {
    return <span className="portrait portrait-missing" style={{ width: size, height: size * tiles }} role="img" aria-label={name} title={name}>?</span>;
  }
  return (
    <img className={`portrait${full ? " portrait-full" : ""}`} src={IMG_BASE + art.file} alt={name} title={name}
         width={size} height={size * tiles} loading="lazy" decoding="async" onError={() => setFailed(true)} />
  );
}

/** Compact strip of a recorded team (tables, cards). */
export function TeamStrip({ team, size = 28, label }: { team: TeamMember[] | undefined; size?: number; label?: string }) {
  const { t } = useTranslation();
  if (!team?.length) return <span className="team-none">{t("team.none")}</span>;
  return (
    <span className="team-strip" role="group" aria-label={label ?? t("team.label")}>
      {team.map((m, i) => <MonsterPortrait key={i} species={m.species} size={size} />)}
    </span>
  );
}

/** Full team with names, levels and stats (result pages). */
export function TeamColumn({ team, changed }: { team: TeamMember[]; changed?: Set<number> }) {
  const cat = useCatalog();
  const locale = useLocale();
  const { t } = useTranslation();
  if (!team.length) return <p className="muted">{t("team.none")}</p>;
  return (
    <ol className="team-column">
      {team.map((m, i) => {
        const s = cat?.byId.get(m.species);
        return (
          <li key={i} className={changed?.has(m.species) ? "changed" : undefined}>
            <MonsterPortrait species={m.species} size={56} full />
            <div className="team-member">
              <L to={`/monsters/${m.species}`} className="strong">{speciesName(cat, m.species, locale)}</L>
              <span className="muted">
                {m.level != null && t("team.level", { level: m.level })}
                {s?.rank ? ` · ${t("monster.rank")} ${RANK_LETTERS[s.rank]}` : ""}
                {s?.family ? <> · <FamilyName family={s.family} /></> : null}
              </span>
              {m.stats && (
                <dl className="mini-stats">
                  {(["hp", "mp", "atk", "def", "agi", "wis"] as const).map((k) => (
                    <div key={k}><dt>{t(`stat.${k}`)}</dt><dd>{m.stats![k]}</dd></div>
                  ))}
                </dl>
              )}
              {changed?.has(m.species) && <span className="tag">{t("team.newMember")}</span>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
