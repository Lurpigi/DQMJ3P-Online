# SpotPass (BOSS) in DQMJ3P v1.3 - note di reverse engineering

Indirizzi = VA Ghidra (code.bin offset + 0x100000). Tool: `re/tools/bsdt.py`.
Marcatori: [CERTO] verificato su codice/campioni, [INCERTO] ipotesi.

NOTA: i file originali SpotPass per H7btVjYWs7p5dGj6 esistono gia' in
`re/data/spotpass_archive/canonical/<TASK>/*.bin.boss` (container BOSS cifrato AES-CTR, chiave console
non disponibile). Il server puo' semplicemente ri-servirli. Dimensioni in chiaro (dal coordinatore):
StealthBox 44, PassingMonster 124, SkyMapMonster 48, PresentDisc 5780, WiFiShopTbl 4744.

## 1. Registrazione dei task nn::boss

Manager: oggetto C++ globale `DAT_00897894`, creato da `FUN_00227398` (alloc + vtable `0x81ca44`,
servizio boss:U/P/M, stringa a 0x7f0b30). Wrapper nn::boss in 0x520d00-0x523700.
Tabella puntatori stringhe a 0x7cc524: [0]=URL base `https://npdl.cdn.nintendowifi.net/p01/nsa/H7btVjYWs7p5dGj6`,
poi "BREAK01","BREAK03","BREAK02", 3 percorsi file, "FGONLYT/BossPresentDisc.bin", "FGONLYT/BossWiFiShopTbl.bin".
La funzione vtable+0x50 (0x2279a4) restituisce il puntatore all'URL base. [CERTO]

URL finale = `"%s/%s"` (base, "TASK/file") -> [CERTO] (boss_vfn_681ca0, FUN_001028d4 con "%s/%s"):

| Task ID  | URL completo (da servire)                                                    | NsData |
|----------|------------------------------------------------------------------------------|--------|
| BREAK01  | `.../H7btVjYWs7p5dGj6/BREAK01/BossStealthBox.bin`                           | BSDT type 1 o 2 |
| BREAK02  | `.../H7btVjYWs7p5dGj6/BREAK02/BossPassingMonster.bin`                       | BSDT type 4 |
| BREAK03  | `.../H7btVjYWs7p5dGj6/BREAK03/BossSkyMapMonster.bin`                        | BSDT type 3 |
| FGONLYT  | `.../FGONLYT/BossPresentDisc.bin`  e  `.../FGONLYT/BossWiFiShopTbl.bin`     | BSDT type 5 / 6 |

(il server BOSS reale usa `<base>/<TASK>/<file>` + container `.boss`; l'estensione/formato lato CDN e'
gestito dal server.)

Chiamate (vtable 0x81ca44, slot offset -> funzione):
- +0x08 RegisterTask `boss_vfn_681ca0(taskId, "TASK/file", intervalHours, p5, flag)` [CERTO].
  Costruisce TaskPolicy (FUN_00520fd0): intervallo = ore*0xe10 secondi, +0x10 = p5; imposta property 5 = 2
  (FUN_00520e74), URL via FUN_00521688, se flag!=0 `FUN_005213d8(url,4)`; poi Register (FUN_00521108).
  Se errore 0xc8a0f836 (gia' registrato) fa Unregister (+0x14) e ripete.
  Chiamata da `FUN_002277d8` (registra BREAK01/BREAK03/BREAK02): `(task, "TASK/file", 0x18, 0x15, 0)`
  => intervallo 24 h (86400 s), p5 = 0x15 (21) [significato di p5 INCERTO: conteggio/durata schedule?], flag 0.
  Se il task esiste gia' (+0x18) viene solo chiamato +0x24 (`boss_vfn_68292c`, StartTask/impostazione con 0x15).
- +0x0c RegisterOneShot `FUN_00681ec8(url, flag)`: usato per FGONLYT. Task id "FGONLYT", intervallo 0xe10 (1 h),
  p5=1, poi StartTaskImmediate (FUN_00521a74); su errore Unregister("FGONLYT"). Chiamato da:
  - `FUN_00370e94` @0x370ff8 con "FGONLYT/BossPresentDisc.bin", flag=1 (menu Present Disc)
  - `FUN_002c9a54` @0x2c9a.. con "FGONLYT/BossWiFiShopTbl.bin", flag=0 (negozio Wi-Fi)
- +0x10 `IsRegistered/HasNsData`, +0x14 UnregisterTask, +0x18 TaskExists (FUN_00682254: confronta ID in lista task),
  +0x1c GetTaskState (6 = completato/dati pronti, 7/9 = errore), +0x2c GetNsDataIdList, +0x30 OpenNsData(id) (FUN_00522550/
  FUN_005222ac read, buffer 0x2000 a 0x8cddb4), +0x34 DeleteNsData, +0x38 GetNsDataReadFlag, +0x3c SetNsDataReadFlag,
  +0x44 GetTaskStatus (FUN_00682..298c), +0x48 ..., +0x50 URL base.
- GetNsDataIdList (`FUN_00227ca8`, chiamata `vtable+0x2c(&vec, mask, 0xffff)`): maschera usata per task:
  BREAK01=2, BREAK03=4, BREAK02=8, FGONLYT=0x20 (0xffff = tutti) [CERTO come argomenti, INCERTO come semantica
  (probabile filtro del tipo di NsData / content-datatype nell'header BOSS)]. Implementazione 0x6823b8 usa
  `FUN_005214f0(mask|0x10000)`.

Modalita' dati: tutti i task sono NsData ("data store"); il gioco legge i contenuti con ReadNsData dal NsDataId,
NON da file statici. NsDataId e' assegnato dalla console al download (numero crescente). Il gioco sceglie l'ID
piu' alto *non letto* (`FUN_00227ca8`), lo confronta con l'ultimo ID salvato nel save (`FUN_00228bfc/c14/c2c`,
struttura `DAT_00897804+0x34`) e carica solo se piu' nuovo. Dopo l'uso: SetReadFlag(+0x3c, id, 1). Cleanup
`FUN_00228298` cancella NsData letti/vecchi. Se la validazione BSDT fallisce: `FUN_002279b4(mgr, taskId)`
fa Unregister e ri-Register del task (loop di ri-download).

Per il server: ogni file e' per NsData un unico file; il server deve usare numero NsData/serial crescente nel
container BOSS (header plaintext del .boss: magic "boss", 0x10001, size) per far considerare nuovi i dati.

## 2. Formato BSDT [CERTO, verificato con HMAC OK sui 5 campioni]

Validatore: `FUN_002273f0` (confronta magic 0x54445342 @0x227404).
```
+0  "BSDT"
+4  u8  type   (1..6; >6 invalido)
+5  u8  flags  ((flags&0x7f) > 3 => rifiutato quando param_2==0)
+6  u16 size totale (include firma)
+8  corpo  (tipi 1-4: XOR con tabella fissa per tipo; 5,6: in chiaro)
-32 HMAC-SHA256(key[type], buf[0:size-32])   (FUN_0025097c -> FUN_001628b0, ipad 0x36/opad 0x5c, blocco 64)
```
Tabella chiavi HMAC (32 B, 0x8978ac[type]): type1 0x8978e4, type2 0x897904, type3 0x897924, type4 0x897964,
type5 0x897944, type6 0x897984 (valori nel tool). Chiavi XOR: type1 0x8979a4 (4 B), type2 0x8979a8 (38 B; il codice
fa 40 iterazioni, ultime 2 sconfinano nella firma, irrilevante), type3 0x897a22 (8 B), type4 0x8979ce (84 B).
Dopo il decode il gioco verifica la semantica (id validi, range) -> contenuti con id inesistenti sono rifiutati.

Layout corpo (offset relativi al corpo, dopo header 8 byte):
- type1 StealthBox item (4 B): u16 item_id (FUN_00163940 valida), u8 pad, u8 count (<100).
- type2 StealthBox monster (38 B): u32 seed, u16 species_id (FUN_001a46f4), u8 level/plus (<=0x32),
  u8 pad, u16 skill_ids[6] (@8, validati con FUN_0068f818), resto 18 B (tail). Validazione extra FUN_0012f254(species, seed)
  (seed deve essere coerente con la specie) [semantica esatta INCERTA].
- type3 SkyMapMonster (8 B): u16 monster_id_a, u16 monster_id_b (entrambi validati FUN_0013add0), u32 seed
  (FUN_0012f254(FUN_002ea524(b), seed)).
- type4 PassingMonster (84 B = 0x54): u32 seed; name UTF-16LE 28 B @4; u32 reward @0x20 [INCERTO: premio/gold];
  u16 skill_ids[4] @0x24 (FUN_0013add0); u16 species_id @0x2c; u8 rank (<4) @0x2e; u8 @0x2f; messaggio UTF-16LE
  36 B @0x30. Ricostruito dal validatore + campione.
- type5 PresentDisc (corpo in chiaro): `u8 nA, u8 nB, u16 0` + `u16 ...`? Struttura (FUN_0039fc0c / FUN_006c4acc):
  hdr4 = [nA, nB, 0, 0]; poi nA record A: header 8 B `{u16 tag(2 caratteri ASCII es. "DS","TT","7N"), u8 kind(<5),
  u8 n, u8 b4, u8 month(1-12), u8 day(1-31), u8 ?}` seguito da n*16 B di item
  `{u16 id (bit15 flag, &0x7fff validato FUN_001a46f4), u16 ref (<10000 => id valido FUN_0013add0; >=10000 => riferimento a
  record B con id uguale), u16 x4 (anche ref/skill), ...}`; poi nB record B da 0x48 B (id 0x2711=10001, 0x2712, ...
  template monster custom: campi species/skills/stat) [campi interni B e b4 INCERTI; b4=15 potrebbe essere anno-2000].
- type6 WiFiShopTbl (corpo in chiaro): 7 giorni x 42 slot x 16 B = 4704 B (8+4704+32 = 4744 OK). Slot:
  `{u16 kind (1=item?, 2=monster), u16 id, u16 f2, u16 f3, u16 f4, u16 f5, u32 e}`. Il gioco (FUN_002c9a54) calcola
  l'indice del giorno con ora JST (now + 32400000 ms, FUN_006d0618), copia 0x2a0 B (42 slot) a partire da
  buf+8+idx*0x2a0, e per slot con kind!=0 chiama FUN_002b0cac (aggiunge al negozio); kind==2 -> FUN_002508f4(specie, e).
  Controllo size NsData = 0x1288 (4744). Il validatore type6 (loop sezione) e' mal decompilato [INCERTO su vincoli].

## 3. Tool
`python -I re/tools/bsdt.py decode IN.bin [OUT.json]`, `encode IN.json OUT.bin`, `selftest FILE...`.
JSON: `{type, flags, body_hex, fields}`; in encode `fields` ha priorita' su `body_hex` (per type5/6 anche).
Round-trip byte-identico verificato sui 5 campioni RomFS (HMAC ok). La nota: per generare NUOVO contenuto bisogna comunque
impacchettare nel container BOSS (cifratura AES-CTR gestita lato server) e usare id/seed validi (il gioco rifiuta altrimenti).

## 4. Contenuto dei campioni (RomFS Debug) e uso nel gioco
- BossStealthBoxItem (type1, 44 B): item_id=39 (0x27), count=10. Letta da `FUN_001f3cf4` (BossLoadNewStealthBoxData_)
  via task BREAK01, mostrata come oggetto sul campo da `FUN_001c0340` (BossArrangeStealthBox_): se type==1 crea
  un tesoro con item/quantita'. Sblocca: "StealthBox" = scatola/forziere a sorpresa in campo con oggetto.
- BossStealthBoxMons (type2, 78 B): seed=0x2ff81dcf, species_id=1, level/plus=10, skill_ids=[1,0,0,0,0,0]. Se type!=1
  `FUN_001c0340` crea un'entita' mostro ("o_com_03") con questi dati: StealthBox con mostro regalo/nemico. Il file di
  produzione BREAK01 (44 B) e' del tipo item; il formato mons e' supportato dal codice (BREAK01 puo' alternare i due).
- BossSkyMapMonster (type3, 48 B): monster_id_a=3310, monster_id_b=3390, seed=0xe54c9dd7. Letto da `FUN_001f4418`
  (BossLoadNewSkyMapMonsterData_, BREAK03); accessori BossGetSkyMapMonsterResName/Scale/PartyID/KindId, e
  `Task_BossSkyMapMonsterAddFellow_` (FUN_001f3dc8 -> FUN_00237c60: aggiunge il mostro come compagno): mostro sulla
  mappa celeste (viaggio aereo) reclutabile/combattibile. [id>=3000: probabilmente mostri evento]
- BossPassingMonster (type4, 124 B): seed=0x64764325 (1685472037), name "SQEXの刺客", reward=530000, skill_ids=[3041,0,0,0],
  species_id=3092, rank=0, messaggio "いつのまにかの刺客だぜ！". Usata da `FUN_003c42d8` (BREAK02): se nuovo NsData
  (ID > ultimo salvato), copia il corpo (FUN_002284f0) in una struttura 0xa88 B (FUN_0029388c/292df8), la valida e la
  aggiunge come avversario/"sfidante" StreetPass ("刺客" = assassino) con premio; poi SetRead e salva ID.
  Dispatcher in `FUN_003c42d8` (chiamato dal loop di gioco quando StreetPass/SpotPass e' attivo, `FUN_002e341c`).
- BossPresentDisc (type5, 1452 B campione; originale 5780 B): 8 record A + 2 record B. Date nei record A:
  (15, 10, 15) e (15, 9, 3) [INCERTO anno]. Usata da `FUN_00370e94` (menu Present Disc): registra FGONLYT one-shot, poi
  legge NsData, valida type5, e il menu elenca i regali (mostri/oggetti con data) selezionabili.
- BossWiFiShopTbl (type6, originale 4744 B, nessun campione): vedi sopra: stock giornaliero del negozio Wi-Fi.

## 5. PassingOfficialDataTable01/02.bin (84 B)
Non sono BSDT (niente magic/HMAC) e il nome non compare in code.bin (nessun riferimento). Contenuto
(UTF-16LE): 01 = "SQEXからの刺客1", reward=100000, species 0x0c11, skill 0x0bd5,0x0bd6, messaggio
"仮※運営時に改めて設定予定です１" ("provvisorio, da impostare all'avvio del servizio"); 02 analogo con "...2".
Stessa dimensione (0x54) e struttura del corpo type4 PassingMonster, ma con 8 B di intestazione casuale invece di 4
(forse seed + checksum) e nome piu' corto (24 B) [INCERTO]. Il codice usa un buffer da 0x54 con
"025_SendOfficialDummy.bin" (FUN_0030e640, via FUN_00268758) => sono dati di test "official" (運営配信) per la
funzione StreetPass "Passing Official" (messaggi MenuMessagePassingOfficial*, FindOfficial). Quasi certamente
asset di debug non usati in produzione. Il server SpotPass non deve fornirli.

## 6. Download in Azahar con il nostro server [CERTO, verificato 2026-10-28]

- Azahar qui usa i moduli online LLE: il modulo `boss` vero (0004013000003402) scarica i task da solo.
  Il task FGONLYT viene registrato con la base URL a VA `0x86a0c4` (file `0x76A0C4`):
  `make_url_patch.py --spotpass-url http://127.0.0.1:8380/p01/nsa/H7btVjYWs7p5dGj6` + `server/spotpass/serve_spotpass.py`
  (porta 8380, file originali in `re/data/spotpass_archive/canonical`). Il modulo accetta `http://` e decifra i `.boss`
  originali; richiede `.../FGONLYT/BossPresentDisc.bin?tm=4`.
- Il BOSS scarta il task in ~0,1 s senza HTTP se il gioco non ha aperto la connessione AC: la schermata di connessione
  della piazza (0x5e) non va saltata.
- Schermata 0x5e (update `0x3879ac`, stato in `+0x68`): 0 gia' connesso? / 4 "Vuoi connetterti?" / 2-3 connessione AC
  (`FUN_005f3c94`, `FUN_0066e42c`, `FUN_00453d0c`) / 6 "WaitConnection" / 7 (8) task di login in `+0x80` (`+0x84`),
  errore -> `FUN_005f3b74` (006-0000 senza NEX) -> 9 / 10 fine. Dopo la schermata regali (`FUN_00439e58`) e negozio
  monete (`FUN_002ca3b8`) proseguono solo se `FUN_00445fb8` (NEX connesso).
- `--skip-nasc` quindi: stati 7/8 -> sempre stato 10 (`0x388044`, `0x3880ac`), `FUN_00445fb8` forzato a 1 solo alle
  chiamate `0x439ec4` (regali) e `0x2ca434` (negozio). Risultato: "Hai ricevuto il Disco Conclavio sacro!" e, nel negozio monete, "Inventario aggiornato." con lo stock
  originale (`BossWiFiShopTbl.bin?tm=4`).
- Con il BOSS HLE (senza moduli LLE) servono invece `spotpass_azahar.py` (NsData nell'extdata) e `--azahar-hle-boss`.

### 6.1 BREAK01-03 in Azahar [CERTO, verificato 2026-10-29]
- I task BREAK sono registrati al boot come task periodici (24 h, 21 esecuzioni) e il gioco non li avvia mai: su console
  li esegue il daemon BOSS (in standby). Il record e' in `BOSS_SS.db` (URL a +0x220 del blocco) e `BOSS_SV.db` (stato).
- StartTaskImmediate (`FUN_00521a74`) sui task periodici in Azahar: il modulo BOSS chiama `ac:u` 0x00140002
  `GetConnectingLocation`, che Azahar non implementa (risposta vuota). Il task finisce in stato 7, risultato `0xD8A0A018`,
  senza HTTP. La sospensione dei daemon (`NDM SuspendDaemons 0x6` al boot) non c'entra: NDM in Azahar e' uno stub.
- I task in primo piano (RegisterImmediateTask `FUN_0052174c`) non fanno quel controllo, ma l'SDK accetta solo l'ID
  "FGONLYT" (`FUN_00522fa8`; `FUN_0052197c` rifiuta proprio quell'ID). Il gioco trova i NsData per tipo di dato
  (`GetNsDataIdList`), non per ID del task, quindi i file BREAK si possono scaricare con un task FGONLYT.
- `make_url_patch.py --spotpass-break`: hook a `0x3880f8` (stato 10 della schermata 0x5e) verso una routine nel padding
  della pagina di .text (`0x7b9810`). Per ogni file (`0x86a140` BREAK01, `0x86a120` BREAK03, `0x86a100` BREAK02):
  Unregister FGONLYT (vtable +0x14), URL `"%s/%s"` con la base (vtable +0x50) e `sprintf` `0x1028d4` (Thumb: `blx`),
  Task FGONLYT `FUN_00520d7c`, TaskAction `FUN_00521734`/`FUN_00521688`, TaskPolicy `FUN_00521008`/`FUN_00520fd0(0xe10, 1)`,
  RegisterImmediateTask, StartTaskImmediate, poi `svcSleepThread` 50 ms fino a GetState (`FUN_00521cc8`) >= 6 (max 10 s).
  Crea il manager BOSS (`FUN_00227398`) solo se manca, e in quel caso lo distrugge alla fine.
- Risultato: tre GET `.../BREAKxx/<file>?tm=4` con risposta 200. Il caricamento della piazza dura qualche secondo in piu'.
  Nella piazza compare la scatola nascosta: "Hai trovato Super Seme dell'Agi" (contenuto originale di BREAK01).
  BREAK03 (mostro della mappa celeste) e BREAK02 (sicario StreetPass) scaricati ma non ancora verificati in gioco.

## Incertezze principali
Semantica di p5=0x15 e della property 5=2 nella TaskPolicy; maschere 2/4/8/0x20 di GetNsDataIdList; campi interni
record B e anno in PresentDisc; semantica seed/FUN_0012f254; campi f2..f5 degli slot WiFiShop.
