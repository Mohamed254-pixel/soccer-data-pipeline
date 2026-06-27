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
