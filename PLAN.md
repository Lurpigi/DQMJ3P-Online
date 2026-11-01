# DQMJ3P Online – Piano e stato

Obiettivo: riattivare le funzioni online di *Dragon Quest Monsters: Joker 3 Professional* (3DS, JP, `00040000001ACB00`, v1.3) su console (Luma3DS) ed emulatore (Azahar PC/Android).

Ultimo aggiornamento: 2026-11-01.

---

## 1. Architettura

Il gioco parla con **tre servizi distinti**, tutti identificati nel `code.bin` v1.3 con Ghidra:

| # | Servizio | Cosa fa nel gioco | Come lo sostituiamo | Stato |
|---|---|---|---|---|
| A | **NEX** (Nintendo, NEX 3.10.1 + Pia) | Lotte Wi-Fi amici e casuali, Comunità, Ranking Race (classifiche + replay) | Game server Go su stack Pretendo → [server/nex](server/nex) | MVP lotte testato in locale |
| B | **SpotPass / BOSS** (Nintendo) | Scatole nascoste, mostri StreetPass e mappa celeste, dischi regalo, tabella WiFi Shop | File originali archiviati, serviti così come sono → [server/spotpass](server/spotpass) | Dischi regalo, negozio monete e scatola nascosta (BREAK01) verificati in Azahar |
| C | **SIL** (Square Enix, HTTPS proprietario) | **Ranking Battle / Grand Prix**, codici regalo, sfondi, backup del salvataggio corrotto | Server Python → [server/sil](server/sil) + patch URL nel gioco | Protocollo completo, test passato; mancano i dati del Grand Prix |

Il login a C passa da Nintendo: il gioco chiede a NASC un *service token* (`SVCLOC`, keyhash `994cba6f`), che Pretendo già rilascia.

### Parametri verificati

| Parametro | Valore |
|---|---|
| Game server ID | `0x001ACB00` |
| Access key NEX | `5812c478` (non `994cba6f`, che è la keyhash SVCLOC) |
| PRUDP | v0, structure header attivi |
| BOSS app ID | `H7btVjYWs7p5dGj6` (task `BREAK01-03`, `FGONLYT`) |
| SIL | `https://dqm32ds.sil2.square-enix.com/00300701/`, title code `00200605`, chiave digest MD5 `3Ef7Db65775e4cCF` |

Dettagli e indirizzi in [re/notes](re/notes):
- [nex_usage.md](re/notes/nex_usage.md)
- [sil_protocol.md](re/notes/sil_protocol.md)
- [spotpass_boss.md](re/notes/spotpass_boss.md)
- [pretendo_research.md](re/notes/pretendo_research.md)

---

## 2. Come arriva il traffico ai nostri server

| Servizio | 3DS (Luma) | Azahar |
|---|---|---|
| Login amici | **Nimbus** con account Pretendo | Stesso, con Nimbus + moduli LLE (guida Pretendo per Azahar) |
| NEX, SpotPass, NAT check, SIL | Patch nel gioco (`luma/titles/00040000001ACB00/code.ips`, unita alla patch della traduzione) | Stessa patch in `load/mods/00040000001ACB00/exefs/code.ips` |

**Strada scelta (2026-10-30): self-hosting.** Pretendo non ha un canale per aggiungere titoli e sembra voler gestire i giochi da sola, quindi non le chiediamo nulla. I server girano su un nostro VPS e la patch ci porta direttamente il gioco: con `--skip-nasc --nex-auth IP:PORTA` il NASC non serve, quindi non dobbiamo ospitarne uno. Pretendo resta solo per il login amici, che da' un PID univoco.

Se Pretendo non fosse piu' utilizzabile, il piano di riserva e' `--skip-frd` senza Nimbus. Va provato da solo, il PID univoco va risolto e la Battaglia Amici non sarebbe disponibile.

---

## 3. Fatto

- [x] Ghidra 12.2 + JDK 25 + server MCP `pyghidra-mcp` (`.mcp.json`) + server di query locale (`re/tools/ghidra_server.py`, `gq.py`).
- [x] `code.bin` → ELF (`re/tools/codebin_to_elf.py`), progetto analizzato e annotato (prefissi `sil_`, `boss_`, `nex_`).
- [x] Parametri NEX, protocolli e metodi usati dal gioco, flussi di matchmaking (amici: gameMode 5, attribs[0] = ID host; casuale: gameMode 2/3, attribs[0] = forza).
- [x] Server NEX (`server/nex`, da template ACNL): login, `SecureConnection`, NAT traversal, matchmaking. `tests/smoke_nex.py` riproduce **lotta amici** (Create → Browse → JoinEx → GetSessionURLs) e **lotta casuale** (AutoMatchmake → stessa sessione).
- [x] SpotPass: file originali dall'archivio `3ds-boss-data`, server statico, codec `BSDT` con HMAC (`re/tools/bsdt.py`) per creare contenuti nuovi.
- [x] SIL: specifica completa, server sostitutivo (`server/sil`), test end-to-end (`tests/test_sil.py`).
- [x] Patch URL con merge della traduzione IT (`re/tools/make_url_patch.py`).

## 3b. Stato al 2026-10-26 (test su Azahar)

- Ranking Battle via SIL **funziona fino al menu**: Piazza Wi-Fi in modalità **offline** → Torre Slime dorata → "Grado Battaglia Wi-Fi". Login amici reale via Nimbus/Pretendo, poi register/login SIL e download di tutte le tabelle pubbliche dal nostro server.
- Patch usata (`load/mods/00040000001ACB00/exefs/code.ips`, backup della sola traduzione in `code.ips.bak-20261026`):
  `python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://127.0.0.1:8381/00300701/ --spotpass-url http://127.0.0.1:8380/p01/nsa/H7btVjYWs7p5dGj6 --skip-nasc --azahar --merge <mods>/exefs/code.ips.bak-20261026 -o <mods>/exefs/code.ips`
  - `--skip-nasc`: salta login NEX e token NASC (Pretendo non ha il gioco → 002-0110) e il controllo "NEX connesso" della schermata Ranking Battle. Le funzioni NEX (lotte, comunità, G-Cup) danno 006-0000.
  - `--azahar`: aggira bug di http:C di Azahar (POST vuoto mai inviato, dimensione header = 1, blocchi POST ordinati per contenuto).
- Server: `cd server && python -I -u sil/sil_server.py --host 0.0.0.0 --port 8381 --data data >> data/sil_server.log 2>&1`. Serve `data/public/030_GP_WallPapers.arc` = copia di `romfs:/data/Layout/menu/wifi_ranking_battle/upper/download.arc`.
- **GP dei Maestri giocato end-to-end** (sera del 2026-10-26): iscrizione `00_UserData.bin` → download `147_Grade_Def_DLBattle.bin` (avversari segnaposto CPU1-3) → upload `09_Grade_PrivateDlBattle.bin` → 3 round automatici → upload `GradeResultPack.bin` (salvato in `gp_results`, punteggio 1694), `04_UpdateSaveData.bin`, scambio `171_/28W_Grade_Other_Countries.bin`. Tutti OK.
  - `azahar_unsort` corretto: un payload staccato può trovarsi subito dopo un record completo (es. `PrivateSCRegister.bin`, Data = "Download_Code" in fondo al corpo); ora prova ogni record come "staccato".
  - Controllo da Claude: script PowerShell (screenshot con PrintWindow + SendInput) con il profilo controlli **Default** di Azahar; con il profilo "xbox1" i tasti da tastiera non arrivano.
- **Avversari veri** (2026-10-26): il server costruisce `09/18_*_PrivateDlBattle` dalle ultime squadre (`gp_results`) degli altri giocatori, ordinate in difficile/simile/facile; i round senza squadre restano CPU di `Def_DLBattle`. Testata del blocco squadra decodificata (località/bandiera, nome, principiante, Mii: vedi `re/notes/grandprix_formats.md` 3.8). Verificato in gioco con `--self-opponents` (la propria squadra come avversario, utile con un solo giocatore): "JEJ"/ITA nel round 1, mostri caricati e battaglia normale. Test: `server/tests/test_sil.py`.
- **Classifiche** (2026-10-26): il server genera da `gp_results` il calendario (`003_Held_Record`: tornei di 7 giorni da `--gp-start`), `089/139_*_Ranking_Pack` (generale fino a ieri con frecce, finale del torneo precedente, per prefettura), `23_UserPackData` (rango, punti, "La tua classifica", torneo precedente) e `141/142_*_ChampionRecord`. Verificato in gioco con `--gp-today 2026-10-27`: "Le classifiche di oggi sono disponibili", JEJ 1° ITA 3/0 1694 in "La tua classifica" e "Classifiche Generali". `PrivateSCRegister.bin` ora OK. Formati in `re/notes/grandprix_formats.md` 3.6/3.7/3.9.
- **GP dello Sfidante** (2026-10-26): regole di `018_LimitSetting` decodificate (taglia, famiglia, classe di rango, grado squadra) e configurabili con `gp_files.py --limit-rule TIPO:VALORE --limit-text --limit-theme --only 018_LimitSetting.bin`. In gioco: tema mostrato, regola 5:1 rifiuta la squadra, 4:8 la accetta; iscrizione, 3 round, upload `LimitResultPack` (1866 punti) OK; classifiche e dati utente Sfidante generati (verificati offline). Regola attiva sul server: 4:8.
- **Fine torneo** (simulata con `--gp-today 2026-11-02`): annuncio "1° torneo terminato", top 10, "Campione n°1", ricarica biglietti e menu Campioni verificati in gioco. Corretto `ChampionRecord`: le voci partono da +0 (il contatore sta nella voce 0).
- **Premi di fine torneo** (verificati in gioco 2026-10-26, date simulate 2/11, 9/11, 16/11):
  - *Regalo speciale* (`23_UserPackData`+0xfc u16 tipo 1, +0xfe id oggetto = chiave `I%04d` di `ItemMessage.mes`): "SQEX ti ha inviato un regalo speciale! ... Grande Sfera di Luce", una volta per torneo. Server: `--gp-prize-champion ITEM` (default 70 Grande Sfera di Luce), `--gp-prize-top10 ITEM` (default 66 Sfera di Luce).
  - *Monete di Rete* (blocco torneo precedente +0x1098: +0x44 u16 = 3, +0x48 platino, +0x4a oro, +0x4c argento, +0x4e bronzo): "Hai guadagnato alcune Monete di Rete! ×3 Monete d'Oro". Server: `--gp-coins-champion B,S,G,P` (default 0,0,3,0), `--gp-coins-top10` (default 0,3,0,0).
- **Regole Sfidante a rotazione** (2026-10-26): il server genera `018_LimitSetting` e `033_Limit_DLNewsMsg` dal numero del torneo, ciclando su 8 set (`LIMIT_RULE_SETS` in `sil_server.py`: libero, Slime, grado<=4, taglia piccola, Drago, grado<=6, Demone, rango SS). Avversari Sfidante solo dal torneo corrente. Verificato in gioco (torneo 4: "Regola: solo mostri di taglia piccola." col tasto Y). `--gp-limit-static` per usare il file fisso.
  - Il save ora e' al torneo 4 (16/11): il server gira con `--gp-today 2026-11-16`; tornando alla data reale il GP si azzera.
- **SpotPass: dischi regalo e negozio monete** (verificati in gioco 2026-10-28): Azahar usa il modulo `boss` vero (moduli online LLE), che scarica dal nostro `server/spotpass/serve_spotpass.py` (porta 8380, file originali) grazie a `--spotpass-url`. "Hai ricevuto il Disco Conclavio sacro!" e "Inventario aggiornato." con lo stock originale. Serve la connessione AC del gioco: `--skip-nasc` ora fa passare la schermata di connessione della piazza (0x5e) anche se il login NEX fallisce e forza "NEX connesso" solo in regali e negozio (dettagli in `re/notes/spotpass_boss.md` 6). Server: `python -I -u server/spotpass/serve_spotpass.py re/data/spotpass_archive/canonical 8380 0.0.0.0`.
  - Gli URL della patch usano `127.0.0.1`: l'IP del PC in LAN cambia (.189 -> .190). Per una console reale usare l'IP del PC.
  - Guida di Azahar delegabile a Codex: `re/tools/azahar/codex_drive.ps1 "obiettivo" -Sandbox danger-full-access` (gpt-6-luna xhigh, resoconto testuale).
- **Codici presente** (verificati in gioco 2026-10-28): codice `SLIME` -> "Hai ricevuto il disco Disco Slime dorato!". I codici stanno nella tabella `present_codes` di `server/data/sil.sqlite3` (`code`, `package_id`, `single_use`), i pacchetti sono `data/public/PresentCodePackageS%02u.bin` (`gp_files.make_present_package`). La tastiera del gioco ha solo lettere: codici senza cifre.
- **Ritocchi GP** (2026-10-28): frecce su/giu' verificate in gioco con una copia di prova dei dati (`server/data_test`, ignorata da git) e due giocatori finti: al giorno 3 "Slimerex 1 su, JEJ 2 su, Draghetto 3 giu'". `147/148_*_Def_DLBattle` rigenerati nell'ordine difficile/simile/facile (`gp_files.py server/data/public --only ...`).
- **Login NEX vero senza NASC** (verificato in Azahar 2026-10-28): `make_url_patch.py --nex-auth 127.0.0.1:45000 --nex-password <PN_DQMJ3P_DEV_PASSWORD>` (con `--skip-nasc`, che allora non finge piu' `NexLoginJob_Start`) + `server/nex` in DEV mode (`LoginEx` accetta qualunque token). Il gioco fa LoginEx -> RequestTicket -> Register sul nostro server col PID Pretendo reale. Avvio: `docker compose -f server/docker-compose.dev.yml -p dqmj3p up -d` (Postgres 127.0.0.1:54329), poi `server/nex/build/dqmj3p-nex.exe` (porte 45000/45001).
- **G-Cup (Ranking Race) fino all'iscrizione** (2026-10-28): 12 comunita' ufficiali G-Cup (`server/nex/sql/gcup_official_communities.sql`) e protocollo Ranking su Postgres (`server/nex/nex/ranking.go`). In gioco: ricerca coppa, iscrizione (nome squadra), coppa della settimana "Campo Prati Silenziosi", menu "Partecipa alla Corsa". Dettagli in `re/notes/nex_usage.md` 3.9.
- **G-Cup: gara, punteggio e classifica** (2026-10-28): l'application buffer delle comunita' ufficiali e' la definizione del torneo (avversari CPU, nome, forza, percorso, evento); con avversari a 0 la gara crashava. Ora la gara parte con 4 corridori, il tempo vinto va in classifica (`UploadScore` in frame a 30 fps) e la classifica istantanea lo mostra. DataStore 115 (`server/nex/nex/datastore.go`: metadati su Postgres, file via HTTP locale) gestisce i replay; upload, download e riproduzione del replay (solo con nuovo record nei primi 3) verificati in gioco.
- **Comunita' (Sfida Comunitaria)** (verificate in Azahar 2026-10-28): creazione, "Tua Comunita' Attuale" con codice, comunita' ufficiali (`server/nex/sql/official_communities.sql`, attribs[0] = 1) e iscrizione funzionano. Le "Comunita' in Evidenza" arrivano via StreetPass, non dal server. "Cerca Avversario" si fermava dopo `ReportNATProperties` per lo stesso problema delle lotte Wi-Fi (vedi sotto). Dettagli in `re/notes/nex_usage.md` 3.8.
- **Lotte Wi-Fi: ricerca avversario da host** (verificata in Azahar 2026-10-29): server NAT check `server/nncs/nncs_server.py` (porting di PretendoNetwork/nncs) su 127.0.0.1/127.0.0.2 e patch `make_url_patch.py --nncs 127.0.0.1,127.0.0.2`. Battaglia Libera crea il gathering con `AutoMatchmakeWithSearchCriteria_Postpone`, lo apre per 30 s e poi "Non trovo avversari". L'errore senza codice era Azahar: con NordVPN attivo `gethostid` restituisce 0, l'URL NEX resta senza `address=` e Pia lo rifiuta (`0xD8A148C1`). Senza VPN funziona. Una volta e' uscito 006-0105 dopo `ReplaceURL`, non riprodotto. Dettagli in `re/notes/nex_usage.md` 6.
- **Lotta Wi-Fi tra due giocatori** (verificata 2026-10-29): due Azahar sullo stesso PC si trovano con Battaglia Libera ("Vuoi sfidare Lurpigi?") e la battaglia parte con turni sincronizzati e si conclude (vittoria/sconfitta, salvataggio, ritorno al menu; al server solo `SendReport` + `EndParticipation`). La seconda istanza e' una copia portabile con patch `--skip-frd --pid-offset 1` (Pretendo non accetta due sessioni amici dello stesso account). Dettagli in `re/notes/nex_usage.md` 6.
- **Battaglia Classificata tra due giocatori** (verificata 2026-10-29): stesso matchmaking della Battaglia Libera (gameMode 3), lotta con punti giudice, al vincitore +10P ("Nuovo Arrivato" -> "Esploratore Apprendista"), perdente invariato. Grado e punti restano nel salvataggio: nessun upload a NEX o SIL. Corretto il server: il gioco manda flag di password casuali nella sessione, che la rendevano invisibile all'avversario (`server/nex/nex/matchmake_extension/password_flags.go`).
- **Sfida Comunitaria tra due giocatori** (verificata in gioco 2026-10-29): funziona tutto. La Battaglia Amici non e' verificabile: richiede due account con l'amicizia sul server amici 3DS di Pretendo.
- **SpotPass: eventi sul campo BREAK01-03** (2026-10-29): con `make_url_patch.py --spotpass-break`, alla connessione della piazza il gioco scarica i tre file dal nostro server (`BREAK01/BossStealthBox.bin`, `BREAK03/BossSkyMapMonster.bin`, `BREAK02/BossPassingMonster.bin`, tutti 200). Verificata in gioco la scatola nascosta di BREAK01: compare nella piazza e aprendola "Hai trovato Super Seme dell'Agi". Da verificare il mostro della mappa celeste (BREAK03) e il sicario StreetPass (BREAK02). In Azahar i task periodici falliscono (il modulo BOSS chiede `ac:u GetConnectingLocation`, non implementato), quindi la patch li scarica come task in primo piano "FGONLYT". Dettagli in `re/notes/spotpass_boss.md` 6.
- **Prossimo passo:** vedi sezione 4 (verifiche BREAK03/02, poi produzione).

## 4. Da fare

Aggiornato il 2026-10-29: in Azahar, con i server locali, funzionano lotte Wi-Fi (libera e classificata), comunita',
G-Cup con replay, Grand Prix via SIL, codici regalo e SpotPass (regali, negozio, BREAK01). Resta soprattutto la produzione.

### Fase A – Verifiche in gioco
- [ ] SpotPass BREAK03 (mostro della mappa celeste) e BREAK02 (sicario StreetPass): file scaricati, non ancora visti in gioco.
- [ ] Battaglia Amici: richiede due account Pretendo con l'amicizia sul server amici 3DS.
- [ ] Backup del salvataggio corrotto via SIL: previsto dal protocollo, mai provato in gioco.
- [ ] Notifiche Pia (eventi 4000-4999) da controllare a runtime (le lotte funzionano comunque).
- [ ] Regole delle comunita' (0x18 byte a +0x60 del buffer) da decodificare, per comunita' ufficiali con regole diverse.
- [ ] (Facoltativo) nuovi contenuti SpotPass creati con `re/tools/bsdt.py` al posto dei file originali.

### Fase B – Produzione
- [x] Stack di prova sul VPS Hetzner (2026-10-31): attivo su `188.245.46.173` e `78.47.138.100`. Da fuori passano `smoke_nex.py`, SpotPass e nncs, e dopo un riavvio del server riparte tutto. Porte 33334-33335/udp non provate.
- [x] Gioco contro il VPS, primo ingresso (2026-10-31): da "Visita Piazza Wi-Fi" su Azahar, con traduzione enhanced, login NEX col PID reale e download dei tre file BREAK (200) dal VPS. `BREAK_CAVE` e' stato spostato a `0x6B9900` perche' collideva con `code_enhanced.ips`. Il gioco resta circa 30 s su "Gioco Salvato!" prima di connettersi.
- [x] SIL in gioco sul VPS (2026-10-31): login, classifiche e dati utente copiati dal database locale. `nuser/getnonce` adotta i friend code sconosciuti, ma un utente senza `00_UserData.bin` non risulta registrato al Grand Prix e il gioco dice che i dati non ci sono piu'.
- [ ] Prima di distribuire: capire cosa vede chi arriva con un save registrato altrove, senza dati sul server.
- [ ] Prima di distribuire: la routine BREAK deve scaricare solo i file mancanti (`GetNsDataIdList`). Riscaricarli costa 22 s a ogni connessione e non aggiorna nulla, quindi la patch attiva di Azahar non include `--spotpass-break`.
- [ ] Sul VPS mancano ancora: comunita', gare del Grand Prix, oggetti BREAK visti in gioco.
- [x] Lotta 3DS reale contro Azahar tramite il VPS (2026-11-01): login con PID diversi, nncs in gioco (tipi 101-103) e sessione 14 completata. Stessa rete di casa: stesso IP pubblico per i due dispositivi.
- [ ] Lotta tra due reti diverse: mai provata. Le lotte Pia sono P2P e non c'e' un relay, quindi verificare cosa succede con CGNAT e NAT simmetrico.
- [x] Password per giocatore (2026-10-31): `accounts.passwords` e `make_url_patch.py --nex-player-password` (password derivata con MD5 dalla password amici, registrata al primo accesso). Verificata sul VPS con `tests/auth_nex.py` e in gioco su Azahar. Dettagli e limiti in `server/README.md`.
- [ ] Fine torneo G-Cup: coppe con flag 513, premi per fascia e notizie nel buffer (`gcup_official_communities.sql`, mappa in `re/notes/nex_usage.md` 3.9), applicati sul VPS il 2026-11-01. Il cambio coppa e l'ordine delle monete vanno provati in gioco.
- [ ] Settimana G-Cup nel server NEX (`nex/gcup_week.go`, 2026-11-01): ogni minuto controlla la settimana, salva i risultati in `ranking.gcup_results`, azzera i vecchi punteggi della coppa che inizia, rimuove i replay vecchi e scrive il podio nelle notizie. Provato su Postgres locale, manca il primo cambio reale.
- [ ] Notizie Grand Prix: `032_Grade_DLNewsMsg.bin` e' un testo fisso in inglese; i vincitori si possono generare in `sil_server.py` senza job, come per `033`.
- [x] Sicurezza SIL (2026-10-31): friend code legato allo SHA-256 del token del giocatore (`users.secret`), token nella patch con `--nex-player-password`. Verificata con `tests/test_sil.py` e in gioco su Azahar.
- [ ] DataStore: URL di upload con token casuale per versione. `tests/smoke_nex.py` lo verifica, manca una gara vera in gioco che carichi un replay.
- [ ] Battaglia Amici: il server non vede le amicizie senza il gRPC di Pretendo (`GetUserFriendPIDs` restituisce vuoto). Verificare se la modalita' ne ha bisogno.
- [ ] Test su 3DS reale, avviato il 2026-11-01. Funzionano avvio, login NEX con password per giocatore e lotta. Da provare: SIL, classifiche, G-Cup e replay, comunita', eventi BREAK in standby.
  - Patch per console: senza `--azahar` e `--spotpass-break`, con `--merge` della `exefs/code.ips` normale. `code_enhanced.ips` e' solo per emulatore e sul 3DS fa crashare il gioco all'avvio.

### Fase C – Distribuzione
- [ ] Pubblicare i sorgenti: `server/nex` e `server/nncs` derivano da codice AGPL-3.0, quindi chi usa il server deve poterli ottenere.
- [ ] Controllare le regole di Pretendo sull'uso dell'account per il login amici con una patch.
- [ ] Guida utente 3DS e Azahar, con patch generata per la versione tradotta.

---

## 5. Rischi

- **Grand Prix:** dipende da dati Square Enix andati persi; ricostruirlo richiede di decodificare formati non documentati.
- **Pretendo:** il login amici dipende da un servizio che non controlliamo e che puo' cambiare.
- **NAT:** senza relay, i giocatori dietro CGNAT o NAT simmetrico potrebbero non riuscire a lottare.
- **Sicurezza:** fino alle password per giocatore lo stack va usato solo per le prove, non aperto al pubblico.
- **Legale:** distribuire solo server, patch e strumenti. Mai ROM, CIA o i file originali scaricati (`re/data`, escluso da git). I file SpotPass originali serviti dal nostro server restano il punto piu' delicato.
