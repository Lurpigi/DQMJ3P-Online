package globals

import (
	"database/sql"

	pbfriends "github.com/PretendoNetwork/grpc/go/friends"
	"github.com/PretendoNetwork/nex-go/v2"
	common_globals "github.com/PretendoNetwork/nex-protocols-common-go/v2/globals"
	"github.com/PretendoNetwork/plogger-go"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

var Postgres *sql.DB
var MatchmakingManager *common_globals.MatchmakingManager
var Logger *plogger.Logger
var KerberosPassword = "password" // * Default password

// AccessKey is the game's PRUDP access key (L"5812c478", passed to NgsFacade::LoginAsync at 0x66c4ec)
const AccessKey = "5812c478"

// GameServerID is the NEX game server ID the client logs into (NASC gameid)
const GameServerID = 0x001ACB00

// TitleIDUniqueID is the unique ID part of title 00040000001ACB00, used to validate NEX tokens
const TitleIDUniqueID = "001ACB00"

// ServerBuildString is reported to clients by the authentication server; set with -ldflags
var ServerBuildString = "dqmj3p-online"

// DevPassword, when set, is the NEX password of every PID (local testing without Pretendo services)
var DevPassword string

var AuthenticationServer *nex.PRUDPServer
var AuthenticationEndpoint *nex.PRUDPEndPoint

var SecureServer *nex.PRUDPServer
var SecureEndpoint *nex.PRUDPEndPoint

var GRPCFriendsClientConnection *grpc.ClientConn
var GRPCFriendsClient pbfriends.FriendsClient
var GRPCFriendsCommonMetadata metadata.MD
