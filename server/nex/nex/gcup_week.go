package nex

import (
	"database/sql"
	"encoding/binary"
	"fmt"
	"os"
	"strings"
	"time"
	"unicode"
	"unicode/utf16"

	"dqmj3p-online/nex/globals"
	"github.com/lib/pq"
)

// * The G-Cup changes every Monday at 00:00 UTC: the game picks the official community with
// * attribs[1] = weeks since 2015-01-05 modulo 12 (FUN_00296340), and the end of a contest runs in
// * the game (FUN_00389aa8). A cup comes back every 12 weeks with the same id, which is also its
// * Ranking category, so the server has to close each week:
// *   - keep the results of the cup that ended in ranking.gcup_results
// *   - remove the old scores of the cup that starts. The cup that ended stays, the game reads it
// *     for the prizes
// *   - remove replays older than the previous week
// *   - write the winners into the news of the cup that starts
//   - for the statistics portal: keep the definition of each week's cup (history.gcup_editions) and
//     the full final standings with their unique ids and common data (history.gcup_finals), before
//     the cleanup, in the same transaction
// * The week runs inside the server rather than from a cron, so a server that was down catches up.

const (
	gcupCups         = 12
	gcupNewsOffset   = 0xEC
	gcupNewsChars    = 97
	gcupNameChars    = 10
	gcupWinners      = 3
	gcupFramesPerSec = 30
)

var gcupEpoch = time.Date(2015, 1, 5, 0, 0, 0, 0, time.UTC)

type gcupResult struct {
	pid        uint32
	score      uint32
	name       string
	uniqueID   uint64
	updateTime time.Time
	data       []byte
}

func gcupWeek(now time.Time) int {
	return int(now.UTC().Sub(gcupEpoch) / (7 * 24 * time.Hour))
}

func gcupWeekStart(week int) time.Time {
	return gcupEpoch.AddDate(0, 0, week*7)
}

// * Race time in frames at 30 fps: 3733 -> 2'04"43
func gcupRaceTime(score uint32) string {
	minutes := score / (60 * gcupFramesPerSec)
	seconds := score / gcupFramesPerSec % 60
	hundredths := score % gcupFramesPerSec * 100 / gcupFramesPerSec
	return fmt.Sprintf("%d'%02d\"%02d", minutes, seconds, hundredths)
}

// * The team name is the UTF-16 string at the start of the Ranking common data
func gcupTeamName(data []byte) string {
	units := make([]uint16, 0, gcupNameChars)
	for i := 0; i+1 < len(data); i += 2 {
		unit := binary.LittleEndian.Uint16(data[i:])
		if unit == 0 {
			break
		}
		units = append(units, unit)
	}
	var name []rune
	for _, r := range utf16.Decode(units) {
		if len(name) == gcupNameChars {
			break
		}
		if unicode.IsControl(r) {
			r = ' '
		}
		name = append(name, r)
	}
	if text := strings.TrimSpace(string(name)); text != "" {
		return text
	}
	return "?"
}

// * Same text as sql/gcup_official_communities.sql: one for all players, in five languages
func gcupDefaultNews(cup int) string {
	return fmt.Sprintf("G-Cup %d\nTop times win coins\nMonete ai migliori\nPremios en monedas\nPièces aux meilleurs\n上位にコイン", cup)
}

func gcupNews(cup int, previous int, results []gcupResult) string {
	if len(results) == 0 {
		return gcupDefaultNews(cup)
	}
	lines := []string{fmt.Sprintf("G-Cup %d", cup), fmt.Sprintf("G-Cup %d Top %d", previous, min(len(results), gcupWinners))}
	for i, result := range results {
		if i == gcupWinners {
			break
		}
		lines = append(lines, fmt.Sprintf("%d %s %s", i+1, result.name, gcupRaceTime(result.score)))
	}
	return strings.Join(lines, "\n")
}

// * Writes the news text into a copy of the 0x1b0-byte application buffer
func gcupBufferWithNews(buffer []byte, news string) []byte {
	out := append([]byte{}, buffer...)
	clear(out[gcupNewsOffset:])
	units := utf16.Encode([]rune(news))
	if len(units) > gcupNewsChars {
		units = units[:gcupNewsChars]
	}
	for i, unit := range units {
		binary.LittleEndian.PutUint16(out[gcupNewsOffset+i*2:], unit)
	}
	return out
}

func initGcupTables() {
	_, err := globals.Postgres.Exec(`CREATE TABLE IF NOT EXISTS ranking.gcup_weeks (
			week integer PRIMARY KEY,
			processed timestamp NOT NULL DEFAULT now());
		CREATE TABLE IF NOT EXISTS ranking.gcup_results (
			week integer NOT NULL,
			cup integer NOT NULL,
			rank integer NOT NULL,
			pid bigint NOT NULL,
			score bigint NOT NULL,
			name text NOT NULL,
			PRIMARY KEY (week, rank));`)
	if err != nil {
		globals.Logger.Criticalf("Failed to create the G-Cup tables: %v", err)
	}
}

func gcupCommunity(tx *sql.Tx, week int) (uint32, []byte, error) {
	var id uint32
	var buffer []byte
	err := tx.QueryRow(`SELECT id, application_buffer FROM matchmaking.persistent_gatherings
		WHERE community_type = 2 AND attribs[1] = 0 AND attribs[2] = $1`, week%gcupCups).Scan(&id, &buffer)
	return id, buffer, err
}

// * Closes the week that ended before `week` and prepares its cup
func processGcupWeek(tx *sql.Tx, week int) (removed []dataStoreRemoval, err error) {
	start := gcupWeekStart(week)
	previousID, previousBuffer, err := gcupCommunity(tx, week-1)
	if err != nil {
		return nil, fmt.Errorf("cup of week %d: %w", week-1, err)
	}
	cupID, buffer, err := gcupCommunity(tx, week)
	if err != nil {
		return nil, fmt.Errorf("cup of week %d: %w", week, err)
	}

	rows, err := tx.Query(`SELECT s.pid, s.score, COALESCE(c.data, ''::bytea), s.unique_id, s.update_time FROM ranking.scores s
		LEFT JOIN ranking.common_data c ON c.pid = s.pid AND c.unique_id = s.unique_id
		WHERE s.category = $1 AND s.update_time >= $2 AND s.update_time < $3
		ORDER BY s.score, s.update_time`, previousID, gcupWeekStart(week-1), start)
	if err != nil {
		return nil, err
	}
	var results []gcupResult
	for rows.Next() {
		var result gcupResult
		var data []byte
		if err := rows.Scan(&result.pid, &result.score, &data, &result.uniqueID, &result.updateTime); err != nil {
			rows.Close()
			return nil, err
		}
		result.name = gcupTeamName(data)
		result.data = data
		results = append(results, result)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}

	for i, result := range results {
		_, err := tx.Exec(`INSERT INTO ranking.gcup_results (week, cup, rank, pid, score, name)
			VALUES ($1, $2, $3, $4, $5, $6)`, week-1, previousID, i+1, result.pid, result.score, result.name)
		if err != nil {
			return nil, err
		}
		_, err = tx.Exec(`INSERT INTO history.gcup_finals
			(week, position, rank, pid, unique_id, score, update_time, name, common_data)
			VALUES ($1, $2, $2, $3, $4, $5, $6, $7, $8) ON CONFLICT (week, position) DO NOTHING`,
			week-1, i+1, result.pid, result.uniqueID, result.score, result.updateTime, result.name, result.data)
		if err != nil {
			return nil, err
		}
	}
	// * The edition that ended (its definition, if the week opened before history existed) and the new one
	if err := gcupOpenEdition(tx, week-1, previousID, previousBuffer); err != nil {
		return nil, err
	}
	if _, err := tx.Exec(`UPDATE history.gcup_editions SET closed_at = now(), entrants = $2 WHERE week = $1`,
		week-1, len(results)); err != nil {
		return nil, err
	}

	if _, err := tx.Exec(`DELETE FROM ranking.scores WHERE category = $1 AND update_time < $2`, cupID, start); err != nil {
		return nil, err
	}

	old, err := tx.Query(`DELETE FROM datastore.objects WHERE
		(upload_completed AND updated_time < $1) OR (NOT upload_completed AND created_time < $2)
		RETURNING data_id, upload_version`, gcupWeekStart(week-1), start)
	if err != nil {
		return nil, err
	}
	var ids []int64
	for old.Next() {
		var removal dataStoreRemoval
		if err := old.Scan(&removal.dataID, &removal.uploadVersion); err != nil {
			old.Close()
			return nil, err
		}
		removed = append(removed, removal)
		ids = append(ids, int64(removal.dataID))
	}
	old.Close()
	if err := old.Err(); err != nil {
		return nil, err
	}
	globals.Logger.Infof("G-Cup week %d: %d results of cup %d, removed replays %v", week, len(results), previousID, pq.Array(ids))

	news := gcupNews(week%gcupCups+1, (week-1)%gcupCups+1, results)
	buffer = gcupBufferWithNews(buffer, news)
	_, err = tx.Exec(`UPDATE matchmaking.persistent_gatherings SET application_buffer = $1 WHERE id = $2`,
		buffer, cupID)
	if err != nil {
		return nil, err
	}
	return removed, gcupOpenEdition(tx, week, cupID, buffer)
}

// * Records the cup definition (application buffer: course, rules, prizes) of a week, once
func gcupOpenEdition(tx *sql.Tx, week int, category uint32, buffer []byte) error {
	_, err := tx.Exec(`INSERT INTO history.gcup_editions (week, cup_index, category, starts_at, ends_at, definition)
		VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (week) DO NOTHING`,
		week, week%gcupCups, category, gcupWeekStart(week), gcupWeekStart(week+1), buffer)
	return err
}

type dataStoreRemoval struct {
	dataID        uint64
	uploadVersion uint32
}

// * Processes every week since the last one, or only the current one on the first run
func advanceGcupWeeks(now time.Time) error {
	current := gcupWeek(now)
	var last sql.NullInt64
	if err := globals.Postgres.QueryRow(`SELECT max(week) FROM ranking.gcup_weeks`).Scan(&last); err != nil {
		return err
	}
	first := current
	if last.Valid {
		first = int(last.Int64) + 1
	}

	for week := first; week <= current; week++ {
		tx, err := globals.Postgres.Begin()
		if err != nil {
			return err
		}
		removed, err := processGcupWeek(tx, week)
		if err == nil {
			_, err = tx.Exec(`INSERT INTO ranking.gcup_weeks (week) VALUES ($1)`, week)
		}
		if err != nil {
			tx.Rollback()
			return err
		}
		if err := tx.Commit(); err != nil {
			return err
		}
		for _, removal := range removed {
			os.Remove(dataStoreFile(removal.dataID))
			os.Remove(dataStoreUploadFile(removal.dataID, removal.uploadVersion))
		}
	}
	return nil
}

func runGcupWeeks() {
	for {
		// * A failure only delays the week: on a new database the cups are not there yet
		if err := advanceGcupWeeks(time.Now()); err != nil {
			globals.Logger.Warningf("G-Cup week: %v", err)
		}
		time.Sleep(time.Minute)
	}
}
