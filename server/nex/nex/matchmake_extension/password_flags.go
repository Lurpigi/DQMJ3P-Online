package matchmake_extension

import (
	"github.com/PretendoNetwork/nex-go/v2"
	"github.com/PretendoNetwork/nex-go/v2/types"
	match_making_types "github.com/PretendoNetwork/nex-protocols-go/v2/match-making/types"
	matchmake_extension "github.com/PretendoNetwork/nex-protocols-go/v2/matchmake-extension"
)

// DQMJ3P never sets MatchmakeSession.UserPasswordEnabled / SystemPasswordEnabled, so they
// carry leftover memory (01 01, 01 00 or 00 00 from one call to the next). Its search
// criteria exclude password-protected sessions, and the common AutoMatchmake answers
// PermissionDenied (006-0105) when the match it found has either flag set, so a random
// host stayed invisible to its opponent. The game has no session passwords: clear both.
func clearPasswordFlags(anyGathering match_making_types.GatheringHolder) match_making_types.GatheringHolder {
	if session, ok := anyGathering.Object.(match_making_types.MatchmakeSession); ok {
		session.UserPasswordEnabled = types.NewBool(session.UserPassword != "")
		session.SystemPasswordEnabled = types.NewBool(false)
		anyGathering.Object = session
	}

	return anyGathering
}

// WrapSessionCreation clears the password flags before the common handlers that create
// a matchmake session from the game's data. Call it after the common protocol is set up.
func WrapSessionCreation(protocol *matchmake_extension.Protocol) {
	create := protocol.CreateMatchmakeSession
	protocol.SetHandlerCreateMatchmakeSession(func(err error, packet nex.PacketInterface, callID uint32, anyGathering match_making_types.GatheringHolder, message types.String, participationCount types.UInt16) (*nex.RMCMessage, *nex.Error) {
		return create(err, packet, callID, clearPasswordFlags(anyGathering), message, participationCount)
	})

	autoMatchmake := protocol.AutoMatchmakeWithSearchCriteriaPostpone
	protocol.SetHandlerAutoMatchmakeWithSearchCriteriaPostpone(func(err error, packet nex.PacketInterface, callID uint32, lstSearchCriteria types.List[match_making_types.MatchmakeSessionSearchCriteria], anyGathering match_making_types.GatheringHolder, strMessage types.String) (*nex.RMCMessage, *nex.Error) {
		return autoMatchmake(err, packet, callID, lstSearchCriteria, clearPasswordFlags(anyGathering), strMessage)
	})
}
