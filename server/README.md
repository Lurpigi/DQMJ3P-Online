# DQMJ3P Online server

Statistics portal: [operations](../docs/dashboard.md). Backend in
`dashboard/` (Compose profile `portal`, HTTPS through `caddy/`), frontend in `../web/` on GitHub Pages.

| Directory | Contents | Status |
|---|---|---|
| `nex/` | NEX game server (Go, nex-go v2) – Wi-Fi battles, communities, Grand Prix, Ranking Race | MVP matchmaking working locally |
| `tests/` | Tests using a mock NEX client (NintendoClients) | `smoke_nex.py` passes |
| `dashboard/` | Statistics portal: importer + public read-only API (Python, FastAPI) | tests on PostgreSQL + SQLite |
| `caddy/` | HTTPS reverse proxy of the portal API | |
| `docker-compose.dev.yml` | Postgres for local testing | |

The NEX server is based on Pretendo's [animal-crossing-new-leaf](https://github.com/PretendoNetwork/animal-crossing-new-leaf) template (AGPL-3.0, see `nex/LICENSE`), which uses the same NEX version, 3.10.1.

## Game parameters (verified in Ghidra)

| Parameter | Value | Location |
|---|---|---|
| Title ID | `00040000001ACB00` | exheader |
| Game server ID (NASC `gameid`) | `0x001ACB00` | `NexLoginJob_Start` 0x66c4ec |
| PRUDP access key | `5812c478` | UTF-16 string at 0x66c688 |
| NEX version | 3.10.1 (PRUDP v0, structure headers enabled) | `NEX_3_10_1` string |
| SVCLOC keyhash (Square Enix token) | `994cba6f`, svc `0000` | `silAuthRequestAuthToken` 0x74041c |

## Local testing (DEV mode)

Prerequisites: Go (`~/tools/go`), Docker, NintendoClients virtual environment (`~/tools/nc-venv`).

```bash
docker compose -f docker-compose.dev.yml -p dqmj3p up -d   # Postgres on 127.0.0.1:54329
cd nex && cp .env.example .env && go build -o build/dqmj3p-nex.exe . && ./build/dqmj3p-nex.exe
# In another terminal
~/tools/nc-venv/Scripts/python tests/smoke_nex.py         # Two clients: create / browse / join a session
```

In DEV mode (with `PN_DQMJ3P_DEV_PASSWORD` set), every PID uses the same NEX password and the simple `Login` method is enabled. **Never use this in production.** Use `tests/auth_nex.py` to test login without DEV mode.

Notes:
- On Windows, UDP ports 59435–63044 are reserved by Hyper-V: DEV mode uses 45000/45001.
- NintendoClients 5.0 only serializes `MatchmakeSessionSearchCriteria` up to the NEX 3.5 fields: the test adds the 3.6–3.8 fields.
- With `PN_DQMJ3P_DEBUG_RMC=1`, the server logs the protocol, method, and parameters of every call to help identify what a real console sends.

## Internet test stack (VPS)

`docker-compose.yml` starts NEX, Postgres, SIL, SpotPass, and NAT checking on one server. It is intended for testing the game over the internet, **not yet for a public launch** (see section 4 of [PLAN.md](../PLAN.md)).

### Player passwords

Without `PN_DQMJ3P_DEV_PASSWORD`, the server uses a separate password for each player. With `--nex-player-password`, the patch computes `MD5(salt + friends password)`, keeps the first 16 hexadecimal characters, and sends them as the `LoginEx` token. The Pretendo friends password never leaves the console. A PID's first login stores the value in `accounts.passwords`; subsequent logins must match.

The same value is used for the SIL token. The SIL server stores its SHA-256 hash per friend code: the first `nuser/register` or `nuser/login` binds it, and subsequent logins must match. Another `nuser/register` with the same value returns the previously assigned friend code.

DataStore upload URLs contain a random token, valid for one version until `Complete`, which is only given to the client that prepared the upload.

To test patches without `--nex-player-password` locally: `sil_server.py --dev-tokens`.

Known limitations:
- The token is sent on every login, in plaintext over HTTP to SIL and using a fixed key over PRUDP, so anyone intercepting the traffic can read it.
- The first client to claim an unowned PID or friend code takes ownership.
- Players who change their friends password or account cannot log into NEX until their row is deleted:

  ```bash
  docker compose exec postgres psql -U dqmj3p -d dqmj3p -c "DELETE FROM accounts.passwords WHERE pid = PID"
  ```

### Setup

You need a Linux server with Docker and **two public IPv4 addresses configured on its network interface**. Providers using 1:1 NAT (such as AWS and Google Cloud) are unsuitable because the NAT check service cannot bind to the public IP addresses.

1. Clone the repository and create the configuration:

   ```bash
   cd server && cp .env.example .env
   ```

   Fill in `.env` as described in its comments. Use IP addresses: the patch accepts at most 15 bytes for the NEX host.

2. Copy the data not included in the repository from your PC, then make it writable by the containers:

   ```bash
   scp -r server/data/public server/data/private_templates root@IP:DQMJ3P-Online/server/data/
   scp -r re/data/spotpass_archive/canonical root@IP:DQMJ3P-Online/re/data/spotpass_archive/
   chown -R 1000:1000 server/data
   ```

3. Open firewall ports `45000-45001/udp`, `10025/udp`, `10125/udp`, `33334-33335/udp`, `8380-8381/tcp`, and `45080/tcp`.

   Use the provider's firewall (Cloud Firewall on Hetzner), allowing only SSH and these ports: Docker-published ports bypass the server's iptables rules. Key-only SSH access and fail2ban are recommended.

4. Start the stack:

   ```bash
   docker compose up -d --build
   ```

   The `seed` service loads the official communities and then exits: this is expected.

5. Generate the patch on your PC using the same values as in `.env`:

   ```bash
   python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://IP:8381/00300701/ --spotpass-url http://IP:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --nex-auth IP:45000 --nex-player-password --nncs IP,IP2 --azahar --merge BASE_CODE_IPS -o code.ips
   ```

   For a real 3DS, omit `--azahar` and use the translation's regular `exefs/code.ips` with `--merge`: `code_enhanced.ips` is emulator-only and crashes the game at startup on a console. `--spotpass-break` downloads BREAK events on Azahar but adds about 22 seconds to each connection.

Data persists in the `pg` and `datastore` Docker volumes and in the `DATA_DIR` directory. View logs with `docker compose logs -f nex`.

Subsequent updates are handled by the GitHub Action on every merge into `main`: see [docs/deploy.md](../docs/deploy.md).
For service details, see [docs/architettura.md](../docs/architettura.md). For patch options, see [docs/patch.md](../docs/patch.md).

No Pretendo server account is needed: with `--nex-auth`, the game skips NASC and connects directly to the NEX server.
