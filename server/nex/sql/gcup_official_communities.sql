-- Official communities for the Wi-Fi Ranking G-Cup (Ranking Race).
-- The G-Cup scene (code.bin 0x3ead74) takes the official community (community_type 2) with
-- attribs[0] = 0 and attribs[1] = FUN_00296340() = weeks since 2015-01-05, modulo 12, then joins it.
-- One community per week index; the 0x1b0-byte application buffer is still unknown (zeros).
-- Run: docker exec -i dqmj3p-postgres-1 psql -U dqmj3p -d dqmj3p < server/nex/sql/gcup_official_communities.sql
BEGIN;

DELETE FROM matchmaking.persistent_gatherings WHERE community_type = 2 AND attribs[1] = 0;
DELETE FROM matchmaking.gatherings g WHERE g.type = 'PersistentGathering'
    AND NOT EXISTS (SELECT 1 FROM matchmaking.persistent_gatherings pg WHERE pg.id = g.id);

DO $$
DECLARE
    week integer;
    gid bigint;
BEGIN
    FOR week IN 0..11 LOOP
        INSERT INTO matchmaking.gatherings
            (owner_pid, host_pid, min_participants, max_participants, participation_policy,
             policy_argument, flags, state, description, type)
        VALUES (2, 0, 1, 100000, 98, 0, 0, 0, 'G-Cup ' || (week + 1), 'PersistentGathering')
        RETURNING id INTO gid;
        INSERT INTO matchmaking.persistent_gatherings
            (id, community_type, password, attribs, application_buffer,
             participation_start_date, participation_end_date)
        VALUES (gid, 2, '', ARRAY[0, week, 0, 0, 0, 0], decode(repeat('00', 432), 'hex'),
                '0002-11-30 00:00:00 BC', '0002-11-30 00:00:00 BC');
    END LOOP;
END $$;

COMMIT;
