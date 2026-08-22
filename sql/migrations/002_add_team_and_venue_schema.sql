USE soccer_db;

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

ALTER TABLE teams
    MODIFY team_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    MODIFY team_name VARCHAR(100) NOT NULL,
    MODIFY country VARCHAR(100) NULL,
    MODIFY league VARCHAR(100) NULL,
    ADD COLUMN api_team_id INT UNSIGNED NULL AFTER team_id,
    ADD COLUMN team_code VARCHAR(20) NULL AFTER team_name,
    ADD COLUMN stadium VARCHAR(150) NULL AFTER league,
    ADD COLUMN founded SMALLINT UNSIGNED NULL,
    ADD COLUMN is_national TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN logo_url VARCHAR(500) NULL,
    ADD COLUMN venue_id INT UNSIGNED NULL,
    ADD UNIQUE KEY uq_team_name_league (team_name, league),
    ADD UNIQUE KEY uq_teams_api_team_id (api_team_id),
    ADD INDEX idx_teams_venue_id (venue_id),
    ADD CONSTRAINT fk_teams_venue
        FOREIGN KEY (venue_id)
        REFERENCES venues (venue_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL;
