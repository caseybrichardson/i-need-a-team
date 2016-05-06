from flask import Flask
from flask import request
from flask import Response
from flask import jsonify
from flask.ext.cors import CORS
from werkzeug.contrib.cache import SimpleCache
from argparse import ArgumentParser
from collections import Counter
from collections import deque
import json
import pykka
import urllib
import requests
import sys
import datetime
import time
import hashlib

app = Flask(__name__)
CORS(app)

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

"""
===============================
Defaults and Utils
===============================
"""

api_key = args.api_key
base_url = "https://na.api.pvp.net"
static_base_url = "https://global.api.pvp.net"

# We're gonna cheat and use this until we use a real data store
store = deque()
cache = SimpleCache()

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

def all_champions():
	if not args.cache:
		champs_data_url = full_url(static_base_url, champ_all(), query_params={"champData": "allytips,enemytips"})
		champs_data = requests.get(champs_data_url).json()["data"]
		return map(lambda c: Champion(c), champs_data.values())
	else:
		return cache_data["champion"].values()

def specific_champion(champion_id):
	if not args.cache:
		champ_data_url = full_url(static_base_url, champ_specific(champion_id), query_params={"champData": "info,tags"})
		champ_data = requests.get(champ_data_url).json()
		return Champion(champ_data)
	else:
		return cache_data["champion"][champion_id]

def name_to_summoner(name):
	normalized = normalize_name(name)
	cache_key = "summ-" + normalized

	# Check our cache no matter what
	cached = cache.get(cache_key)
	if cached is not None:
		return cached

	summoner_data_url = full_url(base_url, summoner_by_name(normalized))
	summoner = Summoner(requests.get(summoner_data_url).json()[normalized])

	if args.cache:
		cache.set(cache_key, summoner)

	return summoner

def get_masteries(summoner_id):
	"""Gets the masteries for the given summoner ID"""
	mastery_data_url = full_url(base_url, mastery_player_all(summoner_id))
	return map(lambda m: Mastery(m), requests.get(mastery_data_url).json())

def get_match_list(summoner_id):
	"""Gets the match list for the given summoner ID"""
	match_data_url = full_url(base_url, match_list(summoner_id))
	return map(lambda m: Match(m), requests.get(match_data_url).json()["matches"])

def get_match(match_id):
	"""Gets the match data for the given match ID"""
	match_data_url = full_url(base_url, match_specific(match_id))
	return MatchData(requests.get(match_data_url).json())

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
		self._masteries = None
		self._matches = None
		self._classifications = None

	@property
	def masteries(self):
		"""Masteries for the current summoner"""
		if self._masteries is None:
			self._masteries = get_masteries(self.s_id)
		return self._masteries

	@property
	def matches(self):
		"""Matches for the current summoner"""
		if self._matches is None:
			self._matches = get_match_list(self.s_id) 
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

class Team():
	def __init__(self):
		pass

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

@app.route("/api/joinateam/<username>", methods=["POST", "GET"])
def join_a_team(username):
	# Not a fan of this
	global store
	global cache

	name = normalize_name(username)
	cache_key = "jat-" + name

	cache_obj = cache.get(cache_key)

	summoner = name_to_summoner(name)

	if cache_obj is not None:
		return make_error(error="No, just no.")
	else:
		# Oh well, just shove them into the only team
		team = None
		if len(store) == 1:
			team = store[0]
			if name not in team:
				team.append(name)
			return make_success(response={"leader": team[0], "teamMembers": list(team), "class": summoner.classifications})
		else:
			return make_error(error="No teams available")

@app.route("/api/makeateam/<username>", methods=["POST", "GET"])
def make_a_team(username):
	# Not a fan of this
	global store
	global cache

	name = normalize_name(username)
	cache_key = "mat-" + name

	cache_obj = cache.get(cache_key)

	if cache_obj is not None:
		team = store[cache_obj]
		return make_success(response={"leader": team[0], "teamMembers": list(team)})
	else:
		if args.cache:
			cache.set(name, len(store))
		team = deque()
		team.append(name)
		store.append(team)
		json_serializable = list(team)
		return make_success(response={"leader": name, "teamMembers": list(team)})
	
"""
===============================
Caching
===============================
"""

cache_data = {}
if args.cache:
	# Warms up our caches.
	# Load the champion cache file.
	champs = json.loads(open("cache/champions.json").read())["data"]
	cache_data["champion"] = {champ["id"]: Champion(champ) for champ in champs.values()}

"""
===============================
Startup
===============================
"""

def main():
	# Stop wasting so much space
	app.config.update(
		JSONIFY_PRETTYPRINT_REGULAR=True
	)

	if args.public:
		app.run(host="0.0.0.0", debug=args.debug, threaded=args.thread)
	else:
		app.run(debug=args.debug, threaded=args.thread)

if __name__ == '__main__':
	main()