import { useTranslation } from "react-i18next";
import type { Championship, Coins, Cup } from "../api";
import { itemName, useCatalog } from "../catalog";
import { useLocale } from "./L";
import { MonsterPortrait } from "./monsters";

const COURSES = ["Grass Field", "Cross Road", "Wild Wall", "Crash Cave"];

function coinsText(t: (k: string, o?: Record<string, unknown>) => string, coins: Coins | null | undefined) {
  if (!coins) return null;
  const parts = (["platinum", "gold", "silver", "bronze"] as const).filter((k) => coins[k]).map((k) => t(`coins.${k}`, { count: coins[k] }));
  return parts.length ? parts.join(", ") : null;
}

export function courseName(t: (k: string, o?: Record<string, unknown>) => string, course: Cup["course"] | null) {
  if (!course) return null;
  return t("cup.course", { name: COURSES[course.map] ?? `#${course.map}`, variant: course.variant + 1 });
}

export function RulesBlock({ c }: { c: Championship }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const cat = useCatalog();
  const r = c.rules;
  const pick = (m?: Record<string, string>) => m?.[locale] ?? m?.en;
  return (
    <section className="rules" aria-labelledby={`rules-${c.id}`}>
      <h2 className="h3" id={`rules-${c.id}`}>{t("rules.title")}</h2>
      {c.mode === "grade" && <p>{t("rules.grade")}</p>}
      {c.mode === "limit" && r.kind === "limit" && (
        <>
          {pick(r.theme) && <p className="theme">{pick(r.theme)}</p>}
          <p>{pick(r.text)}</p>
        </>
      )}
      {c.mode === "limit" && r.kind === "static" && <p>{t("rules.static")}</p>}
      {c.mode === "gcup" && (
        <>
          <p>{[courseName(t, c.cup?.course), c.cup?.event ? t(`cup.event.${c.cup.event}`) : t("cup.event.0")].filter(Boolean).join(" · ")}</p>
          {c.cup?.allowed_species?.length ? (
            <div><span className="muted">{t("rules.allowed")}</span>
              <div className="species-row">{c.cup.allowed_species.map((s) => <MonsterPortrait key={s} species={s} size={28} />)}</div>
            </div>
          ) : <p className="muted">{t("rules.anySpecies")}</p>}
        </>
      )}
      <h2 className="h3">{t("rewards.title")}</h2>
      {c.mode !== "gcup" ? (
        <ul className="plain">
          {(["champion", "top10"] as const).map((k) => {
            const reward = c.rewards[k];
            const parts = [reward?.item ? itemName(cat, reward.item, locale) : null, coinsText(t, reward?.coins)].filter(Boolean);
            return <li key={k}><strong>{t(`rewards.${k}`)}</strong>: {parts.length ? parts.join(" + ") : t("rewards.none")}</li>;
          })}
        </ul>
      ) : c.rewards.prizes?.length ? (
        <ul className="plain">
          {c.rewards.prizes.map((p) => (
            <li key={p.from}><strong>{p.from === p.to ? t("rewards.rank", { rank: p.from }) : t("rewards.ranks", { from: p.from, to: p.to })}</strong>: {coinsText(t, p.coins)}</li>
          ))}
        </ul>
      ) : <p className="muted">{t("rewards.none")}</p>}
    </section>
  );
}
