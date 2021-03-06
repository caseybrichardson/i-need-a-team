from flask import Flask
from flask import request
from flask import Response
from flask import jsonify
from flask import g
from flask.ext.cors import CORS
from werkzeug.contrib.cache import RedisCache
from argparse import ArgumentParser
from collections import Counter
from collections import deque
import sqlite3
import json
import urllib
import requests
import sys
import datetime
import time

app = Flask(__name__)
CORS(app)

args = None
cache = None
if __name__ == '__main__':
	parser = ArgumentParser(description="API for Riot API Challenge 2016 project")
	parser.add_argument("-d", "--debug", dest="debug", action="store_true", help="sets the debug flag when running Flask")
	parser.add_argument("-p", "--public", dest="public", action="store_true", help="allows the API to run publicly")
	parser.add_argument("-c", "--cache", dest="cache", action="store_true", help="causes the API to cache responses and use local resources")
	parser.add_argument("-t", "--thread", dest="thread", action="store_true", help="causes Flask to run in threaded mode")
	parser.add_argument("-k", "--api-key", dest="api_key", default="", help="the Riot API key")
	args = parser.parse_args()

	if args.api_key == "":
		print("No API key provided. Exiting.")
		sys.exit(1)

	if args.cache:
		cache = RedisCache(default_timeout=0)

"""
===============================
Database Tools
(These are ripped almost straight from the Flask docs on sqlite integration)
===============================
"""

def get_db():
	db = getattr(g, '_database', None)
	if db is None:
		db = g._database = sqlite3.connect(database_url)
		db.row_factory = sqlite3.Row
	return db

def query_db(query, args=(), one=False):
	cur = get_db().execute(query, args)
	rv = cur.fetchall()
	cur.close()
	return (rv[0] if rv else None) if one else rv

def init_db():
	with app.app_context():
		db = get_db()
		with app.open_resource('schema.sql', mode='r') as f:
			db.cursor().executescript(f.read())
		db.commit()

@app.teardown_appcontext
def close_connection(exception):
	db = getattr(g, '_database', None)
	if db is not None:
		db.close()

"""
===============================
Defaults and Utils
===============================
"""

def get_arg(arg, default=False):
	"""Gets an argument safely if we were loaded from a module"""
	if args is None or arg not in args:
		return default
	return vars(args)[arg]

api_key = get_arg("api_key", default="")
base_url = "https://na.api.pvp.net"
static_base_url = "https://global.api.pvp.net"
database_url = './database.db'

def set_api_key(key):
	global api_key
	api_key = key

# So the regions for the static endpoints barf on upper-case regions
def champ_all(region="na"):
	return "/api/lol/static-data/{region}/v1.2/champion".format(
		region=region
	)

def champ_specific(champion_id, region="na"):
	return "/api/lol/static-data/{region}/v1.2/champion/{cid}".format(
		region=region,
		cid=champion_id
	)

def mastery_player_specific(player_id, champion_id, platform_id="NA1"):
	return "/championmastery/location/{platformId}/player/{playerId}/champion/{championId}".format(
		platformId=platform_id, 
		playerId=player_id, 
		championId=champion_id
	)

def mastery_player_all(player_id, platform_id="NA1"):
	return "/championmastery/location/{platformId}/player/{playerId}/champions".format(
		platformId=platform_id,
		playerId=player_id
	)

def mastery_player_score(player_id, platform_id="NA1"):
	return "/championmastery/location/{platformId}/player/{playerId}/score".format(
		platformId=platform_id,
		playerId=player_id
	)

def summoner_by_name(summoner_names, region="NA"):
	return "/api/lol/{region}/v1.4/summoner/by-name/{summonerNames}".format(
		region=region,
		summonerNames=summoner_names
	)

def summoners_by_id(summoner_ids, region="NA"):
	return "//api/lol/{region}/v1.4/summoner/{summonerIds}".format(
		region=region,
		summonerIds=summoner_ids
	)

def current_game(summoner_id, platform_id="NA1"):
	return "/observer-mode/rest/consumer/getSpectatorGameInfo/{platformId}/{summonerId}".format(
		platformId=platform_id,
		summonerId=summoner_id
	)

# And apparently uppercase regions make this endpoint barf as well
def match_list(summoner_id, region="na"):
	return "/api/lol/{region}/v2.2/matchlist/by-summoner/{summonerId}".format(
		region=region,
		summonerId=summoner_id
	)

def match_specific(match_id, region="na"):
	return "/api/lol/{region}/v2.2/match/{matchId}".format(
		region=region,
		matchId=match_id
	)

def full_url(base_url, path, query_params={}):
	params = query_params.copy()
	params["api_key"] = api_key
	return "{base}{path}?{query_params}".format(
		base=base_url,
		path=path,
		query_params=urllib.urlencode(params)
	)

def normalize_name(name):
	return name.replace(" ", "").lower().encode("utf-8")

def get_request(url):
	data = requests.get(url)

	if data.status_code == 429:
		print("Just hit the rate limit. Look into this.")
		wait_time = data.headers["Retry-After"]
		time.sleep(wait_time + 2)
		return get_request(url)
	else:
		return data

def all_champions():
	if not args.cache:
		champs_data_url = full_url(static_base_url, champ_all(), query_params={"champData": "allytips,enemytips"})
		champs_data = get_request(champs_data_url).json()["data"]
		return map(lambda c: Champion(c), champs_data.values())
	else:
		return cache.get("champion").values()

def specific_champion(champion_id):
	should_cache = get_arg("cache")
	if not should_cache:
		champ_data_url = full_url(static_base_url, champ_specific(champion_id), query_params={"champData": "info,tags"})
		champ_data = get_request(champ_data_url).json()
		return Champion(champ_data)
	else:
		return cache.get("champ-" + str(champion_id))

def name_to_summoner(name):
	normalized = normalize_name(name)
	cache_key = "summ-" + normalized
	should_cache = get_arg("cache")

	# Check our cache no matter what
	if should_cache:
		cached = cache.get(cache_key)
		if cached is not None:
			return cached

	summoner_data_url = full_url(base_url, summoner_by_name(normalized))
	summoner_data = get_request(summoner_data_url)
	if summoner_data.status_code == 404:
		return None
	summoner = Summoner(summoner_data.json()[normalized])

	if should_cache:
		cache.set(cache_key, summoner)

	return summoner

def ids_to_summoners(ids):
	id_list = ",".join(map(lambda i: str(i), ids))
	should_cache = get_arg("cache")

	summoners_data_url = full_url(base_url, summoners_by_id(id_list))
	response = get_request(summoners_data_url).json()
	summoners = []
	for summoner_data in response.values():
		summoner = Summoner(summoner_data)
		summoners.append(summoner)
		cache_key = "summ-" + normalize_name(summoner.name)
		if should_cache:
			cache.set(cache_key, summoner)

	return summoners

def get_masteries(summoner_id):
	"""Gets the masteries for the given summoner ID"""
	mastery_data_url = full_url(base_url, mastery_player_all(summoner_id))
	return map(lambda m: Mastery(m), get_request(mastery_data_url).json())

def get_match_list(summoner_id):
	"""Gets the match list for the given summoner ID"""
	match_data_url = full_url(base_url, match_list(summoner_id))
	data = get_request(match_data_url).json()
	return map(lambda m: Match(m), data["matches"])

def get_match(match_id):
	"""Gets the match data for the given match ID"""
	match_data_url = full_url(base_url, match_specific(match_id))
	return MatchData(get_request(match_data_url).json())

def epoch_time():
	"""Gets the current epoch time"""
	return int(time.time())

def check_for_player(summoner):
	"""Checks if a player exists for the summoner"""
	db = get_db()
	cur = db.cursor()

	# Going to check if the player exists already.
	player = query_db('''SELECT id FROM player WHERE summoner_name = ?''', [summoner.name], one=True)

	if player is None:
		return False
	else:
		return player["id"]

def create_or_get_player(summoner):
	"""Creates a player if necessary"""
	db = get_db()
	cur = db.cursor()

	# Going to check if the player exists already.
	player = check_for_player(summoner)

	if not player:
		# If the player doesn't exist we're gonna put them in.
		classification = summoner.classifications[0]
		best_type = (classification["champions"][0]["lanes"][0]["lane"], classification["classification"])

		insert_sql = '''INSERT INTO player (id, summoner_name, highest_rank, best_position, create_time) VALUES (NULL, ?, ?, ?, ?)'''
		cur.execute(insert_sql, (summoner.name, summoner.highest_rank, best_type[0] + " " + best_type[1], epoch_time()))
		player = cur.lastrowid

	db.commit()
	return player

def create_player_request(summoner):
	"""Creates a new team request for a player"""
	db = get_db()
	cur = db.cursor()

	player = create_or_get_player(summoner)

	# Check if they have any open reqs out.
	player_req = query_db('''SELECT id FROM player_req WHERE player_id = ? AND finish_time IS NULL''', [player], one=True)

	if player_req is None:
		# If they don't have any open reqs then we can create one.
		insert_sql = '''INSERT INTO player_req (player_id, create_time) VALUES (?, ?)'''
		cur.execute(insert_sql, (player, epoch_time()))
		player_req = cur.lastrowid
	else:
		player_req = player_req["id"]

	db.commit()
	return player_req

def create_team(summoner):
	"""Creates a new team with the summoner as its leader"""
	db = get_db()
	cur = db.cursor()

	# This will only create a player if they don't already exist
	player = create_or_get_player(summoner)

	insert_sql = '''INSERT INTO team (create_time) VALUES (?)'''
	cur.execute(insert_sql, (epoch_time(),))
	team_id = cur.lastrowid

	insert_sql = '''INSERT INTO players_teams (player_id, team_id, leader) VALUES (?, ?, 1)'''
	cur.execute(insert_sql, (player, team_id))

	db.commit()
	return team_id

def join_team(player_id, player_req_id, team_id):
	"""Sets up a player to join a team"""
	db = get_db()
	cur = db.cursor()

	insert_sql = '''INSERT INTO players_teams (player_id, team_id) VALUES (?, ?)'''
	cur.execute(insert_sql, (player_id, team_id))
	team_id = cur.lastrowid

	update_sql = '''UPDATE player_req SET finish_time = ? WHERE id = ?'''
	cur.execute(update_sql, (epoch_time(), player_req_id))

	query_sql = '''SELECT count(*) FROM players_teams WHERE team_id = ?'''
	count = query_db(query_sql, [team_id], one=True)
	print team_id
	print count
	if count >= 5:
		update_sql = '''UPDATE team SET finish_time = ? WHERE id = ?'''
		cur.execute(update_sql, (epoch_time(), team_id))

	db.commit()
	return team_id

def check_summoner_searching(summoner):
	"""Checks to see if the given summoner is currently searching for a team"""
	db = get_db()
	cur = db.cursor()

	player = check_for_player(summoner)

	if not player:
		return False
	else:
		teams = query_db('''SELECT team_id FROM players_teams WHERE player_id = ? AND leader = 1''', [player])

		# Scan through all the teams they've ever lead and see if any are still active
		for team in teams:
			team_active = query_db('''SELECT id FROM team WHERE id = ? AND finish_time IS NULL''', [team["team_id"]], one=True)
			if team_active is not None:
				return True

	return False

"""
===============================
Quick Data Models
===============================
"""

class JSONObject(object):
	def __init__(self, json):
		super(JSONObject, self).__init__()
		self.json = json

class Match(JSONObject):
	"""Match model object for working with data from the API. Treat this as readonly."""
	def __init__(self, json_obj):
		super(Match, self).__init__(json_obj)
		self.timestamp = json_obj["timestamp"]
		self.champion = json_obj["champion"]
		self.region = json_obj["region"]
		self.queue = json_obj["queue"]
		self.season = json_obj["season"]
		self.match_id = json_obj["matchId"]
		self.role = json_obj["role"]
		self.platform_id = json_obj["platformId"]
		self.lane = json_obj["lane"]

		# Non-json private vars
		self._match = None
		self._champion = None

	@property
	def match_data(self):
		"""Match Data for the current match"""
		if self._match is None:
			self._match = get_match(self.match_id)
		return self._match

	@property
	def match_champion(self):
		"""The champion that the player played in this match"""
		if self._champion is None:
			self._champion = specific_champion(self.champion)
		return self._champion

class MatchData(JSONObject):
	"""MatchData model object for working with data from the API. Treat this as readonly."""
	def __init__(self, json_obj):
		super(MatchData, self).__init__(json_obj)
		self.participants = {}
		self.players = []
		participants = json_obj["participants"]
		participant_ids = json_obj["participantIdentities"]
		for participant_id in participant_ids:
			player = MatchPlayer(participant_id["player"])
			self.players.append(player)

			participant = filter(lambda p: p["participantId"] == participant_id["participantId"], participants)
			if participant is not None:
				participant = MatchParticipant(participant[0])
				summoner_id = participant_id["player"]["summonerId"]
				self.participants[summoner_id] = participant

class MatchParticipant(JSONObject):
	"""MatchParticipant model object for working with data from the API. Treat this as readonly."""
	def __init__(self, json_obj):
		super(MatchParticipant, self).__init__(json_obj)
		self.spell_one_id = json_obj["spell1Id"]
		self.spell_two_id = json_obj["spell2Id"]
		self.participant_id = json_obj["participantId"]
		self.champion_id = json_obj["championId"]
		self.team_id = json_obj["teamId"]
		self.highest_achieved_season_tier = json_obj["highestAchievedSeasonTier"]

class MatchPlayer(JSONObject):
	"""MatchPlayer model object for working with data from the API. Treat this as readonly."""
	def __init__(self, json_obj):
		super(MatchPlayer, self).__init__(json_obj)
		self.summoner_id = json_obj["summonerId"]
		self.summoner_name = json_obj["summonerName"]

class Champion(JSONObject):
	"""Champion model object for working with data from the API. Treat this as readonly."""
	def __init__(self, json_obj):
		super(Champion, self).__init__(json_obj)
		self.c_id = json_obj["id"]
		self.title = json_obj["title"]
		self.name = json_obj["name"]
		self.key = json_obj["key"]

		# This makes things a little bit more accessible on the frontend.
		self.square_url = "https://ddragon.leagueoflegends.com/cdn/6.8.1/img/champion/{key}.png".format(key=self.key)
		self.loading_url = "http://ddragon.leagueoflegends.com/cdn/img/champion/loading/{key}_0.jpg".format(key=self.key)
		self.json["squareUrl"] = self.square_url
		self.json["loadingUrl"] = self.loading_url

		if "allytips" in json_obj:
			self.ally_tips = json_obj["allytips"]

		if "enemytips" in json_obj:
			self.enemy_tips_tips = json_obj["enemytips"]

		if "blurb" in json_obj:
			self.blurb = json_obj["blurb"]

		if "lore" in json_obj:
			self.lore = json_obj["lore"]

		if "spells" in json_obj:
			# Need to do some more hardcore parsing here
			pass

		if "info" in json_obj:
			self.info = json_obj["info"]["defense"]

		if "tags" in json_obj:
			self.tags = json_obj["tags"]

class Summoner(JSONObject):
	"""Summoner model object for working with data from the API. Treat this as readonly."""
	def __init__(self, json_obj):
		super(Summoner, self).__init__(json_obj)
		self.s_id = json_obj["id"]
		self.name = json_obj["name"]
		self.profile_icon_id = json_obj["profileIconId"]
		self.revision_date = datetime.datetime.fromtimestamp(json_obj["revisionDate"] / 1000)
		self.summoner_level = json_obj["summonerLevel"]

		self.profile_icon_url = "http://ddragon.leagueoflegends.com/cdn/6.9.1/img/profileicon/{pid}.png".format(pid=self.profile_icon_id)
		self.json["profileIconUrl"] = self.profile_icon_url

		# Non-json private vars
		self._highest_rank = None
		self._masteries = None
		self._matches = None
		self._classifications = None

	@property
	def highest_rank(self):
		"""Summoners highest rank"""
		for match in self.matches:
			return match.match_data.participants[self.s_id].highest_achieved_season_tier

	@property
	def masteries(self):
		"""Masteries for the current summoner"""
		if self._masteries is None:
			self._masteries = get_masteries(self.s_id)
		if get_arg("cache"):
			cache.set("summ-" + normalize_name(self.name), self)
		return self._masteries

	@property
	def matches(self):
		"""Matches for the current summoner"""
		if self._matches is None:
			self._matches = get_match_list(self.s_id) 
		if get_arg("cache"):
			cache.set("summ-" + normalize_name(self.name), self)
		return self._matches

	@property
	def classifications(self):
		"""
		Gets the classifications for the current player.
		"""
		if self._classifications is None:
			# We're going to average the skill in each category
			# of champion i.e. fighter, support, etc.

			# We need to build a mapping of how players
			# play their champions. This will help us make
			# the final decision as to where they should be
			# placed in their team.
			champion_mapping = {}
			champion_lane_mapping = map(lambda m: (m.match_champion.name, m.lane), self.matches)
			for lane_mapping in champion_lane_mapping:
				champ = lane_mapping[0]
				lane = lane_mapping[1]

				# Get the basic stuff in so we can build this
				if champ not in champion_mapping:
					champion_mapping[champ] = {}
				if lane not in champion_mapping[champ]:
					champion_mapping[champ][lane] = 0

				champion_mapping[champ][lane] += 1

			# Make it easier to get everything together.
			# Don't worry we make it awful right after this.
			start = epoch_time()
			bins = {}
			for mastery in self.masteries:
				for bin_type in mastery.champion.tags:
					if bin_type not in bins:
						bins[bin_type] = {"classification": bin_type, "champions": [], "score": 0, "overall_level": 0}

					lanes = None
					if mastery.champion.name in champion_mapping:
						lanes = [{"lane": lane, "count": count} for lane, count in champion_mapping[mastery.champion.name].iteritems()]
					else: 
						lanes = []

					bins[bin_type]["champions"].append(
						{
							"name": mastery.champion.name, 
							"score": mastery.champion_points, 
							"lanes": lanes
						})
					bins[bin_type]["score"] += mastery.champion_points
					bins[bin_type]["overall_level"] += mastery.champion_level

			# Going to rejam everything in here. I blame myself.
			start = epoch_time()
			classifications = []
			for b_type, data in bins.iteritems():
				# Maintain order on each champion
				data["champions"].sort(key=lambda c: c["score"], reverse=True)
				for champion in data["champions"]:
					champion["lanes"].sort(key=lambda l: l["count"], reverse=True)
				classifications.append(data)

			# We also want to maintain order on each type
			classifications.sort(key=lambda c: c["score"], reverse=True)

			self._classifications = classifications

		# Re-cache at this point. We've done a very expensive bit of work.
		# Though as stated earlier I blame myself.
		if get_arg("cache"):
			cache.set("summ-" + normalize_name(self.name), self)
		return self._classifications

class Mastery(JSONObject):
	"""Mastery model object for working with data from the API. Treat this as readonly."""
	def __init__(self, json_obj):
		super(Mastery, self).__init__(json_obj)
		self.champion_points = json_obj["championPoints"]
		self.player_id = json_obj["playerId"]
		self.champion_points_until_next_level = json_obj["championPointsUntilNextLevel"]
		self.chest_granted = json_obj["chestGranted"]
		self.champion_level = json_obj["championLevel"]
		self.champion_id = json_obj["championId"]
		self.champion_points_since_last_level = json_obj["championPointsSinceLastLevel"]
		self.last_play_time = datetime.datetime.fromtimestamp(json_obj["lastPlayTime"] / 1000)

		# Non-json private vars
		self._champion = None

	@property
	def champion(self):
		"""The champion that this mastery is for"""
		if self._champion == None:
			self._champion = specific_champion(self.champion_id)
		return self._champion

"""
===============================
Response Tools
===============================
"""

def make_error(error, response_code=500):
	return _make_response(error=error, response_code=response_code)

def make_success(response, response_code=200):
	return _make_response(response=response, response_code=response_code)

def _make_response(response=None, error=None, response_code=200):
	response = jsonify(response=response, error=error)
	response.status_code = response_code
	return response

"""
===============================
Routes
===============================
"""

@app.route("/api/debug/<username>", methods=["POST", "GET"])
def debug_create_player(username):
	summoner = name_to_summoner(username)
	return make_success(response={"value": summoner.classifications})

@app.route("/api/debug/populate/<username>", methods=["POST", "GET"])
def populate_db(username):
	summoner = name_to_summoner(username)

	if summoner is None:
		return make_error(error={"message": "Could not find summoner."})

	summoner_ids = []
	for idx, match in enumerate(summoner.matches):
		# We're only going to index four matches, should be around 40 players
		# (the limit on how many summoner IDs you can pass into the endpoint)
		# XXX: This just destroyed my rate limit... >.>
		if idx == 3:
			break

		for player in match.match_data.players:
			summoner_ids.append(player.summoner_id)

	summoners = ids_to_summoners(summoner_ids)

	map(lambda s: create_player(s), summoners)

	return make_success(response={"message": "Done Populating"})

@app.route("/api/joinateam/<username>", methods=["POST", "GET"])
def join_a_team(username):
	db = get_db()
	cur = db.cursor()

	name = normalize_name(username)
	summoner = name_to_summoner(name)

	if summoner is None:
		return make_error(error={"message": "Could not find summoner."})

	# We're going to open up a new player request
	player_request = create_player_request(summoner)
	player = query_db('''SELECT p.* FROM player p JOIN player_req pr ON pr.player_id = p.id WHERE pr.id = ?''', [player_request], one=True)

	# Then we're gonna see if we can close this req as fast as possible
	# Quick check to see how many teams there are that are still open
	teams = query_db('''SELECT t.* FROM team t JOIN players_teams pt ON pt.team_id = t.id JOIN player p ON p.id = pt.player_id WHERE finish_time IS NULL AND pt.leader = 1 AND p.highest_rank = ?''', [player["highest_rank"]])
	if len(teams) == 0:
		return make_success(response={"message": "No teams just yet, but you're on the list!"})
	else:
		# There may be a compatible team available so start closer examination
		for row in teams:
			query_sql = '''SELECT p.best_position AS best FROM player p JOIN players_teams pt ON pt.player_id = p.id WHERE pt.team_id = ?'''
			current_positions_filled = query_db(query_sql, [row["id"]])
			collision = False

			# Scan for collisions
			for position_row in current_positions_filled:
				player_data = player["best_position"].split()
				player_lane = player_data[0]
				player_position = player_data[1]
				other_data = position_row["best"].split()
				other_lane = other_data[0]
				other_position = other_data[1]
				if player_lane == other_lane and player_position == other_position:
					if player_lane != "BOTTOM":
						collision = True

			# If we don't have one then we can put them on this team
			if not collision:
				join_team(player["id"], player_request, row["id"])
			else:
				return make_success(response="No teams just yet, but you're on the list!")

		return make_success(response="WE FOUND YOU A TEAM!")


@app.route("/api/makeateam/<username>", methods=["POST", "GET"])
def make_a_team(username):

	name = normalize_name(username)
	summoner = name_to_summoner(name)

	if summoner is None:
		return make_error(error={"message": "Could not find summoner."})
	
	if check_summoner_searching(summoner):
		# If the current summoner is building a team, we're going to return an error
		return make_error(error={"message": "You're already building a team!"}, response_code=200)

	# If they're not actively leading a team, create a new one and insert them as the leader
	create_team(summoner)
	return make_success(response={"leader": summoner.name})

"""
===============================
Cache
===============================
"""

if args and args.cache:
	# Warms up our caches.
	# Load the champion cache file.
	champs = json.loads(open("cache/champions.json").read())["data"]
	for champ in champs.values():
		cache.set("champ-" + str(champ["id"]), Champion(champ))

"""
===============================
Startup
===============================
"""

def main():
	# Stop wasting so much space
	app.config.update(
		JSONIFY_PRETTYPRINT_REGULAR=False
	)

	if args.public:
		app.run(host="0.0.0.0", debug=args.debug, threaded=args.thread)
	else:
		app.run(debug=args.debug, threaded=args.thread)

if __name__ == '__main__':
	main()