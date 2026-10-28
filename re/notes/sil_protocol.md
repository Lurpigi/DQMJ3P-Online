# Protocollo SIL (Square Enix) in DQMJ3P v1.3 - note di reverse engineering

Convenzioni: VA = 0x100000 + offset in code.bin. Le funzioni citate sono state rinominate in Ghidra con prefisso `sil_` / `silXxx`.
Legenda: [CERTO] = letto direttamente dal codice; [PROBABILE] = dedotto; [INCERTO] = da verificare.

---------------------------------------------------------------------

## 1. Trasporto

**Metodo**: sempre `POST` [CERTO]. Il worker `sil_HttpWorker` (0x603a10, thread avviato da `silIfSendRequest` 0x740ee8 via FUN_0044fb14) chiama `FUN_00524500(httpCon, url, 2, 1)`; 2 = POST. Non esiste GET.

**URL finale** [CERTO]: `sil_GetServerURI` (0x1b4fd4) restituisce il buffer a VA 0x8bf6d4. Il worker fa `strcpy(buf, base)` + `strcat(buf, endpoint)` (FUN_002fec40 / FUN_001003f2), limite 255 caratteri totali.
Base = quella impostata da `silSetServerURI` (0x741310 -> FUN_001b9684, copia se len < 0x80).
Quindi, con la base reale: `https://dqm32ds.sil2.square-enix.com/00300701/` + endpoint; il trailing slash e' obbligatorio. Esempi:
- `.../00300701/nuser/register`
- `.../00300701/nuser/getnonce`
- `.../00300701/nuser/login`
- `.../00300701/file/upload`
- `.../00300701/file/download`
- `.../00300701/file/getproperties`

**Chiamate httpC (3DS)** [CERTO per l'ordine, nomi PROBABILI dedotti dai command id]:
`FUN_00524500` (CreateContext 0x20082, metodo POST) -> `FUN_005246b4` AddRequestHeader (0x1100C4) x4-6 -> AddDefaultCert (cmd 0x25, FUN_005249a8, ID = tabella 0x7e19ac[5] = 6) oppure AddTrustedRootCA (cmd 0x24, FUN_0052497c, solo se FUN_001b358c != 0, mai impostato in pratica) -> `FUN_00524690` SetClientCertDefault(0x40 = ClCertA, cmd 0x28) -> `FUN_005247b8` SetLazyPostDataSetting(2) -> `FUN_00524900` BeginRequest (0x90040) -> `FUN_00524724/764` SendPostDataRaw (0x1a0082), una volta per ogni nodo parametro -> `FUN_0052480c` NotifyFinishSendPostData -> `FUN_006dc404/43c` GetResponseStatusCode -> `FUN_006dc304/37c` GetResponseHeader (tutti gli header, in un buffer testuale) -> `FUN_006dc254` GetDownloadSizeState (Content-Length) -> `FUN_0052482c/86c` ReceiveData(body) -> Close (0x5248c4/0x524920/0x5252ec).
Timeout: `sil_Job_Update` case 1 chiama `FUN_001b8484(60000000)` e `FUN_001b4fe0(5)` [INCERTO il significato esatto di 60000000, probabilmente 60 s].

**Header HTTP della richiesta** [CERTO] (stringhe a 0x603da8..0x603e00):
| Header | Valore |
|---|---|
| `Content-Type` | `application/octet-stream` |
| `X-Sil-Version` | `1` |
| `X-Sil-Client` | `3DS` |
| `X-Sil-Title-Code` | `00200605` (8 char, impostato da silInit) |
| `X-Sil-Friend-Code` | friend code a 12 char; solo se impostato (assente in register, presente da getnonce in poi) |
| `X-Sil-Digest` | 32 hex minuscoli; solo dopo il login (vedi sez. 2) |

**Corpo della richiesta**: formato binario TLV, NON form e NON header [CERTO]. `silIfAddRequestParameter(req, name, data, len, copy)` (0x740840) crea nodi in una lista concatenata con inserimento in TESTA; ogni parametro serializza:
```
[u8 name_len][name (senza NUL)][u32 LE data_len][data...]
```
Con copy=0 (es. il parametro "Data") intestazione e dati sono due nodi consecutivi ma sul filo e' lo stesso formato. Il corpo e' la concatenazione dei nodi in ordine di lista = ORDINE INVERSO di aggiunta (ultimo aggiunto per primo). Il server puo' parsare i TLV per nome (l'ordine non conta per il parsing; conta solo per il digest, che e' calcolato sul corpo grezzo).

**Risposta** [CERTO] (`silIfReferResponse` 0x740c1c):
- Richiesto HTTP status == 200, altrimenti errore -200 (0xffffff38).
- Il corpo ha lo STESSO formato TLV `[u8 len][name][u32 LE len][data]`. I campi con nome che NON inizia per `X-Sil-` si cercano nel corpo.
- I nomi che iniziano per `X-Sil-` si cercano negli header di risposta (testo "Nome: valore"; il valore e' preso a name_len+2 dall'inizio del nome, serve quindi esattamente `X-Sil-Digest: <hex>` con un solo ": ").
- Content-Type della risposta: non controllato. Serve Content-Length (il body viene letto con la dimensione dichiarata).

**Gestione dell'esito** (`sil_ParseResultStatus` 0x1c0e78) [CERTO]: il client cerca il campo del corpo `Result` (stringa); se manca prova l'header `X-Sil-Controller-Status`. Se nessuno dei due c'e' -> errore generico -902 (0xfffffc7a). Valori riconosciuti (confronto lunghezza + contenuto, senza NUL):
`OK` -> 0; `UNSUPPORTED_VERSION` -300; `UNSUPPORTED_CLIENT` -301; `INVALID_TITLE` -302; `USER_NOT_EXIST` -303; `INVALID_DATA` -304; `USER_EXISTS` -305; `INTERNAL_ERROR` -306; `FILE_NOT_EXIST` -307; `OTHER_CLIENT` -308; `INVALID_TOKEN` -500; `TOKEN_EXPIRED` -501. Qualunque altro valore -> -902.

Verifica digest di risposta: se il client ha un Token di sessione verifica `X-Sil-Digest` della risposta (sez. 2); fallimento -> errore -304 (0xfffffed0) con log "MD5 digest check failed (received data)" / "MD5 digest wasn't found in received data".

**Note TLS** [INCERTO]: il base URL e' https. Il client usa AddDefaultCert con ID 6 (secondo libctru SSLC_DefaultRootCert sarebbe "Nintendo Class 2 CA G3") e ClCertA. Per un server sostitutivo senza toccare il sistema, la strada piu' semplice e': patchare la stringa a VA 0x86c83c in code.bin con `http://<host>/00300701/` (il client concatena e usa httpC senza TLS; l'URL non e' validato). Alternativa: CFW con patch SSL. La stringa di default (0x8bf6d4) e' gia' `http://wi-fi.infralib.square-enix.com/`.

---------------------------------------------------------------------

## 2. Digest

**Algoritmo: MD5 standard** [CERTO]. `sil_Md5Init` (0x1b24a0) imposta 67452301/efcdab89/98badcfe/10325476; `sil_Md5Update` (0x3019f0) bufferizza a blocchi da 64; `sil_Md5Transform` (0x1b2554) usa le costanti MD5 (0xd76aa478 a 0x1b2e98); `sil_Md5Final` (0x1b2214) padding 0x80 + lunghezza in bit LE (tabella padding a 0x7e196c, primo byte 0x80). Non e' HMAC.

**Chiave** (`sil_GetDigestKey`, 0x1b490c) [CERTO]: restituisce 16 byte copiati da `silInit(param_1, param_2)` (0x7410ec -> `sil_SetDigestKey` 0x1b963c). `sil_Job_Update` (0x66d240, case 1) chiama `silInit(titlecode, "3Ef7Db65775e4cCFDownload_Code")`: la chiave sono i primi 16 byte ASCII = `3Ef7Db65775e4cCF`.

**Token di sessione** (`sil_GetSessionToken`, 0x1c19bc) [CERTO]: 16 byte ricevuti dal server nel campo `Token` della risposta di `nuser/login` (`sil_LoginCb` 0x1b54ec -> `sil_SetSessionToken` 0x1b4928). Azzerato (flag off) in register e login.

**Formule**:
1. Campo `Digest` di `nuser/login` (16 byte RAW, non hex): `Digest = MD5(Nonce[16] || Key[16])`, con Nonce = campo `Nonce` di `nuser/getnonce` (`sil_LoginNonceCb` 0x1b586c).
2. Header `X-Sil-Digest` delle richieste (solo con Token presente) [CERTO, 0x603a10]:
   `hex_lower( MD5( body_request_grezzo || Token[16] || Key[16] ) )` - 32 caratteri `%02x`. "body_request_grezzo" = esattamente i byte POSTati (tutti i TLV concatenati).
3. Verifica header `X-Sil-Digest` della risposta (solo con Token presente): `hex_lower( MD5( body_response_grezzo || Token[16] || Key[16] ) )`, confronto esatto su 32 caratteri minuscoli. Se il corpo e' vuoto si hasha solo Token||Key.
Prima del login (register, getnonce, login) NON c'e' X-Sil-Digest ne' verifica sulla risposta.

---------------------------------------------------------------------

## 3. Significato di `00200605003007013Ef7Db65775e4cCF`

Layout [CERTO, VA 0x7ce9b0]: `00200605` + `00300701` + `3Ef7Db65775e4cCF` (32 char), seguiti da `Download_Code`.
La struct a 0x7ce9ac = {char* url (0x86c83c); 32 byte}. Un inizializzatore statico (codice a 0x70054c..0x700568) copia 8 byte da 0x7ce9b0 in 0x8cff48 e il puntatore URL in 0x8cff50; `sil_Job_Update` passa `0x8cff48` come "title code" a silInit e `*(0x8cff50)` a silSetServerURI.
- `00200605` (offset 0..7): **Title Code**. Header `X-Sil-Title-Code` (copiato da silInit -> `sil_SetTitleCode` 0x1b96c4 in 0x8e9a80). Semantica ulteriore (versione/regione) [INCERTO].
- `00300701` (offset 8..15): **ID applicazione/gioco nel path URL** (`.../00300701/`). In quella posizione non viene letto da nessuna funzione; conta solo il suo duplicato nell'URL (0x86c861).
- `3Ef7Db65775e4cCF` (offset 16..31): **chiave segreta del digest** (16 byte), usata solo nelle formule MD5 della sez. 2.
- `Download_Code` (0x7ce9d0, 13 byte): NON e' una credenziale. E' il payload fisso `Data` inviato dall'operazione "download privato" (sez. 4; `sil_Task_BeginDownloadCode` 0x671860: `job[0x39]="Download_Code"`, `job[0x38]=13`).
Correzione rispetto all'ipotesi iniziale: `FUN_00671860` NON copia questa struct di credenziali; copia il descrittore da 40 byte dell'operazione in coda (nome file 32 byte + size + puntatore buffer).

---------------------------------------------------------------------

## 4. Operazioni SIL usate dal gioco

Stack: `TaskSILStorage` (ctor 0x268794, coda operazioni da 0x28 byte/voce, `sil_StoragePushOp` 0x268390, `sil_StorageDispatchQueue` 0x268030, wrapper 0x268758/0x268720/0x268300) -> 5 comandi di rete `NetworkCommandSIL*` (costruiti in 0x671928) -> job `sil_Job_Update` (0x66d240, macchina a stati) -> API silXxx -> `silIfSendRequest`.
Prima di ogni operazione il job esegue l'autenticazione (`SilAuthJob_Update` 0x66cacc): service token Nintendo (256 byte, NASC via `silAuthRequestAuthToken` 0x74041c con ID 0x1acb00 e "994cba6f"), poi register (se il save non ha friend code) oppure login.
- [CERTO] Stato 0: se il servizio NEX (job 3 di `DAT_00898840` = `nex_SvcNex_UpdateDispatch`) non ha il flag `+0x4c & 0x10` (loggato), `FUN_0066bd38` accoda il comando 2 = `NexLoginJob` (NASC LOGIN + login NEX). Stato 1 attende quel flag, poi chiede il token solo se il buffer `0x8cff54` (0x100 B) e' tutto zero. Quindi il SIL richiede **anche il login NEX**: con Pretendo, finche' il gioco non e' registrato, NASC risponde 110 ("il servizio non e' piu' disponibile").
- [CERTO] Prima ancora, il gestore di rete esegue il job login amici `FUN_0066ed9c` (chiamato da `FUN_0066fe10`): se `FUN_0052c610` (frd HasLoggedIn) e' 0 chiama `FUN_0052d284` = frd:u `Login` (0x00030002), che con i moduli LLE fa NASC. Visto su Azahar (2026-10-26): AC connect, 3 richieste HTTPS con certificati Nintendo, applet errore, nessuna richiesta al SIL.
- Fingere il login amici (`--skip-frd`: 0x66ede0 `bne` -> `b 0x66eee4`) non basta: subito dopo la connessione AC compare l'errore **006-0000** senza traffico HTTP (le chiamate frd successive falliscono). Il login amici va fatto davvero (Pretendo lo supporta per tutti i titoli, serve Nimbus attivo).
- Patch di test `make_url_patch.py --skip-nasc`: NOP a 0x66cb48 (`bleq` login NEX), 0x66cb90 (`beq` attesa flag 0x10), 0x66cbc4 (`beq` richiesta token) -> register/login SIL con token a zero.
API presenti nel binario: silInit/Term/SetServerURI, AccountRegister, AccountLogin, AuthRequestAuthToken e le file-storage `silFileStorageSave` (0x74073c), `silFileStoragePublicSave` (0x7406bc), `silFileStoragePublicLoad` (0x740638), `silFileStoragePublicGetProperties` (0x7405b8). Le varie Delete / ByContentCode / silFileStorageLoad sono solo stringhe (codice rimosso dal linker).

### 4.1 nuser/register (silAccountRegister 0x7402d4, callback sil_RegisterCb 0x1ba490)
- Req: header Title-Code (niente Friend-Code, niente Digest). Body: `Authentication-Token` (256 byte, service token Nintendo).
- Resp: `Result`=OK (o `USER_EXISTS`, tollerato: il client legge comunque `Friend-Code`), `Friend-Code` (12 byte esatti, ASCII; il client lo salva nel save: `FUN_0066ceec` legge 12 char da `*(*(DAT_00897804+0x30)+4)`; se tutti 0 -> register, altrimenti login).

### 4.2 nuser/getnonce (silAccountLogin 0x7401e4)
- Req: header Title-Code + `X-Sil-Friend-Code`; body vuoto.
- Resp: `Result`=OK, `Nonce` (16 byte esatti, altrimenti errore -902).

### 4.3 nuser/login (sil_LoginNonceCb 0x1b586c)
- Req: header Title-Code + Friend-Code. Body (ordine sul filo): `Digest` (16 byte), `Authentication-Token` (256 byte).
- Resp: `Result`=OK, `Token` (16 byte esatti: la "sessione"). Non ci sono session id o user id separati: il Token entra solo nei digest (sez. 2). Errori -500/-501 fanno azzerare il service token in cache e fallire l'operazione.

### 4.4 file/upload (silFileStorageSave 0x74073c, "privato", con Friend-Code)
- Req body (ordine sul filo): `Friend-Code` (12 byte), `Data` (blob), `File-Name` (stringa senza NUL, max 31 char: il nome sta in un campo da 32 byte). Header con X-Sil-Digest.
- Resp semplice (`sil_SimpleResultCb` 0x67c0c4): solo `Result`. Il client considera "soft OK" anche USER_EXISTS/OTHER_CLIENT/USER_NOT_EXIST, ma conviene rispondere `OK`.
- **Variante "scambio"** (comandi DownloadPrivate, callback `sil_AddDataCb` 0x67c148): stessa richiesta `file/upload`, ma la risposta deve contenere anche `Add-Data-Size` (u32 LE) e `Add-Data` (blob). Il client scrive `Add-Data` nel buffer di destinazione solo se `buffer_size >= Add-Data-Size`; altrimenti ignora i dati senza errore.
  - tipo 0 ("download privato"): Data = literal `Download_Code` (13 byte) -> il server deve restituire in `Add-Data` il file privato dell'utente (File-Name + Friend-Code) [PROBABILE: il server riconosce Data == "Download_Code" come richiesta di lettura].
  - tipo 2 ("scambio"): Data = payload reale (es. il codice regalo), risposta in `Add-Data`.

### 4.5 file/download (silFileStoragePublicLoad 0x740638, pubblico)
- Req: solo `File-Name` (nessun Friend-Code). Digest presente.
- Resp: `Result`=OK, `Data` (blob). Il client copia in un buffer di dimensione fissa; se `len(Data)` > buffer -> errore -0x190 (silIfGetResponse). Se e' piu' corto non c'e' errore (il resto del buffer resta com'e'). Non esiste un campo size.
- Per file inesistenti: `Result: FILE_NOT_EXIST`; nelle operazioni col flag 1 il client prosegue senza errore (vedi 4.8).

### 4.6 file/getproperties (silFileStoragePublicGetProperties 0x7405b8, callback FUN_001bee5c)
- Req: `File-Name`. Resp: `Result`, `File-Size` (4 byte LE), `Download-Count` (4 byte LE), `Content-Code` (16 byte). Tutti e tre obbligatori (altrimenti -902). Usato SOLO dal download a dimensione variabile (`030_GP_WallPapers.arc`).

### 4.7 Save pubblico (silFileStoragePublicSave 0x7406bc, "file/upload" senza Friend-Code)
Presente nel job (stato 6, comando `NetworkCommandSILUploadPublicData`) ma nessun tipo della coda lo raggiunge [INCERTO: probabilmente inutilizzato].

### 4.8 Mappatura tipi operazione della coda (entry.type, `sil_StorageDispatchQueue` 0x268030)
| tipo | significato | API sul filo |
|---|---|---|
| 0 | download privato (Data="Download_Code") | file/upload + Add-Data |
| 1 | upload privato | file/upload |
| 2 | scambio privato (Data utente -> Add-Data) | file/upload + Add-Data |
| 3 | download pubblico, buffer fisso | file/download |
| 4 poi 5 | getproperties, poi download con buffer allocato di File-Size | file/getproperties + file/download |
Flag finale dell'operazione (ultimo argomento dei wrapper): se 1, un errore "file non esistente" (FILE_NOT_EXIST, o campo risposta mancante) NON e' fatale (`sil_Job_Update` case 4/5/6/7: `job[0x1e]==0xc && flag==1` -> prosegue). Se 0 l'errore e' fatale.

---------------------------------------------------------------------

## 5. Funzionalita' di gioco che usano SIL

Chiamanti dei wrapper (xrefs a 0x268758/0x268720/0x268300): 0x3e6098, 0x3e62bc, 0x30e544/0x30e640/0x30e740/0x30ea44, 0x3cac04, 0x41fe68, 0x42017c, 0x42022c, 0x42029c, 0x42038c, 0x4203e0, 0x5b9464, 0x594630. NON risulta alcun uso SIL per i `TakeOver*` (trasferimento da SD, locale) ne' per il WiFi shop (usa altro, probabilmente Nex) [INCERTO sul WiFi shop: nessun chiamante SIL trovato].

### 5.1 Backup/ripristino save corrotto (`MenuMessageSaveDataUploading`, `...Downloading`, 0x3e6098 / 0x3e62bc)
- Upload: `PrivateCorruptedSaveData.bin`, 0x37af0 (228 080) byte = intero buffer save (`DAT_00897804+4`), tipo 1.
- Download: `PrivateDLFixedSaveData.bin`, stessa size, tipo 0, flag 1 (`Add-Data` sovrascrive il buffer, poi viene reinstallato: menu "DownloadedSaveData"). Un server sostitutivo puo' rispondere `FILE_NOT_EXIST` (non fatale con flag 1) o restituire il save salvato.

### 5.2 Codici regalo / Present Code ("presentcodemes_*", 0x30e544, 0x30ea44, 0x30e740; stato per slot da 0x2ec byte, max 5 slot)
1. Invio codice: `present_code.bin`, tipo 2 (scambio). Data = codice utente UTF-16LE in buffer da 0x2a (42) byte (21 unita'); risposta `Add-Data` = 8 byte -> slot+0x134 (u32 "numero pacchetto") e slot+0x138 (u32 "stato"). Flag 0 (errori fatali).
2. Se stato == 0 (OK): scarica `PresentCodePackageS%02u.bin` (%u = u32 a slot+0x134), pubblico, tipo 3, 0x17c (380) byte, flag 0, in slot+0x13c. Il formato e' quasi certamente lo stesso dei pacchetti locali `patch:/data/PresentCode/Package/PresentCodePackageR%03d.bin` (FUN_0030eb4c) [PROBABILE].
3. Dopo la consegna del premio: conferma `present_code_recieved.bin`, tipo 1 (upload privato), 0x2a byte (il codice), flag 0.
Codici di stato nella risposta (tabella messaggi a 0x7c76b4 usata da FUN_00323c38): 0 = OK; 1 = `presentcodemes_AlreadyUse`; 2 = `presentcodemes_Wrong`; 3 = AlreadyUse; 4 = AlreadyUse; 5 = Wrong (l'indice 0 della tabella e' `presentcodemes_Authentication`, quindi lo stato 0 non e' un errore) [PROBABILE]. Errori di rete mostrano `presentcodemes_ErrorConnect` / `FailureDownload`. Significato esatto dei campi del pacchetto INCERTO.
4. Verificato in Azahar (2026-10-28) con il nostro server: codice `SLIME` -> `present_code.bin` (risposta pacchetto 1, stato 0) -> `PresentCodePackageS01.bin` (72 B, tipo 2 oggetto 0x2e) -> "Hai ricevuto il disco Disco Slime dorato!". Sequenza nel log: getnonce/login, `025_SendOfficialDummy.bin`, `present_code_recieved.bin`, `present_code.bin`, pacchetto. Il codice si digita con la tastiera del gioco (scheda "Aa" = lettere latine maiuscole e accentate, nessuna cifra: usare codici di sole lettere), max 5 codici per invio. Il menu passa dalla schermata di connessione 0x5e con `+0xb=1` (stato 8 = login SIL) e poi controlla `FUN_00445fb8` a `0x322de4`: forzato da `make_url_patch.py --skip-nasc`.
Test/dummy: `025_SendOfficialDummy.bin`, 0x54 byte, tipo 3 flag 0 (0x30e640; azzera 0x54 byte e scarica).

### 5.3 Download wallpaper ("download.bflyt", 0x3cac04)
`030_GP_WallPapers.arc`, dimensione variabile: tipo 4+5 (getproperties -> `File-Size`, allocazione, poi file/download pubblico).

### 5.4 Ranking Battle (Grade / Limit), classe a 0x4204e8 con tabelle scaricate in 0x41fe68 (da 0x3caaa8); messaggi `MenuMessage*RankingBattle`, `EndReception`, `NotOpenRankingBattle`
Download pubblici (tipo 3, flag 1, buffer fisso):
| File | Size | Note |
|---|---|---|
| `001_Server_Status.bin` | 8 | 0x42038c; byte[0]: 0 = aperto, 1/2 = ricezione chiusa, 3 = anomalia, 4 = non aperto (0x594630) |
| `003_Held_Record.bin` | 0x14 | |
| `600_CorrectPointTable.bin` | 0x28 | |
| `008_PopularTbl.bin` | 0x58 | |
| `009_WinPointTable.bin` | 0x54 | |
| `029W_EvaluationPoint.bin` | 0x3e | |
| `018_LimitSetting.bin` | 0x848 | |
| `144_Grade_Popular.bin` | 0x7fe | |
| `032_Grade_DLNewsMsg.bin`, `033_Limit_DLNewsMsg.bin` | 0x600 ciascuno | |
| `089_Grade_Ranking_Pack.bin`, `139_Limit_Ranking_Pack.bin` | 0x19998 ciascuno | |
| `141_Grade_ChampionRecord.bin`, `142_Limit_ChampionRecord.bin` | 0x1454 ciascuno | |
| `147_Grade_Def_DLBattle.bin`, `148_Limit_Def_DLBattle.bin` | 0x297c | 0x42029c |
| `171_Grade_Other_Countries.bin` | 0xdd4 | 0x4203e0 |
Download privati (tipo 0, Data="Download_Code", flag 1):
`23_UserPackData.bin` 0x2698; `PrivateSCRegister.bin` 4; `09_Grade_PrivateDlBattle.bin` / `18_Limit_PrivateDlBattle.bin` 0x297c; `28W_Grade_Other_Countries.bin` 0x938.
Upload privati (tipo 1, flag 1):
`00_UserData.bin` 0xc4 (0x5b9464, registrazione utente); `04_UpdateSaveData.bin` 0x19b98 (0x42017c, da 0x5a3c5c); `GradeResultPack.bin` / `LimitResultPack.bin` 0x540 (0x42022c, risultato battaglia).
I formati interni dei file non sono stati analizzati [INCERTO].

---------------------------------------------------------------------

## 6. wi-fi.infralib.square-enix.com

Solo valore di default [CERTO]. La stringa `http://wi-fi.infralib.square-enix.com/` a VA 0x8bf6d4 e' il BUFFER (0x80 byte) in cui `silSetServerURI` (0x741310 -> FUN_001b9684) copia la base; `sil_Job_Update` case 1 (0x66d240) lo sovrascrive subito dopo `silInit` con `https://dqm32ds.sil2.square-enix.com/00300701/` (puntatore in 0x8cff50, dalla struct 0x7ce9ac). A runtime non viene mai contattato (a meno che silSetServerURI non venga mai chiamata: non e' il caso).

---------------------------------------------------------------------

## Specifica per il server sostitutivo

Tutte le richieste: `POST <base>/<endpoint>`, body TLV `[u8 nlen][name][u32le dlen][data]*`. Risposte: HTTP 200 con body TLV e Content-Length corretto. In OGNI risposta includere `Result` = `OK` (stringa ASCII senza NUL).
Costanti: Key = `3Ef7Db65775e4cCF` (16 byte ASCII); Title = `00200605`; path app `00300701`.

Header di risposta: dopo il login ogni risposta DEVE avere `X-Sil-Digest: <md5hex>` con md5hex = hex minuscolo di `MD5(body_risposta || Token || Key)` (body vuoto: `MD5(Token || Key)`). Prima del login (register/getnonce/login) non serve.
Verifica richieste (opzionale): `X-Sil-Digest` req = hex di `MD5(body_req || Token || Key)`.

1. `nuser/register`
   - Req: `Authentication-Token` (256 B). Header `X-Sil-Title-Code`.
   - Resp: `Result=OK`, `Friend-Code` = 12 byte ASCII (es. 12 cifre uniche per console, derivabili dal token). Se l'utente esiste: `Result=USER_EXISTS` + stesso `Friend-Code`.
2. `nuser/getnonce`
   - Req: nessun body, header `X-Sil-Friend-Code`.
   - Resp: `Result=OK`, `Nonce` = 16 byte casuali (da ricordare per la login).
3. `nuser/login`
   - Req: `Digest` (16 B) = `MD5(Nonce||Key)`, `Authentication-Token` (256 B). Header `X-Sil-Friend-Code`.
   - Resp: `Result=OK`, `Token` = 16 byte casuali (da ricordare per sessione, serve ai digest successivi). Errori utili: `USER_NOT_EXIST`, `INVALID_DATA`.
   - Il token Nintendo a 256 B e' opaco per il server sostitutivo (non verificabile senza NASC): accettarlo senza controllo.
4. `file/upload` (privato)
   - Req: `File-Name`, `Friend-Code` (12 B), `Data`.
   - Se `Data` == `Download_Code` (13 byte): download privato -> Resp: `Result=OK`, `Add-Data-Size` (u32 LE), `Add-Data` (file memorizzato; se manca: `Result=FILE_NOT_EXIST`, non fatale con flag 1).
   - Se `File-Name` == `present_code.bin`: `Data` = codice UTF-16LE (42 B). Resp: `Result=OK`, `Add-Data-Size`=8, `Add-Data` = u32le package_id + u32le stato (0 OK, 1/3/4 gia' usato, 2/5 errato) [PROBABILE].
   - Altrimenti (upload): memorizzare `Data` per (`File-Name`, `Friend-Code`); Resp: `Result=OK`.
5. `file/download` (pubblico)
   - Req: `File-Name`. Resp: `Result=OK`, `Data` = file (lunghezza <= buffer client, vedi tabelle sez. 5, idealmente esattamente la size indicata). Se manca: `Result=FILE_NOT_EXIST` (non fatale per i file con flag 1; fatale per `PresentCodePackageS%02u.bin` e `025_SendOfficialDummy.bin`, che hanno flag 0).
   - Minimo per far funzionare le funzioni: `001_Server_Status.bin` (8 B, primo byte 0 = aperto), `025_SendOfficialDummy.bin` (0x54 B di zeri), pacchetti `PresentCodePackageS%02u.bin` (0x17c B).
6. `file/getproperties`
   - Req: `File-Name`. Resp: `Result=OK`, `File-Size` (u32 LE), `Download-Count` (u32 LE), `Content-Code` (16 B). Poi il client scarica con `file/download` lo stesso nome (usato per `030_GP_WallPapers.arc`).

Minimo "happy path" di rete: register/getnonce/login come sopra + `X-Sil-Digest` valido sulle risposte successive al login (altrimenti il client segnala errore -304 e interrompe). Per Ranking Battle e Present Code servono inoltre le risposte dei punti 4-5.

Punti aperti: formato interno dei file (ranking, pacchetti regalo), significato di `Download-Count`/`Content-Code`, esatta semantica degli stati present code, TLS (consigliata patch URL a http), autenticazione NASC del service token (non verificabile offline).
