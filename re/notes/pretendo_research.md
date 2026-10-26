# Ricerca Pretendo per un server NEX fan-made di DQMJ3P

Data ricerca: 2026-10-24. Titolo: Dragon Quest Monsters: Joker 3 Professional (JP), title ID `00040000001ACB00`, NEX 3.10.1, access key PRUDP **`5812c478`** (verificata in Ghidra; `994cba6f` è invece la keyhash SVCLOC per il token Square Enix), game server ID `0x001ACB00` (verificato in Ghidra; formato stringa del `gameid` NASC da confermare).

Convenzioni: **[VERIFICATO]** = letto direttamente dal codice/URL citato; **[NON VERIFICATO]** = deduzione o dato non confermato.

Tutte le URL "raw" sono su `https://raw.githubusercontent.com/PretendoNetwork/...` (branch indicati: `account`=master, `nex-go`=master, `nex-protocols-common-go`=main, `BOSS`=dev, `boss-crypto`=master, `nimbus`=master).

---

## Sintesi esecutiva

1. **Account server**: il login 3DS (`POST /ac`, NASC) cerca nel MongoDB (collection `servers`, modello `Server`) un documento con `title_ids` contenente il title ID e verifica che `game_server_id` coincida col `gameid` inviato dalla console. Restituisce `locator = ip:port` del server di autenticazione NEX e un token. Per un nuovo gioco serve **aggiungere un documento nella collection `servers`** (non esiste una API gRPC funzionante: `create-server.ts` e' "Stubbed"; il file di provisioning aggiorna solo documenti esistenti).
2. **nex-go v2**: la versione PRUDP (v0 / v1) **non si configura**: il server la rileva dal primo pacchetto del client (magic `0xEA 0xD0` = v1, altrimenti v0). Un gioco 3DS NEX 3.10.x (come Animal Crossing: New Leaf, 3.10.1) usa lo stesso codice senza impostazioni PRUDP speciali. **Template migliore: `PretendoNetwork/animal-crossing-new-leaf`** (stessa LibraryVersion 3.10.1).
3. **nex-protocols-common-go**: ci sono implementazioni comuni per tutti i protocolli richiesti (incl. community/PersistentGathering, DataStore su S3/MinIO, Ranking). DataStore e Ranking richiedono pero' che il gioco fornisca le funzioni DB (callback); non e' "plug and play".
4. **BOSS**: esiste (TypeScript, MongoDB, S3 o disco). Il 3DS usa `npdl.cdn.nintendowifi.net/p01/nsa/<bossAppId>/<task>/<file>`. Nimbus sostituisce le sottostringhe `nintendowifi.net`, `nintendo.net`, `pokemon-gl.com` con `pretendo.cc` nelle URL HTTP, quindi **si, redirige automaticamente** (con account Pretendo attivo).
5. **Dati SpotPass di DQMJ3(P) ESISTONO pubblicamente**: `https://archive.org/details/3ds-boss-data` contiene `H7btVjYWs7p5dGj6.zip` (26.7 MB, 20748 file). Il BOSS app ID e' gia' nella lista "known apps" di Pretendo BOSS con task `BREAK01`, `BREAK02`, `BREAK03`, `FGONLYT` (titleId ancora `0x0`/Unknown).
6. **NAT/Pia**: Pretendo ha `nncs` (NAT check server, `nncs1/2.app.nintendowifi.net` porte 10025/10125) e il protocollo NEX NATTraversal comune. Non esiste un relay Pia.
7. **Contributi**: Pretendo accetta contributi ma richiede issue approvata prima del codice; non c'e' un processo documentato per "aggiungere un gioco" di terze parti. Esistono progetti community che ospitano giochi 3DS sopra Pretendo (`FreakyBigFoot/fbf-3ds-servers`, `Protarium-Network/nasc-router`) e docker-compose non ufficiali (`MatthewL246/pretendo-docker`).

---

## 1. Account server: da game server ID a indirizzo/porta (NASC 3DS)

### 1.1 Codice del flusso LOGIN

File: `https://raw.githubusercontent.com/PretendoNetwork/account/master/src/services/nasc/routes/ac.ts` [VERIFICATO]

```ts
router.post('/', nascRatelimit, async (request, response) => {
	const requestParams: NASCACRequestParams = request.body;
	const action = nintendoBase64Decode(requestParams.action).toString();
	const titleID = nintendoBase64Decode(requestParams.titleid).toString();
	const gameServerID = nintendoBase64Decode(requestParams.gameid).toString();
	const nexAccount = request.nexAccount;
	...
	const server = await getServerByTitleID(titleID, nexAccount.server_access_level);

	if (!server || !server.aes_key) {
		response.status(200).send(nascError('110').toString());
		return;
	}

	if (gameServerID !== server.game_server_id) {
		// * If there is a server for a given title ID but it has a different game server ID,
		// * then the title probably requires custom patches. ...
		// * 152 is a custom error code
		response.status(200).send(nascError('152').toString());
		return;
	}

	if (server.maintenance_mode) {
		response.status(200).send(nascError('101').toString());
		return;
	}

	const connectInfo = await server.getServerConnectInfo();
	if (action === 'LOGIN' && connectInfo.port <= 0 && connectInfo.ip !== '0.0.0.0') {
		response.status(200).send(nascError('110').toString());
		return;
	}
	...
```

Risposta LOGIN (`processLoginRequest`):

```ts
const token = nintendoBase64Encode(crypto.randomBytes(112));
await NEXToken.create({
	token: crypto.createHash('sha256').update(token).digest('hex'),
	game_server_id: server.game_server_id,
	pid: pid,
	info: {
		system_type: SystemType.CTR,
		token_type: TokenType.NEX,
		title_id: BigInt(parseInt(titleID, 16)),
		issued: new Date(),
		expires: new Date(Date.now() + (3600 * 1000))
	}
});

const connectInfo = await server.getServerConnectInfo();
return new URLSearchParams({
	locator: nintendoBase64Encode(`${connectInfo.ip}:${connectInfo.port}`),
	retry: nintendoBase64Encode('0'),
	returncd: nintendoBase64Encode('001'),
	token: token,
	datetime: nintendoBase64Encode(nascDateTime())
});
```

Quindi: **titleid -> documento `Server` -> `ip`/`ip_list` + `port`** (il `locator` e' l'indirizzo dell'**authentication server** NEX, non del secure server; il secure server lo indica poi il game server stesso via `StationURL` nella risposta Login).

### 1.2 Dove e' configurata la mappatura (DB, non config file)

File: `.../account/master/src/database.ts` [VERIFICATO]

```ts
export async function getServerByTitleID(titleID: string, accessMode: string) {
	const searchModes = accessModeOrder[accessMode] ?? accessModeOrder.prod;
	const servers = await Server.find({
		title_ids: titleID,
		access_mode: { $in: searchModes }
	});
	...
```

Schema Mongoose: `.../account/master/src/models/server.ts` [VERIFICATO]

```ts
const ServerSchema = new Schema<IServer, ServerModel, IServerMethods>({
	client_id: String,
	ip: { type: String, required: false },
	ip_list: { type: [String], required: false },
	port: Number,
	service_name: String,
	service_type: String,
	game_server_id: String,
	title_ids: [String],
	access_mode: String,
	maintenance_mode: Boolean,
	device: Number,
	aes_key: String,
	health_check_port: { type: Number, required: false }
});
```

Tipi: `.../account/master/src/types/mongoose/server.ts`. Il modello e' registrato come `model('Server', ...)`, quindi la collection Mongo e' `servers` (conferma indiretta: il README di `Protarium-Network/nasc-router` parla di "Mongo `servers` collection (`title_ids`)").

Formati attesi (dedotti dal codice; [NON VERIFICATO] contro un DB di produzione):

- `title_ids`: stringhe hex **minuscole a 16 cifre** come inviate dalla console (`titleid` decodificato), es. `"00040000001acb00"`. Il confronto e' una `find({title_ids: titleID})` esatta: verificare la capitalizzazione reale inviata dal 3DS.
- `game_server_id`: stringa hex come arriva in `gameid`, es. `"001ACB00"` / `"1ACB00"` (confronto stringa esatto con `gameid`: **verificare con un dump reale**).
- `access_mode`: `prod` / `test` / `dev` (vedi `accessModeOrder` in `database.ts`).
- `aes_key`: obbligatorio (`!server.aes_key` -> errore 110). Usato come chiave HMAC-SHA256 per i service token (`createServiceToken` in `src/util.ts`), non per AES.
- `device`: numero (1 = Wii U, 2 = 3DS secondo la convenzione Pretendo; [NON VERIFICATO]).
- `client_id`: usato per Wii U (`getServerByClientID`); per 3DS non serve per NASC.
- `health_check_port`: opzionale; l'account server invia un UDP con un UUID e si aspetta che il game server lo rimandi (vedi `nex.EnableBasicUDPHealthCheck(port)` nei server di gioco).

### 1.3 Provisioning (aggiorna solo, non crea)

File: `.../account/master/src/provisioning.ts` [VERIFICATO]

```ts
// Provisioning has a couple edgecases:
// - It will only update existing entries, will not add new one
// - Only the fields in the below schema will be updated
const serverProvisioningSchema = z.object({
	servers: z.array(z.object({
		id: z.string(),                 // ObjectId del documento
		name: z.string().optional(),
		ip: z.string().nullable().optional(),
		ip_list: z.array(z.string()).optional(),
		port: z.number().optional(),
		health_check_port: z.number().nullable().optional(),
		aes_key: z.string().optional()
	}))
});
```

Abilitato con env `PN_ACT_PROVISIONING_SERVER_CONFIG` (path a un JSON). Il file viene riletto a ogni modifica (`fs.watch`).

Gli endpoint gRPC `create_server` / `update_server` ecc. in `src/services/grpc/account/v2/create-server.ts` sono **stub** (`throw new ServerError(Status.UNIMPLEMENTED, 'Stubbed')`) [VERIFICATO per create-server].

### 1.4 Cosa serve per un nuovo gioco 3DS

1. Inserire a mano (mongosh) un documento in `servers`, es. (da adattare):

```js
db.servers.insertOne({
  client_id: "",                       // non usato da 3DS
  ip: "IP_O_HOST_AUTH_SERVER",         // NOTA: il codice usa dgram per health check -> ip tipicamente IPv4
  port: 60000,                         // porta authentication server NEX
  service_name: "dqmj3p",
  service_type: "nex",
  game_server_id: "001ACB00",          // da verificare con il gameid reale
  title_ids: ["00040000001acb00"],
  access_mode: "prod",
  maintenance_mode: false,
  device: 2,                           // 3DS (da verificare)
  aes_key: "<32 hex casuali>",
  health_check_port: 60001             // opzionale
})
```

2. Il game server, nel `ConfigurePNValidation([]string{"001ACB00"})` (ticket-granting common), valida che il `loginData` contenga il token e che il **game server ID** nel token coincida (vedi `ValidatePNLoginData` in `nex-protocols-common-go/globals`). Gli altri server 3DS passano la stringa hex a 8 cifre, es. ACNL `"00086202"`, SSB3DS `"000B8B01"`, MH4U `"0011D701"`, YKW2 `"0012F800"`. Quindi per DQMJ3P: `"001ACB00"` (se confermato).
3. Il server NEX deve poter risolvere `GetNEXPassword(pid)` via gRPC dall'account server (`common_globals.ConnectToAccountGRPC`).
4. Lato console: DNS/patch NASC. Nimbus rimpiazza `nintendowifi.net` -> `pretendo.cc` (vedi punto 4.4), quindi `nasc.nintendowifi.net` -> `nasc.pretendo.cc`.
5. Per un setup **community senza toccare l'account server di Pretendo**, esiste `Protarium-Network/nasc-router` (proxy NASC che instrada ai server locali solo i `titleid` presenti nella collection `servers` e il resto a `nasc.pretendo.cc`) e `FreakyBigFoot/fbf-3ds-servers` (vedi punto 7).

Dettaglio importante dal middleware `src/middleware/nasc.ts`: il NASC richiede `action, fcdcert, csnum, macadr, titleid, servertype, gameid`, valida il certificato della console (`NintendoCertificate`) e l'account NEX (`NEXAccount`). Per usare il server serve quindi una console con account Pretendo (Nimbus).

Nota (mismatch noto): se il game server ID non coincide si risponde errore **152** (commento nel codice: titoli che richiedono patch).

---

## 2. nex-go v2: configurazione di un server 3DS

### 2.1 Versione PRUDP: rilevamento automatico

File: `https://raw.githubusercontent.com/PretendoNetwork/nex-go/master/prudp_server.go` [VERIFICATO]

```go
func (ps *PRUDPServer) handleSocketMessage(packetData []byte, address net.Addr, webSocketConnection *gws.Conn) error {
	...
	// * Support any packet type the client sends and respond
	// * with that same type. ...
	if ps.websocketServer != nil && packetData[0] == 0x80 {
		packets, _ = NewPRUDPPacketsLite(ps, nil, readStream)
	} else if bytes.Equal(packetData[:2], []byte{0xEA, 0xD0}) {
		packets, _ = NewPRUDPPacketsV1(ps, nil, readStream)
	} else {
		packets, _ = NewPRUDPPacketsV0(ps, nil, readStream)
	}
```

Struttura (`PRUDPServer`): campi `AccessKey`, `KerberosTicketVersion`, `LibraryVersions`, `ByteStreamSettings`, `PRUDPV0Settings`, `PRUDPV1Settings`, `SessionKeyLength: 32`, `FragmentSize: 1300`. Impostazioni v0 (`prudp_v0_settings.go`): `IsQuazalMode`, `EncryptedConnect`, `LegacyConnectionSignature`, `UseEnhancedChecksum` + calcolatori custom; v1: `LegacyConnectionSignature`, calcolatori.

Risposta alla domanda "quale PRUDP per NEX 3.10.1 su 3DS": **non e' una scelta del server**; il client decide. [INFERENZA] I titoli 3DS con NEX 3.x (ACNL 3.10.1, YKW2 3.6.1, MH4U 3.6.1, SSB3DS 3.6.9, TFH 3.9.0, Pokemon gen6 3.3.0) usano senza impostazioni PRUDP custom, il che indica PRUDPv1 o v0 gestiti dalle impostazioni di default. Solo MK7 (NEX 2.4.3) e' un caso "vecchio" (probabilmente v0); [NON VERIFICATO] quale versione usa effettivamente DQMJ3P: serve un dump del primo pacchetto (primo byte `EA D0` = v1). Se ci fossero problemi (checksum/firma), le leve sono `PRUDPV0Settings` / `PRUDPV1Settings.LegacyConnectionSignature`.

### 2.2 Access key, LibraryVersion, stream settings, Kerberos

Esempio completo: **Animal Crossing: New Leaf** (NEX **3.10.1**, stesso del nostro target). Repo `PretendoNetwork/animal-crossing-new-leaf` (branch master) [VERIFICATO]:

`nex/secure.go`:

```go
func StartSecureServer() {
	globals.SecureServer = nex.NewPRUDPServer()
	globals.SecureServer.ByteStreamSettings.UseStructureHeader = true

	globals.SecureEndpoint = nex.NewPRUDPEndPoint(1)
	globals.SecureEndpoint.IsSecureEndPoint = true
	globals.SecureEndpoint.ServerAccount = globals.SecureServerAccount
	globals.SecureEndpoint.AccountDetailsByPID = globals.AccountDetailsByPID
	globals.SecureEndpoint.AccountDetailsByUsername = globals.AccountDetailsByUsername
	globals.SecureServer.BindPRUDPEndPoint(globals.SecureEndpoint)

	globals.SecureServer.LibraryVersions.SetDefault(nex.NewLibraryVersion(3, 10, 1))
	globals.SecureServer.AccessKey = "d6f08b40"

	globals.SecureEndpoint.OnData(func(packet nex.PacketInterface) { ... })
	globals.SecureEndpoint.OnError(func(err *nex.Error) { ... })

	globals.MatchmakingManager = common_globals.NewMatchmakingManager(globals.SecureEndpoint, globals.Postgres)

	registerCommonSecureServerProtocols()

	port, _ := strconv.Atoi(os.Getenv("PN_ACNL_SECURE_SERVER_PORT"))
	globals.SecureServer.Listen(port)
}
```

`nex/authentication.go`: identico ma con `AuthenticationServer`, `NewPRUDPEndPoint(1)` senza `IsSecureEndPoint`, stessa `AccessKey` e stessa `LibraryVersion(3, 10, 1)`, poi `registerCommonAuthenticationServerProtocols()` e `Listen(PN_ACNL_AUTHENTICATION_SERVER_PORT)`.

`nex/register_common_authentication_server_protocols.go`:

```go
ticketGrantingProtocol := ticketgranting.NewProtocol()
globals.AuthenticationEndpoint.RegisterServiceProtocol(ticketGrantingProtocol)
commonTicketGrantingProtocol := commonticketgranting.NewCommonProtocol(ticketGrantingProtocol)
commonTicketGrantingProtocol.ConfigurePNValidation([]string{"00086202"})   // game server ID

secureStationURL := types.NewStationURL("")
secureStationURL.SetURLType(constants.StationURLPRUDPS)
secureStationURL.SetAddress(os.Getenv("PN_ACNL_SECURE_SERVER_HOST"))
secureStationURL.SetPortNumber(uint16(port))
secureStationURL.SetConnectionID(1)
secureStationURL.SetPrincipalID(types.NewPID(2))
secureStationURL.SetStreamID(1)
secureStationURL.SetStreamType(constants.StreamTypeRVSecure)
secureStationURL.SetType(uint8(constants.StationURLFlagPublic))

commonTicketGrantingProtocol.SecureStationURL = secureStationURL
commonTicketGrantingProtocol.BuildName = types.NewString("branch:origin/release/ngs/3.10.x.200x build:3_10_22_2006_0")
commonTicketGrantingProtocol.SecureServerAccount = globals.SecureServerAccount
```

Kerberos / account di sistema (`init.go` di YKW2 e SSB3DS) [VERIFICATO]:

```go
kerberosPassword := make([]byte, 0x10)
_, err = rand.Read(kerberosPassword)
globals.KerberosPassword = string(kerberosPassword)
AuthenticationServerAccount = nex.NewAccount(types.NewPID(1), "Quazal Authentication", KerberosPassword, false)
SecureServerAccount        = nex.NewAccount(types.NewPID(2), "Quazal Rendez-Vous",   KerberosPassword, false)
```

`AccountDetailsByPID` per i PID utenti chiama `GetNEXPassword` via gRPC sull'account server (`globals/password_from_pid.go`). La password Kerberos dei server e' casuale a ogni avvio (16 byte). `KerberosTicketVersion` resta di default (0) per questi giochi; la modalita' v1 del ticket e' solo per Wii U/Switch recenti [NON VERIFICATO].

Stream types: `constants.StreamTypeRVSecure` per la StationURL del secure server (enum in `nex-go/constants/stream_type.go`: DO, RV, OldRVSec, SBMGMT, NAT, SessionDiscovery, NATEcho, Routing, Game, RVSecure, Relay). `NewPRUDPEndPoint(1)` = stream ID 1 su entrambi i server. Per titoli con client lenti: `DefaultStreamSettings.MaxSilenceTime = 10000` (MH4U) / `20000` (MK7).

### 2.3 Differenze rilevate fra i vari giochi 3DS (per scegliere i parametri)

| Gioco | NEX | AccessKey | UseStructureHeader | Note |
|---|---|---|---|---|
| Animal Crossing: New Leaf | 3.10.1 | d6f08b40 | si | PNValidation `00086202`; DataStore, Matchmake, Utility |
| Yo-kai Watch 2 | 3.6.1 | 7ab183bb | si | BuildName copiato da "3.10.x"; ConfigurePNValidation `0012F800`; ha community/persistent gathering? no |
| Monster Hunter 4 Ultimate | 3.6.1 | d44c6198 | si | `MaxSilenceTime=10000` |
| Super Smash Bros 3DS | 3.6.9 | 86405e2f | si | modalita' `PN_SSB3DS_LOCAL_AUTH` |
| Tri Force Heroes | 3.9.0 | c1621b84 | si | |
| Pokemon gen 6 | 3.3.0 | 876138df | no (default) | `globals/rmc/*` custom |
| Mario Kart 7 | 2.4.3 | 6181dff1 | no | `MaxSilenceTime=20000` |

`UseStructureHeader = true` (flag di `ByteStreamSettings`) e' necessario per le strutture con header versione, introdotto con NEX 3.5.0+ circa; per NEX 3.10.1 va **abilitato** (come ACNL) [alta confidenza].

### 2.4 Protocolli registrati dai giochi 3DS di riferimento

ACNL (`nex/register_common_secure_server_protocols.go`): SecureConnection (con `EnableInsecureRegister()`, `CreateReportDBRecord`), NATTraversal, MatchMaking, MatchMakingExt, DataStore (`commondatastore.NewCommonProtocol(dataStoreProtocol)` senza callback DB!), Ranking (solo registrato, nessuna logica), MessageDelivery (handler custom), Utility (`GetIntegerSettings` custom), MatchmakeExtension (`SetManager(globals.MatchmakingManager)`, `CleanupSearchMatchmakeSession`, `CleanupMatchmakeSessionSearchCriterias`).

YKW2: SecureConnection, NATTraversal, MatchMaking (`FindByOwner` custom), MatchMakingExt, Ranking (solo registrato), MatchmakeExtension (`GetMyBlockList` custom), MessageDelivery (common messaging), Utility.

SSB3DS: SecureConnection, NATTraversal, MatchMaking, MatchMakingExt, MatchmakeExtension, + DataStore `super-smash-bros-4` custom, MatchmakeReferee, Ranking vuoto (TODO).

Dipendenze comuni a tutti: PostgreSQL (matchmaking, utility, messaging), gRPC account (`GetNEXPassword`), gRPC friends (`GetUserFriendPIDs`). Config via env `PN_<SIGLA>_*` (vedi tabella README di SSB3DS: `POSTGRES_URI`, `AUTHENTICATION_SERVER_PORT`, `SECURE_SERVER_HOST/PORT`, `ACCOUNT_GRPC_*`, `FRIENDS_GRPC_*`, `DATASTORE_S3*`, `LOCAL_AUTH`, `HEALTH_CHECK_PORT`).

### 2.5 Modalita' locale senza account server (utile per sviluppo)

SSB3DS `globals/password_from_pid.go`: `PasswordFromPIDLocal` legge `settings.json` (stesso formato di nex-viewer: `{"accounts":[{"platform","username","pid","password"}]}`) e, con `PN_SSB3DS_LOCAL_AUTH=1`, `ValidateLoginData` ritorna sempre `nil` (token non validati). Copiare questo meccanismo per il testing offline [VERIFICATO nel codice].

---

## 3. nex-protocols-common-go

Repo: `PretendoNetwork/nex-protocols-common-go` (branch `main`, modulo `.../v2`). Struttura letta via API tree [VERIFICATO]. Moduli: `datastore, globals, match-making, match-making-ext, matchmake-extension, message-delivery, messaging, nat-traversal, ranking, secure-connection, ticket-granting, utility`.

### 3.1 Tabella di copertura

| Protocollo | Implementato (handler registrati in `NewCommonProtocol`) | Note |
|---|---|---|
| **MatchmakeExtension** | `OpenParticipation, CloseParticipation, CreateMatchmakeSession, GetSimplePlayingSession, AutoMatchmakePostpone, AutoMatchmakeWithParamPostpone, AutoMatchmakeWithSearchCriteriaPostpone, AutoMatchmakeWithGatheringIDPostpone, GetPlayingSession, **CreateCommunity, FindCommunityByGatheringID, FindOfficialCommunity, FindCommunityByParticipant**, UpdateProgressScore, CreateMatchmakeSessionWithParam, UpdateApplicationBuffer, JoinMatchmakeSession, JoinMatchmakeSessionWithParam, **JoinCommunity**, ModifyCurrentGameAttribute, BrowseMatchmakeSession, JoinMatchmakeSessionEx, GetSimpleCommunity, UpdateNotificationData, GetFriendNotificationData, GetlstFriendNotificationData, UpdateMatchmakeSessionAttribute` | Tabelle Postgres create in `SetManager`: `matchmaking.matchmake_sessions`, `persistent_gatherings`, `notifications`, `tracking.participate_community`. `PersistentGatheringCreationMax` default 4. Hook `OnAfter*`, `CanJoinMatchmakeSession`, `CleanupSearchMatchmakeSession`, `CleanupMatchmakeSessionSearchCriterias`. **Mancano** (nessun SetHandler): `GetMyBlockList` (YKW2 lo implementa a mano), `FindMatchmakeSession*` varianti, `GetGatheringRelationships`, `Search/Browse` ulteriori. [VERIFICATO elenco da `protocol.go`] |
| **MatchMaking** | `UnregisterGathering, GetDetailedParticipants, FindBySingleID, UpdateSessionURL, UpdateSessionHostV1, GetSessionURLs, UpdateSessionHost` | `FindByOwner` non e' comune (YKW2 lo scrive a mano). |
| **MatchMakingExt** | solo `EndParticipation` | |
| **NATTraversal** | `RequestProbeInitiationExt, ReportNATProperties, ReportNATTraversalResult, GetRelaySignatureKey, ReportNATTraversalResultDetail` | README di modulo: una riga. |
| **Ranking** | `GetCachedTopXRanking, GetCachedTopXRankings, GetCommonData, GetRanking, UploadCommonData, UploadScore` | **Solo callback**: devi fornire `InsertRankingByPIDAndRankingScoreData`, `GetRankingsAndCountByCategoryAndRankingOrderParam`, `GetCommonData`, `UploadCommonData`, ecc. Se nil -> `NotImplemented`. Mancano `DeleteCommonData`, `UploadScore` multipli ecc. |
| **DataStore** | `DeleteObject, GetMeta, GetMetas, SearchObject, RateObject, PostMetaBinary, PreparePostObject, PrepareGetObject, CompletePostObject, GetMetasMultipleParam, CompletePostObjects, ChangeMeta, RateObjects` | Tutti i metodi richiesti ci sono, ma richiedono callback DB: `InitializeObjectByPreparePostParam`, `InitializeObjectRatingWithSlot`, `GetObjectInfoByDataID`, `GetObjectInfosByDataStoreSearchParam`, `RateObjectWithPassword`, `DeleteObjectByDataID[WithPassword]`, `UpdateObject*`, `GetObjectOwnerByDataID`, ecc. Senza di essi -> `NotImplemented` (visto in `prepare_post_object.go`). ACNL registra il common DataStore senza callback: di fatto inattivo. |
| **SecureConnection** | `Register, RequestURLs, RegisterEx, ReplaceURL, SendReport` | `CreateReportDBRecord` da fornire; `EnableInsecureRegister()`. |
| **Utility** | `AcquireNexUniqueID, AcquireNexUniqueIDWithPassword, AssociateNexUniqueIDWithMyPrincipalID, AssociateNexUniqueIDsWithMyPrincipalID, GetAssociatedNexUniqueIDWithMyPrincipalID, GetAssociatedNexUniqueIDsWithMyPrincipalID, GetIntegerSettings, GetStringSettings` | `GetIntegerSettings/StringSettings` ritornano mappe; molti giochi le sovrascrivono (ACNL). |
| MessageDelivery / Messaging | `DeliverMessage`, `DeliverMessageMultiTarget` + messaging DB | |
| TicketGranting | `Login, LoginEx, RequestTicket` | `ConfigurePNValidation([]string{gameServerID})`. |

Non coperti dal common: **PersistentGathering** puri (non esiste un protocollo separato; le community sono in MatchmakeExtension), `SubscriptionProtocol` (pokemon-gen6 lo ha custom), `Rating` (pokemon-gen6 lo ha custom), `MatchmakeReferee`, `NintendoNotifications`.

### 3.2 Esempio: handler di community (comune)

`matchmake-extension/create_community.go` (estratto) [VERIFICATO]:

```go
func (commonProtocol *CommonProtocol) createCommunity(err error, packet nex.PacketInterface, callID uint32, community match_making_types.PersistentGathering, strMessage types.String) (*nex.RMCMessage, *nex.Error) {
	...
	if !commonProtocol.manager.CheckValidPersistentGathering(community) { return nil, InvalidArgument }
	createdPersistentGatherings, nexError := database.GetCreatedPersistentGatherings(commonProtocol.manager, connection.PID())
	if createdPersistentGatherings >= commonProtocol.PersistentGatheringCreationMax {
		return nil, nex.NewError(nex.ResultCodes.RendezVous.PersistentGatheringCreationMax, "change_error")
	}
	nexError = database.CreatePersistentGathering(commonProtocol.manager, connection, &community)
	_, nexError = match_making_database.JoinGathering(commonProtocol.manager, uint32(community.ID), connection, 1, string(strMessage))
	...
```

`findOfficialCommunity` usa `database.GetOfficialCommunities(manager, pid, isAvailableOnly, resultRange)` (le "official" sono righe di `persistent_gatherings` create dal gestore, con `participation_start/end_date`). `joinCommunity` verifica password e limite `PersistentGatheringParticipationMax`.

### 3.3 DataStore su S3

`datastore/protocol.go`: campi `S3Bucket`, `s3DataKeyBase`, `s3NotifyKeyBase`, `minIOClient *minio.Client`, `S3Presigner`, `RootCACert`, `S3GetRequestHeaders/S3PostRequestHeaders`; metodi `SetDataKeyBase`, `SetNotifyKeyBase`, `SetMinIOClient` (che crea un `S3Presigner`). `PreparePostObject` genera un POST presigned verso `bucket/<keyBase>/<dataID>.bin` (scadenza 15 min) e restituisce `DataStoreReqPostInfo{DataID, URL, RequestHeaders, FormFields, RootCACert}`. Esempio di config in Super Mario Maker (`nex/register_common_secure_server_protocols.go`): `S3Bucket = os.Getenv("PN_SMM_CONFIG_S3_BUCKET")`, `SetDataKeyBase(os.Getenv("PN_SMM_CONFIG_S3_KEY_BASE"))`, + ~15 callback da `database/datastore/*`. `SSB3DS` mostra l'inizializzazione MinIO (`PN_SSB3DS_DATASTORE_S3BUCKET/KEY/SECRET/URL`) e un `S3Presigner` custom in `globals/s3_presigner.go`.

### 3.4 Giochi con DataStore + Ranking comuni (template)

Verificato via grep degli import `nex-protocols-common-go/v2/(ranking|datastore)` in `register_common_secure_server_protocols.go`:

- **Super Mario Maker** (Wii U): DataStore common con callback DB completi (miglior template per `database/datastore/*`).
- **Puyo Puyo Tetris**: DataStore + Ranking common (entrambi; consultare `PretendoNetwork/puyo-puyo-tetris`).
- **Splatoon**, **Pikmin 3**: Ranking common.
- **Pokemon gen 6**: ranking/rating/subscription implementati a mano in `globals/rmc/` (non via common).
- **Template 3DS NEX 3.10.1**: Animal Crossing New Leaf (struttura minima).

Per DQMJ3P il flusso previsto dal gioco (ipotesi, [NON VERIFICATO]): MatchmakeExtension (scambio/sfide "WiFi"), DataStore (invio mostri/record, es. `PostMetaBinary`/`SearchObject`), Ranking (classifiche), community (`CreateCommunity`/`FindOfficialCommunity`: il tuo elenco). Va confermato con un dump del traffico (HokakuCTR dentro Nimbus sa loggare RMC/PIA).

---

## 4. BOSS (SpotPass) di Pretendo

Repo: `PretendoNetwork/BOSS` (branch default `dev`, TypeScript, MongoDB, S3 o disco) [VERIFICATO].

### 4.1 Servizi HTTP e URL 3DS

Router in `src/services/`: `npdi.ts`, `npdl.ts`, `npfl.ts`, `nppl.ts`, `npts.ts`, `spr.ts`. Domini di default (README): `npdi.cdn.pretendo.cc`, `npdl.cdn.pretendo.cc`, `npfl.c.app.pretendo.cc`, `nppl.app.pretendo.cc,nppl.c.app.pretendo.cc`, `npts.app.pretendo.cc`, `service.spr.app.pretendo.cc`.

Download file 3DS (`src/services/npdl.ts`):

```ts
npdl.get([
	'/p01/nsa/:appID/:taskID/:fileName',
	'/p01/nsa/:appID/:taskID/:languageCode/:fileName',
	'/p01/nsa/:appID/:taskID/:countryCode/:languageCode/:fileName'
], async (request, response) => {
	...
	const file = await getCTRTaskFile(appID, taskID, fileName, country, language);
```

(Casi speciali: `lingua_PAESE` in un solo segmento, o solo paese.) Quindi `GET http://npdl.cdn.nintendowifi.net/p01/nsa/<bossAppId>/<task>/[<country>/][<lang>/]<fileName>` con `fileName` = nome file **senza** `.boss` (es. `BossPresentDisc.bin`; nel filelist le voci sono senza `.boss`) [verificato dal filelist reale degli archivi].

File list (`src/services/npfl.ts`): `GET /p01/filelist/:appID/:taskID?c=&l=&a1=&a2=&a3=&ap=&tm=`; formato: riga SHA1 + riga dimensione (padding 10 caratteri) + righe `nome\tdescrizione\tattr1\tattr2\tattr3\tsize\tupdated` (CRLF). Tasksheet: `npts` (`/p01/tasksheet/1/<bossAppId>/<taskId>`, XML; 3DS "Internal Server Error" se non pubblicato). Policy list: `nppl`.

### 4.2 Modello dati e CLI

`src/models/task.ts` (collection `tasks`): `deleted, id, in_game_id, boss_app_id, creator_pid, status ('open'|'close'), interval, title_id, description, created, updated`.

`src/models/file-ctr.ts` (collection `files-ctr`): `creator_pid, hash, file_key (S3/disk), size, task_id, boss_app_id, supported_countries[], supported_languages[], attributes{attribute1..3, description}, name, serial_number (autoincrement da 50000), payload_contents[{title_id, content_datatype, ns_data_id, version, size}], flags{mark_arrived_privileged}, created, updated`.

CLI (`npm run build && ./boss --help`): env `PN_BOSS_CLI_GRPC_HOST`, `PN_BOSS_CLI_GRPC_APIKEY` (+ chiave 3DS `PN_BOSS_CLI_3DS_AES_KEY`, vedi `ctx.get3DSKeys()` in `src/cli/utils.ts`). Comandi dai sorgenti:

```
./boss app ls | view <id>                         # apps.cmd.ts (lista known apps)
./boss task create <app_id> --id <task> --title-id <hex> [--status open] [--interval N] [--desc ..]
./boss task ls <app_id> | view | delete
# file 3DS (files-3ds.cmd.ts): ls, view, download [--decrypt], create:
./boss file-3ds create <app_id> <task_id> --name <nome> --title-id <hex> --content-datatype N --ns-data-id N --version N --file <path> [--country ..] [--lang ..] [--attribute1..3] [--desc] [-m|--mark-arrived-privileged] [-n|--no-payload]
```

(Il nome esatto del sottocomando 3DS, `file-3ds` o simile, e' [NON VERIFICATO]: vedi `src/cli/cli.ts`/`root.ts`.) Il server gRPC v2 espone `RegisterTask`, `UploadFileCTR`, `ListFilesCTR`, `UpdateFileMetadataCTR`, `ListKnownBOSSApps` ecc.; l'upload richiede permesso `uploadBossFiles`.

Vincolo: `bossAppId` deve essere di 16 caratteri alfanumerici (regex `^[A-Za-z0-9]*$`, lunghezza 16). `H7btVjYWs7p5dGj6` rispetta questo formato.

### 4.3 Cifratura contenuti 3DS

Libreria `PretendoNetwork/boss-crypto` (`src/3ds.ts`) [VERIFICATO]:

- Una sola chiave: **AES-128 in CTR**, chiave dal **keyslot 0x38 (Normalkey)** della console; il repo non la fornisce (verifica solo `MD5(key) == 86fbc2bb4cb703b2a4c6cc9961319926`).
- Header container (big endian): `0x00 'boss'` (magic `626f7373`), `0x04` version `0x00010001`, `0x08` dimensione file, `0x0C` serial number (u64), `0x18` hash type (`2`), `0x1C..0x28` 12 byte di IV, poi dati cifrati da `0x28`. IV = 12 byte + `00 00 00 01`.
- Dati decifrati: content header `0x132` byte (magic 16 byte con bit `0x80` del primo byte = non "mark arrived privileged", numero payload u16 @0x10, SHA-256 @0x12, firma RSA @0x32 da 0x100), poi per ogni payload un header da `0x13C` byte (program ID u64 @0, content datatype u32 @0xC, length u32 @0x10, ns data ID u32 @0x14, version u32 @0x18, SHA-256 @0x1C, firma @0x3C) + contenuto.
- Le firme RSA non possono essere create ne' verificate (Luma le patcha). Encrypt: `encrypt3DS(aesKey, serialNumber, options[], flags?)`.

### 4.4 Nimbus e redirect di `npdl.cdn.nintendowifi.net`

`PretendoNetwork/nimbus` `patches/http/src/main.s` [VERIFICATO]:

```
target1: .asciiz "nintendowifi.net"
target2: .asciiz "nintendo.net"
target3: .asciiz "pokemon-gl.com"
replacementPretendo: .asciiz "pretendo.cc"
```

La patch del modulo `http` esegue `find_and_replace` su ogni stringa URL quando `get_nasc_environment == 2` (account Pretendo). Quindi `npdl.cdn.nintendowifi.net` -> `npdl.cdn.pretendo.cc`, `nppl.app.nintendowifi.net` -> `nppl.app.pretendo.cc`, `nasc.nintendowifi.net` -> `nasc.pretendo.cc`, ecc. Su Azahar/Citra e' presente `HTTPC_Azahar_RegisterURLReplacement`. Per un server self-hosted bisogna ricorrere a DNS/hosts o patch del modulo; Nimbus redirige **solo verso pretendo.cc**.

---

## 5. Dati SpotPass pubblici per DQMJ3P / DQMJ3

### 5.1 Trovato: Internet Archive "3ds-boss-data"

- Progetto: SpotPass Archival Project (`https://spotpassarchive.github.io/`; GitHub org `SpotPassArchive`: `SpotPassDumper9`, `SpotPassDumper11`, `BOSSUploadAPI`, `taskfinder`, `archival-tools`). Concluso; circa 4 TB raccolti da 21.491 dump 3DS.
- Archivio: `https://archive.org/details/3ds-boss-data` (244 file; uno ZIP per BOSS app ID). Metadata: `https://archive.org/metadata/3ds-boss-data`.
- **Presente `H7btVjYWs7p5dGj6.zip`**, 26.771.402 byte, 20.748 file, sha1 `e3b075aa68914371806bdf4bc793be54a1052c12`, md5 `c60af8ff728ac6bb2f6fac996520cd1e`. Download: `https://archive.org/download/3ds-boss-data/H7btVjYWs7p5dGj6.zip` (scaricato e ispezionato per questa ricerca; non copiato nel progetto).
- Struttura: `<COUNTRY>/<lang>/<TASK>/<file>`; 133 codici paese x 12 lingue (de, en, es, fr, it, ja, ko, nl, pt, ru, tw, zh), 13 file per coppia. I contenuti sono **identici** fra tutti i paesi/lingue (solo 5 file distinti):

| Task | File (nel zip: `<nome>.boss`) | Dim. (byte) | Serial container | Note filelist (nome, size payload, updated) |
|---|---|---|---|---|
| `FGONLYT` | `BossPresentDisc.bin.boss` | 6442 | 3380852 | `BossPresentDisc.bin`, 5780, 1591843065 |
| `FGONLYT` | `BossWiFiShopTbl.bin.boss` | 5406 | 1498918 | `BossWiFiShopTbl.bin`, 4744, 1486367400 |
| `BREAK01` | `BossStealthBox.bin.boss` | 706 | 1828324 | `BossStealthBox.bin`, 44, 1496804202 |
| `BREAK02` | `BossPassingMonster.bin.boss` | 786 | 1828344 | `BossPassingMonster.bin`, 124, 1496804475 |
| `BREAK03` | `BossSkyMapMonster.bin.boss` | 710 | 1828366 | `BossSkyMapMonster.bin`, 48, 1496804840 |

Tutti con magic `boss`, version `0x00010001`, hash type 2 (cifrati AES-CTR; si decifrano con `boss-crypto` e la chiave 3DS di una console). Ogni task ha anche `filelist.txt` (formato npfl, esempio `BREAK01`: `BossStealthBox.bin\t\t\t\t\t44\t1496804202`) e `tasksheet.xml` che nell'archivio contiene solo "Internal Server Error" (22 byte), quindi i **tasksheet vanno ricostruiti** (si possono prendere i formati da `BOSS/seeding/tasksheets/*.tasksheet.xml`).
- I nomi (`PresentDisc`, `WiFiShopTbl`, `StealthBox`, `PassingMonster`, `SkyMapMonster`) corrispondono ai contenuti del plugin `Anthcny144/DQMJ3P-unobtainable-content` (dischi scaricabili, starter, ecc. bloccati dietro SpotPass/StreetPass/online). **Il collegamento con DQMJ3P e' una forte inferenza dai nomi file e dalla lista BOSS; non e' confermato che `H7btVjYWs7p5dGj6` sia proprio DQMJ3P (JP) rispetto a DQMJ3 o ad altre regioni.** [NON VERIFICATO: serve il BOSS app ID letto dal gioco, vedi `bossAppId` nel save o dal codice].
- Non trovata nello stesso ZIP la lista per `snhV1gVHgJLnjhid` (altra app con gli stessi task `BREAK01/02/03/FGONLYT`): non controllata nel dettaglio; potrebbe essere DQMJ3 (non Professional) o altra regione. [NON VERIFICATO]

### 5.2 Pretendo BOSS

`src/services/grpc/boss/v2/list-known-boss-apps.ts` [VERIFICATO]:

```ts
{
	bossAppId: 'H7btVjYWs7p5dGj6',
	titleId: 0x0n,
	titleRegion: 'UNK',
	name: 'Unknown',
	tasks: ['BREAK01', 'BREAK02', 'BREAK03', 'FGONLYT']
},
...
{
	bossAppId: 'snhV1gVHgJLnjhid',
	titleId: 0x0n,
	titleRegion: 'UNK',
	name: 'Unknown',
	tasks: ['BREAK01', 'BREAK03', 'BREAK02', 'FGONLYT']
},
```

Nessuna voce con titleId `000400000016AD00` (DQMJ3) o `00040000001ACB00` (DQMJ3P) nella lista. Per confronto esiste `Y49VUspi8Bd4dqV9` = DQM2 (JPN, `0x00040000000CF500`, task `FGONLYT, WHALE01, WHALE02`). Il README di BOSS non elenca task caricati per questo app ID: Pretendo **non** ha ancora i file di DQMJ3(P) pubblicati (non verificabile lato server in produzione).

### 5.3 Dump di traffico di rete

Ricerche su GitHub (repo e codice) per `H7btVjYWs7p5dGj6` e per "DQMJ3" non hanno restituito dump di traffico NEX/Pia pubblici. Repo correlati trovati: `Akoi89/DQMJ3P-english-fixed`, `x1nixmzeng/DragonQuestLoc`, `Slashaim/citra-dqmj3pro`, `Lurpigi/Lime3ds-dqmj3p-proxy`, `Lurpigi/DQMJ3P-IT-FanTranslation`, `Lurpigi/DQMJ3P-Randomizer`, `Anthcny144/DQMJ3P-unobtainable-content`, `game-sampler/DQReader`, `game-sampler/DQ-Breeder`. Nessuno contiene pcap/log di rete [NON VERIFICATO per repo privati]. Nota per il traffico: `HokakuCTR` (plugin in Nimbus `plugin/Sources/{RMCLogger,PIALogger}.cpp`) e `PretendoNetwork/nex-viewer` servono a loggare/decodificare RMC e Pia.

---

## 6. NAT traversal / Pia P2P

- **nncs** (`PretendoNetwork/nncs`) [VERIFICATO README]: NAT check server UDP. Servono `nncs1.app.nintendowifi.net` e `nncs2.app.nintendowifi.net`, ciascuno con porte `10025` e `10125`, **IP pubblici diversi tra nncs1 e nncs2**. Messaggi implementati: tipi 1-5 e 101-103. I client mandano anche pacchetti alle porte 33334/33335 di nncs1 (senza risposta). Env: `PN_NNCS1_IP_ADDRESS`, `PN_NNCS2_IP_ADDRESS`. Anche qui la sostituzione Nimbus porta questi host a `*.pretendo.cc`.
- **NATTraversal NEX**: `nex-protocols-common-go/v2/nat-traversal` (5 metodi: `RequestProbeInitiationExt`, `ReportNATProperties`, `ReportNATTraversalResult`, `GetRelaySignatureKey`, `ReportNATTraversalResultDetail`). Il server inoltra l'inizio del probe fra i peer (usando le StationURL registrate in SecureConnection `Register`/`ReplaceURL`). Non esiste un relay dei dati: se il NAT traversal fallisce i peer non si connettono. Tutti i giochi 3DS di riferimento registrano questo protocollo con `commonnattraversal.NewCommonProtocol(natTraversalProtocol)`.
- **Pia** (wiki: `https://nintendo-wiki.pretendo.network/docs/pia`): libreria Nintendo per mesh P2P; modalita' NEX (matchmaking sul game server + NAT traversal), LDN (Switch), LAN. Il traffico di gioco P2P non passa da Pretendo; il server fornisce solo matchmaking, URL e NAT traversal. Guida utenti NAT: `https://forum.pretendo.network/t/guide-detecting-your-nat-type-on-wii-u-and-3ds-consoles/6159` (si raccomanda NAT tipo A/B).
- Implicazioni per DQMJ3P [INFERENZA]: le battaglie online (se P2P Pia) richiedono: SecureConnection con StationURL corrette, NATTraversal comune, `MatchMaking`/`MatchmakeExtension` che gestiscano la `GatheringHost` URL, e nncs raggiungibile. Eventuali meccaniche di sessione specifiche (application buffer, game attribute) vanno ricavate da un dump.

---

## 7. Contributi, aggiunta giochi, self-hosting

### 7.1 Contributi

`https://raw.githubusercontent.com/PretendoNetwork/.github/HEAD/.github/CONTRIBUTING.md` [VERIFICATO]:

- Prima di scrivere codice serve una **issue approvata** ("an issue for the changes must be made and marked as approved before making the relevant changes"), con i template (bug, feature, question).
- Canali: issue sul repo giusto, forum (Technical Discussion), Discord (sconsigliato).
- Prerequisiti: DCO, solo contenuto di tua proprieta', **rispetto della IP Nintendo** (nessun materiale proprietario; possono bloccare contributi se hai avuto accesso a materiale riservato).
- Piano pubblico: GitHub Project "Plans" (`orgs/PretendoNetwork/projects/34`). Repo `PretendoNetwork/org-issues` per issue senza repo.
- Non esiste una guida "aggiungere un gioco": per giochi ufficiali Pretendo il team inserisce il documento in `servers` (account), il record in BOSS "known apps", il dominio DNS. La mia ricerca non ha trovato documentazione di un processo per giochi di terzi [NON VERIFICATO]. Per una richiesta formale: aprire una issue "feature" (o thread nel forum Technical Discussion) citando titolo, game server ID, access key, versione NEX.

Docs sviluppatori: `https://developer.pretendo.network/home` (repo `developer-documentation`, "Very early. Most documentation is stubbed"; contiene `nex-go`, `nex-protocols-go/datastore`, overview `nex.mdx`/`prudp.mdx`) e wiki `https://nintendo-wiki.pretendo.network/docs/`.

### 7.2 Self-hosting e progetti community

- **MatthewL246/pretendo-docker**: "unofficial Docker Compose setup for self-hosting a Pretendo Network server (because there is no official self-hosting setup)". README: 3DS "Working", Citra "Coming soon". Docs: `https://matthewl246.github.io/pretendo-docker`. Include account, friends, BOSS?, ecc. (elenco container nella doc: `containers-list`) [non letto per intero].
- Fork: `Takabrycheri/taka-pretendo-docker` (MK8), `dawnofthed/Pretendo-Docker-project` (Luigi's Mansion 2), `BannedPenta01/3D-Open-Dock-U`.
- **FreakyBigFoot/fbf-3ds-servers**: server NEX/NASC community **multi-gioco su Pretendo** (Final Fantasy Explorers, Fantasy Life). Funzionamento: app homebrew "Connect" patcha il modulo friends per puntare al proprio NASC; il server instrada per game server ID i giochi ospitati e inoltra tutto il resto a Pretendo; gestisce auth, matchmaking e relay NAT; "Adding a game is a server-side change" (serve access key + endpoint). **Il modello piu' vicino al tuo obiettivo.**
- **Protarium-Network/nasc-router**: front NASC per 3DS; i `titleid` presenti nella collection Mongo `servers` vanno all'account server locale, gli altri a `nasc.pretendo.cc`; endpoint `/protarium-connect/register` per registrare PID e password NEX della console (da `FRD_GetMyPassword`). Richiede TLS legacy (`ssl_protocols TLSv1 ... ssl_ciphers ALL`) per 3DS.
- Stack minimo per test locale: MongoDB (account, BOSS), PostgreSQL (server di gioco), account server (+ gRPC), friends server (per `GetUserFriendPIDs`), server NEX di gioco (auth + secure), MinIO/S3 (DataStore, BOSS), nncs, DNS locale/Nimbus. In alternativa, per sviluppo: `LOCAL_AUTH` come SSB3DS (nessun account/friends server), `PN_YKW2/SSB3DS_*` con host dummy.

---

## 8. Piano di lavoro suggerito (derivato)

1. Ottenere dal gioco: `gameid` NASC (confermare `001ACB00`), access key (`5812c478`, verificata), BOSS app ID (verificare `H7btVjYWs7p5dGj6`), dump RMC con HokakuCTR (primo pacchetto PRUDP v0/v1, protocolli usati e ordine).
2. Clonare la struttura di `animal-crossing-new-leaf` (NEX 3.10.1, auth+secure), cambiare access key `994cba6f`, `ConfigurePNValidation([]string{"001ACB00"})`, env `PN_DQMJ3P_*`, registrare solo i protocolli osservati nel dump.
3. Test locale: modalita' `LOCAL_AUTH` alla SSB3DS, Postgres, pretendo-docker per account/friends/BOSS.
4. DataStore/Ranking: implementare le callback DB sul modello di Super Mario Maker (`database/datastore/*`) e Puyo Puyo Tetris; Ranking con le funzioni elencate.
5. SpotPass: estrarre i 5 file da `H7btVjYWs7p5dGj6.zip`, registrare task `BREAK01..03`, `FGONLYT` e caricare con il CLI BOSS (ricostruendo tasksheet). I file sono gia' cifrati, vanno caricati cosi' come sono oppure decifrati con la chiave 3DS e ri-cifrati con `encrypt3DS` (il server li ri-cifra comunque all'upload: `uploadFileCTR` chiama `encrypt3DS` partendo dal contenuto in chiaro).

## Fonti principali (URL)

- https://github.com/PretendoNetwork/account (`src/services/nasc/routes/ac.ts`, `src/database.ts`, `src/models/server.ts`, `src/provisioning.ts`, `src/middleware/nasc.ts`, `src/util.ts`)
- https://github.com/PretendoNetwork/nex-go (`prudp_server.go`, `prudp_v0_settings.go`, `prudp_v1_settings.go`, `constants/stream_type.go`, `library_version.go`)
- https://github.com/PretendoNetwork/animal-crossing-new-leaf, `yo-kai-watch-2`, `super-smash-bros-3ds`, `monster-hunter-4-ultimate`, `pokemon-gen6`, `mario-kart-7`, `tri-force-heroes`, `super-mario-maker`, `puyo-puyo-tetris`
- https://github.com/PretendoNetwork/nex-protocols-common-go (`datastore/`, `ranking/`, `matchmake-extension/`, `nat-traversal/`, `ticket-granting/protocol.go`)
- https://github.com/PretendoNetwork/BOSS, https://github.com/PretendoNetwork/boss-crypto, https://github.com/PretendoNetwork/nimbus, https://github.com/PretendoNetwork/nncs
- https://spotpassarchive.github.io/ , https://archive.org/details/3ds-boss-data , https://github.com/SpotPassArchive
- https://github.com/PretendoNetwork/.github/blob/main/.github/CONTRIBUTING.md
- https://github.com/MatthewL246/pretendo-docker , https://github.com/FreakyBigFoot/fbf-3ds-servers , https://github.com/Protarium-Network/nasc-router
- https://nintendo-wiki.pretendo.network/docs/pia , https://developer.pretendo.network/home
- https://github.com/Anthcny144/DQMJ3P-unobtainable-content
