import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Mode, Standing } from "../api";
import { locationName, useCatalog } from "../catalog";
import { num } from "../format";
import { Icon } from "./Icon";
import { L, useLocale } from "./L";
import { TeamStrip } from "./monsters";
import { RankCell } from "./ui";

export function PlayerName({ id, name }: { id: string; name: string }) {
  const { t } = useTranslation();
  return <L to={`/players/${id}`} className="player-link">{name || <span className="muted">{t("player.unnamed")}</span>}</L>;
}

export function StandingsTable({ rows, mode, caption, compact }: { rows: Standing[]; mode: Mode; caption: string; compact?: boolean }) {
  const { t } = useTranslation();
  const locale = useLocale();
  const cat = useCatalog();
  const [open, setOpen] = useState<number | null>(null);
  const gp = mode !== "gcup";
  return (
    <div className="table-wrap">
      <table className={`standings${compact ? " compact" : ""}`}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="num col-rank">{t("standings.rank")}</th>
            <th scope="col">{t("standings.player")}</th>
            {gp && <th scope="col" className="hide-sm">{t("standings.team")}</th>}
            {gp && !compact && <th scope="col" className="num hide-sm">{t("standings.rounds")}</th>}
            {gp && !compact && <th scope="col" className="num hide-md">{t("standings.entries")}</th>}
            <th scope="col" className="num">{gp ? t("standings.points") : t("standings.time")}</th>
            {gp && !compact && <th scope="col"><span className="sr-only">{t("standings.details")}</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const place = locationName(cat, r.location, locale);
            const expanded = open === r.position;
            return (
              <Fragment key={r.position}>
                <tr className={r.rank <= 3 ? `podium-row podium-${r.rank}` : undefined}>
                  <td className="num"><RankCell rank={r.rank} previous={r.previous_rank} /></td>
                  <td>
                    <PlayerName id={r.player.id} name={r.player.name} />
                    {place && <span className="place">{place}</span>}
                    {gp && <span className="show-sm"><TeamStrip team={r.team} size={22} /></span>}
                  </td>
                  {gp && <td className="hide-sm"><TeamStrip team={r.team} size={compact ? 24 : 28} /></td>}
                  {gp && !compact && <td className="num hide-sm">{r.rounds_won ?? 0}/{r.rounds ?? 0}</td>}
                  {gp && !compact && <td className="num hide-md">{num(r.entries, locale)}</td>}
                  <td className="num score">{gp ? num(r.points?.total, locale) : r.time ?? "—"}</td>
                  {gp && !compact && (
                    <td className="expand-cell">
                      <button type="button" className="btn btn-icon" aria-expanded={expanded}
                              aria-label={t("standings.toggle", { name: r.player.name })} onClick={() => setOpen(expanded ? null : r.position)}>
                        <Icon name="chevron" />
                      </button>
                    </td>
                  )}
                </tr>
                {expanded && r.points && (
                  <tr className="detail-row">
                    <td colSpan={7}>
                      <dl className="breakdown">
                        <div><dt>{t("points.win")}</dt><dd>{num(r.points.win, locale)}</dd></div>
                        <div><dt>{t("points.popularity")}</dt><dd>{num(r.points.popularity, locale)}</dd></div>
                        <div><dt>{t("points.strength")}</dt><dd>{num(r.points.strength, locale)}</dd></div>
                        <div><dt>{t("points.evaluation")}</dt><dd>{num(r.points.evaluation, locale)}</dd></div>
                        <div><dt>{t("standings.rounds")}</dt><dd>{r.rounds_won ?? 0}/{r.rounds ?? 0}</dd></div>
                        <div><dt>{t("standings.entries")}</dt><dd>{num(r.entries, locale)}</dd></div>
                        <div><dt>{t("standings.position")}</dt><dd>{r.position}</dd></div>
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
