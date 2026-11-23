# DQMJ3P Online

Replacement servers and a game patch to restore the online features of *Dragon Quest Monsters: Joker 3 Professional*
(3DS, Japanese release `00040000001ACB00` v1.3, with or without a fan translation), on consoles running
Luma3DS and on Azahar.

The official Nintendo and Square Enix servers have shut down. This project provides replacement servers
and a game patch that connects to them.

# [Dashboard online](https://lurpigi.github.io/DQMJ3P-Online/#/en)

## What works

| Feature | Service | Status |
|---|---|---|
| Free Battle and Ranked Wi-Fi Battle | NEX | Verified between two Azahar instances and between 3DS and Azahar |
| Friend Battle | NEX | Server implementation ready; testing with two mutually registered friend accounts is still needed |
| Communities: creation, official communities by language, featured communities, Community Challenge | NEX | Verified |
| G-Cup (Ranking Race): weekly cups, rankings, replays, rewards | NEX | Verified |
| Grand Prix (Ranking Battle): Masters and Challenger, rankings, rewards | SIL | Verified |
| Present codes (all 130 original codes) | SIL | Verified on the server |
| Gift discs, Wi-Fi Plaza coin shop | SpotPass | Verified |
| Field events (hidden box, sky map monster, StreetPass assassin) | SpotPass | Only the hidden box has been verified |

See [PLAN.md](PLAN.md) for details.

## Player guide

### Accounts

Every player needs their own player ID. There are three kinds of account:

| | 3DS with Pretendo | Azahar with Pretendo | Azahar without Pretendo |
|---|---|---|---|
| Where the ID comes from | Pretendo friends login | Pretendo friends login | A personal account from the [portal](https://lurpigi.github.io/DQMJ3P-Online/#/en/play) |
| Patch | Release: `3ds/code.ips` | Release: `azahar-enhanced/code.ips` | Personal `code.ips` from the portal |
| You need | A Pretendo account, Nimbus | A Pretendo account, Azahar's online system modules (LLE) | Nothing else |
| Wi-Fi battles, communities, G-Cup, Grand Prix, present codes | Yes | Yes | Yes |
| Friend Battle | Yes | Yes | No (needs a friends list) |
| SpotPass (gift discs, coin shop, field events) | Yes | Yes | No (needs Azahar's LLE modules) |

- **With Pretendo**, the friends login gives every player a unique ID. The game uses no other Pretendo
  services.
- **Without Pretendo**, Azahar gives every player the same ID (0) and no password, so the server refuses
  them. The portal issues an ID instead: it writes the ID and a random secret into a personal `code.ips`.
  The secret is created in your browser and never reaches the server, which only stores a password
  derived from it.
- **The personal file is the account.** Whoever has it plays as you, so do not share it. Keep a copy: a lost
  file cannot be recovered.
- **The two kinds of account are separate.** Switching between Pretendo and a personal account does not
  carry over your online progress: NEX rankings and communities belong to the ID, and the Grand Prix
  account belongs to the password.

All players need version 1.3 of the game, with or without a translation. If you play a translation,
install it first.

**Which patch file:**
- **3DS with Pretendo** and **Azahar with Pretendo:** the
  [releases](https://github.com/Lurpigi/DQMJ3P-Online/releases) have a ready `code.ips` for each game
  language (no translation, Italian, English Fixed). Use the `3ds` folder on a console and the
  `azahar-enhanced` folder on Azahar. You can also build them yourself (see
  [Building the patch](#building-the-patch)).
- **Azahar without Pretendo:** the release files do not work, because they have no player ID. Use the
  personal patch from the portal. It is the release's `azahar-enhanced` patch for your language with
  your account added, so it has the same Azahar fixes and improvements, and it also needs New 3DS mode.

### On 3DS (Luma3DS)

1. Set up Pretendo with [Nimbus](https://pretendo.network/docs/install/3ds) and activate your Pretendo account.
2. Copy the release's `3ds/code.ips` to `SD:/luma/titles/00040000001ACB00/code.ips`, replacing the translation's `code.ips`
   (the online patch already contains it). Leave the translation's other files where they are.
3. In the Luma configuration menu (hold SELECT while powering on), enable **Enable game patching**.
4. Launch the game and enter the Wi-Fi Plaza.

Never use an Azahar patch on a real console: it can crash the game at startup.

### On Azahar with Pretendo

1. Set up Pretendo using the [Azahar guide](https://pretendo.network/docs/install/citra):
   you need the online system modules (LLE) and a Pretendo account.
2. Copy the release's `azahar-enhanced/code.ips` to `<Azahar user directory>/load/mods/00040000001ACB00/exefs/code.ips`
   (on Windows, the user directory is usually `%APPDATA%\Azahar`), replacing the translation's `code.ips`.
3. Turn on New 3DS mode (Emulation > Configure > System) and launch the game.

### On Azahar without Pretendo

1. Open the [Play online](https://lurpigi.github.io/DQMJ3P-Online/#/en/play) page of the portal.
2. Choose your game (Japanese or English Fixed v2.21, or the Italian translation) and press **Create the
   account and download code.ips**. Keep the file somewhere safe.
3. Copy it to `<Azahar user directory>/load/mods/00040000001ACB00/exefs/code.ips`, replacing any existing
   `code.ips`.
4. In Emulation > Configure > System, turn on New 3DS mode and turn off **Enable required LLE modules for
   online features**.
5. Launch the game and enter the Wi-Fi Plaza.

When a new patch version comes out, or you change translation, load your current personal `code.ips`
in the **Update your patch** section of the same page. It builds the new file with the same account,
in the browser, without sending anything.

The page allows a few accounts per connection per day. Server administrators can also issue accounts
by hand with `re/tools/azahar_identity.py` (see [re/notes/azahar_hle_identity.md](re/notes/azahar_hle_identity.md)).

### Troubleshooting

- **An error without a code, or a communication error during battles on Azahar:** a VPN (such as
  NordVPN) can prevent Azahar from reading the local address. Disable it.
- **The game stays on the save confirmation ("Gioco Salvato!" in Italian) for about 30 seconds before entering the Wi-Fi Plaza:** this is normal.
- **Battles do not start between different networks:** battles connect the consoles directly (P2P),
  with no relay server. Some networks (CGNAT, symmetric NAT) may not work.
- **NEX login rejected after changing Pretendo accounts:** the server binds each ID to the first password
  it receives. Ask the administrator to reset it.
- **Grand Prix: "Download failed" with a personal account on an old save:** a save that already played
  the Grand Prix with another account keeps that account's Grand Prix friend code, and the server refuses
  it. Ask the administrator to move it to your personal account.

### Grand Prix CPU teams

Grand Prix opponents are the teams other players used in their last battle, mixed with 20 CPU
teams. Their trainer names start with "CPU". Some are named after the 2017 official tournament
finalists whose teams they copy, such as "CPU Nikoroto". Others copy parties from a Japanese
strategy blog, such as "CPU WORLD". The rest have a theme, such as "CPU Draghi" and "CPU Piccoli".
In Challenger, only the CPU teams that meet the contest's rules take part. CPU teams never appear
in the standings. The list is in [server/sil/cpu_teams.json](server/sil/cpu_teams.json), with the
source of each team.

### Cheats and modified monsters

Play with monsters you raised in an unmodified game. Cheat codes, save editors and memory editors
are not allowed in online modes.

- **Grand Prix:** the server checks every team it receives. A team is rejected when a monster has a
  level above its cap (50, 75, 100 or 120), stats far beyond its species maximum, or a species that
  does not exist. The limits leave room for everything the game allows: seeds, levels above 100,
  equipment and items. A rejected result is kept but counts nowhere:
  - it gets no points in the standings, the rankings or the prizes;
  - other players never get its team as an opponent;
  - the portal shows it as rejected.

  The game has no message for this, so the upload looks normal on the console. Each rule change
  checks the older results again.
- **Wi-Fi battles:** battles connect the consoles directly, so the server never sees the teams and
  cannot check them.
- **G-Cup:** not checked yet.
- **Players who cheat on purpose** can be hidden from the portal or removed from the server. If you
  think a legitimate team was rejected, open an issue with the result's portal link.

## Server administration

- [Stack setup and usage](server/README.md): Docker Compose on a VPS with two IPv4 addresses.
- [Server architecture](docs/architettura.md): services, ports, addresses, and data.
- [Game patch](docs/patch.md): each modification, its address, and its purpose.
- [Automated deployment](docs/deploy.md): GitHub Actions, secrets, and `main` protection.
- [Statistics portal](docs/dashboard.md): public championship archive, player histories and monster catalog (API on the VPS, site on GitHub Pages).
- Reverse engineering notes in [re/notes](re/notes) (currently in Italian).

## Building the patch

Luma and Azahar load only **one** `code.ips` per game. If your translation already has one, the tool
copies its changes into the online patch, which then replaces it.

**You need**

- Python 3.
- The decompressed `code.bin` of the **original** game, version 1.3 (not included in the repository).
- The translation's `code.ips`, if it has one.
- The server's two IPv4 addresses: `IP` (main) and `IP2` (second).

**Steps**

1. Put `code.bin` in `re/bin/code.bin`.
2. Run:

   ```bash
   python -I re/tools/make_url_patch.py --code re/bin/code.bin \
     --sil-url http://IP:8381/00300701/ \
     --spotpass-url http://IP:8380/p01/nsa/H7btVjYWs7p5dGj6 \
     --skip-nasc --nex-auth IP:45000 --nex-player-password --nncs IP,IP2 \
     --merge path/to/translation/code.ips \
     -o code.ips
   ```

3. Install the new `code.ips` in place of the translation's one, as in the [player guide](#player-guide).

**Variants**

| Case | Change |
|---|---|
| Translation with its own `code.ips` | `--merge path/to/translation/code.ips` (as above) |
| No translation | Remove `--merge` |
| Translation installed as a full game (CIA) with a modified executable | `--code` = decompressed `code.bin` of the translated game, without `--merge` |
| Patch for Azahar | Add `--azahar` |
| Patch for a real 3DS | Without `--azahar` |

The tool stops instead of writing a broken patch if `code.bin` is not version 1.3, or if the
translation changes the same bytes as the online patch. Every option is described in
[docs/patch.md](docs/patch.md).

## License and copyright

**Code:** [GNU AGPL-3.0](LICENSE). `server/nex` and `server/nncs` derive from Pretendo Network code
under the same license, so the whole repository uses it. Whoever runs a modified server for others
must offer them its source code.

**Game and artwork:** *Dragon Quest Monsters: Joker 3 Professional*, its names, characters and artwork
© ARMOR PROJECT/BIRD STUDIO/SQUARE ENIX. All rights reserved. Dragon Quest is a registered trademark
of Square Enix; Nintendo 3DS is a trademark of Nintendo. This is an unofficial fan project, not
affiliated with or endorsed by Square Enix, Nintendo or Pretendo Network.

The AGPL covers the code only. It does not cover:

- the monster portraits in `web/public/monsters/` (game artwork, from the *DQM J3 Professional
  Master's guide* by StrangeServer & Yggdrasil);
- the Slime logo and favicons in `web/public/` (from *Dragon Quest I & II HD-2D*) and the family icons in
  `web/public/families/` (from [DQMJ3P-Randomizer](https://github.com/Lurpigi/DQMJ3P-Randomizer));
- game texts and names in `server/dashboard/data/monsters.json`.

They remain the property of their owners and are here only to identify the monsters of the game.
The repository contains no ROMs, CIAs, `code.bin` or other game files.

## Translations

- [DQMJ3P-IT-FanTranslation](https://github.com/Lurpigi/DQMJ3P-IT-FanTranslation): Italian fan translation.
- [DQMJ3P-english-fixed](https://github.com/Akoi89/DQMJ3P-english-fixed): the 2021 English fan translation, rebuilt with its defects fixed.
