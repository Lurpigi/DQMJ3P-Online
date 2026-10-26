# DQMJ3P Online – Piano e stato

Obiettivo: riattivare le funzioni online di *Dragon Quest Monsters: Joker 3 Professional* (3DS, JP, `00040000001ACB00`, v1.3) su console (Luma3DS) ed emulatore (Azahar PC/Android).

Ultimo aggiornamento: 2026-10-24.

---

## 1. Architettura

Il gioco parla con **tre servizi distinti**, tutti identificati nel `code.bin` v1.3 con Ghidra:

| # | Servizio | Cosa fa nel gioco | Come lo sostituiamo | Stato |
|---|---|---|---|---|
| A | **NEX** (Nintendo, NEX 3.10.1 + Pia) | Lotte Wi-Fi amici e casuali, Comunità, Ranking Race (classifiche + replay) | Game server Go su stack Pretendo → [server/nex](server/nex) | MVP lotte testato in locale |
| B | **SpotPass / BOSS** (Nintendo) | Scatole nascoste, mostri StreetPass e mappa celeste, dischi regalo, tabella WiFi Shop | File originali archiviati, serviti così come sono → [server/spotpass](server/spotpass) | Pronto (test locale) |
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
| NEX + NASC + SpotPass | **Nimbus** (account Pretendo): riscrive `*.nintendowifi.net` → `*.pretendo.cc`. Funziona solo se i nostri server sono **dentro Pretendo**. | Stesso, con Nimbus + moduli LLE (guida Pretendo per Azahar) |
| SIL Square Enix | Patch dell'URL nel gioco (`luma/titles/00040000001ACB00/code.ips`, unita alla patch della traduzione) | Stessa patch in `load/mods/00040000001ACB00/exefs/code.ips` |

**Strada consigliata: proporre il gioco a Pretendo**, che deve:
- aggiungere il documento `servers` nell'account server (title ID, `game_server_id`, indirizzo e porta);
- ospitare il game server NEX;
- caricare i file SpotPass.

In questo modo i giocatori non devono installare niente oltre a Nimbus e alla patch dell'URL. In alternativa esistono router community che girano sopra Pretendo (`fbf-3ds-servers`, `nasc-router`), ma richiedono un'app client in più.

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
  `python -I re/tools/make_url_patch.py --code re/bin/code.bin --sil-url http://192.168.1.189:8381/00300701/ --skip-nasc --azahar --merge <mods>/exefs/code.ips.bak-20261026 -o <mods>/exefs/code.ips`
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
- **Premi** (parziale, non verificato in gioco): Special Present = `23_UserPackData`+0xfc u16 tipo (1 oggetto id u16 a +0xfe; 2 mostro: specie a +0xfe + 6 u16 a +0x102; 3 schermata premio generica, 4 u16 a +0x100..+0x106), consegnato una volta per torneo (flag nel save azzerato quando cresce Held N, `FUN_003caaa8`). Server: `--gp-prize-champion ITEM --gp-prize-top10 ITEM` (oggetto al campione / top 10 del torneo precedente). Attestato di fine torneo separato: blocco precedente +0x1098+0x44 u16 == 3 => "MenuMessagePresentPrize" + layout `gp_result_01` (campione) / `_02`-`_05`, 4 u16 a +0x48..+0x4e di significato ignoto (`FUN_005cb39c`, `FUN_005cb0ac`). Da fare: nomi degli id oggetto (`ItemMessage.mes`, parser in `DQMJ3P-IT-FanTranslation/scripts/mes_to_json.py`; id piu' usati nei codici regalo: 47, 66, 43), prova in gioco, attestato.
- **Prossimo passo:** freccia su/giu' da vedere in gioco; rigenerare `147/148_*_Def_DLBattle` con `gp_files.py` (ordine entry corretto: 0 = difficile); regole Sfidante a rotazione per torneo (oggi file statico).

## 4. Da fare

### Fase A – Prova con console/emulatore reale (serve te)
- [ ] Avviare il gioco con Nimbus + patch su 3DS o Azahar, con `HokakuCTR` (dump RMC) o i log del server, per confermare:
  - formato del `gameid` NASC;
  - `Login` vs `LoginEx`, `Register` vs `RegisterEx`;
  - flusso effettivo delle lotte amici.
- [ ] Decidere l'hosting: proposta a Pretendo (issue "feature" con title ID, game server ID, access key, versione NEX) oppure self-hosting con `pretendo-docker`.

### Fase B – Funzioni NEX mancanti
- [ ] Comunità: `UpdateCommunity` (109/18) e `JoinCommunity` (109/19) non sono nelle implementazioni comuni di Pretendo; application buffer da 0x1b0 byte; seed delle comunità ufficiali.
- [ ] Ranking Race:
  - Ranking 112: `UploadScore`, `UploadCommonData`, `GetCommonData`, `GetRanking`, `GetStats` (quest'ultimo manca nelle implementazioni comuni);
  - DataStore 115 per i replay `REPLAY_DATA` (DataType 3, incluso `Prepare/CompleteUpdateObject`, mancanti) con storage S3/MinIO.
- [ ] Notifiche Pia (eventi 4000-4999) da verificare a runtime.

### Fase C – Grand Prix (Ranking Battle) via SIL
- [ ] Decodificare i formati dei circa 30 file (`001_Server_Status.bin`, tabelle punti, `*_Ranking_Pack.bin`, `*_Def_DLBattle.bin`…). Gli originali sono persi.
- [ ] Logica server: ricezione risultati (`GradeResultPack.bin` / `LimitResultPack.bin`), calcolo classifiche, calendario contest.
- [ ] Codici regalo: formato dei pacchetti `PresentCodePackageS%02u.bin` (probabilmente uguale ai pacchetti locali `PresentCodePackageR###.bin`).

### Fase D – Distribuzione
- [ ] Guida utente 3DS e Azahar, con patch generata per la versione tradotta.
- [ ] Deploy (Docker Compose) per SIL e, se self-hosted, per NEX e SpotPass.

---

## 5. Rischi

- **Grand Prix:** dipende da dati Square Enix andati persi; ricostruirlo richiede di decodificare formati non documentati.
- **Pretendo:** accetta contributi solo con una issue approvata, e i tempi non dipendono da noi.
- **Sicurezza SIL:** il service token non viene ancora verificato contro l'account server (TODO in `sil_server.py`). Prima di andare in produzione bisogna legare il Friend-Code SIL al PID.
- **Legale:** distribuire solo server, patch e strumenti. Mai ROM, CIA o i file originali scaricati (`re/data`, escluso da git).
