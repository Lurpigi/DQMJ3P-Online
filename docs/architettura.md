# Come funziona il server

Il gioco usava tre servizi online diversi. Lo stack li sostituisce tutti e gira su un solo VPS con
Docker Compose ([server/docker-compose.yml](../server/docker-compose.yml)).

```text
                    login amici (ID univoco del giocatore)
  3DS / Azahar  ─────────────────────────────────────────────▶  Pretendo Network
       │
       │  patch code.ips: tutti gli altri indirizzi puntano al VPS
       ▼
  ┌──────────────────────────── VPS ────────────────────────────┐
  │  nex       UDP 45000-45001   lotte, comunità, G-Cup          │
  │            TCP 45080         upload e download dei replay     │──▶ postgres
  │  sil       TCP 8381          Grand Prix, codici regalo        │──▶ sqlite in DATA_DIR
  │  spotpass  TCP 8380          dischi regalo, negozio, eventi   │
  │  nncs      UDP 10025, 10125, 33334-33335 (due IP)  NAT check  │
  └──────────────────────────────────────────────────────────────┘
       ▲
       │  lotte: dati di gioco diretti tra le console (Pia, P2P)
  altra console
```

## Servizi

| Servizio | Codice | Porte | Cosa fa |
|---|---|---|---|
| `nex` | Go, [server/nex](../server/nex) | 45000/udp (autenticazione), 45001/udp (secure), 45080/tcp (HTTP DataStore) | Server di gioco Nintendo NEX 3.10.1: login, matchmaking delle lotte, comunità, classifiche e replay della G-Cup |
| `postgres` | immagine `postgres:16-alpine` | solo rete interna | Dati di `nex` |
| `seed` | SQL in [server/nex/sql](../server/nex/sql) | nessuna | Crea o aggiorna le comunità ufficiali e le 12 coppe G-Cup a ogni avvio dello stack, poi si ferma |
| `sil` | Python, [server/sil](../server/sil) | 8381/tcp | Sostituto del server SIL di Square Enix: Grand Prix, codici regalo, sfondi, backup del salvataggio |
| `spotpass` | Python, [server/spotpass](../server/spotpass) | 8380/tcp | Serve i file SpotPass (BOSS) originali, cifrati come li distribuiva Nintendo |
| `nncs` | Python, [server/nncs](../server/nncs) | 10025/udp, 10125/udp, 33334-33335/udp | Test NAT di Nintendo, che Pia usa prima di ogni lotta |

## Perché due indirizzi IP

Il test NAT (`nncs`) deve rispondere sia dallo stesso indirizzo e porta della richiesta, sia da un'altra
porta, sia da **un altro indirizzo**, per capire che tipo di NAT ha la console. Per questo il VPS ha due
IPv4 pubblici configurati sulla scheda di rete (`PUBLIC_IP` e `PUBLIC_IP2` in `.env`), e `nncs` usa la
rete dell'host invece di quella di Docker. Un NAT 1:1 del provider non va bene: il servizio deve poter
fare il bind sugli IP pubblici.

Il VPS di prova usa `188.245.46.173` (principale) e `78.47.138.100` (floating IP).

## Il percorso di una connessione

1. **Login amici.** La console entra in Pretendo con il suo account. Da lì il gioco prende l'ID del
   giocatore (PID) e la password amici.
2. **Login NEX senza NASC.** Il gioco originale chiedeva a Nintendo (NASC) l'indirizzo del server e un
   token. La patch salta la richiesta e usa direttamente `IP:45000`. La password NEX è derivata dalla
   password amici, che non lascia mai la console: il server la registra al primo accesso di ogni PID
   (`accounts.passwords`) e poi la confronta.
3. **Lotte.** `nex` fa solo il matchmaking: trova l'avversario e passa a ciascuna console l'indirizzo
   dell'altra. I dati della lotta viaggiano direttamente tra le console con Pia. Non c'è un relay.
4. **SIL.** Il Grand Prix e i codici regalo passano in HTTP dal server `sil`. Il token del giocatore è lo
   stesso valore derivato del punto 2, legato al suo friend code SIL.
5. **SpotPass.** Il modulo BOSS della console scarica i file da `spotpass` quando il gioco apre la Piazza
   Wi-Fi.

## Dati

| Dove | Contenuto |
|---|---|
| Volume `pg` (Postgres) | Password NEX dei giocatori, sessioni e comunità (`matchmaking.*`), classifiche e risultati G-Cup (`ranking.*`), metadati dei replay |
| Volume `datastore` | File dei replay della G-Cup |
| `DATA_DIR` (`server/data`) | `sil.sqlite3` (utenti, risultati e squadre del Grand Prix, codici regalo usati) e i file pubblici del Grand Prix in `public/` |
| `SPOTPASS_DIR` | File SpotPass originali (`re/data/spotpass_archive/canonical`, non nel repository) |
| `.env` | Indirizzi e password interne (`POSTGRES_PASSWORD`, `KERBEROS_PASSWORD`), mai in git |

## Lavori periodici

- **Settimana G-Cup** ([gcup_week.go](../server/nex/nex/gcup_week.go)): ogni minuto `nex` controlla la
  settimana (dal lunedì 2015-01-05, 12 coppe a rotazione). Al cambio salva i risultati, azzera la coppa che
  inizia, cancella i replay vecchi e scrive il podio nelle notizie. Percorso, evento, avversari e premi di
  ogni coppa sono in [gcup_official_communities.sql](../server/nex/sql/gcup_official_communities.sql).
- **Calendario del Grand Prix**: `sil` lo calcola a ogni richiesta (tornei di 7 giorni, giorno che cambia
  secondo `GP_UTC_OFFSET`). Le regole dello Sfidante ruotano su 8 set a ogni torneo.
- **Comunità in evidenza**: a ogni richiesta vuota `nex` restituisce tutte le comunità mostrabili
  ([featured.go](../server/nex/nex/matchmake_extension/featured.go)).

## Correzioni lato server per il gioco

- **Flag password casuali** ([password_flags.go](../server/nex/nex/matchmake_extension/password_flags.go)):
  il gioco manda i flag password delle sessioni senza inizializzarli, e una sessione con quei flag era
  invisibile all'avversario. Il server li azzera.
- **Battaglia Amici**: il gioco crea la sessione "solo amici" (policy 98), che la libreria NEX
  controllerebbe con il server amici di Pretendo, al quale non abbiamo accesso. Il server le dà la policy
  della lotta casuale. L'amico deve comunque cercare il PID esatto dell'host, preso dalla lista amici della
  console.
- **Comunità**: `JoinCommunity` e `UpdateCommunity` mancano nella libreria comune e sono implementate in
  [community.go](../server/nex/nex/matchmake_extension/community.go). Ogni gathering ha un `started_time`,
  senza il quale uscire da una comunità dava l'errore 006-0102.
- **Replay da Azahar**: Azahar invia i pezzi di un upload in ordine sbagliato. La patch per Azahar li manda in
  un pezzo solo, e il server riordina quelli già caricati.

## Sicurezza

- Login SSH solo con chiave, fail2ban sul log di SSH, aggiornamenti automatici di sicurezza.
- Firewall del provider con aperte solo le porte della tabella e la 22. Le porte pubblicate da Docker
  scavalcano le regole iptables del server, quindi il filtro va fatto prima.
- Ogni container ha un limite di memoria e di processi. I log Docker ruotano (10 MB × 3).
- `sil` rifiuta richieste oltre 512 KiB. `sil` e `spotpass` accettano al massimo 64 connessioni insieme e
  chiudono i client fermi da 15 s. L'HTTP del DataStore ha timeout di lettura e scrittura.
- Gli upload dei replay hanno un token casuale per versione, che riceve solo chi ha preparato l'upload.

Limiti noti:
- il token del giocatore viaggia in chiaro su HTTP verso `sil` e con una chiave fissa su PRUDP;
- chi arriva per primo su un PID o un friend code senza proprietario lo occupa;
- contro un attacco DDoS grande resta solo la protezione di rete del provider.
