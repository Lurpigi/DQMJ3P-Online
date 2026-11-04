# La patch del gioco

[re/tools/make_url_patch.py](../re/tools/make_url_patch.py) crea il `code.ips` che Luma e Azahar applicano
al `code.bin` di DQMJ3P v1.3. Luma e Azahar caricano un solo `code.ips` per titolo, quindi lo strumento
unisce (`--merge`) i record di una patch esistente, per esempio quella della traduzione, ai propri. Se un
record della patch unita si sovrappone ai nostri, lo strumento si ferma.

Ogni record controlla i byte originali: con una versione diversa del gioco lo strumento si ferma invece di
scrivere una patch sbagliata.

Indirizzi: gli **offset** sono posizioni nel `code.bin`, i **VA** sono gli indirizzi in memoria
(VA = offset + `0x100000`), che sono quelli di Ghidra e delle note in [re/notes](../re/notes).

## Opzioni per una patch pubblica

```bash
python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://IP:8381/00300701/ --spotpass-url http://IP:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --nex-auth IP:45000 --nex-player-password --nncs IP,IP2 [--azahar] --merge PATCH_DELLA_TRADUZIONE -o code.ips
```

| Opzione | Cosa cambia | Perché |
|---|---|---|
| `--sil-url` | Stringa `https://dqm32ds.sil2.square-enix.com/00300701/` (offset `0x76C83C`) | Il server SIL di Square Enix è chiuso. L'URL deve finire con `/` |
| `--spotpass-url` | Base dei task BOSS `https://npdl.cdn.nintendowifi.net/p01/nsa/H7btVjYWs7p5dGj6` (offset `0x76A0C4`) | Il CDN SpotPass di Nintendo è chiuso. Il modulo BOSS accetta anche `http://` |
| `--nncs IP,IP2` | `nncs1/nncs2.app.nintendowifi.net`, in ASCII (offset `0x7711AA`, `0x7711C5`, usate da Pia) e in UTF-16 (offset `0x7791DE`, `0x779214`, usate da NEX) | Il test NAT di Nintendo è chiuso |
| `--skip-nasc` | Salta il NASC di Nintendo nel login SIL, nella schermata di connessione della Piazza Wi-Fi e nei menu che richiedono "NEX connesso" | Pretendo non ha il gioco nel suo NASC |
| `--nex-auth IP:PORTA` | Login NEX diretto sul nostro server di autenticazione | Senza NASC il gioco non saprebbe dove si trova il server NEX |
| `--nex-player-password` | La password NEX diventa `MD5(sale + password amici)` (primi 16 caratteri esadecimali) | Una password diversa per ogni giocatore, senza mandare la password amici |
| `--azahar` | Correzioni per i bug di HTTP di Azahar | Solo per l'emulatore |
| `--merge FILE` | Copia i record di un'altra patch | Luma e Azahar caricano un solo `code.ips` |

Opzioni di prova, non per i giocatori: `--nex-password` (password condivisa, server in modalità DEV),
`--skip-frd` e `--pid-offset N` (seconda istanza di Azahar con lo stesso account), `--azahar-hle-boss`,
`--spotpass-break`, `--infra-url`.

## Dettaglio dei record

### `--skip-nasc`

| Offset | Originale | Diventa | Motivo |
|---|---|---|---|
| `0x56CB48` | `bleq 0x66bd38` | `nop` | Il job SIL (`SilAuthJob_Update`, VA `0x66cacc`) non mette in coda il login NEX |
| `0x56CB90` | `beq` | `nop` | Non aspetta il flag "NEX connesso" |
| `0x56CBC4` | `beq` | `nop` | Non chiede a NASC un token di servizio (con `--nex-player-password` qui scrive il token del giocatore) |
| `0x56C4EC` | inizio di `NexLoginJob_Start` | `mov r0,#0; bx lr` | Solo senza `--nex-auth`: finge il login NEX |
| `0x2CA944` | `beq 0x3ca9b0` | `nop` | La schermata del Grand Prix non richiede una sessione NEX |
| `0x288044`, `0x2880AC` | stati 7 e 8 della schermata di connessione della Piazza (`0x5e`) | `b 0x3880f8` | Si va allo stato 10 (connesso) anche se il login di rete fallisce: il modulo BOSS ha bisogno solo della connessione |
| `0x339EC4` e seguenti | `bl FUN_00445fb8` (NEX connesso?) | `mov r0,#1` | Dischi regalo, negozio monete e codici regalo proseguono |

### `--nex-auth`

| Offset | Cosa | Motivo |
|---|---|---|
| `0x356F90`, `0x3572A4`, `0x3572C0` | `mov r0,#0` al posto della richiesta a frd, dell'attesa e della lettura del risultato | Il gioco non chiede più a NASC l'autenticazione |
| `0x42D088` (`FUN_0052d088`) | Restituisce un risultato fisso: HTTP 200, host e porta di `--nex-auth`, token fittizio | È il getter da cui il login legge l'indirizzo del server |
| `0x42C674` (`FUN_0052c674`) | Restituisce la password NEX | Con `--nex-player-password` la chiamata a `0x356B58` va invece a una routine (offset `0x6B9A60`) che calcola la password derivata |
| `0x4B5878` | `bl FUN_0023d168` → `nop` | Le comunità in evidenza chiedono una lista vuota, e il server risponde con tutte le comunità. Un solo ID salvato sarebbe identico a una ricerca per codice, che deve restare esatta |

### `--azahar`

| Offset | Motivo |
|---|---|
| `0x503E88`, `0x503E8C`, `0x6D5F8C` | Azahar non invia mai una POST senza dati: il corpo vuoto diventa un byte `0x00`, che il server SIL tratta come vuoto |
| `0x504290`, `0x504294` | Azahar riporta male la dimensione degli header di risposta: il buffer degli header diventa fisso di 4 KiB, altrimenti `X-Sil-Digest` non si trova |
| `0x3AA3B4` → routine a `0x6B9B60` | Azahar manda i pezzi di un upload ordinati per contenuto: il buffer HTTP viene dimensionato per mandare il replay in un pezzo solo |

### Spazio libero usato

Le routine aggiunte stanno nel padding a fine `.text`: `0x6B9900` (`--spotpass-break`), `0x6B9A60`
(`--nex-player-password`), `0x6B9B60` (upload per Azahar). `0x6B9810-0x6B98F3` è occupato da
`code_enhanced.ips` della traduzione.

## Patch per console e per emulatore

- **3DS**: senza `--azahar` e `--spotpass-break`, unita alla `exefs/code.ips` normale della traduzione.
  `code_enhanced.ips` è solo per emulatore: sulla console il gioco si blocca all'avvio.
- **Azahar**: con `--azahar`, unita alla patch della traduzione che preferisci.

Per aggiungere a una patch già installata il solo record delle comunità in evidenza, senza rigenerarla,
basta leggerla con `read_ips`, aggiungere `FEATURED_ALL_SITE` e riscriverla con `write_ips` (stesse funzioni
dello strumento).
