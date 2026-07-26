CREATE DATABASE IF NOT EXISTS soccer_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE soccer_db;

CREATE TABLE IF NOT EXISTS results (
    id INT NOT NULL,
    match_date DATE NOT NULL,
    home_team VARCHAR(100) NOT NULL,
    away_team VARCHAR(100) NOT NULL,
    home_score SMALLINT UNSIGNED NOT NULL,
    away_score SMALLINT UNSIGNED NOT NULL,
    tournament VARCHAR(150),
    city VARCHAR(150),
    country VARCHAR(100),
    PRIMARY KEY (id),
    INDEX idx_results_date (match_date),
    INDEX idx_results_home_team (home_team),
    INDEX idx_results_away_team (away_team)
);

CREATE TABLE IF NOT EXISTS live_matches (
    match_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    match_date DATETIME NOT NULL,
    home_team VARCHAR(100) NOT NULL,
    away_team VARCHAR(100) NOT NULL,
    home_goals SMALLINT UNSIGNED,
    away_goals SMALLINT UNSIGNED,
    PRIMARY KEY (match_id),
    UNIQUE KEY uq_live_fixture (match_date, home_team, away_team),
    INDEX idx_live_home_team (home_team),
    INDEX idx_live_away_team (away_team)
);

CREATE TABLE IF NOT EXISTS teams (
    team_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    team_name VARCHAR(100) NOT NULL,
    country VARCHAR(100),
    league VARCHAR(100),
    stadium VARCHAR(150),
    PRIMARY KEY (team_id),
    UNIQUE KEY uq_team_name_league (team_name, league)
);
