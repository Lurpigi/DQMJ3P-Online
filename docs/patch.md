# Game patch

[re/tools/make_url_patch.py](../re/tools/make_url_patch.py) creates the `code.ips` that Luma and Azahar apply
to DQMJ3P v1.3's `code.bin`. Luma and Azahar load only one `code.ips` per title, so the tool merges
(`--merge`) records from an existing patch, such as a translation, with its own. If a merged record
overlaps one of this tool's records, the tool stops.

Each record checks the original bytes: with a different game version, the tool stops rather than
writing an incorrect patch.

Addresses: **offsets** are positions within `code.bin`; **VAs** are memory addresses
(VA = offset + `0x100000`), as used in Ghidra and the notes in [re/notes](../re/notes).

## Options for a public patch

```bash
python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://IP:8381/00300701/ --spotpass-url http://IP:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --nex-auth IP:45000 --nex-player-password --nncs IP,IP2 [--azahar] --merge TRANSLATION_PATCH -o code.ips
```

| Option | What it changes | Purpose |
|---|---|---|
| `--sil-url` | The `https://dqm32ds.sil2.square-enix.com/00300701/` string (offset `0x76C83C`) | Square Enix's SIL server has shut down. The URL must end with `/` |
| `--spotpass-url` | BOSS task base URL `https://npdl.cdn.nintendowifi.net/p01/nsa/H7btVjYWs7p5dGj6` (offset `0x76A0C4`) | Nintendo's SpotPass CDN has shut down. The BOSS module also accepts `http://` |
| `--nncs IP,IP2` | `nncs1/nncs2.app.nintendowifi.net`, in ASCII (offsets `0x7711AA`, `0x7711C5`, used by Pia) and UTF-16 (offsets `0x7791DE`, `0x779214`, used by NEX) | Nintendo's NAT check service has shut down |
| `--skip-nasc` | Skips Nintendo NASC during SIL login, on the Wi-Fi Plaza connection screen, and in menus requiring "NEX connected" | Pretendo does not have this game in its NASC |
| `--nex-auth IP:PORT` | Direct NEX login to our authentication server | Without NASC, the game would not know the NEX server's address |
| `--nex-player-password` | Sets the NEX password to `MD5(salt + friends password)` (first 16 hexadecimal characters) | A separate password for each player, without sending the friends password |
| `--azahar` | Fixes for Azahar's HTTP bugs | Emulator only |
| `--merge FILE` | Copies records from another patch | Luma and Azahar load only one `code.ips` |

Testing options, not intended for players: `--nex-password` (shared password, server in DEV mode),
`--skip-frd` and `--pid-offset N` (second Azahar instance using the same account), `--azahar-hle-boss`,
`--spotpass-break`, `--infra-url`.

## Record details

### `--skip-nasc`

| Offset | Original | Replacement | Reason |
|---|---|---|---|
| `0x56CB48` | `bleq 0x66bd38` | `nop` | The SIL job (`SilAuthJob_Update`, VA `0x66cacc`) does not queue NEX login |
| `0x56CB90` | `beq` | `nop` | Does not wait for the "NEX connected" flag |
| `0x56CBC4` | `beq` | `nop` | Does not request a service token from NASC (with `--nex-player-password`, writes the player token here instead) |
| `0x56C4EC` | Start of `NexLoginJob_Start` | `mov r0,#0; bx lr` | Only without `--nex-auth`: simulates NEX login |
| `0x2CA944` | `beq 0x3ca9b0` | `nop` | The Grand Prix screen does not require a NEX session |
| `0x288044`, `0x2880AC` | States 7 and 8 of the Plaza connection screen (`0x5e`) | `b 0x3880f8` | Advances to state 10 (connected) even if network login fails: the BOSS module only needs a connection |
| `0x339EC4` and following | `bl FUN_00445fb8` (NEX connected?) | `mov r0,#1` | Allows gift discs, coin shop, and present codes to proceed |

### `--nex-auth`

| Offset | Change | Reason |
|---|---|---|
| `0x356F90`, `0x3572A4`, `0x3572C0` | `mov r0,#0` replaces the frd request, wait, and result read | The game no longer requests authentication from NASC |
| `0x42D088` (`FUN_0052d088`) | Returns a fixed result: HTTP 200, host and port from `--nex-auth`, dummy token | This is the getter from which login reads the server address |
| `0x42C674` (`FUN_0052c674`) | Returns the NEX password | With `--nex-player-password`, the call at `0x356B58` instead goes to a routine (offset `0x6B9A60`) that computes the derived password |
| `0x4B5878` | `bl FUN_0023d168` → `nop` | Featured communities request an empty list, and the server returns all communities. A single saved ID would be indistinguishable from a code search, which must remain exact |

### `--azahar`

| Offset | Reason |
|---|---|
| `0x503E88`, `0x503E8C`, `0x6D5F8C` | Azahar never sends a POST with no data: the empty body becomes one `0x00` byte, which the SIL server treats as empty |
| `0x504290`, `0x504294` | Azahar reports the response header size incorrectly: the header buffer is fixed at 4 KiB, otherwise `X-Sil-Digest` cannot be found |
| `0x3AA3B4` → routine at `0x6B9B60` | Azahar sends upload chunks sorted by content: the HTTP buffer is sized to send the replay as a single chunk |

### Free space used

The added routines occupy padding at the end of `.text`: `0x6B9900` (`--spotpass-break`), `0x6B9A60`
(`--nex-player-password`), `0x6B9B60` (Azahar upload). `0x6B9810-0x6B98F3` is occupied by the translation's
`code_enhanced.ips`.

## Console and emulator patches

- **3DS**: without `--azahar` or `--spotpass-break`, merged with the translation's regular `exefs/code.ips`.
  `code_enhanced.ips` is emulator-only: it crashes the game at startup on a console.
- **Azahar**: with `--azahar`, merged with your preferred translation patch.

To add only the featured-communities record to an installed patch without regenerating it, read it with
`read_ips`, add `FEATURED_ALL_SITE`, and write it back with `write_ips` (the same functions used by the tool).
