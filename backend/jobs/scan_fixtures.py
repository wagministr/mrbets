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

import os
import sys
import httpx
import redis
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
import asyncio

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
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
API_FOOTBALL_URL = "https://api-football-v1.p.rapidapi.com/v3"
QUEUE_NAME = "queue:fixtures"
LEAGUES_TO_MONITOR = [39, 140, 78, 61, 135, 2, 3]  # Premier League, La Liga, Bundesliga, etc.

async def fetch_fixtures(date_from, date_to):
    """Fetch fixtures from API-Football"""
    headers = {
        "X-RapidAPI-Key": API_FOOTBALL_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    
    # Format dates as YYYY-MM-DD
    date_from_str = date_from.strftime("%Y-%m-%d")
    date_to_str = date_to.strftime("%Y-%m-%d")
    
    logger.info(f"Fetching fixtures from {date_from_str} to {date_to_str}")
    
    params = {
        "from": date_from_str,
        "to": date_to_str,
        "timezone": "UTC"
    }
    
    # If leagues are specified, add them to the query
    if LEAGUES_TO_MONITOR:
        leagues_param = ",".join(map(str, LEAGUES_TO_MONITOR))
        params["league"] = leagues_param
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{API_FOOTBALL_URL}/fixtures",
                headers=headers,
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return []
                
            data = response.json()
            return data.get("response", [])
        except Exception as e:
            logger.error(f"Error fetching fixtures: {e}")
            return []

async def store_fixtures_in_supabase(fixtures):
    """Store fixtures in Supabase database"""
    if not fixtures:
        logger.info("No fixtures to store")
        return
        
    logger.info(f"Storing {len(fixtures)} fixtures in Supabase")
    
    for fixture in fixtures:
        fixture_data = {
            "fixture_id": fixture["fixture"]["id"],
            "league_id": fixture["league"]["id"],
            "home_id": fixture["teams"]["home"]["id"],
            "away_id": fixture["teams"]["away"]["id"],
            "utc_kickoff": fixture["fixture"]["date"],
            "status": fixture["fixture"]["status"]["short"],
            "last_updated": datetime.now().isoformat()
        }
        
        # Add scores if match has started
        if fixture["fixture"]["status"]["short"] != "NS":  # Not 'Not Started'
            fixture_data["score_home"] = fixture["goals"]["home"]
            fixture_data["score_away"] = fixture["goals"]["away"]
            
        try:
            # Upsert the fixture (insert if not exists, update if exists)
            supabase.table("fixtures").upsert(fixture_data).execute()
        except Exception as e:
            logger.error(f"Error storing fixture {fixture_data['fixture_id']}: {e}")

def add_fixtures_to_queue(fixtures):
    """Add fixture IDs to Redis queue for processing"""
    if not fixtures:
        logger.info("No fixtures to add to queue")
        return
        
    # Create a set of existing fixture IDs in the queue to avoid duplicates
    existing_ids = set()
    
    # Get all fixture IDs in the queue
    queue_items = redis_client.lrange(QUEUE_NAME, 0, -1)
    for item in queue_items:
        try:
            existing_ids.add(int(item.decode('utf-8')))
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
        
    logger.info(f"Added {added_count} new fixtures to the queue")

async def main():
    """Main function"""
    logger.info("Starting fixture scan")
    
    # Calculate date range (today + 3 days)
    today = datetime.now()
    end_date = today + timedelta(days=3)
    
    # Fetch fixtures
    fixtures = await fetch_fixtures(today, end_date)
    logger.info(f"Retrieved {len(fixtures)} fixtures")
    
    # Store fixtures in Supabase
    await store_fixtures_in_supabase(fixtures)
    
    # Add fixture IDs to Redis queue for processing
    add_fixtures_to_queue(fixtures)
    
    logger.info("Fixture scan completed")

if __name__ == "__main__":
    asyncio.run(main()) 