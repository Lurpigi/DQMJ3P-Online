# DQMJ3P Online

Replacement servers and a game patch to restore the online features of *Dragon Quest Monsters: Joker 3 Professional*
(3DS, Japanese release `00040000001ACB00` v1.3, including the Italian translation), on consoles running
Luma3DS and on Azahar.

The official Nintendo and Square Enix servers have shut down. This project provides replacement servers
and a game patch that connects to them.

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

### Requirements

- Version 1.3 of the game, with or without a translation patch.
- A [Pretendo Network](https://pretendo.network) account for friends login, which gives each player a
  unique ID. The game does not use any other Pretendo services.
- The DQMJ3P Online `code.ips` patch matching your platform (3DS or Azahar) and translation patch.

### On 3DS (Luma3DS)

1. Set up Pretendo with [Nimbus](https://pretendo.network/docs/install/3ds) and activate your Pretendo account.
2. Copy the patch to `SD:/luma/titles/00040000001ACB00/code.ips`. It replaces the translation patch:
   our patch already includes it.
3. In the Luma configuration menu (hold SELECT while powering on), enable **Enable game patching**.
4. Launch the game and enter the Wi-Fi Plaza.

Use the 3DS patch on a real console. The Azahar patch contains emulator-specific fixes, and using the
"enhanced" translation patch causes the game to crash at startup on a console.

### On Azahar

1. Set up Pretendo using the [Azahar guide](https://pretendo.network/docs/install/citra):
   you need the online system modules (LLE) and a Pretendo account.
2. Copy the patch to `<Azahar user directory>/load/mods/00040000001ACB00/exefs/code.ips`
   (on Windows, the user directory is usually `%APPDATA%\Azahar`).
3. Launch the game.

### Troubleshooting

- **An error without a code, or a communication error during battles on Azahar:** a VPN (such as
  NordVPN) can prevent Azahar from reading the local address. Disable it.
- **The game stays on the save confirmation ("Gioco Salvato!" in Italian) for about 30 seconds before entering the Wi-Fi Plaza:** this is normal.
- **Battles do not start between different networks:** battles connect the consoles directly (P2P),
  with no relay server. Some networks (CGNAT, symmetric NAT) may not work.
- **NEX login rejected after changing Pretendo accounts:** the server binds each ID to the first password
  it receives. Ask the administrator to reset it.

## Server administration

- [Stack setup and usage](server/README.md): Docker Compose on a VPS with two IPv4 addresses.
- [Server architecture](docs/architettura.md): services, ports, addresses, and data.
- [Game patch](docs/patch.md): each modification, its address, and its purpose.
- [Automated deployment](docs/deploy.md): GitHub Actions, secrets, and `main` protection.
- [Statistics portal](docs/dashboard.md): public championship archive, player histories and monster catalog (API on the VPS, site on GitHub Pages).
- Reverse engineering notes in [re/notes](re/notes) (currently in Italian).

### Generating the patch

You need the decompressed `code.bin` from version 1.3 of the game (not included in the repository) and,
if applicable, your translation patch:

```bash
python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://IP:8381/00300701/ --spotpass-url http://IP:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --nex-auth IP:45000 --nex-player-password --nncs IP,IP2 --merge TRANSLATION_PATCH -o code.ips
```

Add `--azahar` for Azahar. See [docs/patch.md](docs/patch.md) for the available options.

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
The repository contains no ROMs, CIAs, `code.bin` or other game files
