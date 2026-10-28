# DQMJ3P (code.bin v1.3) - uso dei protocolli NEX da parte del client

Fonte: reverse di `code.bin` (NEX 3.10.1 + Pia). Indirizzi = VA Ghidra. Nel progetto Ghidra ho rinominato (prefisso `nex_`) le funzioni chiave e salvato.
Legenda affidabilita: **[V]** verificato nel codice, **[I]** dedotto/probabile, **[?]** incerto/da verificare a runtime.

## 0. Come e fatto il client (utile per orientarsi)

- Livello gioco: `DAT_00898840` = network manager con "servizi" indicizzati (`FUN_0066eb80(mgr, idx)`): 2 = Pia/mesh, 3 = **servizio NEX** (state machine in `FUN_00666a54`, rinominata `nex_SvcNex_UpdateDispatch`), 6 = SIL (HTTP), 0xb = servizio "ranking" lato gioco, ecc.
- Le "NexCommand*" (Login, Gathering{Create,Join,End,FindById,Unregister,FindOfficial,FindByParticipant}, DataStore{Get,Post,Update,Delete,Search}, Ranking{DownloadList,DownloadStats,UploadScoreData,UploadCommonData,DownloadMyCommonData}) accodano uno "stato" nel servizio 3 (`FUN_00673ce8(svc,state)`); il dispatcher chiama lo stub NEX. Mappa stato -> chiamata NEX nella sez. 1.
- I protocol client NEX sono creati in `FUN_00667390` (case 3): **MatchmakeExtension client** (ctor `0x4a0ebc`, protocol 109; eredita MatchMaking 21 e MatchMakingExt 50), **Ranking client** (`0x468ad4`, 112) e un **DataStore client custom** (`0x75189c`, protocol 115, timeout 60000 ms, buffer 0x4000/0x8000). Nessun altro client applicativo (niente Utility, niente Ranking2, niente Subscriber).
- Gli stub RMC scrivono il method id con `FUN_004ba7ac(buf, id)` (`nex_Rmc_SetMethodId`) e il protocol id da `this+0x20`; invio con `FUN_0046e0a4`. Gli ID metodo che seguono sono quelli trovati nel codice; i nomi vengono dall'ordine dei metodi nella tabella di reflection del binario (0x89f1e9..), che coincide con la numerazione Kinnay/Pretendo.
- Il gioco usa anche un server HTTP **non-NEX** (SIL2 Square Enix) - vedi sez. 7.

## 1. Tabella riassuntiva (feature -> metodi -> priorita MVP)

| Feature gioco | Protocollo:metodo (id) | Punto nel codice | Priorita MVP |
|---|---|---|---|
| Login NEX | TicketGranting Login/LoginEx/RequestTicket (10) + SecureConnection Register(Ex) (11) [I] | `NexLoginJob_Start` 0x66c4ec -> `NgsFacade_LoginAsync_impl` 0x4bb718 | **Alta** |
| Battaglia amici (host) | MMExt109 `CreateMatchmakeSession` (6) | stato 4, `0x66b1e8` (chiamata `0x4a0b70`) | **Alta** |
| Battaglia amici (guest) | MMExt109 `BrowseMatchmakeSession` (4) + `JoinMatchmakeSessionEx` (30) + MM21 `GetSessionURLs` (41) | stato 5 `0x66bb2c`, stato 6 `0x66b6b8` | **Alta** |
| Battaglia random (free battle) | MMExt109 `AutoMatchmakeWithSearchCriteria_Postpone` (15) (+ GetSessionURLs 41) | stato 7 `0x6689ec` (chiamata `0x4a0abc`) | **Alta** |
| Fine/abbandono sessione | MMExt109 `CloseParticipation` (1) / `OpenParticipation` (2); MMExt50 `EndParticipation` (1); MM21 `UnregisterGathering` (2) | stati 9/8, 0xb/0x1a, 0x19 | **Alta** (rispondere OK) |
| Pia host migration | MM21 `UpdateSessionHost` (42), `GetSessionURLs` (41) | `0x4d1d80`, `0x4d2318`, `0x4d2710` | Media |
| NAT traversal | NATTraversal (3): `ReportNATProperties`(4), `ReportNATTraversalResult`(5), `RequestProbeInitiationExt`(3) (+ in ingresso InitiateProbe(2)) | Pia `0x4c684c`, `0x4c68b4`, `0x4a4668` | **Alta** (senza non si connettono i peer) |
| Community utente / ufficiali | MMExt109 `CreateCommunity`(17), `JoinCommunity`(19), `FindCommunityByGatheringId`(20), `FindOfficialCommunity`(21), `FindCommunityByParticipant`(22), `UpdateCommunity`(18, probabilmente non usata) | stati 0x16,0x18,0x1b,0x1c,0x1d,0x17 | Bassa (dopo MVP) |
| Ranking Race / Grand Prix / community battle ranking | Ranking112 `UploadScore`(1), `UploadCommonData`(4), `GetCommonData`(6), `GetRanking`(9), `GetStats`(11) | stati 0xd,0xc,0x10,0xe,0xf | Media |
| Replay Ranking Race | DataStore115 `PreparePostObject`(24)+`CompletePostObject`(26) (nuovo), `PrepareUpdateObject`(10)+`CompleteUpdateObject`(11) (update), `PrepareGetObject`(25), `SearchObject`(12), `DeleteObject`(4) | stati 0x12,0x13,0x14,0x15 | Media-bassa |
| Notifiche | Notification(14) `ProcessNotificationEvent`, NintendoNotification(100) (server -> client) | handler MMExt `0x4a0f48` (tipi 4000-4999) | Alta per ownership/participation [?] |

Non usati dal gioco (stub assenti o collegati solo per vtable): MatchMaking `RegisterGathering/FindBy*/Participate`, Utility, AccountManagement (stub linkati ma mai chiamati), DataStore `GetMeta(s)`, `RateObject*`, `PostMetaBinary*`, `GetNotificationUrl`, `GetPersistenceInfo`; Ranking `DeleteScore`, `GetRankingByPIDList`, ecc.

## 2. Login / connessione

- `NexLoginJob_Start`: game server id **0x1ACB00**, access key `L"5812c478"`, timeout 60000 ms. Il successo e controllato come QResult `0x10001`; codici di errore gestiti dal gioco: `0x8001000a`, `0x8001000b`, `0x80010004`, `0x80010002`, `0x80650000`, `0x80650002`, `0x80650009` (i 0x8065xxxx sono errori generati localmente da `LoginAsync_impl` quando FRD/NASC non e inizializzato o il PID non corrisponde) [V].
- `LoginAsync_impl` ottiene prima ticket/server da NASC (`frd_RequestServiceLocator` 0x52d868, `frd_RequestGameAuthentication` 0x52d97c): servono NASC (`nncs1/2.app.nintendowifi.net`, `n.app.nintendowifi.net`) e l'auth server NEX. Il gioco confronta il PID FRD con quello atteso (`0x80650009`) [V].
- Job di login (vtable `0x855c84`, passi `FUN_00479c98`): `FUN_00456f50` chiede a frd l'autenticazione NASC (`FUN_0052d1c8` -> `frd_RequestGameAuthentication`), `FUN_0045724c` attende l'evento frd (svc 0x24) e il risultato (`FUN_0052cec0`), `FUN_00456ab4` legge `FUN_0052d088` (+0 risultato 1, +4 HTTP 200, +8 host char[32], +0x28 u16 porta, +0x30 token char[256]) e la password NEX `FUN_0052c674` (0x20 B) e si connette all'auth server (`FUN_00454f9c`) [V].
- **Login senza NASC verificato in Azahar (2026-10-28)**: `make_url_patch.py --nex-auth 127.0.0.1:45000 --nex-password <PN_DQMJ3P_DEV_PASSWORD>` salta la richiesta/attesa frd e riscrive i due getter (host/porta fissi, token "t", password dev); `server/nex` in DEV mode accetta qualunque token di `LoginEx`. Log: Auth `LoginEx` (10/2, username = PID frd) -> `RequestTicket` (10/3) -> Secure `Register` (11/1) con PID 1446573338 e URL `prudp:/port=...;natf=0;natm=0;pmp=0;sid=15;...`. Il PID resta quello dell'account Pretendo (controllo `0x80650009`).
- Metodi esatti di TicketGranting/SecureConnection non individuati (le chiamate non passano da `FUN_0046e0a4`). Implementare lo stack standard Pretendo: `Login`, `LoginEx`, `RequestTicket`, `GetPID`, SecureConnection `Register`, `RegisterEx`, `UpdateURLs`, `ReplaceURL`, `TestConnectivity` [?].

## 3. Matchmaking (priorita 1)

### 3.1 Struct di parametri lato gioco (copiate nel servizio 3)

- **Create/Browse param** (0x12c byte) copiato in `svc3+0xa8` da `nex_SetCreateMatchParam_0x12c` (`0x669e78`) [V]. Layout (offset nella struct):
  - `+0x00 u32 gameMode`
  - `+0x04 u16 maxParticipants` (se <2 il gioco usa `*(DAT_00898840+0x38)`, impostato a **2** prima della chiamata)
  - `+0x06 u8` flag (random: 1, amici: 2) [I: probabile "anybody=1 / friends=2" di MatchmakeSystemType/ParticipationPolicy; il valore viene passato a `FUN_0014f51c` della MatchmakeSession]
  - `+0x08 u32` (0 in tutti i casi osservati; finisce in `MatchmakeSession+0xa8`) [?]
  - `+0x0c..0x10b` application buffer 256 byte (azzerato nei casi osservati)
  - `+0x10c..0x11b` attributi[0..3] (u32 ciascuno, usati nella Create)
  - `+0x11c..` min per attributi (browse) e max a `+0x12c..`/svc+0x1c4 (browse)
- **AutoMatch param** (0x160 byte) copiato in `svc3+0x1d4` da `nex_SetAutoMatchParam_0x160` (`0x66ade0`) [V]: stessa testa (gameMode, maxParticipants, flag, u32, app buffer 256 B @+0x0c), attributi[0..3] @+0x10c, poi 2 criteri di ricerca (stride 0x20: 4 min + 4 max) con un bool per criterio.

### 3.2 CreateMatchmakeSession (MMExt 6) - stato 4 `0x66b1e8` [V]
`MatchmakeSession` costruita con:
- description (Gathering) `"PiaInet Matchmake"`; minParticipants = **1**; maxParticipants = param; gameMode = param; attribs[0..3] = param (attribs[4],[5] default 0); applicationBuffer = 256 byte (vettore) dal param; `flags |= 0x10` (**DisconnectChangeOwner**) [I]; il flag byte del param passa a `FUN_0014f51c` (vedi sopra).
- Chiamata `CreateMatchmakeSession(sourceSession, strMessage = L"...", out gatheringId)`; il gioco poi usa gatheringId (`DAT_00898848`) e il campo `DAT_00898844` letto dalla risposta (`*(resp+8)->+0xc` = host/owner PID [?]).

### 3.3 BrowseMatchmakeSession (MMExt 4) - stato 5 `0x66bb2c` [V]
`MatchmakeSessionSearchCriteria`: gameMode (u32), `+0xac` u16 (maxParticipants/range), `+0xae` u8 (flag), systemType/u32 `+0xb0`, `FUN_004ab0c0(...,0)` (= "vacantOnly" false), attribs[0..3] come **range** (min da `svc+0x1b4+4i`, max da `svc+0x1c4+4i`; formato stringa tipo "min,max" costruito da `FUN_004ab0e8` [?]). `ResultRange`: offset 0, size 100 (`local_14=100`), `local_18=-1`.

### 3.4 JoinMatchmakeSessionEx (MMExt 30) - stato 6 `0x66b6b8` [V]
`JoinMatchmakeSessionEx(gatheringId = DAT_00898848, strMessage, bDontCareMyBlacklist, participationCount)` seguita da **MM21 GetSessionURLs(gid) (41)** per ottenere gli URL dell'host; risposta usata: MatchmakeSession (campo `+0xc` letto in `DAT_00898844`).

### 3.5 AutoMatchmakeWithSearchCriteria_Postpone (MMExt 15) - stato 7 `0x6689ec` [V]
Parametri: `lstSearchCriteria` = **2 criteri**; `sourceMatchmakeSession` (per creare la sessione se non esiste match) con description `"PiaInet Automatch"`, minParticipants 1, maxParticipants/gameMode/flag/attribs[0..3]/appBuffer 256 B come da AutoMatch param; `strMessage = L"AutoMatchmake message"`; risposta: `MatchmakeSession` (gid in `+8`, owner/host `+0xc`, `+0x18` vettore = application buffer o URL) copiata nel servizio. Il server deve: cercare per criterio 1 poi criterio 2, altrimenti creare la sessione dalla source e farvi entrare il chiamante (comportamento "Postpone" standard Pretendo).

### 3.6 Valori usati dalle scene (cosa mettere nei criteri)

- **Random battle ("misiramuhitofreebattle", scene `0x5c6db4`, classi init `0x5c69bc` singolo / `0x5c6ea4` doppio)** [V]:
  - `gameMode` = **2** (battaglia singola) o **3** (doppia) (`scene+0x158`), maxParticipants = **2**.
  - attribute[0] = punteggio forza del giocatore (`FUN_002472a4`, u32). Range di ricerca attribute[0] calcolato in `nex_RandomBattle_getMatchAttr` (`0x5c6a74`): `score * f` con f da tabella in base alla "completezza" (0..4) del party: criterio 0 (stretto) min/max in {1.0,0.95,0.9,0.8,0.7} / {2.0,1.8,1.6,1.4,1.2}; criterio 1 (largo) min/max in {0.9,0.8,0.7,0.6,0.5} / {2.2,2.0,1.8,1.6,1.4}. In pratica: il server deve supportare range numerici su attribs[0] e rispondere con un match se esiste una sessione con attrib0 dentro il range; **MVP semplice: accettare qualsiasi attribs[0] con stesso gameMode**.
  - attribs[1..3] = 0, app buffer = 0 (nei casi osservati).
- **Battaglia amici (scena `friendbattle` 0x5789fc, update `0x57701c`)** [V]: `gameMode` = **5**, maxParticipants = **2**, flag = **2**, attribute[0] = ID dell'amico/host (`scene+0xf8` per il guest, `FUN_0052c888()` = ID proprio per l'host; probabilmente PID/friend code a 32 bit); i criteri usano min=max=attribute[0]. Quindi host e guest si "incontrano" per uguaglianza di attribute[0]. Il codice per il guest ha il ramo "creator==0" -> chiama Create+Browse. Il server deve gestire Create (host) e Browse con criterio `attrib0 == X && gameMode == 5`, poi Join. [Il flusso esatto host/guest va confermato in test: potrebbe anche essere AutoMatchmake.]
- **Community battle** (`communitybattle`, scena `0x5dc85c`): usa `AutoMatch` (stesso `0x5fc41c`/`0x5fc714`) + Ranking GetStats/GetRanking + `FindCommunityByGatheringId`; gameMode/attributi da una virtuale `+0x1f8` della sottoclasse (non decompilata) [?].
- **Ranking battle ("wifirankingbattle")** [?]: non ho trovato un percorso di matchmaking dedicato; probabilmente passa dallo stesso `EstablishSession` (`0x675cc4`) con gameMode proprio.

### 3.7 Altri metodi sul gathering
- `CloseParticipation(gid)` / `OpenParticipation(gid)` (stati 9 / 8): chiamate a sessione piena/aperta; rispondere `true`.
- `EndParticipation(gid, strMessage)` (MMExt50:1, stati 0xb/0x1a) e `UnregisterGathering(gid)` (MM21:2, stato 0x19): rispondere OK; il server deve rimuovere il partecipante e, se host, cancellare/cambiare owner.
- `UpdateSessionHost` (MM21:42) e `GetSessionURLs` (MM21:41) da Pia `NexProcessHostMigrationJob` (migrazione host).

### 3.8 Community (Gathering* commands) [I/V]
Mappa comandi -> NEX:
| Comando gioco | Stato | NEX | Parametri (offset svc3) |
|---|---|---|---|
| GatheringCreate | 0x16 | CreateCommunity (109:17) | PersistentGathering in `svc+0x4ac`: **application buffer 0x1b0 (432) byte** (regole community: cfr. stringhe `RuleCommunity_Species/Level/Location/PartyRank/StandbyRankError`), password opzionale (stringa, flag a `+0x1c8` nella struttura gioco), messaggio |
| GatheringJoin | 0x18 | JoinCommunity (109:19) | gid (`+0x520`), password/stringa (`+0x524`), out community (`+0x52c`) |
| GatheringEnd | 0x1a | EndParticipation (50:1) | gid (`+0x534`), messaggio (`+0x538`) |
| GatheringUnregister | 0x19 | UnregisterGathering (21:2) | gid (`+0x540`) |
| GatheringFindById | 0x1b | FindCommunityByGatheringId (109:20) | lista gid (`+0x544`) |
| GatheringFindOfficial | 0x1c | FindOfficialCommunity (109:21) | bool (`+0x548`), ResultRange (`+0x54c`) |
| GatheringFindByParticipant | 0x1d | FindCommunityByParticipant (109:22) | pid (`+0x560`), ResultRange (`+0x564`) |
- Le community **ufficiali** (FindCommunity_FindOfficial, "osusume") vanno **pre-seminate** lato server come PersistentGathering ufficiali con application buffer di 432 byte nel formato regole del gioco (formato non ancora decodificato) [?].

### 3.9 Wi-Fi Ranking G-Cup ("Great Riders Cup", Ranking Race) [V, verificato in Azahar 2026-10-28]
- Banco Classifiche Wi-Fi -> "Classifiche Wi-Fi G-Cup". Prima volta: `FindCommunityByParticipant`(22) + `FindOfficialCommunity`(21, isAvailableOnly, range 0..20); la scena (`0x3ead74`) prende la comunita' ufficiale con `attribs[0] == 0` e `attribs[1] == FUN_00296340()` (settimane dal 2015-01-05 modulo 12, ora del server NEX), poi `JoinCommunity`(19). Con lista vuota resta per sempre su "Attendi..." (nessun errore). Volte successive: `FindCommunityByGatheringId`(20) con l'id salvato.
- Server: 12 comunita' ufficiali (`community_type` 2, attribs `{0,k,0,0,0,0}`) da `server/nex/sql/gcup_official_communities.sql`.
- **Application buffer (0x1b0) = definizione del torneo** [V]: dopo il join `FUN_00296234` lo copia in info G-Cup `+0x3c` (globale `0x89783c`). Campi (offset nel buffer): `+0x04` 3 x u16 specie dei 3 avversari CPU; `+0x0a` u16 restrizione (0 = nessuna, `FUN_002962d0`); `+0x6e` nome UTF-16 (`tb_gcupname`); `+0x90` u8 forza avversari 0..100 (<=33 Debole, 34..66 Normale, >66 Forte, `FUN_0029650c`); `+0x91` u8 ignoto (copiato su ogni avversario); `+0x92`/`+0x93` percorso (`coursename%d_%d` +1); `+0x94` evento (0 nessuno, 1 rocce bomba, 2 oggetti); `+0x95` flag "happening". Verificato: nome "G-Cup 5" e "Sfida Normale" mostrati dal gioco.
- **Crash con buffer a zero** [V]: la gara (`FUN_003cc478` stato 2) crea 4 corsie (giocatore + 3 avversari dal buffer) e conta i corridori fino alla prima specie 0 (`FUN_006e68b4`); la tabella delle animazioni d'ingresso `0x7c6268` e' vuota per 0-1 corridori, quindi con avversari a 0 `FUN_005849ec` chiama un oggetto fuori vettore (PC=0, LR `0x584bd8`) dopo le 2 monete di partecipazione. Con specie valide (71, 346, 442) la gara parte con 4 corridori.
- Fantasmi: dopo la classifica il task `FUN_003cb938` cerca i replay (DataStore `SearchObject`) dei primi in classifica e li scarica (`TaskNexDataStoreGetData`) in info G-Cup `+0x2c8` (3 slot, dataId a `+0x2d8`).
- Poi `Ranking::GetRanking`(9) categoria 29 (modo 0 = range, orderCalc 1, groupIndex 0xff, 0..100) due volte; `Ranking::NotFound` con classifica vuota e' gestito dal gioco (senza Ranking: 006-0103). Ranking implementato in `server/nex/nex/ranking.go` (Postgres `ranking.scores` / `ranking.common_data`).
- Registrazione: nome squadra con la tastiera del gioco, poi menu "Corri Forte! Great Riders Cup" (Partecipa alla Corsa / Modifica Profilo).
- **Dopo la gara** (`FUN_003741d4`) [V]: solo con vittoria (con sconfitta "MenuMessageRankingRaceLose" e nessuna chiamata) il gioco mostra il tempo e chiede se caricarlo (non lo chiede se il tempo e' peggiore del record locale). Upload: `Ranking::UploadScore`(1) categoria 29, punteggio = tempo in frame a 30 fps (2'04"43 -> 3733), poi `GetCommonData`(6) (NotFound ok), `UploadCommonData`(4) (nome squadra UTF-16 + dati), `GetRanking`(9) x2, `GetApproxOrder`(11).
- **Risultati e replay** (`FUN_00585f34`) [V]: scarica la classifica, mostra la "classifica istantanea" (verificato: "1° JEJ 2'04"43 Rank in!!"). Il replay si carica solo se la voce del giocatore (flag `+0x123`) e' nei primi 3 e ha esattamente il tempo di questa gara (nuovo record): `SearchObject`(12) del proprio replay, `DeleteObject`(4) se c'e', poi `TaskNexDataStoreSendData` = `PreparePostObject`(24, nome "REPLAY_DATA", dataType 5?, tag "CTR"/"2"/"EUR"/"83"/"IT") + POST HTTP multipart con corpo chunked + `CompletePostObject`(26). Il primo handler HTTP cercava una parte "file" e rispondeva 400 -> `isSuccess` false e 006-0526; ora prende la parte file o l'ultima parte (da riverificare con un nuovo record).

## 4. DataStore (115)

Il gioco usa DataStore **solo per i replay del Ranking Race** (stringa `REPLAY_DATA`) [V per Post, I per il resto]:
- **Post/Update** (`FUN_00678944`, cmd DataStorePost/Update): oggetto con nome **"REPLAY_DATA"** (buffer da 0x20 byte), **DataType = 3** (campo `param+0xa4 = 3`), payload = buffer fornito dalla scena (puntatore+dimensione, size nel campo `+0x32/0x33`). `dataId == 0` -> *Post* (PreparePostObject 24 + upload HTTP a RootUrl + CompletePostObject 26); `dataId != 0` -> *Update* (PrepareUpdateObject 10 + CompleteUpdateObject 11). Periodo/flag/permission/tag: non decodificati [?].
- **Get** (`vtable +0x118`): PrepareGetObject (25) con dataId (+ password 64 bit) poi download HTTP (`nn::http`) dall'URL ritornato; il server deve ritornare `DataStoreReqGetInfo` con `url`, `requestHeaders`, `size`, `rootCaCert` e servire il file.
- **Search** (`vtable +0x98`, stato 0x14 `0x66a574`): SearchObject (12) con DataStoreSearchParam; `resultRange` count 20 (0x14) [?], tag/lista u32 da `svc+0x678`, DataType 3.
- **Delete** (`vtable +0x64`, stato 0x15): DeleteObject (4) con `(dataId u64, updatePassword u64)`.
- Server: serve un endpoint HTTP per upload/download (stile S3 presigned) e metadati; nessun oggetto pre-seminato obbligatorio (replay "ufficiali" top-N potrebbero esserlo per la visualizzazione `ranking_race_view_replay`) [?].

## 5. Ranking (112)

Chiamate (tutte con `unique_id` / pid come da protocollo standard):
- `UploadScore(RankingScoreData, uniqueId)` (stato 0xd `0x668320`): `RankingScoreData{category u32 (+0x438), score u32 (+0x43c), order u8 (+0x440!=0), updateMode u8 (+0x444!=0), groups[2] u8 (+0x448,+0x449), param u64 (+0x450)}`. Dalla scena Ranking Race: uploaded con `order=1`, `updateMode=1` [V `0x5d55e8`].
- `UploadCommonData(commonData buffer 255 byte, uniqueId)` (stato 0xc, buffer in `svc+0x334`): dati utente (nome team, `ranking_race_userdata`) [I].
- `GetCommonData(uniqueId)` per il proprio (stato 0x10) = `DownloadMyCommonData` [I].
- `GetRanking(rankingMode, category, RankingOrderParam, uniqueId, pid)` (stato 0xe `0x667678`): `rankingMode` = 1 se flag comando ==1 (probabilmente "global around self") altrimenti 0; `RankingOrderParam{orderCalc u8 (0..2, default 2), groupIndex u8 (0xff default), groupNum u8, timeScope u8 (==1), offset u32, count u8 (default 10)}` [V campi, valori default in `FUN_0067ab10`: count 10, offset 0, orderCalc 2, group 0xffffffff].
- `GetStats(category, RankingOrderParam, out stats)` (stato 0xf).
- **Category** = `**(DAT_00897804+0x40)` (`FUN_006bec10`): id della "contest"/gara corrente, preso dai dati di gioco (probabilmente da `ranking_race_contest_info` scaricato da SIL o salvato) [?]. Il server deve accettare qualsiasi category (u32) e creare la classifica al primo upload.
- Come si identificano periodi/contest: non emerso dal codice NEX (nessun TimeScope/reset specifico, solo `timeScope`); probabile che il periodo sia incapsulato nella category [?].
- Tabella punteggi/ordine: ordine `order=1` (ascendente: tempi) per Ranking Race [I].

## 6. Notifiche e pia

- Il client MMExt gestisce eventi con `type` in [4000, 5000) (`0x4a0f48`: li memorizza in lista con deduplica per timestamp) [V]; i tipi standard NEX (Participation 3001.., OwnershipChange..., GatheringUnregistered) vengono consumati da Pia (`NexProcessHostMigrationJob`, `AutoMatchmakeJob`, `BrowseMatchmakeJob`). Servono: `ProcessNotificationEvent` (Notification 14) per **Participation** (host avvisato dell'ingresso del guest), **OwnershipChange / Unregistered** [?].
- Pia usa: `NexConnectStationJob` + `NatTraverser/NatDetectionJob` (richiedono i **NATCheckServers**: server UDP di nat-check raggiungibile, di norma sulla stessa macchina del secure server), protocollo NAT traversal NEX (3) con `RequestProbeInitiationExt`, `ReportNATProperties`, `ReportNATTraversalResult`, e **host migration** (`UpdateSessionHost`). Non ho trovato uso di NAT relay forzato (`NexNatRelay` e linkato ma solo `RequestProbe`).
- Heap Pia "pia inet heap", `setting.networkTopology` - topologia mesh/full-mesh 2 giocatori [?].

## 7. Server SIL2 (HTTP, non NEX) - fuori scope ma necessario al gioco

Il gioco parla anche con `https://dqm32ds.sil2.square-enix.com/00300701/` (lib SIL): endpoint `nuser/getnonce`, `nuser/register`, header `Authentication-Token`, `file/getproperties`, `file/download`, `file/upload` (comandi `NetworkCommandSIL{Login,UploadPublicData,UploadPrivateData,DownloadPublicData,DownloadPrivateData,GetPropertiesPublicData}`); `silInit(..., "3Ef7Db65775e4cCFDownload_Code")`. Serve verosimilmente per dati pubblici (mostri/take-over, contest info) e login CheckNetworkLogin prima del login NEX [?]. Anche `npdl.cdn.nintendowifi.net` (NSA) e SIL errors `SIL_ERR_*`.

## 8. Specifica minima per MVP lotte Wi-Fi (friend battle + random battle)

Cio che il server deve implementare (tutto il resto puo rispondere "NotImplemented/Core::Unknown"):

1. **NASC + Auth + Secure** standard 3DS (Pretendo): game server id `0x1ACB00`, access key `5812c478`, NEX 3.10.1. TicketGranting `Login/LoginEx/RequestTicket`; SecureConnection `Register/RegisterEx/UpdateURLs/ReplaceURL`. Il client verifica `0x10001` e un PID uguale a quello FRD.
2. **NATTraversal (3)**: `RequestProbeInitiationExt`(3), `ReportNATProperties`(4), `ReportNATTraversalResult`(5) -> risposta vuota/OK; in uscita `InitiateProbe`(2)/`RequestProbeInitiation`(1) verso il peer. + responder **NAT check UDP** (NatDetecter).
3. **MatchmakeExtension (109)**, risposte come Pretendo `matchmake_extension` common:
   - `CreateMatchmakeSession`(6): crea MatchmakeSession (gameMode, attribs[0..5], minP=1, maxP=2, app buffer 256 B, description libera, flags 0x10); ritorna sessione con gid, `owner=host=PID chiamante`, e la gestione dei `StationURLs` del chiamante.
   - `BrowseMatchmakeSession`(4): lista di MatchmakeSession che soddisfano il criterio `gameMode == X`, `attribs[i]` nell'intervallo [min,max] (stringa), non piena, aperta (`OpenParticipation`); range 0..100.
   - `JoinMatchmakeSessionEx`(30): aggiungi partecipante e ritorna `MatchmakeSession`; notifica **Participation** all'host.
   - `AutoMatchmakeWithSearchCriteria_Postpone`(15): cerca con la lista di 2 criteri; se non trova, crea dalla `sourceMatchmakeSession`; ritorna `MatchmakeSession` con `StationURLs`/sessionKey. (Per random battle e probabilmente per amici.)
   - `OpenParticipation`(2) / `CloseParticipation`(1): imposta stato apertura.
4. **MatchMaking (21)**: `UnregisterGathering`(2), `GetSessionURLs`(41) (ritorna gli URL "prudp" dell'host/partecipanti del gathering), `UpdateSessionHost`(42). **MatchMakingExt (50)**: `EndParticipation`(1).
5. **Notification (14)**: invio `ProcessNotificationEvent` per Participation / ownership change / gathering unregistered ai partecipanti [formato eventi standard Pretendo].
6. Server UDP **Pia**: nessun relay dedicato noto; i peer si connettono direttamente (P2P mesh a 2) dopo `GetSessionURLs` + probe.

Criteri di matching da rispettare per le due modalita:
- Random: `gameMode` 2 (singolo) o 3 (doppio), maxP=2, `attribs[0]` in [min,max] (due tentativi: stretto e largo). Semplificazione ammessa: ignorare i range attribs[0] e abbinare per `gameMode`.
- Amici: `gameMode` 5, maxP=2, `attribs[0] == ID host`.

## 9. Punti incerti / da verificare a runtime

1. Metodi di Login (Login vs LoginEx) e Secure (Register vs RegisterEx).
2. Se la battaglia amici usa Create+Browse+Join (stati 4/5/6) o AutoMatchmake (stato 7) - il codice contiene entrambi i percorsi (`0x57701c` scrive il Create param, `0x5fc41c`/`0x5fc714` scrivono l'AutoMatch param).
3. Significato esatto del byte `+0x06` e del u32 `+0x08` del param (MatchmakeSystemType/ParticipationPolicy).
4. Valori di `gameMode`/attributi di ranking battle, community battle (virtuale `0x1f8`).
5. Category/contest del Ranking e provenienza dello schedule (SIL?); DataStore: periodo/flag/permessi/tag; formato application buffer community (0x1b0 byte) e delle community ufficiali.
6. Tipi di NintendoNotificationEvent effettivamente richiesti da Pia (3001..3009 / 4000+) - solo la classe 4000-4999 e confermata nel client MMExt.
7. Formato esatto stringhe criteri attribs (FUN_004ab0e8) e `StationURLs` richiesti da Pia.

## 10. Funzioni rinominate (Ghidra, prefisso `nex_`)
`0x666a54 nex_SvcNex_UpdateDispatch`, `0x66b1e8/0x66bb2c/0x66b6b8/0x6689ec` (stati 4/5/6/7), `0x66ade0`, `0x669e78` (param copy), `0x667678/0x667c48/0x668320` (ranking), `0x66abd4/0x6699f4/0x66a574` (datastore), `0x4a0abc..0x4a0c9c` (wrapper MMExt), `0x4820b4/0x4820cc/0x48210c/0x482128` (MM/MMExt50), `0x4ba7ac nex_Rmc_SetMethodId`, `0x46e0a4 nex_Rmc_SendRequest`, `0x5c6a74 nex_RandomBattle_getMatchAttr` (funzione creata a mano), `0x5fc41c nex_Scene_StartAutoMatch`, `0x5960bc nex_Scene_StartCreateMatch_random`, `0x57701c nex_Scene_friendbattle_update`.
