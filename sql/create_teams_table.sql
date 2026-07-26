USE soccer_db;

CREATE TABLE IF NOT EXISTS teams (
    team_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    team_name VARCHAR(100) NOT NULL,
    country VARCHAR(100),
    league VARCHAR(100),
    stadium VARCHAR(150),
    PRIMARY KEY (team_id),
    UNIQUE KEY uq_team_name_league (team_name, league)
);

INSERT INTO teams (team_name, country, league) VALUES
('Arsenal', 'England', 'Premier League'),
('Liverpool', 'England', 'Premier League'),
('Manchester City', 'England', 'Premier League'),
('Chelsea', 'England', 'Premier League'),
('Real Madrid', 'Spain', 'La Liga'),
('Barcelona', 'Spain', 'La Liga'),
('Atletico Madrid', 'Spain', 'La Liga'),
('Bayern Munich', 'Germany', 'Bundesliga'),
('Borussia Dortmund', 'Germany', 'Bundesliga'),
('Inter Milan', 'Italy', 'Serie A'),
('Juventus', 'Italy', 'Serie A'),
('AC Milan', 'Italy', 'Serie A'),
('PSG', 'France', 'Ligue 1'),
('Marseille', 'France', 'Ligue 1'),
('LAFC', 'USA', 'MLS'),
('Inter Miami', 'USA', 'MLS'),
('Seattle Sounders', 'USA', 'MLS'),
('Argentina', 'Argentina', 'International'),
('Brazil', 'Brazil', 'International'),
('France', 'France', 'International'),
('England', 'England', 'International')
ON DUPLICATE KEY UPDATE
    country = VALUES(country);
