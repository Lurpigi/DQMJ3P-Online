-- Grand Prix team check: SIL marks results whose team cannot come from an unmodified game
-- (gp_results.rejected, server/sil/sil_server.py team_problems); they stay listed but count nowhere.
ALTER TABLE dashboard.entries DROP CONSTRAINT entries_validation_check;
ALTER TABLE dashboard.entries ADD CONSTRAINT entries_validation_check
    CHECK (validation IN ('unverified', 'malformed', 'source_lost', 'other_cup', 'rejected'));
-- Layout the team_members rows were decoded with: 2 = level at monster +0x2e. NULL = imported
-- when the level was read at +0x3c (the level cap byte); the importer decodes those teams again.
ALTER TABLE dashboard.entries ADD COLUMN team_layout smallint;
