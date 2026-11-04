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
// Calls for one id go through FUN_0067901c (search by community code, the community battle
// scenes) and must stay exact: an unknown code has to come back empty (FindCommunity_CodeNotFound).
// A single saved StreetPass id looks the same, so make_url_patch.py --nex-auth skips the copy of
// the saved ids and the featured request always comes empty.
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
		asked := len(lstGID)
		if err == nil && asked != 1 {
			lstGID = withFeatured(lstGID)
		}
		globals.Logger.Infof("FindCommunityByGatheringId: asked %v, looking up %d", []types.UInt32(lstGID[:asked]), len(lstGID))
		return find(err, packet, callID, lstGID)
	})
}
