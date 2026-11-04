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

// The Friend Battle session is friends only: FUN_0014f51c sets MatchmakeSystemType 2 and
// participation policy 98. The common handlers check that policy with GetUserFriendPIDs,
// which needs Pretendo's friends gRPC and is empty here, so the friend could neither find
// nor join the session. The console already picks the opponent from its friend list and
// searches for the host's exact PID (attribs[0]), so give the session the policy of a
// random battle (95, FUN_0014f51c flag 1), which the server does not check.
const (
	friendsOnlyPolicy = 98
	anybodyPolicy     = 95
)

func openFriendSession(anyGathering match_making_types.GatheringHolder) match_making_types.GatheringHolder {
	if session, ok := anyGathering.Object.(match_making_types.MatchmakeSession); ok && session.ParticipationPolicy == friendsOnlyPolicy {
		session.ParticipationPolicy = anybodyPolicy
		anyGathering.Object = session
	}

	return anyGathering
}

func fromGame(anyGathering match_making_types.GatheringHolder) match_making_types.GatheringHolder {
	return openFriendSession(clearPasswordFlags(anyGathering))
}

// WrapSessionCreation fixes the game's session data (password flags, friends only policy)
// before the common handlers that create a matchmake session from it. Call it after the
// common protocol is set up.
func WrapSessionCreation(protocol *matchmake_extension.Protocol) {
	create := protocol.CreateMatchmakeSession
	protocol.SetHandlerCreateMatchmakeSession(func(err error, packet nex.PacketInterface, callID uint32, anyGathering match_making_types.GatheringHolder, message types.String, participationCount types.UInt16) (*nex.RMCMessage, *nex.Error) {
		return create(err, packet, callID, fromGame(anyGathering), message, participationCount)
	})

	autoMatchmake := protocol.AutoMatchmakeWithSearchCriteriaPostpone
	protocol.SetHandlerAutoMatchmakeWithSearchCriteriaPostpone(func(err error, packet nex.PacketInterface, callID uint32, lstSearchCriteria types.List[match_making_types.MatchmakeSessionSearchCriteria], anyGathering match_making_types.GatheringHolder, strMessage types.String) (*nex.RMCMessage, *nex.Error) {
		return autoMatchmake(err, packet, callID, lstSearchCriteria, fromGame(anyGathering), strMessage)
	})
}
