#!/usr/bin/env python
"""
Metadata Fetcher

This script fetches league, team, and player data from API-Football
and populates the corresponding tables in the Supabase database.
It's designed to be run periodically (e.g., daily or weekly) to keep
the metadata up-to-date.

Usage:
    python -m fetchers.metadata_fetcher

Environment variables:
    - API_FOOTBALL_KEY: API-Football API key
    - SUPABASE_URL: Supabase URL
    - SUPABASE_SERVICE_KEY: Supabase service key (for backend operations)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from supabase import create_client, Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("metadata_fetcher")

# Load environment variables
load_dotenv()

# API credentials and configuration
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
API_FOOTBALL_URL = "https://v3.football.api-sports.io"
if not API_FOOTBALL_KEY:
    logger.error("API_FOOTBALL_KEY environment variable not set")
    sys.exit(1)

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") # Use SUPABASE_SERVICE_KEY for backend
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables not set")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Leagues to process - consistent with scan_fixtures.py
# Using a subset for brevity in example, can be expanded to full LEAGUES_TO_MONITOR_EXTENDED
LEAGUES_TO_PROCESS = [
    39,    # EPL (England)
 #   140,   # La Liga (Spain)
 #   78,    # Bundesliga (Germany)
 #   61,    # Ligue 1 (France)
 #   135,   # Serie A (Italy)
    # Add more leagues from LEAGUES_TO_MONITOR_EXTENDED as needed for full coverage
 #   2,     # Champions League
 #   3,     # Europa League
    # 15,    # FIFA World Cup (usually not relevant for club seasons)
 #   255,   # Eredivisie (Netherlands)
    # 921,   # Conference League Qualifiers (example, adjust as needed)
 #   848,   # UEFA Conference League
    # 1,     # Euro Championship (usually not relevant for club seasons)
 #   4,     # Copa Libertadores (South America)
 #   9,     # Copa Sudamericana (South America)
 #   253,   # MLS (USA)
 #   94,    # Primeira Liga (Portugal)
 #   203,   # Super Lig (Turkey)
    # 201,   # Super League (Greece) - example if needed
    # 195,   # Pro League (Belgium) - example if needed
    # 197,   # Superliga (Denmark) - example if needed
    # 196,   # Veikkausliiga (Finland) - example if needed
 #   200,   # Premiership (Scotland)
 #   208,   # Eliteserien (Norway)
 #   210,   # Allsvenskan (Sweden)
    # 211,   # Super League (Switzerland) - example if needed
    # 216,   # Premier League (Russia) - consider if needed
 #   218,   # Premier Liga (Bosnia and Herzegovina)
 #   219,   # HNL (Croatia)
 #   220,   # 1. Liga (Czech Republic)
    # 222,   # Superliga (Serbia) - example if needed
    # 223,   # Fortuna liga (Slovakia) - example if needed
 #   262,   # Liga MX (Mexico)
    # 94,    # Primeira Liga (Portugal) - already listed
 #   71,    # Serie A (Brazil)
    # 77,    # Primera Division (Argentina) - example if needed
    # 80,    # A-League (Australia) - example if needed
 #   307    # Saudi Professional League (Saudi Arabia)
]

# API request delay to respect rate limits
REQUEST_DELAY_SECONDS = 2  # Adjust based on your API plan's rate limit (e.g., 30 req/min means 2s delay)

async def get_current_season_for_league(league_id: int, client: httpx.AsyncClient) -> Optional[int]:
    """Fetch the current season year for a given league."""
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"id": str(league_id)}
    try:
        response = await client.get(f"{API_FOOTBALL_URL}/leagues", headers=headers, params=params, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        if data["results"] > 0 and data["response"]:
            for season_info in data["response"][0]["seasons"]:
                if season_info["current"]:
                    logger.info(f"Current season for league {league_id} is {season_info['year']}.")
                    return int(season_info['year'])
            logger.warning(f"No 'current' season found for league {league_id}. Using latest available season.")
            if data["response"][0]["seasons"]: # Fallback to the latest season if "current" is not explicitly true
                 return int(data["response"][0]["seasons"][-1]["year"]) # Often the last one is the most recent or current
        logger.warning(f"No season information found for league {league_id}.")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"API error fetching current season for league {league_id}: {e.response.status_code} {e.response.text}")
    except Exception as e:
        logger.error(f"Exception fetching current season for league {league_id}: {e}")
    return None

async def fetch_teams_for_league(league_id: int, season: int, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Fetch teams for a given league and season."""
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"league": str(league_id), "season": str(season)}
    try:
        response = await client.get(f"{API_FOOTBALL_URL}/teams", headers=headers, params=params, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        teams_raw = data.get("response", [])
        # Add league_id and season context to each team entry
        teams_with_context = [
            {**team_entry, '_league_id_context': league_id, '_season_context': season}
            for team_entry in teams_raw
        ]
        logger.info(f"Fetched {len(teams_with_context)} teams for league {league_id}, season {season}.")
        return teams_with_context
    except httpx.HTTPStatusError as e:
        logger.error(f"API error fetching teams for league {league_id}, season {season}: {e.response.status_code} {e.response.text}")
    except Exception as e:
        logger.error(f"Exception fetching teams for league {league_id}, season {season}: {e}")
    return []

async def upsert_teams_to_supabase(teams_data_list: List[Dict[str, Any]]):
    """Upsert team data into the Supabase 'teams' table."""
    if not teams_data_list:
        return

    records_to_upsert = []
    for item in teams_data_list:
        team = item.get("team", {})
        venue = item.get("venue", {})
        if not team.get("id"):
            logger.warning(f"Skipping team with no ID: {team.get('name')}")
            continue

        record = {
            "team_id": team["id"],
            "name": team.get("name"),
            "code": team.get("code"),
            "country": team.get("country"),
            "founded": team.get("founded"),
            "national": team.get("national", False),
            "logo_url": team.get("logo"),
            # Venue details
            "venue_id": venue.get("id"),
            "venue_name": venue.get("name"),
            "venue_address": venue.get("address"),
            "venue_city": venue.get("city"),
            "venue_capacity": venue.get("capacity"),
            "venue_surface": venue.get("surface"),
            "venue_image_url": venue.get("image"),
            # Context from fetch_teams_for_league
            "api_football_league_id": item.get('_league_id_context'),
            "api_football_season": item.get('_season_context'),
            "last_updated_api_football": datetime.now().isoformat(),
            "meta_data": item, # Store the full API response item as meta_data
        }
        records_to_upsert.append(record)

    if not records_to_upsert:
        return
        
    try:
        logger.info(f"Upserting {len(records_to_upsert)} teams to Supabase.")
        # Supabase client's upsert handles `on_conflict` for primary key `team_id`
        supabase.table("teams").upsert(records_to_upsert).execute()
        logger.info(f"Successfully upserted {len(records_to_upsert)} teams.")
    except Exception as e:
        logger.error(f"Error upserting teams to Supabase: {e}")

async def fetch_coaches_for_team(team_id: int, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Fetch coaches for a given team."""
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    # API-Football uses /coachs endpoint with team parameter
    params = {"team": str(team_id)}
    try:
        response = await client.get(f"{API_FOOTBALL_URL}/coachs", headers=headers, params=params, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        coaches_raw = data.get("response", [])
        # Add team_id context to each coach entry
        coaches_with_context = [
            {**coach_entry, '_team_id_context': team_id}
            for coach_entry in coaches_raw
        ]
        logger.info(f"Fetched {len(coaches_with_context)} coaches for team {team_id}.")
        return coaches_with_context
    except httpx.HTTPStatusError as e:
        logger.error(f"API error fetching coaches for team {team_id}: {e.response.status_code} {e.response.text}")
    except Exception as e:
        logger.error(f"Exception fetching coaches for team {team_id}: {e}")
    return []

async def upsert_coaches_to_supabase(coaches_data_list: List[Dict[str, Any]]):
    """Upsert coach data into the Supabase 'coaches' table."""
    if not coaches_data_list:
        return

    records_to_upsert = []
    for item in coaches_data_list:
        # API-Football returns coach details directly in the item
        if not item.get("id"):
            logger.warning(f"Skipping coach with no ID: {item.get('name')}")
            continue

        # Ensure birth date is in YYYY-MM-DD format or None
        birth_date_str = item.get("birth", {}).get("date")
        birth_date_obj = None
        if birth_date_str:
            try:
                birth_date_obj = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(f"Could not parse birth date '{birth_date_str}' for coach {item.get('id')}. Setting to None.")

        record = {
            "coach_id": item["id"],
            "name": item.get("name"),
            "firstname": item.get("firstname"),
            "lastname": item.get("lastname"),
            "photo_url": item.get("photo"),
            "nationality": item.get("nationality"),
            "birth_date": birth_date_obj.isoformat() if birth_date_obj else None,
            "current_team_id": item.get('_team_id_context'), # Context added in fetch_coaches_for_team
            "api_response_coach": item, # Store the full API response item
            "last_updated_api_football": datetime.now().isoformat(),
        }
        records_to_upsert.append(record)

    if not records_to_upsert:
        return

    try:
        logger.info(f"Upserting {len(records_to_upsert)} coaches to Supabase.")
        supabase.table("coaches").upsert(records_to_upsert, on_conflict="coach_id").execute() # Specify on_conflict
        logger.info(f"Successfully upserted {len(records_to_upsert)} coaches.")
    except Exception as e:
        logger.error(f"Error upserting coaches to Supabase: {e}")

async def fetch_players_for_team(team_id: int, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Fetch players (squad) for a given team using /players/squads endpoint (latest available)."""
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"team": str(team_id)} # Season parameter removed
    all_players_from_squad = []
    
    try:
        logger.info(f"Fetching squad for team {team_id} using /players/squads (latest available).")
        response = await client.get(f"{API_FOOTBALL_URL}/players/squads", headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        
        # The /players/squads endpoint returns a list, and the first element (if present) contains the team and players
        if data.get("response") and len(data["response"]) > 0:
            squad_data = data["response"][0] # Assuming the first element is the relevant squad
            # team_info_squad = squad_data.get("team", {})
            players_list = squad_data.get("players", [])
            all_players_from_squad.extend(players_list)
            logger.info(f"Fetched {len(all_players_from_squad)} players for team {team_id} from /players/squads.")
        else:
            logger.warning(f"No squad data found in response for team {team_id} from /players/squads. Response: {data.get('response')}")
            
    except httpx.HTTPStatusError as e:
        logger.error(f"API error fetching squad for team {team_id}: {e.response.status_code} {e.response.text}")
    except Exception as e:
        logger.error(f"Exception fetching squad for team {team_id}: {e}")
            
    return all_players_from_squad

async def upsert_players_to_supabase(players_data_list: List[Dict[str, Any]]):
    """Upsert player data into the Supabase 'players' table."""
    if not players_data_list:
        return

    deduplicated_records_map = {}

    for item in players_data_list: # Iterate over the original list before deduplication to get team context
        player_info = item.get("player", {}) # Data from API response for the player
        player_id = player_info.get("id")

        if not player_id:
            logger.warning(f"Skipping player with no ID in item: {item}")
            continue

        # Use the squad_team_id passed in the item's context
        squad_team_id_for_player = item.get("_squad_team_id_context")
        if not squad_team_id_for_player:
            logger.warning(f"Player {player_id} is missing _squad_team_id_context. Skipping.")
            continue

        full_name = player_info.get("name")
        # firstname, lastname = extract_first_last_name(full_name) # Removed as API provides only full name

        player_record = {
            "player_id": player_id,
            "name": full_name,
            "firstname": None, # Set to None as API provides only full name
            "lastname": None,  # Set to None as API provides only full name
            "age": player_info.get("age"),
            "number": player_info.get("number"), # New field
            "position": player_info.get("position"),
            "photo_url": player_info.get("photo"),
            "current_team_id": squad_team_id_for_player, # Set from context
            "nationality": player_info.get("nationality"), # Keep if API provides, else None
            "last_updated_api_football": datetime.now(timezone.utc).isoformat(),
            "meta_data": { # Store raw player_info for future use if needed
                "raw_squad_player_data": player_info
            }
        }
        # Filter out None values to prevent overriding existing data with None during upsert,
        # except for fields we explicitly want to set or clear.
        # For simplicity, we'll send all mapped fields for now.
        # Supabase upsert with ignore_duplicates=False will update existing records.
        
        # Add to list for deduplicated upsert
        # We use player_id as key to ensure only one record per player_id is prepared for upsert
        # If multiple entries for the same player (e.g. from different squad_team_id contexts if logic changes),
        # this will take the last one encountered. Given current logic, this is fine.
        deduplicated_records_map[player_id] = player_record

    if not deduplicated_records_map:
        logger.info("No valid player records to upsert after processing and deduplication.")
        return

    final_records_to_upsert = list(deduplicated_records_map.values())
    
    logger.info(f"Attempting to upsert {len(final_records_to_upsert)} deduplicated player records to Supabase.")

    try:
        logger.info(f"Upserting {len(final_records_to_upsert)} players to Supabase.")
        # Supabase client's upsert handles `on_conflict` for primary key `player_id`
        supabase.table("players").upsert(final_records_to_upsert).execute()
        logger.info(f"Successfully upserted {len(final_records_to_upsert)} players.")
    except Exception as e:
        logger.error(f"Error upserting players to Supabase: {e}")

async def main():
    logger.info("Starting metadata fetch process...")
    start_time = datetime.now()

    all_fetched_teams = []
    # league_season_map = {} # Not strictly needed if season is handled per league for team fetching

    async with httpx.AsyncClient() as client:
        for league_id in LEAGUES_TO_PROCESS:
            logger.info(f"Processing league: {league_id}")
            
            current_season_for_teams: Optional[int] = None
            # --- MANUAL SEASON OVERRIDE FOR TESTING DURING OFF-SEASON ---
            if league_id == 39: # Premier League
                current_season_for_teams = 2023 # Get teams from the just-completed season 2023/2024
                logger.info(f"MANUAL OVERRIDE: Using season {current_season_for_teams} to fetch TEAMS for league {league_id}.")
            else:
                # Determine the current season for the league dynamically for other leagues
                current_season_for_teams = await get_current_season_for_league(league_id, client)
            # --- END MANUAL SEASON OVERRIDE ---
            
            if not current_season_for_teams:
                logger.warning(f"Skipping league {league_id} as no season could be determined for fetching teams.")
                await asyncio.sleep(REQUEST_DELAY_SECONDS) # Add delay even if skipping
                continue
            
            # league_season_map[league_id] = current_season_for_teams # Store if needed elsewhere
            logger.info(f"Using season {current_season_for_teams} to fetch teams for league {league_id}.")

            # Fetch teams for the determined (or overridden) season
            teams_in_league = await fetch_teams_for_league(league_id, current_season_for_teams, client)
            if teams_in_league:
                all_fetched_teams.extend(teams_in_league)
            await asyncio.sleep(REQUEST_DELAY_SECONDS) # Delay after fetching teams for a league

        if all_fetched_teams:
            await upsert_teams_to_supabase(all_fetched_teams)
        
        # After fetching and upserting teams, fetch players and coaches for each team
        all_fetched_players = []
        all_fetched_coaches = [] 

        for team_entry in all_fetched_teams: # team_entry is the raw response from API-Football/teams
            team_id = team_entry.get("team", {}).get("id")
            league_id_context = team_entry.get('_league_id_context') # Context from when teams were fetched
            
            if not team_id or not league_id_context: 
                logger.warning(f"Skipping player/coach fetch for team entry due to missing ID/league context: {team_entry.get('team',{}).get('name')}")
                continue

            # Fetch players - no explicit season for /players/squads, API should return current squad
            logger.info(f"Fetching players for team ID: {team_id} (League: {league_id_context}) - requesting latest season squad.")
            players_for_team = await fetch_players_for_team(team_id, client) # No season passed here
            
            if players_for_team:
                players_with_context = [
                    {
                        "player": p, # Nest player data under "player" key
                        "_squad_team_id_context": team_id, # This is the team_id for player's current_team_id
                        "_league_id_context": league_id_context, # League context for reference, if needed for meta_data
                        "_season_context": current_season_for_teams # Add season context as well
                    }
                    for p in players_for_team
                ]
                all_fetched_players.extend(players_with_context)
            await asyncio.sleep(REQUEST_DELAY_SECONDS) # Delay after fetching players for a team

            logger.info(f"Fetching coaches for team ID: {team_id}")
            coaches_for_team = await fetch_coaches_for_team(team_id, client)
            if coaches_for_team: # coaches_for_team already has _team_id_context from its fetch function
                all_fetched_coaches.extend(coaches_for_team)
            await asyncio.sleep(REQUEST_DELAY_SECONDS) # Delay after fetching coaches for a team

        if all_fetched_players:
            await upsert_players_to_supabase(all_fetched_players) 

        if all_fetched_coaches:
            await upsert_coaches_to_supabase(all_fetched_coaches)

    end_time = datetime.now()
    logger.info(f"Metadata fetch process completed. Total time taken: {end_time - start_time}")

if __name__ == "__main__":
    asyncio.run(main()) 