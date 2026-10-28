package nex

import (
	"database/sql"
	"math"
	"sort"
	"time"

	"dqmj3p-online/nex/globals"
	"github.com/PretendoNetwork/nex-go/v2"
	"github.com/PretendoNetwork/nex-go/v2/types"
	commonranking "github.com/PretendoNetwork/nex-protocols-common-go/v2/ranking"
	ranking "github.com/PretendoNetwork/nex-protocols-go/v2/ranking"
	"github.com/PretendoNetwork/nex-protocols-go/v2/ranking/constants"
	ranking_types "github.com/PretendoNetwork/nex-protocols-go/v2/ranking/types"
)

// * Ranking (112) for the Wi-Fi Ranking G-Cup (Ranking Race). The game calls UploadScore (1),
// * UploadCommonData (4), GetCommonData (6), GetRanking (9) and GetStats (11); categories are
// * per cup (e.g. 29). Scores are kept in Postgres, one row per (pid, category, unique id).

func initRankingTables() {
	_, err := globals.Postgres.Exec(`CREATE SCHEMA IF NOT EXISTS ranking;
		CREATE TABLE IF NOT EXISTS ranking.scores (
			pid bigint NOT NULL,
			category bigint NOT NULL,
			unique_id numeric(20,0) NOT NULL,
			score bigint NOT NULL,
			order_by smallint NOT NULL,
			groups bytea NOT NULL,
			param numeric(20,0) NOT NULL,
			update_time timestamp NOT NULL,
			PRIMARY KEY (pid, category, unique_id));
		CREATE TABLE IF NOT EXISTS ranking.common_data (
			pid bigint NOT NULL,
			unique_id numeric(20,0) NOT NULL,
			data bytea NOT NULL,
			PRIMARY KEY (pid, unique_id));`)
	if err != nil {
		globals.Logger.Criticalf("Failed to create the ranking tables: %v", err)
	}
}

type rankingRow struct {
	pid        uint32
	uniqueID   uint64
	score      uint32
	orderBy    uint8
	groups     []byte
	param      uint64
	updateTime time.Time
	order      uint32
}

func insertRankingScore(pid types.PID, scoreData ranking_types.RankingScoreData, uniqueID types.UInt64) error {
	descending := uint8(scoreData.OrderBy) == uint8(constants.OrderByDescending)
	// * UpdateModeNormal keeps the best score, UpdateModeDeleteOld always replaces it
	keepBest := uint8(scoreData.UpdateMode) == uint8(constants.UpdateModeNormal)
	_, err := globals.Postgres.Exec(`INSERT INTO ranking.scores
		(pid, category, unique_id, score, order_by, groups, param, update_time)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (pid, category, unique_id) DO UPDATE SET
			score = excluded.score, order_by = excluded.order_by, groups = excluded.groups,
			param = excluded.param, update_time = excluded.update_time
		WHERE NOT $9 OR ($10 AND excluded.score > ranking.scores.score)
			OR (NOT $10 AND excluded.score < ranking.scores.score)`,
		uint32(pid), uint32(scoreData.Category), uint64(uniqueID), uint32(scoreData.Score),
		uint8(scoreData.OrderBy), []byte(scoreData.Groups), uint64(scoreData.Param), time.Now().UTC(),
		keepBest, descending)
	return err
}

func uploadRankingCommonData(pid types.PID, uniqueID types.UInt64, commonData types.Buffer) error {
	_, err := globals.Postgres.Exec(`INSERT INTO ranking.common_data (pid, unique_id, data) VALUES ($1, $2, $3)
		ON CONFLICT (pid, unique_id) DO UPDATE SET data = excluded.data`,
		uint32(pid), uint64(uniqueID), []byte(commonData))
	return err
}

func rankingCommonData(pid uint32, uniqueID uint64) ([]byte, error) {
	var data []byte
	err := globals.Postgres.QueryRow(`SELECT data FROM ranking.common_data WHERE pid = $1 AND unique_id = $2`,
		pid, uniqueID).Scan(&data)
	return data, err
}

// * rankedRows returns the scores of a category that match the group filter, sorted and numbered
func rankedRows(category types.UInt32, orderParam ranking_types.RankingOrderParam) ([]rankingRow, error) {
	rows, err := globals.Postgres.Query(`SELECT pid, unique_id, score, order_by, groups, param, update_time
		FROM ranking.scores WHERE category = $1`, uint32(category))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	groupIndex := uint8(orderParam.GroupIndex)
	var result []rankingRow
	for rows.Next() {
		var r rankingRow
		if err := rows.Scan(&r.pid, &r.uniqueID, &r.score, &r.orderBy, &r.groups, &r.param, &r.updateTime); err != nil {
			return nil, err
		}
		if groupIndex != uint8(constants.FilterGroupIndexNone) &&
			(int(groupIndex) >= len(r.groups) || r.groups[groupIndex] != uint8(orderParam.GroupNum)) {
			continue
		}
		result = append(result, r)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	descending := len(result) > 0 && result[0].orderBy == uint8(constants.OrderByDescending)
	sort.SliceStable(result, func(i, j int) bool {
		if result[i].score != result[j].score {
			return (result[i].score > result[j].score) == descending
		}
		return result[i].updateTime.Before(result[j].updateTime)
	})
	// * OrderCalculation113 gives tied scores the same order, OrderCalculation123 numbers them 1, 2, 3
	ties := uint8(orderParam.OrderCalculation) == uint8(constants.OrderCalculation113)
	for i := range result {
		result[i].order = uint32(i + 1)
		if ties && i > 0 && result[i].score == result[i-1].score {
			result[i].order = result[i-1].order
		}
	}
	return result, nil
}

func rankDataList(category types.UInt32, rows []rankingRow) types.List[ranking_types.RankingRankData] {
	list := types.NewList[ranking_types.RankingRankData]()
	for _, r := range rows {
		data := ranking_types.NewRankingRankData()
		data.PrincipalID = types.NewPID(uint64(r.pid))
		data.UniqueID = types.NewUInt64(r.uniqueID)
		data.Order = types.NewUInt32(r.order)
		data.Category = category
		data.Score = types.NewUInt32(r.score)
		data.Groups = types.NewBuffer(r.groups)
		data.Param = types.NewUInt64(r.param)
		if common, err := rankingCommonData(r.pid, r.uniqueID); err == nil {
			data.CommonData = types.NewBuffer(common)
		}
		updateTime := types.NewDateTime(0)
		data.UpdateTime = updateTime.FromTimestamp(r.updateTime)
		list = append(list, data)
	}
	return list
}

func window(rows []rankingRow, offset uint32, length uint8) []rankingRow {
	if int(offset) >= len(rows) {
		return nil
	}
	end := int(offset) + int(length)
	if end > len(rows) {
		end = len(rows)
	}
	return rows[offset:end]
}

func rankingRange(category types.UInt32, orderParam ranking_types.RankingOrderParam) (types.List[ranking_types.RankingRankData], uint32, error) {
	rows, err := rankedRows(category, orderParam)
	if err != nil {
		return nil, 0, err
	}
	return rankDataList(category, window(rows, uint32(orderParam.Offset), uint8(orderParam.Length))), uint32(len(rows)), nil
}

func rankingNear(pid types.PID, category types.UInt32, orderParam ranking_types.RankingOrderParam) (types.List[ranking_types.RankingRankData], uint32, error) {
	rows, err := rankedRows(category, orderParam)
	if err != nil {
		return nil, 0, err
	}
	for i, r := range rows {
		if r.pid == uint32(pid) {
			start := i - int(orderParam.Length)/2
			if start < 0 {
				start = 0
			}
			return rankDataList(category, window(rows, uint32(start), uint8(orderParam.Length))), uint32(len(rows)), nil
		}
	}
	return rankDataList(category, nil), uint32(len(rows)), nil
}

func rankingOwn(pid types.PID, category types.UInt32, orderParam ranking_types.RankingOrderParam) (types.List[ranking_types.RankingRankData], uint32, error) {
	rows, err := rankedRows(category, orderParam)
	if err != nil {
		return nil, 0, err
	}
	for _, r := range rows {
		if r.pid == uint32(pid) {
			return rankDataList(category, []rankingRow{r}), uint32(len(rows)), nil
		}
	}
	return rankDataList(category, nil), uint32(len(rows)), nil
}

// * GetCommonData returns the caller's own common data; the common protocol's callback has no PID
func getRankingCommonData(err error, packet nex.PacketInterface, callID uint32, uniqueID types.UInt64) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		return nil, nex.NewError(nex.ResultCodes.Ranking.InvalidArgument, "change_error")
	}
	connection := packet.Sender()
	endpoint := connection.Endpoint()
	data, dbErr := rankingCommonData(uint32(connection.PID()), uint64(uniqueID))
	if dbErr == sql.ErrNoRows {
		return nil, nex.NewError(nex.ResultCodes.Ranking.NotFound, "change_error")
	} else if dbErr != nil {
		globals.Logger.Error(dbErr.Error())
		return nil, nex.NewError(nex.ResultCodes.Ranking.Unknown, "change_error")
	}

	stream := nex.NewByteStreamOut(endpoint.LibraryVersions(), endpoint.ByteStreamSettings())
	types.NewBuffer(data).WriteTo(stream)
	response := nex.NewRMCSuccess(endpoint, stream.Bytes())
	response.ProtocolID = ranking.ProtocolID
	response.MethodID = ranking.MethodGetCommonData
	response.CallID = callID
	return response, nil
}

// * GetStats: one value per requested flag, in flag order (total, sum, min, max, average)
func getRankingStats(err error, packet nex.PacketInterface, callID uint32, category types.UInt32, orderParam ranking_types.RankingOrderParam, flags constants.StatsFlag) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		return nil, nex.NewError(nex.ResultCodes.Ranking.InvalidArgument, "change_error")
	}
	rows, dbErr := rankedRows(category, orderParam)
	if dbErr != nil {
		globals.Logger.Error(dbErr.Error())
		return nil, nex.NewError(nex.ResultCodes.Ranking.Unknown, "change_error")
	}

	sum, minimum, maximum := 0.0, math.Inf(1), math.Inf(-1)
	for _, r := range rows {
		score := float64(r.score)
		sum += score
		minimum = math.Min(minimum, score)
		maximum = math.Max(maximum, score)
	}
	if len(rows) == 0 {
		minimum, maximum = 0, 0
	}
	average := 0.0
	if len(rows) > 0 {
		average = sum / float64(len(rows))
	}

	stats := ranking_types.NewRankingStats()
	for _, stat := range []struct {
		flag  uint32
		value float64
	}{
		{constants.StatsFlagTotal, float64(len(rows))},
		{constants.StatsFlagSum, sum},
		{constants.StatsFlagMin, minimum},
		{constants.StatsFlagMax, maximum},
		{constants.StatsFlagAverage, average},
	} {
		if uint32(flags)&stat.flag != 0 {
			stats.StatsList = append(stats.StatsList, types.NewDouble(stat.value))
		}
	}

	endpoint := packet.Sender().Endpoint()
	stream := nex.NewByteStreamOut(endpoint.LibraryVersions(), endpoint.ByteStreamSettings())
	stats.WriteTo(stream)
	response := nex.NewRMCSuccess(endpoint, stream.Bytes())
	response.ProtocolID = ranking.ProtocolID
	response.MethodID = ranking.MethodGetStats
	response.CallID = callID
	return response, nil
}

// * nex-protocols-go v2.3.5: ranking.Interface declares SetHandlerGetStats with a types.UInt32 flags
// * argument but *ranking.Protocol takes constants.StatsFlag, so the protocol does not satisfy the
// * interface the common protocol wants. GetStats is registered on the protocol directly instead.
type rankingProtocolAdapter struct {
	*ranking.Protocol
}

func (rankingProtocolAdapter) SetHandlerGetStats(func(error, nex.PacketInterface, uint32, types.UInt32, ranking_types.RankingOrderParam, types.UInt32) (*nex.RMCMessage, *nex.Error)) {
}

func registerRankingProtocol() {
	initRankingTables()

	rankingProtocol := ranking.NewProtocol()
	globals.SecureEndpoint.RegisterServiceProtocol(rankingProtocol)
	commonRankingProtocol := commonranking.NewCommonProtocol(rankingProtocolAdapter{rankingProtocol})
	commonRankingProtocol.InsertRankingByPIDAndRankingScoreData = insertRankingScore
	commonRankingProtocol.UploadCommonData = uploadRankingCommonData
	commonRankingProtocol.GetRankingsAndCountByCategoryAndRankingOrderParam = rankingRange
	commonRankingProtocol.GetNearbyRankingsAndCountByCategoryAndRankingOrderParam = rankingNear
	commonRankingProtocol.GetOwnRankingByCategoryAndRankingOrderParam = rankingOwn
	// * No friends list in DEV mode: friend rankings fall back to the caller's own entries
	commonRankingProtocol.GetFriendsRankingsAndCountByCategoryAndRankingOrderParam = rankingOwn
	commonRankingProtocol.GetNearbyFriendsRankingsAndCountByCategoryAndRankingOrderParam = rankingOwn

	rankingProtocol.SetHandlerGetCommonData(getRankingCommonData)
	rankingProtocol.SetHandlerGetStats(getRankingStats)
}
