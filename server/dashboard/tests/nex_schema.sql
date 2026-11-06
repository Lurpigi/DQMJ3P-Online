-- The NEX tables the importer reads, as server/nex creates them (ranking.go, gcup_week.go,
-- matchmaking from nex-protocols-common-go). Keep in sync with the Go code.
CREATE SCHEMA matchmaking;
CREATE TABLE matchmaking.persistent_gatherings (id bigint PRIMARY KEY, community_type integer, attribs bigint[],
    application_buffer bytea, password text);
CREATE SCHEMA ranking;
CREATE TABLE ranking.scores (pid bigint NOT NULL, category bigint NOT NULL, unique_id numeric(20,0) NOT NULL,
    score bigint NOT NULL, order_by smallint NOT NULL, groups bytea NOT NULL, param numeric(20,0) NOT NULL,
    update_time timestamp NOT NULL, PRIMARY KEY (pid, category, unique_id));
CREATE TABLE ranking.common_data (pid bigint NOT NULL, unique_id numeric(20,0) NOT NULL, data bytea NOT NULL,
    PRIMARY KEY (pid, unique_id));
CREATE TABLE ranking.gcup_weeks (week integer PRIMARY KEY, processed timestamp NOT NULL DEFAULT now());
CREATE TABLE ranking.gcup_results (week integer NOT NULL, cup integer NOT NULL, rank integer NOT NULL, pid bigint NOT NULL,
    score bigint NOT NULL, name text NOT NULL, PRIMARY KEY (week, rank));
CREATE SCHEMA history;
CREATE TABLE history.gcup_submissions (id bigserial PRIMARY KEY, pid bigint NOT NULL, category bigint NOT NULL,
    unique_id numeric(20,0) NOT NULL, score bigint NOT NULL, order_by smallint NOT NULL, update_mode smallint NOT NULL,
    groups bytea NOT NULL, param numeric(20,0) NOT NULL, received timestamptz NOT NULL, week integer NOT NULL,
    changed_best boolean NOT NULL);
CREATE TABLE history.gcup_common_data (id bigserial PRIMARY KEY, pid bigint NOT NULL, unique_id numeric(20,0) NOT NULL,
    data bytea NOT NULL, received timestamptz NOT NULL, week integer NOT NULL);
CREATE TABLE history.gcup_editions (week integer PRIMARY KEY, cup_index integer NOT NULL, category bigint NOT NULL,
    starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, definition bytea NOT NULL,
    opened_at timestamptz NOT NULL DEFAULT now(), closed_at timestamptz, entrants integer);
CREATE TABLE history.gcup_finals (week integer NOT NULL, position integer NOT NULL, rank integer NOT NULL, pid bigint NOT NULL,
    unique_id numeric(20,0) NOT NULL, score bigint NOT NULL, update_time timestamp NOT NULL, name text NOT NULL,
    common_data bytea NOT NULL, PRIMARY KEY (week, position));
