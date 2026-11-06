# DQMJ3P Online – Plan and status

Goal: restore the online features of *Dragon Quest Monsters: Joker 3 Professional* (3DS, JP, `00040000001ACB00`, v1.3) on consoles (Luma3DS) and emulators (Azahar PC/Android).

Last status update: 2026-11-04.

Statistics portal (2026-11-05): implemented, see [portal operations](docs/dashboard.md).
The game-service status below is unchanged.

---

## 1. Architecture

The game communicates with **three separate services**, all identified in v1.3's `code.bin` using Ghidra:

| # | Service | In-game purpose | Replacement | Status |
|---|---|---|---|---|
| A | **NEX** (Nintendo, NEX 3.10.1 + Pia) | Friend and random Wi-Fi battles, communities, Ranking Race (rankings + replays) | Go game server using the Pretendo stack → [server/nex](server/nex) | On the VPS: battles, communities, and G-Cup verified in-game |
| B | **SpotPass / BOSS** (Nintendo) | Hidden boxes, StreetPass and sky map monsters, gift discs, WiFi Shop table | Archived original files, served unchanged → [server/spotpass](server/spotpass) | Gift discs, coin shop, and hidden box (BREAK01) verified |
| C | **SIL** (Square Enix, proprietary HTTPS) | **Ranking Battle / Grand Prix**, present codes, wallpapers, corrupted-save backup | Python server → [server/sil](server/sil) + in-game URL patch | Complete Grand Prix (schedule, opponents, rankings, rewards) and present codes |

The original login to C goes through Nintendo: the game requests a *service token* from NASC (`SVCLOC`, keyhash `994cba6f`), which Pretendo already issues.

### Verified parameters

| Parameter | Value |
|---|---|
| Game server ID | `0x001ACB00` |
| NEX access key | `5812c478` (not `994cba6f`, which is the SVCLOC keyhash) |
| PRUDP | v0, structure headers enabled |
| BOSS app ID | `H7btVjYWs7p5dGj6` (tasks `BREAK01-03`, `FGONLYT`) |
| SIL | `https://dqm32ds.sil2.square-enix.com/00300701/`, title code `00200605`, MD5 digest key `3Ef7Db65775e4cCF` |

Guides and documentation: [README.md](README.md), [docs/architettura.md](docs/architettura.md) (services, ports, data),
[docs/patch.md](docs/patch.md) (each game modification and its address), [docs/deploy.md](docs/deploy.md) (GitHub Action).

Details and addresses in [re/notes](re/notes) (currently in Italian):

- [nex_usage.md](re/notes/nex_usage.md)
- [sil_protocol.md](re/notes/sil_protocol.md)
- [spotpass_boss.md](re/notes/spotpass_boss.md)
- [pretendo_research.md](re/notes/pretendo_research.md)

---

## 2. How traffic reaches our servers

| Service | 3DS (Luma) | Azahar |
|---|---|---|
| Friends login | **Nimbus** with a Pretendo account | Same, with Nimbus + LLE modules (Pretendo's Azahar guide) |
| NEX, SpotPass, NAT check, SIL | Game patch (`luma/titles/00040000001ACB00/code.ips`, merged with the translation patch) | Same patch in `load/mods/00040000001ACB00/exefs/code.ips` |

**Chosen approach (2026-10-30): self-hosting.** Pretendo has no channel for adding titles and appears to prefer managing games itself, so we are not requesting integration. The servers run on our own VPS, and the patch connects the game directly: `--skip-nasc --nex-auth IP:PORT` removes the need for NASC, so we do not need to host one. Pretendo is used only for friends login, which provides a unique PID.

If Pretendo becomes unusable, the fallback is `--skip-frd` without Nimbus. This needs independent testing, unique PIDs still need a solution, and Friend Battle would be unavailable.

---

## 3. Completed

- [x] Ghidra 12.2 + JDK 25 + `pyghidra-mcp` MCP server (local configuration, outside git) + local query server (`re/tools/ghidra_server.py`, `gq.py`).
- [x] `code.bin` → ELF (`re/tools/codebin_to_elf.py`), project analyzed and annotated (`sil_`, `boss_`, `nex_` prefixes).
- [x] NEX parameters, protocols and methods used by the game, matchmaking flows (friends: gameMode 5, attribs[0] = host ID; random: gameMode 2/3, attribs[0] = strength).
- [x] NEX server (`server/nex`, based on the ACNL template): login, `SecureConnection`, NAT traversal, matchmaking. `tests/smoke_nex.py` reproduces **friend battles** (Create → Browse → JoinEx → GetSessionURLs) and **random battles** (AutoMatchmake → same session).
- [x] SpotPass: original files from the `3ds-boss-data` archive, static server, `BSDT` codec with HMAC (`re/tools/bsdt.py`) for creating new content.
- [x] SIL: complete specification, replacement server (`server/sil`), end-to-end test (`tests/test_sil.py`).
- [x] URL patch with Italian translation merging (`re/tools/make_url_patch.py`).

## 3b. Progress log starting 2026-10-26 (Azahar testing)

Quoted Italian messages below refer to the translation used during testing.

- Ranking Battle through SIL **works up to the menu**: Wi-Fi Plaza in **offline** mode → golden Slime tower → "Grado Battaglia Wi-Fi" (Wi-Fi battle rank). Real friends login through Nimbus/Pretendo, followed by SIL registration/login and downloads of all public tables from our server.
- Patch used (`load/mods/00040000001ACB00/exefs/code.ips`, translation-only backup in `code.ips.bak-20261026`):
  `python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://127.0.0.1:8381/00300701/ --spotpass-url http://127.0.0.1:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --azahar --merge <mods>/exefs/code.ips.bak-20261026 -o <mods>/exefs/code.ips`
  - `--skip-nasc`: skips NEX login, the NASC token (Pretendo does not have the game → 002-0110), and the Ranking Battle screen's "NEX connected" check. NEX features (battles, communities, G-Cup) return 006-0000.
  - `--azahar`: works around Azahar's http:C bugs (empty POST never sent, header size = 1, POST chunks sorted by content).
- Server: `cd server && python -I -u sil/sil_server.py --host 0.0.0.0 --port 8381 --data data >> data/sil_server.log 2>&1`. Requires `data/public/030_GP_WallPapers.arc`, a copy of `romfs:/data/Layout/menu/wifi_ranking_battle/upper/download.arc`.
- **Masters GP played end-to-end** (evening of 2026-10-26): registration with `00_UserData.bin` → download `147_Grade_Def_DLBattle.bin` (CPU1-3 placeholder opponents) → upload `09_Grade_PrivateDlBattle.bin` → 3 automatic rounds → upload `GradeResultPack.bin` (stored in `gp_results`, score 1694), `04_UpdateSaveData.bin`, exchange `171_/28W_Grade_Other_Countries.bin`. All successful.
  - Fixed `azahar_unsort`: a detached payload may immediately follow a complete record (e.g. `PrivateSCRegister.bin`, Data = "Download_Code" at the end of the body); it now tries every record as "detached".
- **Real opponents** (2026-10-26): the server builds `09/18_*_PrivateDlBattle` from other players' latest teams (`gp_results`), ordered hard/similar/easy; rounds without teams retain the CPUs from `Def_DLBattle`. Team block header decoded (location/flag, name, beginner, Mii: see `re/notes/grandprix_formats.md` 3.8). Verified in-game with `--self-opponents` (own team as opponent, useful with only one player): "JEJ"/ITA in round 1, monsters loaded and battle played normally. Test: `server/tests/test_sil.py`.
- **Rankings** (2026-10-26): from `gp_results`, the server generates the schedule (`003_Held_Record`: 7-day tournaments starting at `--gp-start`), `089/139_*_Ranking_Pack` (overall through yesterday with arrows, previous tournament final, by prefecture), `23_UserPackData` (rank, points, personal ranking, previous tournament), and `141/142_*_ChampionRecord`. Verified in-game with `--gp-today 2026-10-27`: today's rankings available, JEJ 1st ITA 3/0 1694 in personal and overall rankings. `PrivateSCRegister.bin` now works. Formats in `re/notes/grandprix_formats.md` 3.6/3.7/3.9.
- **Challenger GP** (2026-10-26): `018_LimitSetting` rules decoded (size, family, rank class, team grade) and configurable with `gp_files.py --limit-rule TYPE:VALUE --limit-text --limit-theme --only 018_LimitSetting.bin`. In-game: theme displayed, rule 5:1 rejects the team, 4:8 accepts it; registration, 3 rounds, and `LimitResultPack` upload (1866 points) successful; Challenger rankings and user data generated (verified offline). Active server rule: 4:8.
- **Tournament end** (simulated with `--gp-today 2026-11-02`): first-tournament completion announcement, top 10, champion no. 1, ticket refill, and Champions menu verified in-game. Fixed `ChampionRecord`: entries start at +0 (the counter is inside entry 0).
- **End-of-tournament rewards** (verified in-game on 2026-10-26, simulated dates 2026-11-02, 2026-11-09, 2026-11-16):
  - *Special gift* (`23_UserPackData`+0xfc u16 type 1, +0xfe item ID = `I%04d` key in `ItemMessage.mes`): SQEX special gift message, awarding "Grande Sfera di Luce", once per tournament. Server: `--gp-prize-champion ITEM` (default 70, "Grande Sfera di Luce"), `--gp-prize-top10 ITEM` (default 66, "Sfera di Luce").
  - *Network coins* (previous tournament block +0x1098: +0x44 u16 = 3, +0x48 platinum, +0x4a gold, +0x4c silver, +0x4e bronze): reward message awarding 3 gold coins. Server: `--gp-coins-champion B,S,G,P` (default 0,0,3,0), `--gp-coins-top10` (default 0,3,0,0).
- **Rotating Challenger rules** (2026-10-26): the server generates `018_LimitSetting` and `033_Limit_DLNewsMsg` from the tournament number, cycling through 8 sets (`LIMIT_RULE_SETS` in `sil_server.py`: unrestricted, Slime, grade<=4, small size, Dragon, grade<=6, Demon, SS rank). Challenger opponents come only from the current tournament. Verified in-game (tournament 4: small monsters only, displayed with Y). Use `--gp-limit-static` for a fixed file.
  - The test save is now at tournament 4 (2026-11-16): the server runs with `--gp-today 2026-11-16`; returning to the real date resets the GP.
- **SpotPass: gift discs and coin shop** (verified in-game 2026-10-28): Azahar uses the real `boss` module (online LLE modules), downloading from our `server/spotpass/serve_spotpass.py` (port 8380, original files) through `--spotpass-url`. Gift-disc receipt ("Disco Conclavio sacro") and inventory update messages appear with the original stock. The game's AC connection is required: `--skip-nasc` now bypasses the Plaza connection screen (0x5e) even when NEX login fails, forcing "NEX connected" only for gifts and the shop (details in `re/notes/spotpass_boss.md` 6). Server: `python -I -u server/spotpass/serve_spotpass.py re/data/spotpass_archive/canonical 8380 0.0.0.0`.
  - Patch URLs use `127.0.0.1`: the PC's LAN IP changes (.189 -> .190). For a real console, use the PC's IP address.
- **Present codes** (verified in-game 2026-10-28): code `SLIME` awards the golden Slime disc ("Disco Slime dorato"). Codes are stored in the `present_codes` table in `server/data/sil.sqlite3` (`code`, `package_id`, `single_use`); packages are `data/public/PresentCodePackageS%02u.bin` (`gp_files.make_present_package`). The game's keyboard only has letters: no digits in codes.
  - **Original codes** (2026-11-02): `server/sil/present_codes.json` (from `re/tools/make_present_codes.py`) contains the 130 DQMJ3 and DQMJ3P codes (game table + Game8 list), with a letters-only alias per gift (e.g. `SEEDOFLIFE`, `GOLDSLIMEDISC`). Active on the VPS, SIL test passed, not yet tested in-game. Details and Plaza discs in `re/notes/present_codes.md`.
- **GP refinements** (2026-10-28): up/down arrows verified in-game using a test data copy (`server/data_test`, ignored by git) and two mock players: on day 3, Slimerex 1 up, JEJ 2 up, Draghetto 3 down. `147/148_*_Def_DLBattle` regenerated in hard/similar/easy order (`gp_files.py server/data/public --only ...`).
- **Real NEX login without NASC** (verified on Azahar 2026-10-28): `make_url_patch.py --nex-auth 127.0.0.1:45000 --nex-password <PN_DQMJ3P_DEV_PASSWORD>` (with `--skip-nasc`, which then no longer simulates `NexLoginJob_Start`) + `server/nex` in DEV mode (`LoginEx` accepts any token). The game performs LoginEx -> RequestTicket -> Register on our server with the real Pretendo PID. Start with `docker compose -f server/docker-compose.dev.yml -p dqmj3p up -d` (Postgres 127.0.0.1:54329), then `server/nex/build/dqmj3p-nex.exe` (ports 45000/45001).
- **G-Cup (Ranking Race) through registration** (2026-10-28): 12 official G-Cup communities (`server/nex/sql/gcup_official_communities.sql`) and the Ranking protocol on Postgres (`server/nex/nex/ranking.go`). In-game: cup search, registration (team name), weekly cup "Campo Prati Silenziosi", race entry menu. Details in `re/notes/nex_usage.md` 3.9.
- **G-Cup: race, score, and ranking** (2026-10-28): official communities' application buffer defines the tournament (CPU opponents, name, strength, course, event); zeroed opponents caused the race to crash. Races now start with 4 racers, the winning time is uploaded (`UploadScore` in frames at 30 fps), and the live ranking displays it. DataStore 115 (`server/nex/nex/datastore.go`: metadata in Postgres, files over local HTTP) handles replays; upload, download, and playback (only for a new top-3 record) verified in-game.
- **Communities (Community Challenge)** (verified on Azahar 2026-10-28): creation, current community with code, official communities (`server/nex/sql/official_communities.sql`, attribs[0] = 1), and joining work. Original featured communities come through StreetPass (since 2026-11-04 the server displays all of them, see below). Opponent search stalled after `ReportNATProperties` due to the same issue as Wi-Fi battles (see below). Details in `re/notes/nex_usage.md` 3.8.
- **Wi-Fi battles: opponent search as host** (verified on Azahar 2026-10-29): NAT check server `server/nncs/nncs_server.py` (port of PretendoNetwork/nncs) on 127.0.0.1/127.0.0.2 and patch `make_url_patch.py --nncs 127.0.0.1,127.0.0.2`. Free Battle creates the gathering with `AutoMatchmakeWithSearchCriteria_Postpone`, opens it for 30 seconds, then reports no opponents found. The error without a code was caused by Azahar: with NordVPN active, `gethostid` returns 0, the NEX URL has no `address=`, and Pia rejects it (`0xD8A148C1`). It works without the VPN. Error 006-0105 appeared once after `ReplaceURL`, not reproduced. Details in `re/notes/nex_usage.md` 6.
- **Wi-Fi battle between two players** (verified 2026-10-29): two Azahar instances on the same PC find each other in Free Battle (prompt to challenge Lurpigi), then play a battle with synchronized turns through completion (win/loss, save, return to menu; only `SendReport` + `EndParticipation` reach the server). The second instance is a portable copy with `--skip-frd --pid-offset 1` (Pretendo does not accept two friends sessions for the same account). Details in `re/notes/nex_usage.md` 6.
- **Ranked Battle between two players** (verified 2026-10-29): same matchmaking as Free Battle (gameMode 3), battle with judge points, winner gains +10P ("Nuovo Arrivato" -> "Esploratore Apprendista"), loser unchanged. Rank and points remain in the save: no NEX or SIL upload. Server fix: the game sends random session password flags, which made the session invisible to opponents (`server/nex/nex/matchmake_extension/password_flags.go`).
- **Community Challenge between two players** (verified in-game 2026-10-29): everything works. Friend Battle cannot yet be verified: it requires two accounts registered as friends on Pretendo's 3DS friends server.
- **SpotPass: BREAK01-03 field events** (2026-10-29): with `make_url_patch.py --spotpass-break`, connecting to the Plaza downloads all three files from our server (`BREAK01/BossStealthBox.bin`, `BREAK03/BossSkyMapMonster.bin`, `BREAK02/BossPassingMonster.bin`, all HTTP 200). BREAK01's hidden box verified in-game: it appears in the Plaza and awards "Super Seme dell'Agi" when opened. The sky map monster (BREAK03) and StreetPass assassin (BREAK02) still need verification. Periodic tasks fail on Azahar (the BOSS module requests the unimplemented `ac:u GetConnectingLocation`), so the patch downloads them as foreground "FGONLYT" tasks. Details in `re/notes/spotpass_boss.md` 6.
- **Next step:** see section 4 (verify BREAK03/02, then production).

## 4. To do

Updated 2026-10-29: on Azahar with local servers, Wi-Fi battles (free and ranked), communities, G-Cup with
replays, Grand Prix through SIL, present codes, and SpotPass (gifts, shop, BREAK01) work. The main remaining work is production.

### Phase A – In-game verification

- [ ] SpotPass BREAK03 (sky map monster) and BREAK02 (StreetPass assassin): files downloaded, not yet seen in-game.
- [ ] Friend Battle in-game: the two Pretendo accounts must be friends.
- [ ] Corrupted-save backup through SIL: supported by the protocol, never tested in-game.
- [ ] Pia notifications (events 4000-4999) need runtime checks (battles work regardless).
- [ ] Decode community rules (0x18 bytes at buffer +0x60) for official communities with different rules.
- [ ] SpotPass with new content: not planned. The server serves original files (shop: 7 inventories, one
  per day of the week in Japan, decoded in `re/notes/spotpass_boss.md`).

### Phase B – Production

- [x] Test stack on the Hetzner VPS (2026-10-31): running on `188.245.46.173` and `78.47.138.100`. External `smoke_nex.py`, SpotPass, and nncs checks pass; everything restarts after a server reboot. Ports 33334-33335/udp not tested.
- [x] Game connecting to the VPS for the first time (2026-10-31): from the Wi-Fi Plaza entry menu on Azahar with the enhanced translation, NEX login with the real PID and downloads of the three BREAK files (HTTP 200) from the VPS. `BREAK_CAVE` moved to `0x6B9900` because it overlapped `code_enhanced.ips`. The game stays on the save confirmation ("Gioco Salvato!") for about 30 seconds before connecting.
- [x] SIL in-game on the VPS (2026-10-31): login, rankings, and user data copied from the local database. `nuser/getnonce` adopts unknown friend codes, but a user without `00_UserData.bin` is not registered in the Grand Prix, and the game reports that the data is no longer available.
- [ ] Before distribution: determine what players see when using a save registered elsewhere, with no data on the server.
- [ ] Before distribution: the BREAK routine must download only missing files (`GetNsDataIdList`). Downloading them again costs 22 seconds per connection without updating anything, so the active Azahar patch does not include `--spotpass-break`.
- [ ] Still missing on the VPS: seeing BREAK objects in-game.
- [x] Communities on the VPS (2026-11-04): one official community per language (Italian, English, Spanish, French, Japanese, with text in
  the corresponding language), and featured communities displaying all communities (official and player-created, maximum 100). The patch with
  `--nex-auth` sends an empty request (`0x5b5878`: `bl FUN_0023d168` -> `nop`), because a single saved ID is indistinguishable from
  a code search. Verified on Azahar; 3DS patch prepared.
- [x] Rotating G-Cup (2026-11-03): course, event, and opponents change every week; cup 6 verified in-game.
- [x] VPS security (2026-11-04): key-only SSH, fail2ban, updates, Hetzner Cloud Firewall allowing only game ports.
  Services: SIL's 512 KiB limit, maximum 64 connections and timeouts for SIL and SpotPass, DataStore timeouts,
  memory and process limits for every container. Details in `docs/architettura.md`.
- [ ] Automated deployment (2026-11-04): `.github/workflows/deploy.yml` tests and updates the VPS on every push to `main`. Still needed:
  the deployment key on the VPS, GitHub secrets, and `main` protection (`docs/deploy.md`).
- [x] Real 3DS battle against Azahar through the VPS (2026-11-01): login with different PIDs, in-game nncs (types 101-103), and session 14 completed. Same home network: both devices shared a public IP.
- [ ] Battle between two different networks: never tested. Pia battles are P2P with no relay, so behavior with CGNAT and symmetric NAT needs verification.
- [x] Per-player passwords (2026-10-31): `accounts.passwords` and `make_url_patch.py --nex-player-password` (password derived from the friends password using MD5, recorded on first login). Verified on the VPS with `tests/auth_nex.py` and in-game on Azahar. Details and limitations in `server/README.md`.
- [ ] G-Cup tournament end: cups with flag 513, rewards by placement, and news in the buffer (`gcup_official_communities.sql`, map in `re/notes/nex_usage.md` 3.9), applied on the VPS on 2026-11-01. First cup rollover tested on Azahar on 2026-11-02 (after fixing `started_time`): leaving cup 5, entering cup 6, gold coins for 1st place (`+0x97` = gold). Still to verify: podium news, rollover on 3DS, and reward tiers from 2nd place onward.
- [ ] G-Cup week in the NEX server (`nex/gcup_week.go`, 2026-11-01): every minute, checks the week, saves results in `ranking.gcup_results`, resets old scores for the incoming cup, removes old replays, and writes the podium in the news. Tested on local Postgres; first real rollover still pending.
- [ ] Grand Prix news: `032_Grade_DLNewsMsg.bin` is fixed English text; winners can be generated in `sil_server.py` without a job, as with `033`.
- [x] SIL security (2026-10-31): friend code bound to the SHA-256 hash of the player token (`users.secret`), token in the patch through `--nex-player-password`. Verified with `tests/test_sil.py` and in-game on Azahar.
- [ ] DataStore: upload URLs with a random token per version. Verified by `tests/smoke_nex.py`; a real in-game race uploading a replay is still needed.
- [x] Server-side Friend Battle (2026-11-04, on the VPS): the game creates a friends-only session (policy 98), which nobody could find without Pretendo's friends gRPC. The server assigns random-battle policy 95: the friend finds it by searching for the host's exact PID. `tests/smoke_nex.py` verifies this (fails without the change). In-game testing requires two Pretendo accounts registered as friends.
- [ ] Real 3DS testing, started 2026-11-01. Startup, NEX login with a per-player password, and battles work. Still to test: SIL, rankings, G-Cup and replays, communities, BREAK events in standby.
  - Console patch: without `--azahar` or `--spotpass-break`, using `--merge` with the regular `exefs/code.ips`. `code_enhanced.ips` is emulator-only and crashes the game at startup on 3DS.

### Phase C – Distribution

- [ ] Publish the source: `server/nex` and `server/nncs` derive from AGPL-3.0 code, so server users must be able to obtain it (the GitHub repository).
- [ ] Check Pretendo's rules on using accounts for friends login with a patch.
- [x] 3DS and Azahar player guide in the [README](README.md) (2026-11-04).
- [ ] Distribute ready-to-use patches for 3DS and Azahar, for each translation version.

---

## 5. Risks

- **Grand Prix:** depends on lost Square Enix data; reconstruction requires decoding undocumented formats.
- **Pretendo:** friends login depends on a service we do not control and which may change.
- **NAT:** without a relay, players behind CGNAT or symmetric NAT may be unable to battle.
- **Security:** player tokens travel in plaintext over HTTP to SIL; large DDoS attacks can only be mitigated by the provider's protection.
- **Legal:** distribute only servers, patches, and tools. Never ROMs, CIAs, or downloaded original files (`re/data`, excluded from git). Original SpotPass files served by our server remain the most sensitive issue.
