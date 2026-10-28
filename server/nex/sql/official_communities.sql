-- Official communities for Community Battle ("Sfida Comunitaria" -> "Trova una Comunita'" ->
-- "Comunita' Ufficiale"). The game calls FindOfficialCommunity (community_type 2) and keeps only the
-- ones with attribs[0] == 1 (the G-Cup communities have attribs[0] == 0, see gcup_official_communities.sql).
--
-- The 0x1b0-byte application buffer has the layout the game writes for user communities
-- (CreateCommunity); the community page (FUN_005bdce8) reads it at +0x558 of its data:
--   +0x00 UTF-16  community name (at most 16 characters, zero terminated)
--   +0x24 UTF-16  comment
--   +0x48 UTF-16  owner name
--   +0x60 0x18 B  rules (not decoded yet; copied from a community created in game with the default
--                 rules: 10 turns, any tactics, no swap, same family, 30 s per turn, speed x2,
--                 any community level, origin and grade)
--   +0x78, +0x98, +0xb8 UTF-16 (0x20 B each)  official communities only: three text lines shown
--                 instead of community level / origin / grade (tb_rule_00..02)
-- The participation start date is shown as the creation date.
-- Existing rows are kept (players save the ids they joined) and only get their buffer rewritten.
-- Run: docker exec -i dqmj3p-postgres-1 psql -U dqmj3p -d dqmj3p < server/nex/sql/official_communities.sql
BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.put_utf16(buf bytea, pos integer, value text) RETURNS bytea AS $$
DECLARE
    i integer;
BEGIN
    FOR i IN 1..length(value) LOOP
        buf := set_byte(buf, pos + (i - 1) * 2, ascii(substr(value, i, 1)) & 255);
        buf := set_byte(buf, pos + (i - 1) * 2 + 1, ascii(substr(value, i, 1)) >> 8);
    END LOOP;
    RETURN buf;
END $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pg_temp.community_buffer(name text, comment text, rules text[]) RETURNS bytea AS $$
DECLARE
    buf bytea := decode(repeat('00', 432), 'hex');
    i integer;
BEGIN
    buf := pg_temp.put_utf16(buf, 0, name);
    buf := pg_temp.put_utf16(buf, 0x24, comment);
    buf := pg_temp.put_utf16(buf, 0x48, 'DQMJ3P');
    buf := overlay(buf PLACING decode('060200020001000200000000004b000000000000', 'hex') FROM 0x61);
    FOR i IN 1..array_length(rules, 1) LOOP
        buf := pg_temp.put_utf16(buf, 0x58 + i * 0x20, rules[i]);
    END LOOP;
    RETURN buf;
END $$ LANGUAGE plpgsql;

DO $$
DECLARE
    official record;
    gid bigint;
BEGIN
    -- Rows are matched by description (the name), since the game expects attribs {1, 0, ...}.
    -- Rule lines: at most 15 characters each.
    FOR official IN SELECT * FROM (VALUES
        ('Ufficiale 1', 'Benvenuti!', ARRAY['Comunità aperta', 'a tutti i', 'domatori!'])
    ) AS t(name, comment, rules) LOOP
        SELECT pg.id INTO gid FROM matchmaking.persistent_gatherings pg
        JOIN matchmaking.gatherings g USING (id)
        WHERE pg.community_type = 2 AND pg.attribs[1] = 1 AND g.description = official.name;
        IF gid IS NULL THEN
            INSERT INTO matchmaking.gatherings
                (owner_pid, host_pid, min_participants, max_participants, participation_policy,
                 policy_argument, flags, state, description, type)
            VALUES (2, 0, 0, 0, 97, 0, 513, 0, official.name, 'PersistentGathering')
            RETURNING id INTO gid;
            INSERT INTO matchmaking.persistent_gatherings
                (id, community_type, password, attribs, application_buffer,
                 participation_start_date, participation_end_date)
            VALUES (gid, 2, '', ARRAY[1, 0, 0, 0, 0, 0], ''::bytea,
                    date_trunc('second', now()), '0002-11-30 00:00:00 BC');
        END IF;
        UPDATE matchmaking.persistent_gatherings
        SET application_buffer = pg_temp.community_buffer(official.name, official.comment, official.rules)
        WHERE id = gid;
    END LOOP;
END $$;

COMMIT;
