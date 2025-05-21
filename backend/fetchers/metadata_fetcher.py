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
from datetime import datetime
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
    140,   # La Liga (Spain)
    78,    # Bundesliga (Germany)
    61,    # Ligue 1 (France)
    135,   # Serie A (Italy)
    # Add more leagues from LEAGUES_TO_MONITOR_EXTENDED as needed for full coverage
    2,     # Champions League
    3,     # Europa League
    # 15,    # FIFA World Cup (usually not relevant for club seasons)
    255,   # Eredivisie (Netherlands)
    # 921,   # Conference League Qualifiers (example, adjust as needed)
    848,   # UEFA Conference League
    # 1,     # Euro Championship (usually not relevant for club seasons)
    4,     # Copa Libertadores (South America)
    9,     # Copa Sudamericana (South America)
    253,   # MLS (USA)
    94,    # Primeira Liga (Portugal)
    203,   # Super Lig (Turkey)
    # 201,   # Super League (Greece) - example if needed
    # 195,   # Pro League (Belgium) - example if needed
    # 197,   # Superliga (Denmark) - example if needed
    # 196,   # Veikkausliiga (Finland) - example if needed
    200,   # Premiership (Scotland)
    208,   # Eliteserien (Norway)
    210,   # Allsvenskan (Sweden)
    # 211,   # Super League (Switzerland) - example if needed
    # 216,   # Premier League (Russia) - consider if needed
    218,   # Premier Liga (Bosnia and Herzegovina)
    219,   # HNL (Croatia)
    220,   # 1. Liga (Czech Republic)
    # 222,   # Superliga (Serbia) - example if needed
    # 223,   # Fortuna liga (Slovakia) - example if needed
    262,   # Liga MX (Mexico)
    # 94,    # Primeira Liga (Portugal) - already listed
    71,    # Serie A (Brazil)
    # 77,    # Primera Division (Argentina) - example if needed
    # 80,    # A-League (Australia) - example if needed
    307    # Saudi Professional League (Saudi Arabia)
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


async def fetch_players_for_team(team_id: int, season: int, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Fetch players for a given team and season (paginated)."""
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    all_players = []
    current_page = 1
    total_pages = 1 # Assume 1 page initially, will be updated by API response

    while current_page <= total_pages:
        params = {"team": str(team_id), "season": str(season), "page": str(current_page)}
        try:
            logger.info(f"Fetching players for team {team_id}, season {season}, page {current_page}.")
            response = await client.get(f"{API_FOOTBALL_URL}/players", headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            page_players = data.get("response", [])
            all_players.extend(page_players)
            
            if current_page == 1: # Set total_pages only on the first request
                total_pages = data.get("paging", {}).get("total", 1)
            
            logger.info(f"Fetched {len(page_players)} players on page {current_page}/{total_pages} for team {team_id}.")

            if current_page < total_pages:
                 await asyncio.sleep(REQUEST_DELAY_SECONDS) # Delay between paginated requests for the same team
            current_page += 1

        except httpx.HTTPStatusError as e:
            logger.error(f"API error fetching players for team {team_id}, season {season}, page {current_page}: {e.response.status_code} {e.response.text}")
            break # Stop pagination on error
        except Exception as e:
            logger.error(f"Exception fetching players for team {team_id}, season {season}, page {current_page}: {e}")
            break # Stop pagination on error
            
    logger.info(f"Fetched a total of {len(all_players)} players for team {team_id}, season {season}.")
    return all_players

async def upsert_players_to_supabase(players_data_list: List[Dict[str, Any]], team_id_fk: int, league_id_fk: int, season_fk: int):
    """Upsert player data into the Supabase 'players' table."""
    if not players_data_list:
        return

    records_to_upsert = []
    for item in players_data_list:
        player = item.get("player", {})
        if not player.get("id"):
            logger.warning(f"Skipping player with no ID: {player.get('name')}")
            continue

        birth_info = player.get("birth", {})
        
        # Extract position and rating specific to the league_id_fk
        player_position = None
        player_rating = None
        statistics = item.get("statistics", [])
        if isinstance(statistics, list):
            for stat_entry in statistics:
                if stat_entry.get("league", {}).get("id") == league_id_fk:
                    player_position = stat_entry.get("games", {}).get("position")
                    # API-Football rating can be null or a string, ensure it's stored as text
                    rating_value = stat_entry.get("games", {}).get("rating")
                    player_rating = str(rating_value) if rating_value is not None else None
                    break # Found specific league stats

        record = {
            "player_id": player["id"],
            "name": player.get("name"),
            "firstname": player.get("firstname"),
            "lastname": player.get("lastname"),
            "age": player.get("age"),
            "birth_date": birth_info.get("date"), # This should be 'YYYY-MM-DD'
            "nationality": player.get("nationality"),
            "height": player.get("height"),
            "weight": player.get("weight"),
            "injured": player.get("injured", False), # Default to False if null/missing
            "photo_url": player.get("photo"),
            "current_team_id": team_id_fk, # Explicitly use the team_id for which players were fetched
            "api_football_league_id": league_id_fk, # Context: league for this player entry
            "api_football_season": season_fk,       # Context: season for this player entry
            "position": player_position,            # From specific league context
            "rating": player_rating,                # From specific league context
            "last_updated_api_football": datetime.now().isoformat(),
            "meta_data": item, # Store the full API response item as meta_data
        }
        records_to_upsert.append(record)
    
    if not records_to_upsert:
        return

    try:
        logger.info(f"Upserting {len(records_to_upsert)} players for team {team_id_fk} (League: {league_id_fk}, Season: {season_fk}) to Supabase.")
        # Supabase client's upsert handles `on_conflict` for primary key `player_id`
        supabase.table("players").upsert(records_to_upsert).execute()
        logger.info(f"Successfully upserted {len(records_to_upsert)} players for team {team_id_fk} (League: {league_id_fk}).")
    except Exception as e:
        logger.error(f"Error upserting players for team {team_id_fk} (League: {league_id_fk}) to Supabase: {e}")


async def main():
    """Main function to orchestrate fetching and storing metadata."""
    logger.info("Starting metadata fetcher process.")
    async with httpx.AsyncClient() as client:
        for league_id in LEAGUES_TO_PROCESS:
            logger.info(f"Processing league ID: {league_id}")
            await asyncio.sleep(REQUEST_DELAY_SECONDS) # Delay before fetching league season
            
            current_season = await get_current_season_for_league(league_id, client)
            if not current_season:
                logger.warning(f"Skipping league {league_id} as current season could not be determined.")
                continue

            await asyncio.sleep(REQUEST_DELAY_SECONDS) # Delay before fetching teams
            teams = await fetch_teams_for_league(league_id, current_season, client)
            if not teams:
                logger.info(f"No teams found for league {league_id}, season {current_season}. Skipping player fetch for this league.")
                continue
            
            await upsert_teams_to_supabase(teams)

            for team_item in teams:
                team_id = team_item.get("team", {}).get("id")
                if not team_id:
                    continue
                
                logger.info(f"Processing team ID: {team_id} from league {league_id}")
                await asyncio.sleep(REQUEST_DELAY_SECONDS) # Delay before fetching players for a team
                
                players = await fetch_players_for_team(team_id, current_season, client)
                if players:
                    await upsert_players_to_supabase(players, team_id, league_id, current_season) # Pass team_id, league_id, and current_season
            
            logger.info(f"Finished processing league ID: {league_id}")

    logger.info("Metadata fetcher process completed.")

if __name__ == "__main__":
    asyncio.run(main()) 