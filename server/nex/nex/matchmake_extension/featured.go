package matchmake_extension

import (
	"dqmj3p-online/nex/globals"
	"github.com/PretendoNetwork/nex-go/v2"
	"github.com/PretendoNetwork/nex-go/v2/types"
	matchmake_extension "github.com/PretendoNetwork/nex-protocols-go/v2/matchmake-extension"
)

// featuredLimit is the most communities added to the featured list, like the 0..100 range the
// game uses for FindOfficialCommunity.
const featuredLimit = 100

// The featured communities ("Comunita' in Evidenza", FUN_005b5774) are a FindCommunityByGatheringId
// with the ids that came over StreetPass (FUN_0023d168: up to 32 from the save, usually none).
// The game keeps the results with attribs[0] == 1 (FUN_0023ce58). The server adds every player
// and official community with attribs[0] == 1, most members first, so they can all be found.
// Calls for one id (a community page, Cerca Avversario) are left alone.
func featuredCommunityIDs() []uint32 {
	rows, err := globals.MatchmakingManager.Database.Query(`SELECT g.id
		FROM matchmaking.gatherings AS g
		INNER JOIN matchmaking.persistent_gatherings AS pg ON g.id = pg.id
		WHERE g.registered=true AND g.type='PersistentGathering' AND pg.attribs[1]=1
		ORDER BY pg.community_type DESC, cardinality(g.participants) DESC, g.id DESC
		LIMIT $1`, featuredLimit)
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil
	}
	defer rows.Close()

	var ids []uint32
	for rows.Next() {
		var id uint32
		if err := rows.Scan(&id); err == nil {
			ids = append(ids, id)
		}
	}

	return ids
}

func withFeatured(lstGID types.List[types.UInt32]) types.List[types.UInt32] {
	seen := make(map[uint32]bool)
	result := types.NewList[types.UInt32]()
	for _, gid := range lstGID {
		if !seen[uint32(gid)] {
			seen[uint32(gid)] = true
			result = append(result, gid)
		}
	}
	for _, id := range featuredCommunityIDs() {
		if !seen[id] {
			seen[id] = true
			result = append(result, types.UInt32(id))
		}
	}

	return result
}

// WrapFindCommunityByGatheringID adds every community to the featured list. Call it after the
// common protocol is set up.
func WrapFindCommunityByGatheringID(protocol *matchmake_extension.Protocol) {
	find := protocol.FindCommunityByGatheringID
	protocol.SetHandlerFindCommunityByGatheringID(func(err error, packet nex.PacketInterface, callID uint32, lstGID types.List[types.UInt32]) (*nex.RMCMessage, *nex.Error) {
		if err == nil && len(lstGID) != 1 {
			lstGID = withFeatured(lstGID)
		}
		return find(err, packet, callID, lstGID)
	})
}
