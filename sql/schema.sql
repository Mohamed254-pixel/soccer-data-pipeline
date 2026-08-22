CREATE DATABASE IF NOT EXISTS soccer_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE soccer_db;


CREATE TABLE IF NOT EXISTS live_matches (
    fixture_id BIGINT UNSIGNED NOT NULL,
    match_date DATETIME NOT NULL,
    home_team VARCHAR(100) NOT NULL,
    away_team VARCHAR(100) NOT NULL,
    home_goals SMALLINT UNSIGNED,
    away_goals SMALLINT UNSIGNED,
    PRIMARY KEY (fixture_id),
    UNIQUE KEY uq_live_fixture (match_date, home_team, away_team),
    INDEX idx_live_match_date (match_date),
    INDEX idx_live_home_team (home_team),
    INDEX idx_live_away_team (away_team)
);

CREATE TABLE IF NOT EXISTS venues (
    venue_id INT UNSIGNED NOT NULL,
    venue_name VARCHAR(150) NOT NULL,
    address VARCHAR(255),
    city VARCHAR(100),
    capacity INT UNSIGNED,
    surface VARCHAR(50),
    image_url VARCHAR(500),
    PRIMARY KEY (venue_id),
    INDEX idx_venues_city (city)
);

CREATE TABLE IF NOT EXISTS teams (
    team_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    api_team_id INT UNSIGNED,
    team_name VARCHAR(100) NOT NULL,
    team_code VARCHAR(20),
    country VARCHAR(100),
    league VARCHAR(100),
    stadium VARCHAR(150),
    founded SMALLINT UNSIGNED,
    is_national TINYINT(1) NOT NULL DEFAULT 0,
    logo_url VARCHAR(500),
    venue_id INT UNSIGNED,
    PRIMARY KEY (team_id),
    UNIQUE KEY uq_teams_api_team_id (api_team_id),
    UNIQUE KEY uq_team_name_league (team_name, league),
    INDEX idx_teams_venue_id (venue_id),
    CONSTRAINT fk_teams_venue
        FOREIGN KEY (venue_id)
        REFERENCES venues (venue_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);
