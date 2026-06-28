CREATE TABLE teams (
    team_id INT AUTO_INCREMENT PRIMARY KEY,
    team_name VARCHAR(50),
    country VARCHAR(50),
    league VARCHAR(50)
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
('England', 'England', 'International');
