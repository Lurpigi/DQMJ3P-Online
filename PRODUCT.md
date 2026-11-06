# DQMJ3P Online statistics portal

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

DQMJ3P Online players and spectators looking for championship results, battle records, and player
histories. Every portal page and history is public; browsing requires no account or login.

## Product Purpose

Make competition results accessible through an international dashboard. Preserve each championship
edition after the game's weekly reset and make old editions searchable.

## Operating Context

The game server runs on a VPS with Docker Compose. NEX uses PostgreSQL; SIL uses SQLite.
The frontend must be published on GitHub Pages; its backend belongs in this repository's `server/` tree.
The first release covers existing in-game championships. Website-organized events come later.

## Capabilities and Constraints

- Separate Masters GP, Challenger GP, and G-Cup editions and statistics.
- Support English, Italian, Spanish, French, and Japanese, matching the server.
- Keep permanent links to editions and public profiles across weekly resets.
- Direct battles use P2P; the current server does not persist their outcomes.
- Authentication material, save backups, and network addresses remain internal.
- Implemented: see [portal operations](docs/dashboard.md).

## Brand Commitments

Use monster imagery from the user's supplied
[spreadsheet](https://docs.google.com/spreadsheets/d/1VUfqzY6PmmtJycY0p1Y0egJ8-n9BcqM6lK6osIp8u_w/edit).
Rows are matched to species ids by name and stats (tools/import-monsters); the portraits are published
with the site. Family icons and the logo come from the DQMJ3P Randomizer.

## Evidence on Hand

- [Server architecture](docs/architettura.md).
- [SIL implementation](server/sil/sil_server.py): results, teams, scoring and calendar.
- [NEX rankings](server/nex/nex/ranking.go) and [weekly archive](server/nex/nex/gcup_week.go).
- [Grand Prix format research](re/notes/grandprix_formats.md), including uncertainty labels.

## Product Principles

- Edition identities and results survive weekly resets.
- Distinguish published standings, provisional results, and unavailable history.
- Browsing works without authentication.
- Show evidence the server actually has, with explicit coverage limits.
- Competition calendars and game behavior remain authoritative.
