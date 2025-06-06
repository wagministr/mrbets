#!/usr/bin/env python
"""
Scan Fixtures

This script fetches upcoming fixtures from API-Football, stores/updates them in Supabase,
and adds their IDs to a Redis queue for further processing.
It's designed to be run as a cron job (e.g., every 30 minutes or hourly).

Usage:
    python -m jobs.scan_fixtures

Environment variables:
    - API_FOOTBALL_KEY: API-Football API key
    - REDIS_URL: Redis connection URL
    - SUPABASE_URL: Supabase URL
    - SUPABASE_SERVICE_KEY: Supabase API key
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import redis
from dotenv import load_dotenv
from supabase import create_client, Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scan_fixtures")

# Load environment variables from .env in the backend directory or project root
dotenv_path_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
dotenv_path_project_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')

if os.path.exists(dotenv_path_backend):
    load_dotenv(dotenv_path_backend)
    logger.info(f"Loaded .env from {dotenv_path_backend}")
elif os.path.exists(dotenv_path_project_root):
    load_dotenv(dotenv_path_project_root)
    logger.info(f"Loaded .env from {dotenv_path_project_root}")
else:
    load_dotenv() # try loading from current dir or standard locations
    logger.info("Attempted to load .env from default locations.")


# API credentials
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
if not API_FOOTBALL_KEY:
    logger.error("API_FOOTBALL_KEY environment variable not set")
    sys.exit(1)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client: redis.Redis = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True) # decode_responses=True for easier string handling
    redis_client.ping()
    logger.info(f"Successfully connected to Redis at {REDIS_URL}")
except redis.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"An unexpected error occurred while connecting to Redis: {e}")
    sys.exit(1)

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") # Use service key for backend
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables not set")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
logger.info(f"Supabase client initialized for URL: {SUPABASE_URL[:20]}...") # Log part of URL for confirmation

# Configuration
API_FOOTBALL_URL = "https://v3.football.api-sports.io"
FIXTURES_QUEUE_NAME = "queue:fixtures:normal" # Normal queue for fixture IDs (priority queue is separate)
PROCESSED_FIXTURES_SET_NAME = "set:fixtures_scanned_today" # For de-duplication by this scanner run
# TTL for the de-duplication set, e.g., 24 hours in seconds
PROCESSED_FIXTURES_SET_TTL = 24 * 60 * 60

# LEAGUES_TO_MONITOR should ideally be sourced from a shared config or dynamically
LEAGUES_TO_MONITOR = [
    39, # EPL (England)
    140, # La Liga (Spain)
    78, # Bundesliga (Germany)
    61, # Ligue 1 (France)
    135, # Serie A (Italy)
    2, # Champions League
    3, # Europa League
    255, # Eredivisie (Netherlands)
    848, # UEFA Conference League
    4, # Euro Championship
    9, # Copa America
    253, # Liga Profesional Argentina
    94, # Premier Liga (Portugal)
    203, # Super Lig (Turkey)
    # 200, # Belgium Jupiler Pro League - Example, add as needed
    # 208, # Danish Superliga - Example, add as needed
    # 210, # Swiss Super League - Example, add as needed
    # 218, # Norwegian Eliteserien - Example, add as needed
    # 219, # Swedish Allsvenskan - Example, add as needed
    # 220, # Austrian Bundesliga - Example, add as needed
    # 262, # MLS (USA) - Example, add as needed
    71, # Serie A (Brazil)
    307 # Saudi Professional League
]
# For testing, you can reduce this list:
# LEAGUES_TO_MONITOR = [39] # EPL Only

DAYS_FORWARD = 30 # Fetch fixtures for today and next 29 days (total 30 days)
REQUEST_DELAY_SECONDS = 1 # Delay between API calls to respect rate limits

# Configuration for fetching past season data for testing
TEST_MODE_PAST_SEASON = True # Set to False to revert to current season fetching
TEST_SEASON = "2023" # Season year (e.g., 2023 for 2023/2024 season)
TEST_DATE_FROM = f"{TEST_SEASON}-08-01" # Example: August 2023
TEST_DATE_TO = f"{TEST_SEASON}-08-05"   # Example: August 2023

async def fetch_fixtures_for_league_range(league_id: int, date_from: str, date_to: str, season: str, client: httpx.AsyncClient):
    """Fetch fixtures for a league within a date range (from-to) for a specific season."""
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {
        "league": str(league_id),
        "season": season,
        "from": date_from,
        "to": date_to,
        "timezone": "UTC" # Ensure all times are UTC
    }
    try:
        logger.info(f"Fetching fixtures for league {league_id}, season {season}, from {date_from} to {date_to}")
        response = await client.get(f"{API_FOOTBALL_URL}/fixtures", headers=headers, params=params, timeout=30.0)
        response.raise_for_status() # Raise an exception for HTTP errors 4xx/5xx
        data = response.json()
        fixtures = data.get("response", [])
        logger.info(f"Fetched {len(fixtures)} fixtures for league {league_id}, season {season}, from {date_from} to {date_to}.")
        return fixtures
    except httpx.HTTPStatusError as e:
        logger.error(f"API error fetching fixtures for league {league_id}, season {season}: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error fetching fixtures for league {league_id}, season {season}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching fixtures for league {league_id}, season {season}: {type(e).__name__} - {e}")
    return []

async def upsert_fixtures_to_supabase(fixtures_to_store: list):
    """Upserts fixture data into the Supabase 'fixtures' table."""
    if not fixtures_to_store:
        logger.info("No fixtures to store in Supabase.")
        return 0

    records_to_upsert = []
    for fixture_api_data in fixtures_to_store:
        f_details = fixture_api_data.get("fixture", {})
        f_league = fixture_api_data.get("league", {})
        f_teams = fixture_api_data.get("teams", {})
        f_goals = fixture_api_data.get("goals", {})
        f_status = f_details.get("status", {})

        if not all([f_details.get("id"), f_league.get("id"), f_teams.get("home", {}).get("id"), f_teams.get("away", {}).get("id"), f_details.get("date")]):
            logger.warning(f"Skipping fixture due to missing critical data: {f_details.get('id')}")
            continue

        record = {
            "fixture_id": f_details["id"],
            "league_id": f_league["id"],
            "home_team_id": f_teams["home"]["id"],
            "away_team_id": f_teams["away"]["id"],
            "event_date": f_details["date"], # This should be UTC from API if timezone=UTC is used
            "status_short": f_status.get("short"),
            "status_long": f_status.get("long"),
            "score_home": f_goals.get("home"), # Will be None if not available
            "score_away": f_goals.get("away"), # Will be None if not available
            "api_response_fixture": fixture_api_data, # Store the full API response
            "last_updated_api_football": datetime.now(timezone.utc).isoformat(),
        }
        records_to_upsert.append(record)

    if not records_to_upsert:
        logger.info("No valid records to upsert to Supabase.")
        return 0
        
    try:
        logger.info(f"Attempting to upsert {len(records_to_upsert)} fixtures to Supabase.")
        # supabase-py uses on_conflict based on the primary key defined in the table (fixture_id)
        response = supabase.table("fixtures").upsert(records_to_upsert).execute()
        
        # Basic check for PostgREST response success (data is usually a list of upserted items)
        if response.data and not getattr(response, 'error', None): # Check if data exists and no error attribute or error is None
            logger.info(f"Successfully upserted {len(response.data)} fixtures.")
            return len(response.data)
        elif getattr(response, 'error', None):
            logger.error(f"Error upserting fixtures to Supabase: {response.error}")
            return 0
        else: # Fallback for unexpected response structure
            logger.warning(f"Upsert fixtures response from Supabase was not as expected: {response}")
            # Count successful upserts if possible or assume 0 if unclear.
            # For this example, assuming 0 on unexpected response.
            return 0
            
    except Exception as e:
        logger.error(f"Exception during Supabase upsert: {type(e).__name__} - {e}")
        return 0

def add_fixture_ids_to_redis_queue(fixture_ids: list):
    """Adds unique fixture IDs to the Redis queue for processing."""
    if not fixture_ids:
        logger.info("No fixture IDs to add to Redis queue.")
        return 0

    added_to_queue_count = 0
    try:
        # Use a pipeline for efficiency if adding many items
        pipe = redis_client.pipeline()
        new_ids_for_queue = []

        for fixture_id in fixture_ids:
            # Check if already processed by this scanner run (using the SET)
            # SADD returns 1 if element was added (new), 0 if it was already there.
            if redis_client.sadd(PROCESSED_FIXTURES_SET_NAME, str(fixture_id)):
                # If it's a new addition to the SET, set/update its TTL and add to queue
                redis_client.expire(PROCESSED_FIXTURES_SET_NAME, PROCESSED_FIXTURES_SET_TTL)
                new_ids_for_queue.append(str(fixture_id))
            # else:
                # logger.debug(f"Fixture ID {fixture_id} already in {PROCESSED_FIXTURES_SET_NAME}. Skipping queue add.")

        if new_ids_for_queue:
            pipe.lpush(FIXTURES_QUEUE_NAME, *new_ids_for_queue)
            results = pipe.execute()
            # The result of LPUSH is the new length of the list.
            # We are interested in how many items we attempted to push.
            added_to_queue_count = len(new_ids_for_queue) 
            logger.info(f"Added {added_to_queue_count} new fixture IDs to Redis queue '{FIXTURES_QUEUE_NAME}'.")
        else:
            logger.info("No new fixture IDs to add to the queue (all were already processed or in set).")

    except redis.RedisError as e:
        logger.error(f"Redis error adding fixture IDs to queue: {e}")
    except Exception as e:
        logger.error(f"Unexpected error adding fixture IDs to Redis queue: {e}")
    return added_to_queue_count

async def main():
    """Main function to fetch and process fixtures."""
    
    date_from_to_use = ""
    date_to_to_use = ""
    season_to_use = ""

    if TEST_MODE_PAST_SEASON:
        logger.info(f"--- TEST MODE: Fetching data for past season {TEST_SEASON} ---")
        logger.info(f"Using leagues for test: {LEAGUES_TO_MONITOR}")
        date_from_to_use = TEST_DATE_FROM
        date_to_to_use = TEST_DATE_TO
        season_to_use = TEST_SEASON
        logger.info(f"Targeting period: {date_from_to_use} to {date_to_to_use} for season {season_to_use}")
    else:
        logger.info(f"--- REGULAR MODE: Fetching current/upcoming data ---")
        logger.info(f"Starting fixture scan for {DAYS_FORWARD} days across {len(LEAGUES_TO_MONITOR)} leagues.")
        today_utc = datetime.now(timezone.utc).date()
        date_from_to_use = today_utc.strftime("%Y-%m-%d")
        date_to_to_use = (today_utc + timedelta(days=DAYS_FORWARD - 1)).strftime("%Y-%m-%d")
        # For current fixtures, the season is usually determined by the API based on the date.
        # However, some APIs might require it, or it helps to be explicit if known.
        # We can try to get current season from API or use current year as a guess if needed.
        # For now, assuming API handles season correctly for current dates or using a recent one.
        # If API_Football strictly requires season for date ranges, this might need adjustment.
        # For /fixtures with date range, season is often optional if the dates imply current season.
        # Let's try without explicitly setting season for current dates first, API might infer it.
        # If errors occur, we might need to add a dynamic current_season fetch here.
        current_year_season = str(datetime.now(timezone.utc).year) # Fallback/example
        season_to_use = current_year_season # Or fetch dynamically if API needs it for current dates
        logger.info(f"Targeting period: {date_from_to_use} to {date_to_to_use} for current season (approx {season_to_use})")

    all_fetched_fixtures = []
    
    async with httpx.AsyncClient() as client:
        for league_id in LEAGUES_TO_MONITOR:
            await asyncio.sleep(REQUEST_DELAY_SECONDS) # Respect API rate limits
            league_fixtures = await fetch_fixtures_for_league_range(league_id, date_from_to_use, date_to_to_use, season_to_use, client)
            if league_fixtures:
                all_fetched_fixtures.extend(league_fixtures)

    if not all_fetched_fixtures:
        logger.info("No fixtures found for any monitored league in the specified date range.")
        logger.info("Fixture scan completed.")
        return

    logger.info(f"Total fixtures fetched from API: {len(all_fetched_fixtures)}")

    # Store/update fixtures in Supabase
    upserted_count = await upsert_fixtures_to_supabase(all_fetched_fixtures)
    logger.info(f"Upserted {upserted_count} fixtures in Supabase.")

    # Add unique fixture IDs to Redis queue for processing
    # Extract fixture_ids from the originally fetched list
    fixture_ids_to_queue = [f["fixture"]["id"] for f in all_fetched_fixtures if f.get("fixture") and f["fixture"].get("id")]
    if fixture_ids_to_queue:
         queued_count = add_fixture_ids_to_redis_queue(fixture_ids_to_queue)
         logger.info(f"Added {queued_count} fixture IDs to Redis queue.")
    else:
        logger.info("No valid fixture IDs extracted from fetched data to queue.")

    logger.info("Fixture scan completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
