-- Run only through migrate_sources.py, after reviewed migration 003.
-- Writers must be stopped. MySQL DDL commits implicitly.
CREATE TABLE IF NOT EXISTS source_registry_state (
    control_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    ready BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO source_registry_state (control_id,ready) VALUES (1,FALSE)
ON DUPLICATE KEY UPDATE control_id=source_registry_state.control_id;
-- step: teams
ALTER TABLE teams
    ADD COLUMN source_provider ENUM('api_football','football_data') NOT NULL DEFAULT 'api_football',
    DROP INDEX uq_team_name_league,
    ADD UNIQUE KEY uq_team_name_league (team_name,league,source_provider),
    ADD UNIQUE KEY uq_team_source (api_team_id,source_provider);
-- step: fixtures
ALTER TABLE live_matches ADD UNIQUE KEY uq_fixture_id_season (fixture_id,season);
CREATE TABLE IF NOT EXISTS season_sources (
    season SMALLINT UNSIGNED NOT NULL PRIMARY KEY,
    provider ENUM('api_football','football_data') NOT NULL,
    UNIQUE KEY uq_season_source (season,provider),
    CONSTRAINT chk_archive_source CHECK (season<>2024 OR provider='api_football')
);
CREATE TABLE IF NOT EXISTS team_source_ids (
    provider ENUM('api_football','football_data') NOT NULL,
    source_id INT UNSIGNED NOT NULL,
    canonical_id INT UNSIGNED NOT NULL,
    PRIMARY KEY (provider,source_id),
    UNIQUE KEY uq_team_canonical (canonical_id),
    CONSTRAINT fk_source_team FOREIGN KEY (canonical_id,provider) REFERENCES teams(api_team_id,source_provider),
    CONSTRAINT chk_team_namespace CHECK (source_id>0 AND source_id<2147483648 AND
      ((provider='api_football' AND canonical_id=source_id) OR
       (provider='football_data' AND canonical_id=source_id+2147483648)))
);
CREATE TABLE IF NOT EXISTS fixture_source_ids (
    provider ENUM('api_football','football_data') NOT NULL,
    source_id BIGINT UNSIGNED NOT NULL,
    canonical_id BIGINT UNSIGNED NOT NULL,
    season SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (provider,source_id),
    UNIQUE KEY uq_fixture_canonical (canonical_id),
    CONSTRAINT fk_source_fixture FOREIGN KEY (canonical_id,season) REFERENCES live_matches(fixture_id,season),
    CONSTRAINT fk_source_season FOREIGN KEY (season,provider) REFERENCES season_sources(season,provider),
    CONSTRAINT chk_fixture_namespace CHECK (source_id>0 AND source_id<9223372036854775808 AND
      ((provider='api_football' AND canonical_id=source_id) OR
       (provider='football_data' AND canonical_id=source_id+9223372036854775808)))
);
INSERT INTO season_sources (season,provider) SELECT DISTINCT season,'api_football' FROM live_matches
ON DUPLICATE KEY UPDATE season=season_sources.season;
INSERT INTO team_source_ids (provider,source_id,canonical_id)
SELECT 'api_football',api_team_id,api_team_id FROM teams WHERE source_provider='api_football'
ON DUPLICATE KEY UPDATE source_id=team_source_ids.source_id;
INSERT INTO fixture_source_ids (provider,source_id,canonical_id,season)
SELECT 'api_football',fixture_id,fixture_id,season FROM live_matches
ON DUPLICATE KEY UPDATE source_id=fixture_source_ids.source_id;
