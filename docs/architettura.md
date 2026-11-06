# Server architecture

The game used three separate online services. This stack replaces all of them and runs on a single VPS
with Docker Compose ([server/docker-compose.yml](../server/docker-compose.yml)).

```text
                    Friends login (unique player ID)
  3DS / Azahar  ─────────────────────────────────────────────▶  Pretendo Network
       │
       │  code.ips patch: all other addresses point to the VPS
       ▼
  ┌──────────────────────────── VPS ─────────────────────────────┐
  │  nex       UDP 45000-45001   Battles, communities, G-Cup       │
  │            TCP 45080         Replay uploads and downloads     │──▶ postgres
  │  sil       TCP 8381          Grand Prix, present codes        │──▶ SQLite in DATA_DIR
  │  spotpass  TCP 8380          Gift discs, shop, events          │
  │  nncs      UDP 10025, 10125, 33334-33335 (two IPs)  NAT check │
  └──────────────────────────────────────────────────────────────┘
       ▲
       │  Battles: game data sent directly between consoles (Pia, P2P)
  Other console
```

## Services

| Service | Code | Ports | Purpose |
|---|---|---|---|
| `nex` | Go, [server/nex](../server/nex) | 45000/udp (authentication), 45001/udp (secure), 45080/tcp (HTTP DataStore) | Nintendo NEX 3.10.1 game server: login, battle matchmaking, communities, G-Cup rankings and replays |
| `postgres` | `postgres:16-alpine` image | Internal network only | `nex` data |
| `seed` | SQL in [server/nex/sql](../server/nex/sql) | None | Creates or updates official communities and the 12 G-Cup cups whenever the stack starts, then exits |
| `sil` | Python, [server/sil](../server/sil) | 8381/tcp | Replacement for Square Enix's SIL server: Grand Prix, present codes, wallpapers, save backup |
| `spotpass` | Python, [server/spotpass](../server/spotpass) | 8380/tcp | Serves original SpotPass (BOSS) files, encrypted as originally distributed by Nintendo |
| `nncs` | Python, [server/nncs](../server/nncs) | 10025/udp, 10125/udp, 33334-33335/udp | Nintendo NAT check, used by Pia before every battle |

## Why two IP addresses are needed

The NAT check (`nncs`) must respond from the same address and port as the request, from a different
port, and from **a different address** to determine the console's NAT type. The VPS therefore needs two
public IPv4 addresses configured on its network interface (`PUBLIC_IP` and `PUBLIC_IP2` in `.env`), and
`nncs` uses host networking instead of Docker networking. Provider-side 1:1 NAT is unsuitable: the service
must be able to bind to the public IP addresses.

The test VPS uses `188.245.46.173` (primary) and `78.47.138.100` (floating IP).

## Connection flow

1. **Friends login.** The console signs into Pretendo with its account. The game retrieves the player ID
   (PID) and friends password.
2. **NEX login without NASC.** The original game asked Nintendo (NASC) for the server address and a
   token. The patch skips that request and uses `IP:45000` directly. The NEX password is derived from the
   friends password, which never leaves the console: the server records the derived value on each PID's
   first login (`accounts.passwords`) and checks it on subsequent logins.
3. **Battles.** `nex` handles matchmaking only: it finds an opponent and gives each console the other's
   address. Battle data travels directly between consoles using Pia. There is no relay.
4. **SIL.** Grand Prix and present codes use HTTP through the `sil` server. The player token is the same
   derived value as in step 2, bound to the player's SIL friend code.
5. **SpotPass.** The console's BOSS module downloads files from `spotpass` when the game opens the
   Wi-Fi Plaza.

## Data

| Location | Contents |
|---|---|
| `pg` volume (Postgres) | Player NEX passwords, sessions and communities (`matchmaking.*`), G-Cup rankings and results (`ranking.*`), replay metadata |
| `datastore` volume | G-Cup replay files |
| `DATA_DIR` (`server/data`) | `sil.sqlite3` (users, Grand Prix results and teams, redeemed present codes) and public Grand Prix files in `public/` |
| `SPOTPASS_DIR` | Original SpotPass files (`re/data/spotpass_archive/canonical`, not included in the repository) |
| `.env` | Addresses and internal passwords (`POSTGRES_PASSWORD`, `KERBEROS_PASSWORD`), never committed to git |

## Scheduled work

- **G-Cup week** ([gcup_week.go](../server/nex/nex/gcup_week.go)): every minute, `nex` checks the current
  week (counted from Monday, 2015-01-05, with 12 rotating cups). At rollover, it saves results, resets the
  incoming cup, deletes old replays, and publishes the podium in the news. Each cup's course, event,
  opponents, and rewards are defined in [gcup_official_communities.sql](../server/nex/sql/gcup_official_communities.sql).
- **Grand Prix schedule**: `sil` calculates it on every request (7-day tournaments, with the day changing
  according to `GP_UTC_OFFSET`). Challenger rules rotate through 8 sets, one per tournament.
- **Featured communities**: for each empty-list request, `nex` returns all communities eligible for display
  ([featured.go](../server/nex/nex/matchmake_extension/featured.go)).

## Server-side game fixes

- **Random password flags** ([password_flags.go](../server/nex/nex/matchmake_extension/password_flags.go)):
  the game sends uninitialized session password flags, making the session invisible to opponents.
  The server clears them.
- **Friend Battle**: the game creates a friends-only session (policy 98), which the NEX library would
  check against Pretendo's friends server, to which we have no access. The server assigns the random-battle
  policy instead. The friend must still search for the host's exact PID, taken from the console's friends
  list.
- **Communities**: `JoinCommunity` and `UpdateCommunity` are missing from the common library and are
  implemented in [community.go](../server/nex/nex/matchmake_extension/community.go). Every gathering has a
  `started_time`; without it, leaving a community caused error 006-0102.
- **Azahar replays**: Azahar sends upload chunks in the wrong order. The Azahar patch sends them as one
  chunk, and the server reorders previously uploaded data.

## Security

- Key-only SSH login, fail2ban monitoring the SSH log, automatic security updates.
- Provider firewall allowing only the ports in the table and port 22. Docker-published ports bypass the
  server's iptables rules, so filtering must happen upstream.
- Each container has memory and process limits. Docker logs rotate (10 MB × 3).
- `sil` rejects requests larger than 512 KiB. `sil` and `spotpass` accept at most 64 concurrent connections
  and close clients idle for 15 seconds. DataStore HTTP has read and write timeouts.
- Replay uploads use a random token per version, given only to the client that prepared the upload.

Known limitations:
- Player tokens travel in plaintext over HTTP to `sil` and using a fixed key over PRUDP.
- The first client to claim an unowned PID or friend code takes ownership.
- Large DDoS attacks can only be mitigated by the provider's network protection.
