-- Applied only through scripts/migrate_phase2.py after snapshot preflight.
-- MySQL DDL commits implicitly. Each named step is independently resumable.

-- step: season_teams
CREATE TABLE IF NOT EXISTS season_teams (
    season SMALLINT UNSIGNED NOT NULL,
    api_team_id INT UNSIGNED NOT NULL,
    team_name VARCHAR(100) NOT NULL,
    venue_id INT UNSIGNED NULL,
    team_data JSON NOT NULL,
    venue_data JSON NULL,
    PRIMARY KEY (season, api_team_id),
    CONSTRAINT fk_season_team FOREIGN KEY (api_team_id) REFERENCES teams(api_team_id),
    CONSTRAINT fk_season_venue FOREIGN KEY (venue_id) REFERENCES venues(venue_id)
);

-- step: sync_state
CREATE TABLE IF NOT EXISTS season_sync_state (
    season SMALLINT UNSIGNED NOT NULL PRIMARY KEY,
    last_success_at DATETIME(6) NOT NULL,
    last_full_sync_at DATETIME(6) NULL
);

-- step: control
CREATE TABLE IF NOT EXISTS pipeline_control (
    control_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    pending_run_id VARCHAR(250) NULL,
    pending_started_at DATETIME(6) NULL,
    pending_lease_until DATETIME(6) NULL,
    last_completed_at DATETIME(6) NULL,
    last_completed_run_id VARCHAR(250) NULL
);

-- step: control_row
INSERT INTO pipeline_control (control_id, enabled) VALUES (1,FALSE)
ON DUPLICATE KEY UPDATE control_id=pipeline_control.control_id;

-- step: metadata
ALTER TABLE live_matches
    MODIFY match_date DATETIME(6) NULL,
    ADD COLUMN season SMALLINT UNSIGNED NULL,
    ADD COLUMN status_short VARCHAR(5) NULL,
    ADD COLUMN status_long VARCHAR(100) NULL,
    ADD COLUMN elapsed SMALLINT UNSIGNED NULL,
    ADD COLUMN home_api_team_id INT UNSIGNED NULL,
    ADD COLUMN away_api_team_id INT UNSIGNED NULL,
    ADD COLUMN source_observed_at DATETIME(6) NULL,
    ADD INDEX idx_fixture_season_status_date (season,status_short,match_date),
    ADD CONSTRAINT fk_fixture_home_season FOREIGN KEY (season,home_api_team_id)
        REFERENCES season_teams(season,api_team_id),
    ADD CONSTRAINT fk_fixture_away_season FOREIGN KEY (season,away_api_team_id)
        REFERENCES season_teams(season,api_team_id);

-- step: historical_memberships
INSERT INTO season_teams (season,api_team_id,team_name,venue_id,team_data,venue_data)
SELECT 2024,t.api_team_id,t.team_name,t.venue_id,
    JSON_OBJECT('api_team_id',t.api_team_id,'team_name',t.team_name,'team_code',t.team_code,
        'country',t.country,'league',t.league,'stadium',t.stadium,'founded',t.founded,
        'is_national',t.is_national,'logo_url',t.logo_url,'venue_id',t.venue_id),
    IF(v.venue_id IS NULL,NULL,JSON_OBJECT('venue_id',v.venue_id,'venue_name',v.venue_name,
        'address',v.address,'city',v.city,'capacity',v.capacity,'surface',v.surface,'image_url',v.image_url))
FROM teams t LEFT JOIN venues v ON v.venue_id=t.venue_id
WHERE t.api_team_id IS NOT NULL
ON DUPLICATE KEY UPDATE api_team_id=season_teams.api_team_id;

-- step: historical_metadata
UPDATE live_matches m
JOIN teams h ON h.team_name=m.home_team AND h.league='Premier League'
JOIN teams a ON a.team_name=m.away_team AND a.league='Premier League'
SET m.season=2024, m.status_short='FT', m.status_long='Match Finished',
    m.home_api_team_id=h.api_team_id, m.away_api_team_id=a.api_team_id
WHERE m.season IS NULL AND m.fixture_id IN (__ARCHIVE_FIXTURE_IDS__);

-- step: enable
UPDATE pipeline_control SET enabled=TRUE WHERE control_id=1;
