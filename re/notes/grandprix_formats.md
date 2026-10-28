# Ranking Battle (Grand Prix) / Present Code - formati dei file SIL

Fonte: reverse di `code.bin` v1.3 (VA Ghidra). Legenda: **[CERTO]** verificato nel codice, **[PROBABILE]** dedotto da piu' indizi, **[INCERTO]** ipotesi.
Tool generatore: `re/tools/gp_files.py` (`python -I gp_files.py OUTDIR [--private-template] [--demo-ranking]`; `--selftest ROMFS_DATA`).
Tutti i valori sono little-endian. Download pubblici = `file/download` (tipo 3, flag 1: file mancante NON e' fatale, il buffer resta a zero); privati = `file/upload` con `Data="Download_Code"` (tipo 0, flag 1); upload privati = tipo 1 flag 1.

## 1. Oggetto "R" (stato Ranking Battle) e mappa dei buffer [CERTO]

`R = *(DAT_008977ec + 0x28)` (getter `FUN_002f6fa8`), costruttore `FUN_004204e8` (handle SIL a `R+0x5b3a4`). I file scaricati vengono scritti in questi offset (da `sil_RankingDownloadTables` 0x41fe68, `FUN_0042029c`, `FUN_004203e0`, `FUN_0042017c/022c`, `FUN_005b9464`, `FUN_00594630`):

| Offset R | Size | File | Note |
|---|---|---|---|
| +0x04 | 8 | 001_Server_Status | (0x42038c) |
| +0x0c | 0x14 | 003_Held_Record | copia usata per scrivere la data nel save (`FUN_002f7714`) |
| +0x20 | 0x14 | 003_Held_Record | seconda copia, scaricata a ogni ingresso (`FUN_00594630`) per il controllo "Invalid" |
| +0x34 | 0x2698 | 23_UserPackData (priv.) | vedi 3.9 |
| +0x26cc | 3*0xdd4 | 147/148_*_Def_DLBattle | |
| +0x5048 | 3*0xdd4 | 09/18_*_PrivateDlBattle (priv.) | |
| +0x79c4 | 0xdd4 | 171_Grade_Other_Countries | solo modo Grade |
| +0x8798 | 0x938 | 28W_Grade_Other_Countries (priv.) | |
| +0x90d0 | 0x848 | 018_LimitSetting | |
| +0x9918 | 0x28 | 600_CorrectPointTable | |
| +0x9940 | 0x54 | 009_WinPointTable | |
| +0x9994 | 0x3e | 029W_EvaluationPoint | |
| +0x99d2 | 0x58 | 008_PopularTbl | |
| +0x9a2a | 0x7fe | 144_Grade_Popular | (accessor `FUN_006cd58c` prevede 2 modi: Limit cade a +0xa228, mai scaricato -> zeri) |
| +0xaa28 | 2*0x1454 | 141/142_ChampionRecord | |
| +0xd2d0 | 2*0x19998 | 089/139_Ranking_Pack | |
| +0x40600 | 2*0x600 | 032/033_DLNewsMsg | consumatore non localizzato [INCERTO] |
| +0x41200 | 0xc4 | 00_UserData (upload) | |
| +0x412c4 | 0x540 | Grade/LimitResultPack (upload) | |
| +0x41808 | 0x19b98 | 04_UpdateSaveData (upload) | |
| +0x5b3a0 | 4 | PrivateSCRegister (priv.) | accessor `FUN_006cd9fc`, consumo non analizzato [INCERTO] |

Modo: byte `screen(0xd6)+0x10` (`FUN_002f8914`): 0 = Grade, 1 = Limit [CERTO]. Nel save, il record ranking e' `*(DAT_00897804+0x3c)`: `+0x50 + modo*0x3d8` (`FUN_006c3ab0`).

## 2. Flusso del menu Ranking Battle

1. NPC (`L00_00.nut: TalkWiFiRanking`, `MENU_OPEN.WIFI_RANKING`) -> schermata `connect.bflyt` (`FUN_003ca8cc` / `FUN_003caaa8` @0x3caaa8): chiama `sil_RankingDownloadTables` (tutti i download pubblici + `23_UserPackData`, `PrivateSCRegister`). Attende che la coda SIL sia vuota (`FUN_006cda14`) o in errore (`FUN_006cda24`). [CERTO]
2. `FUN_003cacc4`: per ciascun modo, se nel save il flag "registrato" (`rec+0x3d6`) e' != 0 ma `R+0xed` (= UserPackData+0xb9) e' 0 => messaggio `MenuMessageDeleteUserData` e cancellazione dati locali (`FUN_002f79d0`). Quindi per un utente gia' registrato il server DEVE restituire un `23_UserPackData` con byte 0xb9 != 0. [CERTO]
3. `FUN_003cb4b0` / `FUN_003cae8c`: "Special Present" (premio) letto dall'header di UserPackData: u16 a UserPack+0xfc (R+0x130): 0 = nessuno, 1 = oggetto (u16 id a +0xfe), 2 = struttura da 6 u16 (+0x102..+0x10c, `FUN_006cd750`), 3 = 4 u16 (+0x100..+0x106) + testo [PROBABILE].
4. Scelta Ranking Battle -> `FUN_00594630` (stato ingresso): scarica `001_Server_Status` e `003_Held_Record`(a R+0x20). Con `ok`:
   - se `puVar10[5]==0` (stato schermata) la data in Held (`R+0x24` u16 anno, `R+0x26` mese, `R+0x27` giorno) deve essere uguale a quella nel save (`rec+0x3d0`), altrimenti `MenuMessageInvalidRankingBattle` ("il torneo a cui partecipi e' chiuso, rientra") [CERTO].
   - `Server_Status[0]`: 0 = prosegue; 1,2 = `EndReception`; 3 = `AbnormalRankingBattle`; 4 = `NotOpenRankingBattle`; altro = Abnormal [CERTO].
5. Selezione modo -> `FUN_0044b27c`: N = Held+0xc (R+0x18). Se N != `rec+0x3c8` il record del modo viene azzerato (nuovo torneo). Se N>=2, N-rec.N==1, `rec+0x3c6`!=0 (aveva partecipato) e pack[modo]+0x808 != 0 e UserPack[modo]+0x1098 != 0 => schermata risultati di ieri (0xea). Altrimenti schermata 0xd6/0xe9 (nuova iscrizione, `FUN_002f7714` scrive data/N/flag di Held nel save) [PROBABILE].
6. Iscrizione: upload `00_UserData.bin` (0xc4, `FUN_005b9464`) [CERTO].
7. Scelta avversario (`FUN_005b90cc`/`FUN_005b8d24`): 3 scelte (indice 0 = difficile, 1 = simile, 2 = facile, dal menu in gioco). Le scelte sono abilitate in base a `UserPack mode block +0x3c / +0x40` (`FUN_0041fe24`) [PROBABILE].
8. Avversari: `FUN_005f97b8`: se `PrivateDlBattle[1]` (R+0x5e1c, 16 byte) non e' tutto zero usa `R+0x5048+idx*0xdd4` (privato), altrimenti `Def_DLBattle` (`R+0x26cc+idx*0xdd4`). `FUN_002f66b8` -> `FUN_003e8d3c` copia 3 team da 0x49c in battaglia (`FUN_003e8d88`). [CERTO]
9. Battaglia, poi `FUN_005a3c5c` (post-battaglia): bit0 di `screen+0xdc`: costruisce (`FUN_002f7c64`) e carica `GradeResultPack.bin`/`LimitResultPack.bin`; bit1: `FUN_002f7444` + upload `04_UpdateSaveData.bin`; bit2 (solo Grade): scarica `171_Grade_Other_Countries` + `28W_...` e li fonde nel save (`FUN_002f7a6c`). [CERTO] Se non si carica, il messaggio dice che i ticket vengono consumati ma il risultato non finisce in classifica.
10. Classifiche: `FUN_005dba50` (3 pagine da 10 dal blocco 0 del pack), `FUN_0060bcc4` (per area/prefettura), `FUN_00602424` (ChampionRecord), `FUN_005a4548` (stima posizione di domani da ResultPack + pack), `FUN_005cb284/5cb584` (annunci top 10), `FUN_005b4a2c` (risultati correnti/precedenti), `FUN_00585468` (`NotChampion` se count==0). [CERTO per le chiamate]
11. Ticket: `MenuMessageReceiveTicket`/"participation tickets this week": `Server_Status[4]` e' il numero di ticket (u8) scritto in `rec+0x3c2` quando `rec+0x3c5==0` (`FUN_00572a60`) [PROBABILE]. Il ciclo e' settimanale (messaggi "this week", "final day").

**Con TUTTI i file mancanti** (FILE_NOT_EXIST non fatale) i buffer restano a zero: Server_Status=0 => aperto, Held=0 => data 0000-00-00 uguale a quella del save azzerato, N=0, ranking vuote, tabelle punti 0, MA gli avversari sono team vuoti (nessuna specie valida) => la battaglia non e' utilizzabile [PROBABILE]. Serve quindi almeno `*_Def_DLBattle`.

## 3. Formati

### 3.1 001_Server_Status.bin (8) [CERTO byte0, PROBABILE byte4]
`+0 u8 state` (0 open, 1/2 reception closed, 3 anomaly, 4 not open), `+4 u8 tickets` (settimanali). Resto 0.

### 3.2 003_Held_Record.bin (0x14)
| Off | Tipo | Significato |
|---|---|---|
| +0 | u32 | indice 0..6 in `600_CorrectPointTable` [CERTO]; significato = giorno della settimana [PROBABILE] |
| +4 | u16 | anno [CERTO] |
| +6 | u8 | mese [CERTO] |
| +7 | u8 | giorno [CERTO] (data torneo = id del "periodo": confrontata con `rec+0x3d0`: u16 anno, u8 mese, u8 giorno) |
| +8 | u32 | flag: 0 => `FUN_006cd8a0` richiede N>=2 e usa il blocco "precedente" (pack+0x808), !=0 => blocco corrente; copiato in `rec+0x3cc` [PROBABILE] |
| +0xc | u32 | numero torneo N (>=1; confrontato con `rec+0x3c8`) [CERTO] |
| +0x10 | u32 | non usato/ignoto [INCERTO] |

Il periodo e' identificato da (data, N). Per cambiare giorno basta incrementare N e aggiornare la data: i giocatori col N vecchio vengono azzerati (44b27c) e vedono i risultati di ieri se N-rec.N==1.

### 3.3 Tabelle punteggio (calcolo lato client in `FUN_002f5944/5b28/6298/6980/65b4`) [CERTO struttura, valori ignoti]
Punti per team = (win + popolarita' + differenza di forza + valutazione) * `CorrectPoint[Held+0]` * `CorrectPoint[7+scelta_avversario]`.
- **600_CorrectPointTable (0x28)**: `float[7]` (moltiplicatore per Held+0) + `float[3]` (a +0x1c, per scelta avversario 0..2).
- **009_WinPointTable (0x54)** = `u32[21]`: 10 coppie (soglia, punti) con soglie crescenti: la prima con diff<=soglia (diff = forza avversario - forza giocatore, somma `FUN_00247444` sui 4 mostri; diff<=0 => 0 punti) da' i punti; `u32` a +0x50 = punti base vittoria (`FUN_002f5b28`).
- **029W_EvaluationPoint (0x3e)** = `u16[31]`: [0..10] per indice battaglia (`battle+0x28 + (battle+0x3c!=0)`), [11..20] bonus per bucket (10 - int(ratio1*10)), [21..30] idem ratio2 (`battle+0x2c/+0x30` float) [PROBABILE].
- **008_PopularTbl (0x58)**: per modo 0x2c byte = 11 coppie `(u16 soglia_media_popolarita, u16 punti)`; si ferma alla prima coppia con punti==0; prima coppia con media<=soglia vince (`FUN_002f6980`) [CERTO].
- **144_Grade_Popular (0x7fe)** = `u16[1023]` popolarita' per specie (mostrata/ordinata se <=10000, `FUN_0065e598`, top 20 -> schermata "mostri popolari") [CERTO].

### 3.4 018_LimitSetting.bin (0x848) [CERTO, verificato in gioco 2026-10-26]
`+0`: 3 regole `(u32 tipo, u32 valore)` verificate da `FUN_002f7e9c` su ogni mostro della squadra (solo GP dello Sfidante); se una fallisce: "Alcuni mostri nella squadra non rientrano nei criteri di registrazione".
- 0 = taglia (`FUN_006bfe90`: tratto 0x46..0x4a se presente -> 0..4, altrimenti `KindParam` +0x30: 0/1 piccola, 2 media, 3 gigante, 4 mega; valore 0 accetta anche 1) [CERTO: la squadra JEJ ha il tratto 0x47 su tutti i mostri e passa 0:0 pur avendo specie di taglia 2]
- 1 = famiglia, `KindParam` +0x23 (`FUN_00661088`): 1 Slime, 2 Drago, 3 Bestia, 4 Natura, 5 Demone, 6 Non-morto, 7 Materiale, 8, 9 [CERTO tabella, nomi dal randomizer]
- 4 = classe di rango (`FUN_006bfdec`: rango specie `KindParam` +0x22, 1..8 = F..SS, alzato dal livello: 25-49 -> 4, 50-99 -> 6, 100 -> 8). In gioco: 4:8 accetta una squadra SS+ al livello massimo.
- 5 = grado massimo della squadra: `FUN_002473c0` sulla forza totale (`FUN_00247444`): 1..8 per <4000, <8000, <12000, <18000, <32000, <46000, <74000, oltre. In gioco: 5:1 rifiuta la squadra SS+.
- 9 = nessun vincolo; qualsiasi altro tipo rifiuta tutto.
`+0x18` (R+0x90e8, 0x520 B): testo UTF-16LE con la descrizione regole, mostrato col tasto Y (説明) nel menu GP (`FUN_0044b1b0`) [CERTO]. Il tema compare entrando nello Sfidante solo se un flag del save e' 0 (`FUN_00572e1c` -> `FUN_006c3b5c`). Server: rotazione per torneo `LIMIT_RULE_SETS` in `sil_server.py` (anche `033_Limit_DLNewsMsg` = tema + regola); `--gp-limit-static` per servire il file statico. `+0x538` (R+0x9608, 0x310 B): testo UTF-16LE del tema, mostrato entrando nel GP dello Sfidante dopo "Annuncio del titolo dei Challenger GP" [CERTO]. Generatore: `gp_files.py --only 018_LimitSetting.bin --limit-rule TIPO:VALORE ... --limit-text ... --limit-theme ...` (il server legge il file a ogni richiesta; il gioco lo scarica alla connessione).

### 3.5 032/033_*_DLNewsMsg.bin (0x600) [CERTO]
Testo UTF-16LE mostrato nel menu del GP: Notizie -> "ULTIME INFORMAZIONI" (verificato in gioco con la frase di `gp_files.py`).

### 3.6 089/139_*_Ranking_Pack.bin (0x19998 = 51 blocchi da 0x808) [CERTO, verificato in gioco 2026-10-26]
Per modo (stride 0x19998). Blocco k a `pack + k*0x808`: `k=0` classifica generale del torneo in corso fino a ieri (3 pagine da 10, `FUN_005dba50`), `k=1` classifica finale del torneo precedente (annuncio top-10 a fine torneo, `FUN_005cb584` "RankingBattleEnd"/"AnnounceTopTen"), `k=2+loc` classifica per localita' `loc_000..046` (`FUN_0060bcc4`, `FUN_006cd684`; solo prefetture giapponesi: l'Italia = 76 non ha blocco). Un blocco "esiste" se la prima u32 della voce 0 e' != 0 (`FUN_006cd8a0`). Ogni blocco = 30 voci da 0x44 + 0x10 byte finali (ignoti, 0). Voce (0x44) (`FUN_002f5624`, `FUN_005d4638`, disegno `FUN_0043f3d4`):
- +0x00..0x1f: id [INCERTO]; il server mette +0 u32 = rango (non zero), +8 u32 = posizione (1..n, usata per evidenziare la riga dell'utente in "La tua classifica": indice = UserPack.mode+8 - voce0+8), +0x10 friend code SIL
- +0x20 u16 punti (cumulativi del torneo; `FUN_005a4548` li confronta con i punti dell'utente per stimare il rango di domani)
- +0x24 u16 localita' `loc_NNN` (bandiera), +0x26 u8 vittorie, +0x27 u8 sconfitte (colonna V/S)
- +0x28 u32 rango precedente, +0x2c u32 rango: freccia su/giu' (`FUN_005b85a0`: prev 0 = nessuna, prev > rango = su), rango mostrato
- +0x30 nome UTF-16LE (0x14 B = 10 caratteri)

**Calendario** (`003_Held_Record`): un torneo = 7 giorni (`Held+0` indice del giorno 0..6), N = numero del torneo, data = giorno corrente. `Held+8` = 0 il primo giorno (nessuna classifica: il gioco controlla solo N>=2 e il blocco 1 e dice "nuova competizione iniziata oggi"), 1 dagli altri giorni (serve il blocco 0: "le classifiche di oggi sono disponibili"). L'iscrizione vale per la data: se il giorno cambia prima del caricamento dei risultati il gioco dice "Verrai rimosso dal Torneo" e non carica. [CERTO, Azahar]

Server (`sil_server.py`, `GpCalendar`): `--gp-start` (default 2026-10-26), `--gp-days` (7), `--gp-utc-offset` (default fuso del PC), `--gp-today` (test). Punti = somma di tutti i `ResultPack` del torneo (un biglietto = 3 round); classifica pubblicata ogni giorno con i giorni precedenti; `gp_results.day` = giorno di caricamento.

### 3.7 141/142_*_ChampionRecord.bin (0x1454) [CERTO layout]
`u32 count` a +0 (numero di campioni, max 100 mostrati, `FUN_00602424`; 0 => `MenuMessageNotChampion`). **Le voci da 0x34 partono da +0** (voce i a file + i*0x34): il contatore occupa i primi 4 byte della voce 0 [CERTO, verificato in gioco: con le voci a +4 i campi risultano sfasati]. Dalla piu' recente: il gioco le numera "torneo count, count-1, ..." (`FUN_005d46a0`, colonna "Torneo": "Numero WMC N"). Voce: +0..7 ignoto (0; voce 0: count), +8 u32 localita', +0xc u32 punti, +0x10 u8 vittorie, +0x11 u8 sconfitte, +0x14 nome UTF-16LE 0x20 B. 100*0x34+4 = 0x1454.

**Fine torneo (verificato in gioco, `--gp-today` = primo giorno del torneo 2):** entrando nel GP: "Il 1° torneo ... e' terminato", "Per prima cosa, annunceremo i primi 10!" (blocco 1 del Ranking_Pack), "Sei arrivato tra i primi 10" (UserPack +0x1098 rango <= 10), "Ecco i tuoi risultati!", schermata "Congratulazioni! Sei diventato Campione n°1" (rango 1), "non ci sono premi per aver raggiunto questo rango" (Special Present = 0, vedi 3.9), poi ricarica dei biglietti settimanali. L'annuncio compare una sola volta (il gioco salva di averlo mostrato).

### 3.8 Squadre avversarie: *_Def_DLBattle / *_PrivateDlBattle (0x297c) [CERTO struttura]
`3 entry (scelta avversario 0,1,2) * 0xdd4`; ogni entry = `3 team * 0x49c` (3 combattimenti consecutivi: `FUN_003e8d3c` itera 3 volte). Team (0x49c) (da `FUN_002f7a6c`, `FUN_002f5fa0`, `FUN_002f4f1c`):
| Off | Size | Significato |
|---|---|---|
| +0x00 | 0x14 | id del proprietario [INCERTO, mai letto dal client]. **I primi 16 byte della entry 1 di `PrivateDlBattle` devono essere != 0**, altrimenti il file privato e' ignorato (`FUN_006cd8f4`). Il nostro server ci mette il friend code SIL (ASCII). [CERTO il controllo] |
| +0x14 | 2 | u16 localita' `loc_NNN` (`LocationMessage.mes`) + bandiera (`FUN_0028be4c`); = `00_UserData+4` (76 = Italia "ITA", 0 = Giappone "Hokkaido") [CERTO, Azahar 2026-10-26] |
| +0x18 | 4 | u32 numero mostrato accanto al round nella lista avversari (`tb_battle_counter`, `FUN_005a5bf8`) [CERTO lettura, semantica INCERTA; 0 va bene] |
| +0x20 | 0x24 | nome allenatore UTF-16LE [CERTO] |
| +0x44 | 1 | marchio principiante (`Null_beginner`, `FUN_005a5bf8`) = `00_UserData+0xb8` [CERTO] |
| +0x45 | 1 | flag "ha Mii/profilo" = `00_UserData+0xba` [CERTO] |
| +0x46 | 4 | u32 [INCERTO, 0 va bene] |
| +0x4a | 5 | 5 byte del profilo (`FUN_00176fb0`: u32 + u8) = `00_UserData+0xbb` (profilo+0xc4) [PROBABILE] |
| +0x50 | 0x88 | Mii/profilo (letto solo se +0x45!=0, `FUN_0066193c`) = `00_UserData+0x30` [PROBABILE] |
| +0xd8 | 0x3c4 | record squadra del save: 4 mostri da 0xf0 + 4 byte = `ResultPack[0x17c:0x540]` [CERTO, Azahar 2026-10-26] |

Entry (menu `FUN_005b8d24`, righe 0..2): 0 = "Sfida un avversario difficile", 1 = "simile", 2 = "facile" [CERTO testo menu IT]. Il gioco valuta da solo la forza (messaggio "sembra un avversario molto impegnativo"). Server: `sil_server.py` costruisce `09/18_*_PrivateDlBattle` dalle ultime squadre (`gp_results`) degli altri giocatori dello stesso modo, ordinate per una forza approssimata (stat + livello; quella del gioco, `FUN_00247444`, usa anche specie/abilita'); i round senza squadre restano quelli di `Def_DLBattle`. Verificato in gioco: nome, bandiera e mostri caricati e combattono.

Mostro (0xf0, formato save): `+0x1c s16 specie` (valida se `MonsterParam[specie]+0x32 != 0`), `+0x1e HP max, +0x20 MP max, +0x22 HP att, +0x24 MP att, +0x26 ATK, +0x28 DEF, +0x2a AGI, +0x2c WIS` (s16), `+0x3c u8 livello`, `+0x44` 9 s16 (tratti/abilita'), `+0x72` nome [PROBABILE], `+0xe0/+0xe4` equip. Le stat dell'avversario sono scalate in `FUN_003e8d88` (se la tua forza < avversario) e modificate da accessori/abilita'. Il generatore crea mostri con solo specie/livello/stat (**GUESS** che bastino); per dati reali: costruire il team dal `ResultPack` (3.10) del giocatore (ultimo 0x3c4 byte) + nome da `00_UserData`.
`PrivateDlBattle`: se tutto zero (primi 16 byte della entry 1) viene ignorato e si usa Def.

### 3.9 23_UserPackData.bin (0x2698, privato) [PARZIALE]
Header 0x110 + 2 blocchi modo da 0x12c4 (Grade a +0x110, Limit a +0x13d4): 
- `+0xb9` u8: "utente registrato sul server" (`R+0xed`) [CERTO]
- `+0xc4..0xe0` e `+0xf8/+0x114` (0x1c per modo): dati scritti nel save (`FUN_002f7714`: u32 a +0, u16 a +0x18) [INCERTO]
- `+0xfc` u16: tipo Special Present (`FUN_003cb4b0`, `FUN_003cae8c`): 1 = oggetto, id u16 a +0xfe (chiave `I%04d` di `ItemMessage.mes`) [CERTO, in gioco: "SQEX ti ha inviato un regalo speciale! Grande Sfera di Luce"]; 2 = mostro (specie +0xfe, 6 u16 a +0x102..+0x10c); 3 = schermata premio con 4 u16 a +0x100..+0x106. Consegnato una volta per torneo: flag nel save (`FUN_0036a848`, save+0x48) azzerato quando Held N supera il torneo salvato (`FUN_003caaa8`).
- blocco precedente (+0x1098 del blocco modo) `+0x44` u16 = 3 => a fine torneo "Hai guadagnato alcune Monete di Rete!" + Monete: `+0x48` platino, `+0x4a` oro, `+0x4c` argento, `+0x4e` bronzo (`FUN_005cb39c`, `FUN_005cb0ac`, `FUN_002f84d0`, `FUN_0065baa0`) [CERTO, in gioco: "×3 Monete d'Oro"]; altrimenti "non ci sono premi per aver raggiunto questo rango".
- blocco modo (`FUN_0041fe24`) [CERTO, verificato in gioco]: `+0` u32 rango (0 = non in classifica), `+4` u32 giocatori in classifica [PROBABILE], `+8` u32 posizione, `+0x10` u32 numero torneo, `+0x14` punti vittoria, `+0x18` popolarita', `+0x1c` forza, `+0x20` valutazione (cumulativi fino a ieri; schermata risultati `FUN_005b4a2c`: vittoria / valutazione / popolarita'+forza / totale), `+0x24` u32 round giocati, `+0x28` u32 round vinti; `+0x3c/+0x40` u32 scelte avversario evidenziate (0 = nessuna); `+0x44` ignoto (`FUN_006cd6fc`); `+0x88` 10 voci di classifica (0x44) intorno all'utente per "La tua classifica" (`FUN_002f6b80`; prima u32 != 0 = presente); `+0x1098` stessa struttura di +0 per il torneo precedente (`+0` rango <=10 => "sei nella top ten", `+0x10` numero torneo; `FUN_005cb284`, `FUN_005b4a2c`). Se file assente: tutto zero = "nessun dato" (valido per nuovi utenti).
`PrivateSCRegister.bin` (4) [INCERTO]; `28W_Grade_Other_Countries` (0x938 = 2 team) e `171_Grade_Other_Countries` (0xdd4 = 3 team) stessi team-block, fusi nel save da `FUN_002f7a6c` (non necessari).

### 3.10 Upload [CERTO]
- **00_UserData.bin (0xc4)** (`FUN_002f7618`) [CERTO layout]: `+0` 0, `+4` u32 localita' `loc_NNN` (u16 profilo+0x58, `FUN_006b6238`), `+8` u32 (modo==Limit), `+0xc` nome 0x24 B (da `save+0x3c` [0]), `+0x30` Mii 0x88 B (profilo+100), `+0xb8` u8 principiante (rec+0x3c3<4), `+0xb9` u8=1, `+0xba` u8 Mii presente (profilo+0x60), `+0xbb` 5 byte (profilo+0xc4), resto 0.
- **Grade/LimitResultPack.bin (0x540)** (`FUN_002f7c64`): `0x17c` risultato + `0x3c4` record squadra del giocatore. Risultato: `+0 u8 =3`, `+2/+4/+6/+8 u16` somme punti (popolarita', forza, valutazione, vittoria), `+0xc u32` totale (somma delle 4 voci su 3 team = PUNTEGGIO), `+0x10 u16`, e a `+0x14 + i*0x78` 3 riepiloghi team da 0x78 (`FUN_002f5fa0`): `+0` nome avversario 0x24, `+0x24` testata avversario 0x1c (contiene il friend code messo dal server), `+0x40 u32` 1 = round vinto, `+0x44 u32` punti vittoria, `+0x48/4a/4c u16` punti pop/forza/valutazione, `+0x4e u8`, `+0x50/+0x54 u32`, `+0x58` **HMAC-SHA256** di 0x58 byte con chiave `RESULT_HMAC_KEY` (nel gp_files.py; `FUN_001628b0`+`FUN_002f5fa0`). Il client non verifica nulla in ricezione: la HMAC serve al server anti-cheat (opzionale).
- **04_UpdateSaveData.bin (0x19b98)** (`FUN_002f7444`): regioni del save, offset buffer <- offset save (len): 0x0<-0x8 (0x2c0); 0x2c0<-0x1de44 (0x208); 0x4c8<-0x1e04c (0x92e); 0xdf8<-0x1e97c (0xc88); 0x1a80<-0x1f604 (0x51c); 0x1f9c<-0x1fb20 (0x68); 0x2004<-0x1fb88 (0x88c); 0x2890<-0x20418 (0xb20); 0x33b0<-0x20f38 (0x20); 0x33d0<-0x20f58 (100); 0x3434<-0x20fbc (0x20); 0x3458<-0x20fe0 (0x13c08); 0x17060<-0x34be8 (0x1e44); 0x18ea4<-0x36afc (0x2a0); 0x19148<-0x36da0 (0x18); 0x19160<-0x36db8 (0xa34). Il server puo' semplicemente memorizzarlo.

## 4. Minimo per usare la feature [PROBABILE]

Server SIL gia' funzionante (register/login/file). File necessari (gli altri possono mancare -> FILE_NOT_EXIST):
0. `030_GP_WallPapers.arc` [CERTO, Azahar 2026-10-26]: prima delle tabelle la schermata (`FUN_003cac04`) fa `getproperties` + download di questo archivio SARC e, se presente, ne carica `download.bflyt`. Con `FILE_NOT_EXIST` il job SIL (stato 8) va in errore e la schermata resta su "Attendi un momento...". Va bene una copia di `romfs:/data/Layout/menu/wifi_ranking_battle/upper/download.arc` (file del gioco: copiarlo dal proprio RomFS, non distribuirlo).
1. `001_Server_Status.bin` (byte0=0, byte4=ticket)
2. `003_Held_Record.bin` (data odierna, N>=1)
3. `147/148_*_Def_DLBattle.bin` con specie valide (3 entry x 3 team)
4. `600/009/029W/008` (altrimenti i punti sono 0: funziona ma tutte le battaglie danno 0 punti)
5. Upload `GradeResultPack`/`LimitResultPack`/`00_UserData`/`04_UpdateSaveData` accettati con `Result=OK`.
6. Per mostrare classifica: `089/139_Ranking_Pack` (anche vuoti). Per utenti registrati: `23_UserPackData` con byte 0xb9=1.

Logica server: (a) a ogni upload di `00_UserData` registrare l'utente; (b) a ogni ResultPack leggere punteggio (`+0xc u32`) e record squadra (`+0x17c`, 0x3c4); tenere il miglior punteggio per (modo, periodo N); (c) a fine giornata (incrementare N + data in Held) ordinare per punteggio e costruire `*_Ranking_Pack` (blocco 0 = top 30, blocchi location = per `UserData` regione, voci da 0x44 come in 3.6), `23_UserPackData` per utente (posizione, punteggi di ieri), `ChampionRecord` (+1 e vincitore); (d) costruire gli `*_Def_DLBattle` scegliendo 3 squadre (debole/pari/forte) dagli ultimi ResultPack: team block = testata 0 + nome + profilo + `ResultPack[0x17c:0x540]` a +0xd8, 3 team per entry.

## 5. Present Code [CERTO se non indicato]

- Server: `PresentCodePackageS%02u.bin` (%u = numero pacchetto dato dalla risposta `present_code.bin`), buffer client 0x17c ma e' un massimo: il client copia solo la dimensione dedotta dal tipo (sotto). Controllo `FUN_006c4918`: magic "BPCP" (0x50435042), versione 0x1000, e **HMAC-SHA256 degli ultimi 32 byte** (chiave indicata da `u32@0x10`, indice 1 = `21dc24dd6a48fde68c934832a87b1762b522031cadf4f53f9e21ea8eed3ccc2d`; indice 0 = `2f4cb04e16f37be07961ab83fd88fdf3675d6ebb35041c820e6735ba78c0638e`) calcolata sui byte `[0:size-32]`. Verificato su tutti i 115 pacchetti locali.
- Locale: `patch:/data/PresentCode/Package/PresentCodePackageR%03d.bin` (`FUN_0030eb4c`) stessa struttura. Il codice digitato e' cercato in `PresentCodeROMCode.bin` (`FUN_0030ded0`): **AES-128-CTR** (chiave LE `90bc1182e5aaf96d55752cf7be4bfcd9`, counter iniziale = IV LE `d0733b8cdbdbc0e3a9c6950ef8025561`) -> sorgente Squirrel Shift-JIS `TABLE_LIST`/`TABLE_ROMCODE_NNN <- { id = N code = "..." }` (115 tabelle). Confronto stringa esatto (U+301C sostituito con U+FF5E); se uguale -> pacchetto R`id`. Nessun checksum del codice: nel RomFS inglese le stringhe sono placeholder (`熙NNN`) per gli id >= 99; i codici veri (ids 1..98) sono i testi giapponesi nel file. Le tabelle `id=0 code="開発用"` = terminatore.
- Layout pacchetto: `+0 "BPCP"`, `+4 u32 0x1000`, `+8 u32 id`, `+0xc u32 tipo`, `+0x10 u32 indice chiave (1)`, `+0x14..0x1f` zeri. Size dedotta (FUN_00388df8): tipo 0 = disco/mostro: `0x54 + n*0x48` con `n = u8 @+0x20` (record da 0x48 = template mostro come i "record B" di BossPresentDisc; +0x24 e' un item da 16 B), tipo 1 = sfondo `0x44`, tipo 2 = oggetto `0x48`: `+0x20 s16 item_id`, `+0x22 s16 quantita'`, `+0x24 u32 0`, `+0x28 HMAC`. Gli R101..R115 (80 byte) hanno `0xfc*8` di padding prima della HMAC: con size 0x48 la verifica fallisce => voci inutilizzabili/placeholder [PROBABILE]. `gp_files.make_present_package(id, item, count)` riproduce byte-per-byte `R003`.
- Messaggi: `presentcodemes_GetDisc` (tipo 0), `_GetWallpaper` (tipo 1), `_GetNow`/`_GetNowPlural` (tipo 2, plurale se quantita'>=2).

## 6. Altro trovato nel RomFS
`data/Parameter/GrandprixCpu.tp` (magic "GCPC", 0x30 header + 6 record da 0x2c: nome Shift-JIS 12 B, u16, 12 u16) = squadre CPU del Grand Prix locale (non usate dai file SIL) [PROBABILE]. `MonsAuthKey.bin`/`MonsCheckKey.bin` (4096 B) appartengono ai controlli mostri NEX.
