# Statistics portal: operations

Public championship archive, standings, player
histories and monster catalog, without accounts or logins.

| Part | Where | Runs on |
|---|---|---|
| Result capture | `server/sil/sil_server.py` (`gp_snapshots`, `gp_calendars`, `meta`), `server/nex/nex/ranking.go` and `gcup_week.go` (`history.*`) | the game services, always |
| Importer + public API | `server/dashboard/` (FastAPI, one process) | VPS, Compose profile `portal` |
| HTTPS | `server/caddy/Caddyfile` | VPS, Compose profile `portal` |
| Frontend | `web/` (Vite, React, hash routes, five languages) | GitHub Pages |
| Monster catalog | `tools/import-monsters/` → `server/dashboard/data/monsters.json` | developer machine |

Capture lives in the game services, so stopping or breaking the portal never loses a result and never
delays the game or the weekly G-Cup closing. The portal only reads: SIL's SQLite file through a
read-only mount and connection, the NEX tables through a role limited to the tables it imports.

## What is recorded

- **Grand Prix:** every uploaded entry stays in `gp_results` (as before). Each new upload also gets a
  `gp_snapshots` row in the same SQLite transaction: calendar version, contest number, the name and
  location from `00_UserData` at that moment, decoder version. `gp_calendars` records each
  `--gp-start/--gp-days/--gp-utc-offset` combination the server ran with (edition ids `gp-grade-cal1-n2`).
- **G-Cup:** `history.gcup_submissions` (every race upload of a G-Cup category, with whether it became the
  best), `history.gcup_common_data` (each new team name), `history.gcup_editions` (the cup definition of
  every week) and `history.gcup_finals` (full final standings, written by the weekly closing inside its
  transaction, before the cleanup). `ranking.*` and the game behaviour are unchanged.
- Results stored before this capture existed are imported with their original data; their names come
  from the current profile and are labelled *reconstructed*.

## One-time setup

1. **DNS:** an `A` record for the API name (e.g. `stats.example.org`) pointing at `PUBLIC_IP`.
   Without a domain, use the free [sslip.io](https://sslip.io) name of the IP: the production VPS uses
   `78-47-138-100.sslip.io` (the floating IP). Let's Encrypt issues certificates for it like any other name.
   Open TCP 443 and UDP 443 in the firewall, and keep TCP 80 closed: Caddy gets the certificate through
   the TLS-ALPN challenge on 443 and listens on nothing else. With 80 open, a flood meant for another site
   that still points at the floating IP filled the kernel connection table and dropped game packets.
   The VPS also has a larger table (`/etc/sysctl.d/60-conntrack.conf`: 131072 entries, 30 s for closed
   TCP connections).
2. **`.env`** on the VPS (see `server/.env.example`):
   ```
   COMPOSE_PROFILES=portal
   DASHBOARD_HOSTNAME=stats.example.org
   DASHBOARD_ALLOWED_ORIGINS=https://lurpigi.github.io
   DASHBOARD_IMPORTER_PASSWORD=<openssl rand -hex 16>
   DASHBOARD_API_PASSWORD=<openssl rand -hex 16>
   DASHBOARD_ID_SALT=<openssl rand -hex 16>
   ```
   `DASHBOARD_ID_SALT` must never change: public player ids (`/players/p…`) are derived from it.
   Back it up with `.env`. On the production VPS these values were generated on 2026-11-06; the previous
   `.env` is in `/root/env-backup-20261106183230`.
3. **GitHub:** Settings → Pages → Source: *GitHub Actions*. Settings → Variables → `PORTAL_API_URL` =
   `https://stats.example.org/api/v1`. The next push touching `web/` publishes the site at
   `https://lurpigi.github.io/DQMJ3P-Online/`.
4. Push to `main`: the deploy workflow builds `server-dashboard` with `server-nex`, and `remote.sh`
   starts `dashboard-migrate` (tables and roles), `dashboard` and `caddy`, then checks the API health.

Without `COMPOSE_PROFILES=portal` the stack runs exactly as before; capture still happens, so history is
kept from the day the capture-enabled game servers are deployed.

## Monster catalog and portraits

```bash
python -I tools/import-monsters/import_monsters.py \
  --sheet "DQM_J3Professional Master's guide IT V1.0 by StrangeServer & Yggdrasil.zip" \
  --kindparam romfs/data/Parameter/KindParam.tp \
  --translation ../DQMJ3P-IT-FanTranslation \
  --french fr/Message/MonsterKindMessage.mes --french-items fr/Message/ItemMessage.mes \
  --japanese-locations fr/Message/LocationMessage.mes
```

It matches every sheet row to game species ids by name and max stats (never by row order) and writes
`server/dashboard/data/monsters.json` (names in it/en/fr/ja, rank, family, size, stats, locations, items),
`web/public/monsters/s####.webp` and `tools/import-monsters/report.md` (match evidence, the rows it could
not match). Large monsters keep their 2–4 stacked tiles, as in the game's party list.

**Portraits are not committed** (`web/.gitignore`): they are game artwork collected by the guide's authors.
Until their redistribution is cleared, GitHub Pages shows a neutral placeholder for every monster and
the catalog still works with names. To publish them, remove the ignore rule and commit the `.webp`
files (about 4 MB).

## Maintenance (SSH)

```bash
cd /opt/dqmj3p/server
docker compose logs -f dashboard                       # import progress and errors
docker compose exec dashboard python -m dashboard import-once
docker compose exec dashboard python -m dashboard revise gp-grade-cal1-n2 "reason"   # new revision if standings changed
docker compose exec dashboard python -m dashboard rename-alias p0123456789ab "Old" "New"
docker compose exec dashboard python -m dashboard hide-player p0123456789ab          # removal request
```

Final standings are revision 1 at closing; corrections add revisions and never rewrite earlier ones.
If SIL's database is restored from an older backup, the importer notices (fingerprint of the row at its
cursor), marks the entries the source no longer has as `source_lost` (kept, out of the standings) and
adds a `source_reconciled` revision to the final editions that change.

`/api/v1/status` is the public summary (import freshness, editions waiting for finalization). An import
lag above 10 minutes marks it *degraded*; internal errors stay in the logs and in
`dashboard.import_checkpoints`.

## Backups, restore and rollback

- Back up as before: PostgreSQL (now also `history` and `dashboard`), `server/data` (SIL SQLite) and `.env`.
  `history` is the only copy of G-Cup attempts and full finals; `dashboard` can be rebuilt.
- Rebuild the portal tables from the sources: stop `dashboard`, `DROP SCHEMA dashboard CASCADE`, run
  `docker compose up -d dashboard-migrate dashboard`. Ids and links stay the same (salt + source ids);
  revisions of corrections are lost, revision 1 is recomputed.
- Rolling back the portal only: `docker tag server-dashboard:previous server-dashboard:latest` and
  `docker compose up -d --no-build dashboard`, or remove `portal` from `COMPOSE_PROFILES`.
- Rolling the **game servers** back to a build without capture leaves a gap in the history; keep a
  capture-enabled build as the rollback baseline.

## Local development

```bash
docker run -d --rm --name portal-pg -p 127.0.0.1:54339:5432 -e POSTGRES_USER=dqmj3p -e POSTGRES_PASSWORD=dqmj3p postgres:16-alpine
cd server/dashboard && python -m pip install -r requirements-dev.txt
DASHBOARD_TEST_DB=postgresql://dqmj3p:dqmj3p@127.0.0.1:54339/dqmj3p python -m pytest -q tests
DASHBOARD_TEST_DB=postgresql://dqmj3p:dqmj3p@127.0.0.1:54339/dqmj3p python tests/demo_data.py /tmp/portal-demo   # synthetic players
DASHBOARD_DB_URL=postgresql://dqmj3p:dqmj3p@127.0.0.1:54339/dqmj3p DASHBOARD_SIL_DB=/tmp/portal-demo/sil.sqlite3 \
  DASHBOARD_SIL_CODE=../sil/sil_server.py DASHBOARD_IMPORT=0 python -m dashboard serve --port 8090
cd ../../web && npm ci && VITE_BASE=/ npm run dev        # http://localhost:5173, /api proxied to :8090
```

## Known limits

- Direct Wi-Fi battles are not recorded (P2P; the server never receives an outcome).
- GP round outcomes: only wins are decoded; other rounds show "not won", never "lost".
- The GP round checksum check follows the reverse engineering and is reported, not enforced, until it is
  confirmed on real uploads (`/status`).
- SIL and G-Cup profiles are separate: there is no proven link between a friend code and a NEX PID.
- Not built yet: rival comparison, share cards, communities pages, weekly recap,
  website-organized events.
