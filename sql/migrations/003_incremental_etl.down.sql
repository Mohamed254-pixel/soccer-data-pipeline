-- Executed ONLY by the guarded migration runner before any incremental writes.
-- Refuse rollback once other seasons exist. Never delete fixture rows.

ALTER TABLE live_matches
    DROP FOREIGN KEY fk_fixture_home_season,
    DROP FOREIGN KEY fk_fixture_away_season,
    DROP INDEX idx_fixture_season_status_date,
    DROP COLUMN source_observed_at,
    DROP COLUMN away_api_team_id,
    DROP COLUMN home_api_team_id,
    DROP COLUMN elapsed,
    DROP COLUMN status_long,
    DROP COLUMN status_short,
    DROP COLUMN season,
    MODIFY match_date DATETIME NOT NULL;

DROP TABLE season_sync_state;
DROP TABLE pipeline_control;
DROP TABLE season_teams;
