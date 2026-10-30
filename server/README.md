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

## Stack di prova pubblico (VPS)

`docker-compose.yml` avvia NEX, Postgres, SIL, SpotPass e il controllo NAT su un solo server. Il login resta quello DEV: tutti i giocatori usano la stessa password, scritta nella patch. Serve per provare il gioco via internet, **non per aprirlo al pubblico**: prima vanno fatte le password per giocatore (`PLAN.md` sezione 4).

Serve un server Linux con Docker e **due IPv4 pubblici configurati sulla sua interfaccia di rete**. I provider che usano il NAT 1:1 (per esempio AWS e Google Cloud) non vanno bene, perché il controllo NAT non può fare il bind sugli IP pubblici.

1. Clona il repository e crea la configurazione:

   ```bash
   cd server && cp .env.example .env
   ```

   Compila `.env` come spiegato nei suoi commenti. Gli indirizzi devono essere IP: la patch accetta al massimo 15 byte per l'host NEX.

2. Copia dal tuo PC i dati che non sono nel repository, poi rendili scrivibili per i container:

   ```bash
   scp -r server/data/public server/data/private_templates root@IP:DQMJ3P-Online/server/data/
   scp -r re/data/spotpass_archive/canonical root@IP:DQMJ3P-Online/re/data/spotpass_archive/
   chown -R 1000:1000 server/data
   ```

3. Apri nel firewall le porte `45000-45001/udp`, `10025/udp`, `10125/udp`, `33334-33335/udp` e `8380-8381/tcp`, `45080/tcp`.

4. Avvia lo stack:

   ```bash
   docker compose up -d --build
   ```

   Il servizio `seed` carica le comunità ufficiali e poi si ferma: è normale.

5. Genera la patch sul tuo PC, con gli stessi valori di `.env`:

   ```bash
   python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://IP:8381/00300701/ --spotpass-url http://IP:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --nex-auth IP:45000 --nex-password NEX_PASSWORD --nncs IP,IP2 --spotpass-break --azahar --merge CODE_IPS_DI_PARTENZA -o code.ips
   ```

   Togli `--azahar` per la patch destinata a un 3DS vero.

I dati restano nei volumi Docker `pg` e `datastore` e nella cartella `DATA_DIR`. Per i log: `docker compose logs -f nex`.

L'account server di Pretendo non serve: con `--nex-auth` il gioco salta NASC e si collega direttamente al server NEX.
