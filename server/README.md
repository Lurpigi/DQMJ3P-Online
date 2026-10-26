# Server DQMJ3P Online

| Cartella | Contenuto | Stato |
|---|---|---|
| `nex/` | Game server NEX (Go, nex-go v2) – lotte Wi-Fi, comunità, Grand Prix, Ranking Race | MVP matchmaking funzionante in locale |
| `tests/` | Test con client NEX finto (NintendoClients) | `smoke_nex.py` passa |
| `docker-compose.dev.yml` | Postgres per i test locali | |

Il server NEX deriva dal template [animal-crossing-new-leaf](https://github.com/PretendoNetwork/animal-crossing-new-leaf) di Pretendo (AGPL-3.0, vedi `nex/LICENSE`): stessa versione NEX 3.10.1.

## Parametri del gioco (verificati in Ghidra)

| Parametro | Valore | Dove |
|---|---|---|
| Title ID | `00040000001ACB00` | exheader |
| Game server ID (NASC `gameid`) | `0x001ACB00` | `NexLoginJob_Start` 0x66c4ec |
| Access key PRUDP | `5812c478` | stringa UTF-16 a 0x66c688 |
| Versione NEX | 3.10.1 (PRUDP v0, structure header attivi) | stringa `NEX_3_10_1` |
| Keyhash SVCLOC (token Square Enix) | `994cba6f`, svc `0000` | `silAuthRequestAuthToken` 0x74041c |

## Test locale (modalità DEV)

Prerequisiti: Go (`~/tools/go`), Docker, venv NintendoClients (`~/tools/nc-venv`).

```bash
docker compose -f docker-compose.dev.yml -p dqmj3p up -d   # Postgres su 127.0.0.1:54329
cd nex && cp .env.example .env && go build -o build/dqmj3p-nex.exe . && ./build/dqmj3p-nex.exe
# in un altro terminale
~/tools/nc-venv/Scripts/python tests/smoke_nex.py         # due client: crea / cerca / entra in una sessione
```

In modalità DEV (`PN_DQMJ3P_DEV_PASSWORD` impostata) ogni PID usa la stessa password NEX, i servizi gRPC account/friends di Pretendo non servono e il metodo `Login` semplice è abilitato. **Mai in produzione.**

Note:
- Su Windows le porte UDP 59435–63044 sono riservate da Hyper-V: in DEV usiamo 45000/45001.
- NintendoClients 5.0 serializza `MatchmakeSessionSearchCriteria` solo fino ai campi di NEX 3.5: il test aggiunge i campi 3.6–3.8.
- Con `PN_DQMJ3P_DEBUG_RMC=1` il server stampa protocollo, metodo e parametri di ogni chiamata, che è il modo per scoprire cosa invia la console vera.

## Produzione (stack Pretendo)

Togliere `PN_DQMJ3P_DEV_PASSWORD` e impostare `PN_DQMJ3P_ACCOUNT_GRPC_*` e `PN_DQMJ3P_FRIENDS_GRPC_*`. L'account server di Pretendo deve avere un documento nella collezione `servers` con `title_ids: ["00040000001ACB00"]`, `game_server_id: "001ACB00"` (formato da confermare: probabilmente `%08X` dal modulo frd), indirizzo e porta del server di autenticazione (vedi `re/notes/pretendo_research.md`).
