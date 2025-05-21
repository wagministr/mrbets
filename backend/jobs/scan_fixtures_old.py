#!/usr/bin/env python
"""
Scan Fixtures

This script fetches upcoming fixtures from API-Football and adds them to Redis queue for processing.
It's designed to be run as a cron job every 30 minutes.

Usage:
    python -m jobs.scan_fixtures

Environment variables:
    - API_FOOTBALL_KEY: API-Football API key
    - REDIS_URL: Redis connection URL
    - SUPABASE_URL: Supabase URL
    - SUPABASE_KEY: Supabase API key
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import redis
from dotenv import load_dotenv
from supabase import create_client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scan_fixtures")

# Load environment variables
load_dotenv()

# API credentials
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
if not API_FOOTBALL_KEY:
    logger.error("API_FOOTBALL_KEY environment variable not set")
    sys.exit(1)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()  # Check connection
    logger.info("Connected to Redis")
except redis.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {e}")
    sys.exit(1)

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_KEY environment variables not set")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuration
API_FOOTBALL_URL = "https://v3.football.api-sports.io"

QUEUE_NAME = "queue:fixtures"
LEAGUES_TO_MONITOR = [
    39,
    140,
    78,
    61,
    135,
    2,
    3,
    15,
    255,
    921,
]  # Premier League, La Liga, Bundesliga, etc.

sys.path.append(str(Path(__file__).parent.parent))

async def fetch_fixtures(date_from, date_to):
    """Fetch fixtures from API-Football day-by-day using ?date=YYYY-MM-DD&league=ID1,ID2,..."""

    headers = {
        "x-apisports-key": API_FOOTBALL_KEY,
    }

    fixtures = []

    current_day = date_from
    while current_day <= date_to:
        date_str = current_day.strftime("%Y-%m-%d")
        params = {
            "date": date_str,
            "timezone": "UTC"
        }
        if LEAGUES_TO_MONITOR:
            leagues_param = ",".join(map(str, LEAGUES_TO_MONITOR))
            params["league"] = leagues_param
        logger.info(f"[fixtures_scanned][api-football][started] Fetching fixtures for {date_str} leagues {params.get('league','')}")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{API_FOOTBALL_URL}/fixtures", headers=headers, params=params
                )
                if response.status_code != 200:
                    logger.error(f"[fixtures_scanned][api-football][error] API request failed for {date_str} leagues {params.get('league','')}: {response.status_code} {response.text}")
                    continue
                data = response.json()
                daily_fixtures = data.get("response", [])
                logger.info(f"[fixtures_scanned][api-football][success] Retrieved {len(daily_fixtures)} fixtures for {date_str} leagues {params.get('league','')}")
                for f in daily_fixtures:
                    logger.info(f"[fixture_found][api-football][info] {f['teams']['home']['name']} vs {f['teams']['away']['name']} — League ID {f['league']['id']} — {f['fixture']['date']}")
                fixtures.extend(daily_fixtures)
            except Exception as e:
                logger.error(f"[fixtures_scanned][api-football][error] Exception fetching fixtures for {date_str} leagues {params.get('league','')}: {e}")
        current_day += timedelta(days=1)
    logger.info(f"[fixtures_scanned][api-football][finished] Total fixtures collected: {len(fixtures)}")
    return fixtures


async def store_fixtures_in_supabase(fixtures):
    """Store fixtures in Supabase database"""
    if not fixtures:
        logger.info("[fixtures_stored][supabase][skipped] No fixtures to store")
        return

    logger.info(f"[fixtures_stored][supabase][started] Storing {len(fixtures)} fixtures in Supabase")

    for fixture in fixtures:
        fixture_data = {
            "fixture_id": fixture["fixture"]["id"],
            "league_id": fixture["league"]["id"],
            "home_id": fixture["teams"]["home"]["id"],
            "away_id": fixture["teams"]["away"]["id"],
            "utc_kickoff": fixture["fixture"]["date"],
            "status": fixture["fixture"]["status"]["short"],
            "last_updated": datetime.now().isoformat(),
        }

        # Add scores if match has started
        if fixture["fixture"]["status"]["short"] != "NS":  # Not 'Not Started'
            fixture_data["score_home"] = fixture["goals"]["home"]
            fixture_data["score_away"] = fixture["goals"]["away"]

        try:
            # Upsert the fixture (insert if not exists, update if exists)
            supabase.table("fixtures").upsert(fixture_data).execute()
        except Exception as e:
            logger.error(f"[fixtures_stored][supabase][error] Error storing fixture {fixture_data['fixture_id']}: {type(e).__name__}: {e}")



def add_fixtures_to_queue(fixtures):
    """Add fixture IDs to Redis queue for processing"""
    if not fixtures:
        logger.warning("[fixture_queued][redis][skipped] No fixtures to add to queue")
        return

    # Create a set of existing fixture IDs in the queue to avoid duplicates
    existing_ids = set()

    # Get all fixture IDs in the queue
    queue_items = redis_client.lrange(QUEUE_NAME, 0, -1)
    for item in queue_items:
        try:
            existing_ids.add(int(item.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            pass

    added_count = 0
    for fixture in fixtures:
        fixture_id = fixture["fixture"]["id"]

        # Skip if already in queue
        if fixture_id in existing_ids:
            continue

        # Add to Redis queue
        redis_client.lpush(QUEUE_NAME, fixture_id)
        added_count += 1
        logger.info(f"[fixture_queued][redis][success] Match {fixture_id} added to Redis queue")

    logger.info(f"[fixture_queued][redis][finished] Added {added_count} new fixtures to the queue")


async def main():
    """Main function"""
    logger.info("Starting fixture scan")

    # Calculate date range (историческая дата для теста)
    today = datetime(2025, 4, 1)
    end_date = today + timedelta(days=30)

    # Сначала ищем только в топ-5 лигах
    fixtures = await fetch_fixtures(today, end_date)
    logger.info(f"Retrieved {len(fixtures)} fixtures in top-5 leagues")

    # Если ничего не найдено — fallback на топ-20 лиг
    if not fixtures:
        logger.warning("No fixtures found in top-5 leagues, expanding search to extended list for test purposes")
        LEAGUES_TO_MONITOR_EXTENDED = [
            39,   # Premier League
            140,  # La Liga
            78,   # Bundesliga
            61,   # Ligue 1
            135,  # Serie A
            2,    # Champions League
            3,    # Europa League
            848,  # Conference League
            1,    # World Cup
            4,    # Euro Championship
            9,    # Copa America
            253,  # MLS
            94,   # J-League (Japan)
            203,  # Turkey
            201,  # Portugal
            195,  # Netherlands
            197,  # Belgium
            196,  # Switzerland
            200,  # Greece
            208,  # Denmark
            210,  # Sweden
            211,  # Norway
            216,  # Poland
            218,  # Czech Republic
            219,  # Croatia
            220,  # Serbia
            222,  # Ukraine
            223,  # Israel
            262,  # Mexico
            94,   # Argentina
            71,   # Brazil
            77,   # China
            80,   # Australia
            307,  # South Korea
            307,  # Saudi Arabia
            307,  # Egypt
            307,  # South Africa
        ]
        global LEAGUES_TO_MONITOR
        LEAGUES_TO_MONITOR = LEAGUES_TO_MONITOR_EXTENDED
        fixtures = await fetch_fixtures(today, end_date)
        logger.info(f"Retrieved {len(fixtures)} fixtures in extended leagues fallback mode")

    # Store fixtures in Supabase
    await store_fixtures_in_supabase(fixtures)

    # Add fixture IDs to Redis queue for processing
    add_fixtures_to_queue(fixtures)

    logger.info("Fixture scan completed")


if __name__ == "__main__":
    asyncio.run(main())
