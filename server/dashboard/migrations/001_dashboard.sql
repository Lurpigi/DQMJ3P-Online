-- Statistics portal query model (docs/dashboard.md). Everything here can be rebuilt from the
-- game databases (SIL SQLite, NEX ranking/history schemas) except the revision history of final
-- standings, which records corrections.
CREATE SCHEMA IF NOT EXISTS dashboard;

-- One row per competition edition. id is permanent: gp-<mode>-cal<calendar>-n<contest>, gcup-w<week>.
CREATE TABLE dashboard.championships (
    id text PRIMARY KEY,
    server_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('grade', 'limit', 'gcup')),
    source_edition integer NOT NULL,            -- GP contest number N, or G-Cup week since 2015-01-05
    calendar_version text NOT NULL,             -- cal<N> (SIL gp_calendars.id) or gcup
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,               -- exclusive
    utc_offset_minutes integer NOT NULL,        -- official competition time zone
    rules jsonb NOT NULL DEFAULT '{}',
    rewards jsonb NOT NULL DEFAULT '{}',
    cup jsonb,                                  -- G-Cup: cup number, course, event, allowed species
    definition_provenance text NOT NULL DEFAULT 'observed' CHECK (definition_provenance IN ('observed', 'reconstructed')),
    final_revision integer,
    finalized_at timestamptz,
    coverage jsonb NOT NULL DEFAULT '{}',       -- {feature: complete|partial|reconstructed|unavailable}
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (server_id, mode, calendar_version, source_edition)
);
CREATE INDEX championships_mode_start ON dashboard.championships (mode, starts_at DESC);
CREATE INDEX championships_start ON dashboard.championships (starts_at DESC);

-- Public identities. id is opaque (HMAC of the source id); source ids stay in player_sources.
CREATE TABLE dashboard.players (
    id text PRIMARY KEY,
    namespace text NOT NULL CHECK (namespace IN ('sil', 'nex')),
    display_name text NOT NULL DEFAULT '',
    name_search text NOT NULL DEFAULT '',
    first_seen timestamptz,
    last_seen timestamptz,
    hidden boolean NOT NULL DEFAULT false       -- data removal request: names are never published
);
CREATE INDEX players_name ON dashboard.players (name_search text_pattern_ops);

-- Private mapping: never readable by the API role.
CREATE TABLE dashboard.player_sources (
    namespace text NOT NULL,
    source_id text NOT NULL,
    player_id text NOT NULL REFERENCES dashboard.players (id),
    PRIMARY KEY (namespace, source_id)
);
CREATE INDEX player_sources_player ON dashboard.player_sources (player_id);

CREATE TABLE dashboard.player_aliases (
    player_id text NOT NULL REFERENCES dashboard.players (id),
    name text NOT NULL,
    name_search text NOT NULL,
    provenance text NOT NULL CHECK (provenance IN ('observed', 'reconstructed')),
    first_seen timestamptz NOT NULL,
    last_seen timestamptz NOT NULL,
    PRIMARY KEY (player_id, name, provenance)
);
CREATE INDEX player_aliases_name ON dashboard.player_aliases (name_search text_pattern_ops);

-- One uploaded GP entry (one ticket = three rounds) or one G-Cup race upload.
CREATE TABLE dashboard.entries (
    id bigserial PRIMARY KEY,
    source_generation text NOT NULL,
    source_ns text NOT NULL,                    -- sil-gp, nex-gcup
    source_key text NOT NULL,
    source_hash text,                           -- detects a source row replaced after a restore
    championship_id text NOT NULL REFERENCES dashboard.championships (id),
    player_id text NOT NULL REFERENCES dashboard.players (id),
    kind text NOT NULL CHECK (kind IN ('gp', 'gcup')),
    received_at timestamptz NOT NULL,
    contest_day date,                           -- GP: the day the result counts for (upload day)
    points integer,
    points_win integer,
    points_pop integer,
    points_strength integer,
    points_eval integer,
    rounds integer,
    rounds_won integer,
    frames integer,                             -- G-Cup race time, 30 frames per second
    improved boolean,                           -- G-Cup: became the player's best
    observed_name text NOT NULL DEFAULT '',
    observed_location integer,
    name_provenance text NOT NULL CHECK (name_provenance IN ('observed', 'reconstructed', 'unknown')),
    validation text NOT NULL DEFAULT 'unverified'
        CHECK (validation IN ('unverified', 'malformed', 'source_lost', 'other_cup')),
    signature text CHECK (signature IN ('valid', 'invalid')),  -- GP round summary HMAC (client-made)
    decoder_version integer,
    UNIQUE (source_generation, source_ns, source_key)
);
CREATE INDEX entries_championship_player ON dashboard.entries (championship_id, player_id);
CREATE INDEX entries_championship_day ON dashboard.entries (championship_id, contest_day);
CREATE INDEX entries_player_time ON dashboard.entries (player_id, received_at DESC);
CREATE INDEX entries_time ON dashboard.entries (received_at DESC, id DESC);

CREATE TABLE dashboard.rounds (
    entry_id bigint NOT NULL REFERENCES dashboard.entries (id) ON DELETE CASCADE,
    idx smallint NOT NULL,
    opponent_name text NOT NULL DEFAULT '',
    opponent_player_id text REFERENCES dashboard.players (id),
    won boolean,                                -- true, or null: other outcomes are not decoded yet
    points_win integer,
    points_pop integer,
    points_strength integer,
    points_eval integer,
    PRIMARY KEY (entry_id, idx)
);
CREATE INDEX rounds_opponent ON dashboard.rounds (opponent_player_id);

CREATE TABLE dashboard.team_members (
    entry_id bigint NOT NULL REFERENCES dashboard.entries (id) ON DELETE CASCADE,
    slot smallint NOT NULL,
    species integer NOT NULL,
    level smallint,
    hp smallint, mp smallint, atk smallint, def smallint, agi smallint, wis smallint,
    PRIMARY KEY (entry_id, slot)
);
CREATE INDEX team_members_species ON dashboard.team_members (species, entry_id);

-- Live G-Cup leaderboard of open editions (ranking.scores rows of the edition's week).
CREATE TABLE dashboard.gcup_best (
    championship_id text NOT NULL REFERENCES dashboard.championships (id),
    player_id text NOT NULL REFERENCES dashboard.players (id),
    unique_id text NOT NULL,
    frames integer NOT NULL,
    updated_at timestamptz NOT NULL,
    team_name text NOT NULL DEFAULT '',
    PRIMARY KEY (championship_id, player_id, unique_id)
);

-- Final standings, by revision (1 = at closing; corrections add revisions, never rewrite them).
CREATE TABLE dashboard.revisions (
    championship_id text NOT NULL REFERENCES dashboard.championships (id),
    revision integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL,
    source jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (championship_id, revision)
);

CREATE TABLE dashboard.standings (
    championship_id text NOT NULL,
    revision integer NOT NULL,
    position integer NOT NULL,
    rank integer NOT NULL,
    player_id text NOT NULL REFERENCES dashboard.players (id),
    name text NOT NULL DEFAULT '',
    location integer,
    points integer, points_win integer, points_pop integer, points_strength integer, points_eval integer,
    rounds integer, rounds_won integer, entries integer,
    frames integer,
    PRIMARY KEY (championship_id, revision, position),
    FOREIGN KEY (championship_id, revision) REFERENCES dashboard.revisions (championship_id, revision)
);
CREATE INDEX standings_player ON dashboard.standings (player_id);
CREATE INDEX standings_rank ON dashboard.standings (championship_id, revision, rank);

-- Import state per source. Private: errors can name internals; the API reads dashboard.freshness.
CREATE TABLE dashboard.import_checkpoints (
    source text PRIMARY KEY,
    generation text,
    cursor bigint NOT NULL DEFAULT 0,
    fingerprint text,                           -- hash of the source row at the cursor
    source_as_of timestamptz,                   -- source read time of the last successful import
    last_success timestamptz,
    last_error text,
    last_error_at timestamptz,
    rows_total bigint NOT NULL DEFAULT 0
);

CREATE VIEW dashboard.freshness AS
    SELECT source, source_as_of, last_success, COALESCE(last_error_at > last_success, last_error_at IS NOT NULL) AS failing
    FROM dashboard.import_checkpoints;
