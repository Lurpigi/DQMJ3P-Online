"""Standings shared by the importer (final revisions) and the API (live views).

Grand Prix: the points of every valid entry of the edition are summed (one ticket = one entry of
three rounds), exactly like sil_server.Handler._standings(); rank = 1 + players with more points
(ties share it), position breaks ties by the opaque player id. The published view counts the
contest days before `cutoff_day`, like the game; the provisional view counts every imported entry.
G-Cup: one row per ranking.scores row (player, unique id), fastest time first, earlier upload first.
"""

GP_STANDINGS = """
WITH totals AS (
    SELECT e.player_id,
           sum(e.points)::int AS points, sum(e.points_win)::int AS points_win, sum(e.points_pop)::int AS points_pop,
           sum(e.points_strength)::int AS points_strength, sum(e.points_eval)::int AS points_eval,
           sum(e.rounds)::int AS rounds, sum(e.rounds_won)::int AS rounds_won, count(*)::int AS entries,
           (array_agg(e.observed_name ORDER BY e.received_at DESC, e.id DESC))[1] AS name,
           (array_agg(e.observed_location ORDER BY e.received_at DESC, e.id DESC))[1] AS location,
           max(e.id) AS last_entry
    FROM dashboard.entries e
    WHERE e.championship_id = %(championship)s AND e.kind = 'gp' AND e.validation = 'unverified'
      AND (%(cutoff_day)s::date IS NULL OR e.contest_day < %(cutoff_day)s::date)
      AND (%(max_entry)s::bigint IS NULL OR e.id <= %(max_entry)s::bigint)
    GROUP BY e.player_id
)
SELECT t.*, rank() OVER (ORDER BY t.points DESC)::int AS rank,
       row_number() OVER (ORDER BY t.points DESC, t.player_id)::int AS position
FROM totals t
ORDER BY position
"""

GCUP_LIVE = """
SELECT b.player_id, b.frames, b.team_name AS name, b.updated_at,
       row_number() OVER (ORDER BY b.frames, b.updated_at, b.player_id, b.unique_id)::int AS position
FROM dashboard.gcup_best b
WHERE b.championship_id = %(championship)s
ORDER BY position
"""


def gp_standings(conn, championship, cutoff_day=None, max_entry=None):
    return conn.execute(GP_STANDINGS, {"championship": championship, "cutoff_day": cutoff_day,
                                       "max_entry": max_entry}).fetchall()


def gcup_live(conn, championship):
    rows = conn.execute(GCUP_LIVE, {"championship": championship}).fetchall()
    for r in rows:  # the game numbers every row (OrderCalculation123 in gcup_week.go)
        r["rank"] = r["position"]
    return rows


def write_revision(conn, championship, rows, reason, source=None, mode="gp"):
    """Stores `rows` as the next revision of the final standings; the first one finalizes the
    edition. Returns the revision number."""
    from psycopg.types.json import Jsonb

    rev = conn.execute("SELECT COALESCE(max(revision), 0) + 1 AS r FROM dashboard.revisions WHERE championship_id = %s",
                       (championship,)).fetchone()["r"]
    conn.execute("INSERT INTO dashboard.revisions (championship_id, revision, reason, source) VALUES (%s, %s, %s, %s)",
                 (championship, rev, reason, Jsonb(source or {})))
    for r in rows:
        conn.execute(
            "INSERT INTO dashboard.standings (championship_id, revision, position, rank, player_id, name, location, "
            "points, points_win, points_pop, points_strength, points_eval, rounds, rounds_won, entries, frames) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (championship, rev, r["position"], r["rank"], r["player_id"], r.get("name") or "", r.get("location"),
             r.get("points"), r.get("points_win"), r.get("points_pop"), r.get("points_strength"), r.get("points_eval"),
             r.get("rounds"), r.get("rounds_won"), r.get("entries"), r.get("frames")))
    conn.execute("UPDATE dashboard.championships SET final_revision = %s, finalized_at = COALESCE(finalized_at, now()), "
                 "updated_at = now() WHERE id = %s", (rev, championship))
    return rev


STANDING_KEYS = ("position", "rank", "player_id", "points", "points_win", "points_pop", "points_strength",
                 "points_eval", "rounds", "rounds_won", "entries", "frames")


def same_standings(a, b):
    pick = lambda rows: [tuple(r.get(k) for k in STANDING_KEYS) for r in rows]
    return pick(a) == pick(b)
