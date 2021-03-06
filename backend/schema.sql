DROP TABLE IF EXISTS team;
DROP TABLE IF EXISTS player;
DROP TABLE IF EXISTS players_teams;
DROP TABLE IF EXISTS player_req;

CREATE TABLE team(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  create_time INTEGER NOT NULL,
  finish_time INTEGER
);

CREATE TABLE player(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  summoner_name TEXT NOT NULL UNIQUE,
  highest_rank TEXT NOT NULL,
  best_position TEXT NOT NULL,
  create_time INTEGER NOT NULL
);

CREATE TABLE players_teams(
  player_id INTEGER NOT NULL,
  team_id INTEGER NOT NULL,
  leader TINYINT DEFAULT 0
);

CREATE TABLE player_req(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER NOT NULL,
  team_id INTEGER,
  create_time INTEGER NOT NULL,
  finish_time INTEGER
);