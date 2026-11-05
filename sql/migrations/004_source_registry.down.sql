-- Guarded by migrate_sources.py. refuses football-data bindings/rows.
DROP TABLE fixture_source_ids;
DROP TABLE team_source_ids;
DROP TABLE season_sources;
ALTER TABLE live_matches DROP INDEX uq_fixture_id_season;
ALTER TABLE teams DROP INDEX uq_team_name_league, DROP INDEX uq_team_source,
    DROP COLUMN source_provider, ADD UNIQUE KEY uq_team_name_league (team_name,league);
DROP TABLE source_registry_state;
