// Package matchmake_extension holds MatchmakeExtension methods DQMJ3P needs that
// nex-protocols-common-go does not implement (communities = persistent gatherings).
package matchmake_extension

import (
	"time"

	"dqmj3p-online/nex/globals"
	"github.com/PretendoNetwork/nex-go/v2"
	"github.com/PretendoNetwork/nex-go/v2/types"
	match_making_database "github.com/PretendoNetwork/nex-protocols-common-go/v2/match-making/database"
	"github.com/PretendoNetwork/nex-protocols-common-go/v2/matchmake-extension/database"
	match_making_types "github.com/PretendoNetwork/nex-protocols-go/v2/match-making/types"
	matchmake_extension "github.com/PretendoNetwork/nex-protocols-go/v2/matchmake-extension"
	pqextended "github.com/PretendoNetwork/pq-extended"
)

func emptyResponse(packet nex.PacketInterface, callID uint32, methodID uint32) *nex.RMCMessage {
	endpoint := packet.Sender().(*nex.PRUDPConnection).Endpoint().(*nex.PRUDPEndPoint)

	rmcResponse := nex.NewRMCSuccess(endpoint, nil)
	rmcResponse.ProtocolID = matchmake_extension.ProtocolID
	rmcResponse.MethodID = methodID
	rmcResponse.CallID = callID

	return rmcResponse
}

func plausible(t time.Time) bool {
	return t.Year() >= 2000 && t.Year() <= 3000
}

// JoinCommunity (109/19) adds the caller to a community's participants after checking
// its password and participation period.
func JoinCommunity(err error, packet nex.PacketInterface, callID uint32, gid types.UInt32, strMessage types.String, strPassword types.String) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.Core.InvalidArgument, "change_error")
	}

	connection := packet.Sender().(*nex.PRUDPConnection)
	manager := globals.MatchmakingManager

	manager.Mutex.Lock()
	defer manager.Mutex.Unlock()

	community, nexError := database.GetPersistentGatheringByID(manager, connection.PID(), uint32(gid))
	if nexError != nil {
		return nil, nexError
	}

	if community.Password != "" && community.Password != strPassword {
		return nil, nex.NewError(nex.ResultCodes.RendezVous.InvalidPassword, "change_error")
	}

	// * Unset dates (DateTime 0) do not survive the Postgres round trip as 0 (they come back
	// * with absurd years), so only dates in a plausible range are treated as real limits
	now := time.Now()
	start := community.ParticipationStartDate.Standard()
	end := community.ParticipationEndDate.Standard()
	if (plausible(start) && now.Before(start)) || (plausible(end) && now.After(end)) {
		globals.Logger.Warningf("JoinCommunity %d outside participation period (%v - %v)", gid, start, end)
		return nil, nex.NewError(nex.ResultCodes.RendezVous.WithoutParticipationPeriod, "change_error")
	}

	_, nexError = match_making_database.JoinGathering(manager, uint32(gid), connection, 1, string(strMessage))
	if nexError != nil {
		return nil, nexError
	}

	return emptyResponse(packet, callID, matchmake_extension.MethodJoinCommunity), nil
}

// UpdateCommunity (109/18) lets the owner change a community's description, limits,
// password, attributes, application buffer and participation period.
func UpdateCommunity(err error, packet nex.PacketInterface, callID uint32, community match_making_types.PersistentGathering) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.Core.InvalidArgument, "change_error")
	}

	connection := packet.Sender().(*nex.PRUDPConnection)
	manager := globals.MatchmakingManager
	gid := uint32(community.Gathering.ID)

	manager.Mutex.Lock()
	defer manager.Mutex.Unlock()

	gathering, gatheringType, _, _, nexError := match_making_database.FindGatheringByID(manager, gid)
	if nexError != nil {
		return nil, nexError
	}

	if gatheringType != "PersistentGathering" {
		return nil, nex.NewError(nex.ResultCodes.Core.InvalidArgument, "change_error")
	}

	if gathering.OwnerPID != connection.PID() {
		return nil, nex.NewError(nex.ResultCodes.RendezVous.PermissionDenied, "change_error")
	}

	attribs := make([]uint32, len(community.Attribs))
	for i, value := range community.Attribs {
		attribs[i] = uint32(value)
	}

	tx, sqlErr := manager.Database.Begin()
	if sqlErr != nil {
		return nil, nex.NewError(nex.ResultCodes.Core.Unknown, sqlErr.Error())
	}
	defer tx.Rollback()

	_, sqlErr = tx.Exec(`UPDATE matchmaking.gatherings SET
		min_participants=$1,
		max_participants=$2,
		participation_policy=$3,
		policy_argument=$4,
		flags=$5,
		description=$6
		WHERE id=$7`,
		uint16(community.Gathering.MinimumParticipants),
		uint16(community.Gathering.MaximumParticipants),
		uint32(community.Gathering.ParticipationPolicy),
		uint32(community.Gathering.PolicyArgument),
		uint32(community.Gathering.Flags),
		string(community.Gathering.Description),
		gid,
	)
	if sqlErr != nil {
		return nil, nex.NewError(nex.ResultCodes.Core.Unknown, sqlErr.Error())
	}

	_, sqlErr = tx.Exec(`UPDATE matchmaking.persistent_gatherings SET
		password=$1,
		attribs=$2,
		application_buffer=$3,
		participation_start_date=$4,
		participation_end_date=$5
		WHERE id=$6`,
		string(community.Password),
		pqextended.Array(attribs),
		[]byte(community.ApplicationBuffer),
		community.ParticipationStartDate.Standard(),
		community.ParticipationEndDate.Standard(),
		gid,
	)
	if sqlErr != nil {
		return nil, nex.NewError(nex.ResultCodes.Core.Unknown, sqlErr.Error())
	}

	if sqlErr = tx.Commit(); sqlErr != nil {
		return nil, nex.NewError(nex.ResultCodes.Core.Unknown, sqlErr.Error())
	}

	return emptyResponse(packet, callID, matchmake_extension.MethodUpdateCommunity), nil
}
