DROP TABLE IF EXISTS team;
DROP TABLE IF EXISTS player;
DROP TABLE IF EXISTS players_teams;

CREATE TABLE team(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  create_time INT NOT NULL
);

CREATE TABLE player(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  summoner_name TEXT NOT NULL UNIQUE,
  highest_rank TEXT NOT NULL,
  best_position TEXT NOT NULL
);

CREATE TABLE players_teams(
  player_id INT NOT NULL,
  team_id INT NOT NULL,
  leader TINYINT DEFAULT 0
);