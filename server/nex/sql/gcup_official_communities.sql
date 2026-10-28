-- Official communities for the Wi-Fi Ranking G-Cup (Ranking Race).
-- The G-Cup scene (code.bin 0x3ead74) takes the official community (community_type 2) with
-- attribs[0] = 0 and attribs[1] = FUN_00296340() = weeks since 2015-01-05, modulo 12, then joins it.
-- One community per week index. Existing rows are kept (the game saves the gathering id it joined)
-- and only get their application buffer rewritten.
--
-- The 0x1b0-byte application buffer is the tournament definition: FUN_00296234 copies it to
-- G-Cup info + 0x3c (global at 0x89783c). Known fields (offsets in the buffer):
--   +0x04 3 x u16  species of the 3 CPU opponents (FUN_003cc478 race setup). Must be non-zero:
--                  the race counts racers up to the first species 0 and the intro table at
--                  0x7c6268 is empty for 0-1 racers, so a lone player crashes (PC=0, LR 0x584bd8).
--   +0x0a u16      entry restriction, 0 = none (FUN_002962d0, "ranking_race_limit_on/off")
--   +0x6e UTF-16   tournament name (tb_gcupname), up to 16 characters
--   +0x90 u8       opponent strength 0..100 (weak <= 33, normal 34..66, strong > 66, FUN_0029650c)
--   +0x91 u8       copied to every opponent next to the strength (unknown)
--   +0x92,+0x93 u8 course (text "coursename%d_%d" with both + 1)
--   +0x94 u8       event: 0 none, 1 bomb rocks, 2 items
--   +0x95 u8       "happening" flag (tb_happening_1)
-- Run: docker exec -i dqmj3p-postgres-1 psql -U dqmj3p -d dqmj3p < server/nex/sql/gcup_official_communities.sql
BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.gcup_buffer(week integer) RETURNS bytea AS $$
DECLARE
    buf bytea := decode(repeat('00', 432), 'hex');
    -- Species from a real Grand Prix team; any monster that can be ridden works.
    opponents integer[] := ARRAY[71, 346, 442];
    name text := 'G-Cup ' || (week + 1);
    i integer;
BEGIN
    FOR i IN 1..3 LOOP
        buf := set_byte(buf, 2 + i * 2, opponents[i] & 255);
        buf := set_byte(buf, 3 + i * 2, opponents[i] >> 8);
    END LOOP;
    FOR i IN 1..length(name) LOOP
        buf := set_byte(buf, 0x6e + (i - 1) * 2, ascii(substr(name, i, 1)));
    END LOOP;
    buf := set_byte(buf, 0x90, 10 + week * 7);
    RETURN buf;
END $$ LANGUAGE plpgsql;

DO $$
DECLARE
    week integer;
    gid bigint;
BEGIN
    FOR week IN 0..11 LOOP
        IF NOT EXISTS (SELECT 1 FROM matchmaking.persistent_gatherings
                       WHERE community_type = 2 AND attribs[1] = 0 AND attribs[2] = week) THEN
            INSERT INTO matchmaking.gatherings
                (owner_pid, host_pid, min_participants, max_participants, participation_policy,
                 policy_argument, flags, state, description, type)
            VALUES (2, 0, 1, 100000, 98, 0, 0, 0, 'G-Cup ' || (week + 1), 'PersistentGathering')
            RETURNING id INTO gid;
            INSERT INTO matchmaking.persistent_gatherings
                (id, community_type, password, attribs, application_buffer,
                 participation_start_date, participation_end_date)
            VALUES (gid, 2, '', ARRAY[0, week, 0, 0, 0, 0], ''::bytea,
                    '0002-11-30 00:00:00 BC', '0002-11-30 00:00:00 BC');
        END IF;
        UPDATE matchmaking.persistent_gatherings SET application_buffer = pg_temp.gcup_buffer(week)
        WHERE community_type = 2 AND attribs[1] = 0 AND attribs[2] = week;
    END LOOP;
END $$;

COMMIT;
