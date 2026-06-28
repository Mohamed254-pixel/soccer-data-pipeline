-- Show all matches
SELECT * FROM matches;

-- Show home teams and goals
SELECT home_team, home_goals
FROM matches;

-- Show away teams and goals
SELECT away_team, away_goals
FROM matches;

-- Home team scored more than 2 goals
SELECT *
FROM matches
WHERE home_goals > 2;

-- Total goals scored in each match
SELECT
    home_team,
    away_team,
    home_goals + away_goals AS total_goals
FROM matches;

-- Count total matches
SELECT COUNT(*) AS total_matches
FROM matches;

-- Top 10 highest scoring matches
SELECT home_team,
       away_team,
       home_goals + away_goals AS total_goals
FROM matches
ORDER BY total_goals DESC
LIMIT 10;

-- Team with most home games
SELECT home_team,
       COUNT(*) AS games_played
FROM matches
GROUP BY home_team
ORDER BY games_played DESC;

-- Average home goals by team
SELECT home_team,
       AVG(home_goals) AS avg_goals
FROM matches
GROUP BY home_team
ORDER BY avg_goals DESC;

-- Total goals scored by team
SELECT home_team,
       SUM(home_goals) AS total_goals
FROM matches
GROUP BY home_team
ORDER BY total_goals DESC;

-- Matches with 0 goals by home team
SELECT *
FROM matches
WHERE home_goals = 0;

-- Matches with 5 or more total goals
SELECT *
FROM matches
WHERE home_goals + away_goals >= 5;

-- Highest home score
SELECT *
FROM matches
ORDER BY home_goals DESC
LIMIT 1;

-- Highest away score
SELECT *
FROM matches
ORDER BY away_goals DESC
LIMIT 1;

-- Teams that scored at least 3 goals on average at home
SELECT home_team,
       AVG(home_goals) AS avg_goals
FROM matches
GROUP BY home_team
HAVING AVG(home_goals) >= 3;

-- Join matches with team information
SELECT
    m.home_team,
    t.country,
    t.league,
    m.home_goals
FROM matches m
JOIN teams t
ON m.home_team = t.team_name
LIMIT 20;

-- Average goals by league
SELECT
    t.league,
    AVG(m.home_goals) AS avg_goals
FROM matches m
JOIN teams t
ON m.home_team = t.team_name
GROUP BY t.league
ORDER BY avg_goals DESC;