# Azahar without Pretendo: personal identity patch (2026-11-16)

Implemented: `make_url_patch.py --identity`, `re/tools/azahar_identity.py`, and the reserved range in
`server/nex/globals/accounts.go`. Checked on 2026-11-16:

- Capstone disassembly of a personal IPS applied to code.bin: branch targets and literals are
  correct, and the cave stays inside free space.
- The local NEX server without DEV mode (`server/tests/auth_nex.py`): an unissued PID of the range is
  refused, an issued account logs in, and a wrong password for it is refused.

- In game on 2026-11-16: Azahar2 with the online LLE modules off, the Italian 1.1.9 Azahar patch plus
  an issued identity (PID 4180523542), against the VPS:
  - HLE frd logs in, the game reads the PID, and NEX logs in on the secure server (row in
    `accounts.passwords`).
  - Grand Prix ("Grado Battaglia Wi-Fi"): the save was a copy of a save with its own SIL friend
    code (456093702889), so `nuser/login` answered INVALID_TOKEN ("Download non riuscito. Accedi e
    riprova"). That is correct: the friend code belongs to another player.
  - After zeroing that friend code in RAM through the GDB stub (12 chars at `*(*(*0x897804+0x30)+4)`),
    the game showed the server's "registration expired" message, registered, and got friend code
    182498162454. Login and every table download were OK, up to the team-name screen; I stopped
    there, so there is no GP registration.

Not tested: a random battle, communities, and G-Cup with the issued identity.

The NEX change was deployed to the VPS on 2026-11-16 (old image kept as `server-nex:previous`). A
LoginEx with an unissued PID of the range then got InvalidUsername. The test account was removed
afterwards: its `accounts.passwords` row and the SIL `users`/`sessions` rows of 182498162454.

A player who switches a save from Pretendo to an issued account keeps the save's SIL friend code,
which is bound to the old password: Grand Prix fails with INVALID_TOKEN. An admin has to rebind
`users.secret` of that friend code to SHA-256 of the new player password. Not automated. Goal: Azahar players on the HLE friends module (no
Pretendo, no LLE modules) get NEX (random battles, communities, G-Cup, Ranking Race) and SIL (Grand
Prix, gift codes). Friend Battle stays out (needs a real friends list).

## Why it fails today

Azahar's HLE frd (`src/core/hle/service/frd/frd.cpp`, master on 2026-11-16):

- `Login` succeeds after 500 ms, after that `HasLoggedIn` / `IsOnline` return true.
- `GetMyFriendKey` returns `my_friend_key = {0, 0, 0}`: every player has PID 0.
- `GetMyPassword` (0x0010) and `RequestGameAuthentication` (0x0028) are not implemented. An
  unimplemented function answers result 0 and leaves the output untouched, so the password buffer
  stays empty. The `--nex-player-password` routine then fails on purpose ("no password").

On the server, NEX rejects PID <= 2 (`server/nex/globals/accounts.go`) and a token that does not
look like a player password. SIL rejects a token that does not look like a player password
(`_token_secret`). So nobody shares an identity, but nobody without Pretendo can play either.

## Design (as implemented)

Each player gets their own IPS: the normal Azahar patch plus two records that carry a PID and a
16-character secret. Everything else is unchanged.

1. **PID.** Replace the 4 instructions at `PID_OFFSET_SITE` (0x42D48C, `--pid-offset` uses the
   same place) with `bl cave` and 3 NOPs. The cave does `str high,[r5,#0xc]`,
   `ldr r1,=PID`, `mov r2,#0`, `mov r3,r1`, `bx lr`. The `stm r5,{r1-r3}` after it stores PID, pad
   and the friend code low word. Friend code high word = `SHA1(pid as u32 LE)[0] >> 1`, which keeps
   the friend code valid.
2. **Secret.** In the `--nex-player-password` routine, replace `bl 0x52c674` (frd GetMyPassword,
   routine +0x0C) with `bl` to a routine that copies the baked 16 bytes to r0 and returns 0. The
   routine then hashes it as usual: the NEX token and the SIL token are the same player password.
   `--skip-frd` is not needed, because the HLE login succeeds.
3. **Space.** 0x6B9B6C–0x6B9C00 is free (148 bytes, checked in code.bin v1.3). 0x6B9C00 onward is
   the translation padding (`build_optional_ips.py`). Both routines together take about 72 bytes.

Server:

- Reserved range 0xF0000000–0xFFFFFFFE (4,026,531,840–4,294,967,294). Pretendo's account server
  (PretendoNetwork/account, `src/models/nex-account.ts` and `pnid.ts`, checked 2026-11-16) gives
  3DS NEX accounts and PNIDs a random PID in 1,000,000,000–1,799,999,999. Nintendo's own PIDs counted
  down from 1,800,000,000. Our tables store PIDs as `bigint`, the Pretendo matchmaking tables use
  `numeric(20)`, and the dashboard uses hashed text ids, so PIDs above 2³¹ fit everywhere. NEX login
  with PID 4180523542 worked in game. Pia matchmaking with such a PID is untested.
- NEX: in `AccountDetailsByUsername`, a PID in that range without a row in `accounts.passwords`
  is rejected (no first-login registration). Issuing an account inserts
  `(pid, MD5(PLAYER_SALT + secret)[:8] hex)`. This blocks anyone who makes up a PID in the range.
- SIL: no change. Its identity is SHA-256 of the player password, and a random secret cannot
  collide.

Issuing (`azahar_identity.py`):

- Picks a random free PID of the range and a random 16-character secret (80 bits).
- Writes the personal IPS: the release Azahar IPS (`--base`) with the call in the player routine
  rewritten and the two identity records added. The records are fixed bytes except PID, friend code
  high word and secret, so issuing does not need code.bin.
- Writes the SQL that inserts the NEX row. It has no `ON CONFLICT`, so an existing PID fails instead
  of being taken over.
- Appends PID and secret to a private registry TSV (`azahar_accounts*.tsv`, git-ignored). With
  `--pid`, the tool writes the same patch again, for example on another translation's base.

A portal page ("create Azahar account", with a rate limit) can call the same code later.

## Limits and risks

- The IPS file is the credential: sharing it shares the account. If it is lost, an admin issues it
  again (same PID and secret, from the DB).
- A player who later switches to Pretendo gets a different PID and Grand Prix identity. Moving
  them over is manual.
- The game must reach our servers on HLE frd at all: other frd calls return empty data. Untested.
- SpotPass: no (needs the LLE boss module, out of scope).
- Friend Battle: no.

## Test plan

Use the Azahar2 portable copy with the LLE modules off, while the user's Azahar runs on Pretendo:

1. NEX login, then a random battle between the two instances.
2. A community and the G-Cup.
3. GP connect: register, 23_UserPackData, download tables.
4. A gift code.
5. A second issued IPS gets a different SIL friend code. A made-up PID in the range is rejected.
