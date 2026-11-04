# DQMJ3P Online

Server e patch per riattivare le funzioni online di *Dragon Quest Monsters: Joker 3 Professional*
(3DS, versione giapponese `00040000001ACB00` v1.3, anche con la traduzione italiana), su console con
Luma3DS e su Azahar.

I server ufficiali di Nintendo e Square Enix sono chiusi. Qui ci sono dei server sostitutivi e una patch
del gioco che lo collega a loro.

## Cosa funziona

| Funzione | Dove | Stato |
|---|---|---|
| Battaglia Libera e Battaglia Classificata Wi-Fi | NEX | Verificate tra Azahar e Azahar e tra 3DS e Azahar |
| Battaglia Amici | NEX | Lato server pronta, manca una prova con due account amici |
| Comunità: creazione, ufficiali per lingua, in evidenza, Sfida Comunitaria | NEX | Verificate |
| G-Cup (Ranking Race): coppe settimanali, classifiche, replay, premi | NEX | Verificata |
| Grand Prix (Ranking Battle): Maestri e Sfidante, classifiche, premi | SIL | Verificato |
| Codici regalo (i 130 codici originali) | SIL | Verificati sul server |
| Dischi regalo, negozio monete della Piazza Wi-Fi | SpotPass | Verificati |
| Eventi sul campo (scatola nascosta, mappa celeste, sicario StreetPass) | SpotPass | Solo la scatola nascosta verificata |

Per il dettaglio vedi [PLAN.md](PLAN.md).

## Guida per i giocatori

### Cosa serve

- Il gioco alla versione 1.3, con o senza la traduzione.
- Un account [Pretendo Network](https://pretendo.network): serve per il login amici, che dà a ogni
  giocatore un ID univoco. Il gioco non usa nient'altro di Pretendo.
- La patch `code.ips` di DQMJ3P Online, adatta alla piattaforma (3DS o Azahar) e alla traduzione che usi.

### Su 3DS (Luma3DS)

1. Configura Pretendo con [Nimbus](https://pretendo.network/docs/install/3ds) e attiva l'account Pretendo.
2. Copia la patch in `SD:/luma/titles/00040000001ACB00/code.ips`. Sostituisce la patch della traduzione:
   la nostra la contiene già.
3. Nella configurazione di Luma (tieni SELECT all'accensione) attiva **Enable game patching**.
4. Avvia il gioco ed entra nella Piazza Wi-Fi.

Sulla console usa la patch per 3DS. Quella per Azahar contiene correzioni solo per l'emulatore, e con la
versione "enhanced" della traduzione il gioco si blocca all'avvio.

### Su Azahar

1. Configura Pretendo seguendo la [guida per Azahar](https://pretendo.network/docs/install/citra):
   servono i moduli di sistema online (LLE) e un account Pretendo.
2. Copia la patch in `<cartella utente di Azahar>/load/mods/00040000001ACB00/exefs/code.ips`
   (su Windows di solito `%APPDATA%\Azahar`).
3. Avvia il gioco.

### Problemi comuni

- **Errore senza codice o "Errore di comunicazione" nelle lotte, su Azahar:** una VPN (per esempio
  NordVPN) impedisce ad Azahar di leggere l'indirizzo locale. Disattivala.
- **Il gioco resta circa 30 secondi su "Gioco Salvato!" prima della Piazza Wi-Fi:** è normale.
- **Le lotte non partono tra reti diverse:** le lotte sono dirette tra le console (P2P) e non c'è un
  server di relay. Con alcune reti (CGNAT, NAT simmetrico) può non funzionare.
- **Login NEX rifiutato dopo aver cambiato account Pretendo:** il server lega ogni ID alla prima password.
  Chiedi all'amministratore di azzerarla.

## Per chi gestisce il server

- [Installazione e uso dello stack](server/README.md): Docker Compose su un VPS con due IPv4.
- [Come funziona il server](docs/architettura.md): servizi, porte, indirizzi e dati.
- [La patch del gioco](docs/patch.md): ogni modifica, il suo indirizzo e perché serve.
- [Deploy automatico](docs/deploy.md): GitHub Action, secret, protezione di `main`.
- Note di reverse engineering in [re/notes](re/notes).

### Generare la patch

Serve il `code.bin` decompresso del gioco v1.3 (non è nel repository) e la patch della traduzione, se la usi:

```bash
python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://IP:8381/00300701/ --spotpass-url http://IP:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --nex-auth IP:45000 --nex-player-password --nncs IP,IP2 --merge PATCH_DELLA_TRADUZIONE -o code.ips
```

Per Azahar aggiungi `--azahar`. Le opzioni sono spiegate in [docs/patch.md](docs/patch.md).

## Licenze e materiale protetto

- `server/nex` e `server/nncs` derivano da codice di Pretendo Network con licenza AGPL-3.0 (`server/nex/LICENSE`):
  chi usa il server deve poterne ottenere i sorgenti, che sono questo repository.
- Il repository non contiene ROM, CIA, il `code.bin` né i file originali di Nintendo e Square Enix
  (`re/bin` e `re/data` sono esclusi da git). Non aggiungerli.
- Dragon Quest Monsters è un marchio di Square Enix. Il progetto non ha legami con Square Enix, Nintendo o Pretendo.
