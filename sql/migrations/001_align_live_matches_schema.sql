USE soccer_db;

ALTER TABLE live_matches
    MODIFY fixture_id BIGINT UNSIGNED NOT NULL,
    MODIFY home_goals SMALLINT UNSIGNED NULL,
    MODIFY away_goals SMALLINT UNSIGNED NULL,
    ADD UNIQUE KEY uq_live_fixture (
        match_date,
        home_team,
        away_team
    ),
    ADD INDEX idx_live_match_date (match_date),
    ADD INDEX idx_live_home_team (home_team),
    ADD INDEX idx_live_away_team (away_team);
