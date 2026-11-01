package nex

import (
	"database/sql"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"
	"unicode/utf16"

	"dqmj3p-online/nex/globals"
	"github.com/PretendoNetwork/plogger-go"
	"github.com/lib/pq"
)

func TestGcupWeek(t *testing.T) {
	for _, test := range []struct {
		now   time.Time
		week  int
		index int
	}{
		{time.Date(2015, 1, 5, 0, 0, 0, 0, time.UTC), 0, 0},
		{time.Date(2026, 11, 1, 23, 59, 59, 0, time.UTC), 616, 4},
		{time.Date(2026, 11, 2, 0, 0, 0, 0, time.UTC), 617, 5},
		{time.Date(2026, 11, 9, 0, 0, 0, 0, time.UTC), 618, 6},
	} {
		week := gcupWeek(test.now)
		if week != test.week || week%gcupCups != test.index {
			t.Errorf("%v: week %d index %d, want %d %d", test.now, week, week%gcupCups, test.week, test.index)
		}
	}
	if start := gcupWeekStart(617); !start.Equal(time.Date(2026, 11, 2, 0, 0, 0, 0, time.UTC)) {
		t.Errorf("start of week 617: %v", start)
	}
}

func TestGcupRaceTime(t *testing.T) {
	for score, want := range map[uint32]string{3733: "2'04\"43", 4490: "2'29\"66", 0: "0'00\"00", 30: "0'01\"00"} {
		if got := gcupRaceTime(score); got != want {
			t.Errorf("%d: %s, want %s", score, got, want)
		}
	}
}

func utf16Bytes(text string) []byte {
	var out []byte
	for _, unit := range utf16.Encode([]rune(text)) {
		out = append(out, byte(unit), byte(unit>>8))
	}
	return append(out, 0, 0)
}

func TestGcupTeamName(t *testing.T) {
	for want, data := range map[string][]byte{
		"JEJ":        utf16Bytes("JEJ"),
		"ABCDEFGHIJ": utf16Bytes("ABCDEFGHIJKLMNOP"),
		"A B":        utf16Bytes("A\nB"),
		"?":          nil,
		"コイン":        utf16Bytes("コイン"),
	} {
		if got := gcupTeamName(data); got != want {
			t.Errorf("%q, want %q", got, want)
		}
	}
}

func TestGcupNews(t *testing.T) {
	long := strings.Repeat("W", gcupNameChars)
	longest := []gcupResult{{name: long, score: 35999}, {name: long, score: 35999}, {name: long, score: 35999}, {name: long, score: 35999}}
	news := gcupNews(12, 11, longest)
	if units := len(utf16.Encode([]rune(news))); units > gcupNewsChars {
		t.Errorf("%d characters, limit %d: %q", units, gcupNewsChars, news)
	}
	if strings.Count(news, "\n") != 4 {
		t.Errorf("expected title, heading and three winners: %q", news)
	}
	if units := len(utf16.Encode([]rune(gcupDefaultNews(12)))); units > gcupNewsChars {
		t.Errorf("default news: %d characters", units)
	}
	if got := gcupNews(6, 5, nil); got != gcupDefaultNews(6) {
		t.Errorf("no results: %q", got)
	}

	buffer := make([]byte, 0x1b0)
	for i := range buffer {
		buffer[i] = 0xAA
	}
	out := gcupBufferWithNews(buffer, strings.Repeat("x", 200))
	if buffer[gcupNewsOffset] != 0xAA || out[gcupNewsOffset-1] != 0xAA {
		t.Error("buffer changed outside the news field")
	}
	if out[gcupNewsOffset+gcupNewsChars*2-2] != 'x' || out[gcupNewsOffset+gcupNewsChars*2] != 0 || out[len(out)-1] != 0 {
		t.Error("news not limited to the field with a terminator")
	}
}

// * Needs an empty database, for example:
// * PN_DQMJ3P_TEST_POSTGRES_URI=postgres://dqmj3p:dqmj3p@127.0.0.1:54329/gcup_test?sslmode=disable
func TestAdvanceGcupWeeks(t *testing.T) {
	uri := os.Getenv("PN_DQMJ3P_TEST_POSTGRES_URI")
	if uri == "" {
		t.Skip("PN_DQMJ3P_TEST_POSTGRES_URI not set")
	}
	var err error
	globals.Logger = plogger.NewLogger()
	if globals.Postgres, err = sql.Open("postgres", uri); err != nil {
		t.Fatal(err)
	}
	db := globals.Postgres
	exec := func(query string, args ...any) {
		t.Helper()
		if _, err := db.Exec(query, args...); err != nil {
			t.Fatal(err)
		}
	}
	dataStoreDir = t.TempDir()
	exec(`DROP SCHEMA IF EXISTS matchmaking, ranking, datastore CASCADE`)
	exec(`CREATE SCHEMA matchmaking`)
	exec(`CREATE TABLE matchmaking.persistent_gatherings (id bigint PRIMARY KEY, community_type integer,
		attribs bigint[], application_buffer bytea)`)
	initDataStoreTables()
	initRankingTables()
	initGcupTables()

	buffer := make([]byte, 0x1b0)
	for index := 0; index < gcupCups; index++ {
		exec(`INSERT INTO matchmaking.persistent_gatherings VALUES ($1, 2, $2, $3)`,
			index+1, pq.Array([]int64{0, int64(index), 0, 0, 0, 0}), buffer)
	}
	score := func(pid, category, value int, when time.Time) {
		exec(`INSERT INTO ranking.scores VALUES ($1, $2, 0, $3, 0, ''::bytea, 0, $4)`, pid, category, value, when)
	}
	object := func(id int, completed bool, when time.Time) {
		exec(`INSERT INTO datastore.objects (data_id, owner, size, name, data_type, meta_binary, permission,
			del_permission, flag, period, refer_data_id, tags, persistence_slot_id, upload_completed,
			created_time, updated_time) VALUES ($1, 1, 1, 'REPLAY_DATA', 0, ''::bytea, 0, 0, 0, 0, 0, '{}', 0, $2, $3, $3)`,
			id, completed, when)
		if err := os.WriteFile(dataStoreFile(uint64(id)), []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	count := func(query string, args ...any) int {
		t.Helper()
		var n int
		if err := db.QueryRow(query, args...).Scan(&n); err != nil {
			t.Fatal(err)
		}
		return n
	}
	news := func(cup int) string {
		t.Helper()
		var out []byte
		if err := db.QueryRow(`SELECT application_buffer FROM matchmaking.persistent_gatherings WHERE id = $1`, cup).Scan(&out); err != nil {
			t.Fatal(err)
		}
		return strings.TrimRight(string(out[gcupNewsOffset:]), "\x00")
	}
	ascii := func(text string) string {
		var out strings.Builder
		for i, b := range []byte(text) {
			if i%2 == 0 {
				out.WriteByte(b)
			}
		}
		return out.String()
	}

	// * Week 616 is cup 5 (index 4), week 617 cup 6 (index 5)
	during := gcupWeekStart(616).Add(24 * time.Hour)
	score(100, 5, 4490, during)
	score(101, 5, 3733, during)
	score(102, 5, 5000, gcupWeekStart(604)) // * same cup 12 weeks ago: removed, not a result of week 616
	score(103, 6, 4000, gcupWeekStart(605)) // * cup 6 last time: removed when it comes back
	score(104, 6, 4100, gcupWeekStart(617).Add(time.Hour))
	exec(`INSERT INTO ranking.common_data VALUES (100, 0, $1), (101, 0, $2)`, utf16Bytes("JEJ"), utf16Bytes("Lurpigi"))
	object(1, true, gcupWeekStart(614))
	object(2, true, during)
	object(3, false, during)

	if err := advanceGcupWeeks(gcupWeekStart(616).Add(48 * time.Hour)); err != nil {
		t.Fatal(err)
	}
	if n := count(`SELECT count(*) FROM ranking.scores WHERE category = 5`); n != 2 {
		t.Errorf("first run must drop only the score from 12 weeks ago: %d left", n)
	}

	if err := advanceGcupWeeks(gcupWeekStart(617).Add(time.Minute)); err != nil {
		t.Fatal(err)
	}
	if err := advanceGcupWeeks(gcupWeekStart(617).Add(2 * time.Minute)); err != nil {
		t.Fatal(err)
	}
	if n := count(`SELECT count(*) FROM ranking.gcup_results WHERE week = 616`); n != 2 {
		t.Errorf("%d results for week 616, want 2 without the older score", n)
	}
	if n := count(`SELECT pid FROM ranking.gcup_results WHERE week = 616 AND rank = 1`); n != 101 {
		t.Errorf("winner %d, want the lowest time", n)
	}
	if n := count(`SELECT count(*) FROM ranking.scores WHERE category = 5`); n != 2 {
		t.Errorf("the cup that ended lost its scores: %d left", n)
	}
	if n := count(`SELECT count(*) FROM ranking.scores WHERE pid = 103`); n != 0 {
		t.Error("old score of the new cup not removed")
	}
	if n := count(`SELECT count(*) FROM ranking.scores WHERE pid = 104`); n != 1 {
		t.Error("score of the new week removed")
	}
	if n := count(`SELECT count(*) FROM datastore.objects`); n != 1 {
		t.Errorf("%d objects left, want the recent completed replay", n)
	}
	if _, err := os.Stat(dataStoreFile(1)); err == nil {
		t.Error("file of the old replay not removed")
	}
	want := "G-Cup 6\nG-Cup 5 Top 2\n1 Lurpigi " + gcupRaceTime(3733) + "\n2 JEJ " + gcupRaceTime(4490)
	if got := ascii(news(6)); got != want {
		t.Errorf("news %q, want %q", got, want)
	}

	// * Two weeks late: both are processed. Nobody raced cup 6 before the jump to week 619
	if err := advanceGcupWeeks(gcupWeekStart(619).Add(time.Hour)); err != nil {
		t.Fatal(err)
	}
	if n := count(`SELECT count(*) FROM ranking.gcup_weeks`); n != 4 {
		t.Errorf("%d weeks processed, want 4", n)
	}
	if got := ascii(news(8)); !strings.HasPrefix(got, "G-Cup 8\nTop times") {
		t.Errorf("default news expected: %q", fmt.Sprint(got))
	}
}
