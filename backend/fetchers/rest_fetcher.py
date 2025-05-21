"""
REST API Fetcher

Fetches data from REST APIs (e.g., API-Football) and adds it to the raw events stream.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

import httpx
import redis
import uuid
from supabase import create_client

# Set up logging
logger = logging.getLogger("rest_fetcher")

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RAW_EVENTS_STREAM = "stream:raw_events"

# API configuration
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
API_FOOTBALL_URL = "https://api-football-v1.p.rapidapi.com/v3"

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
S3_BUCKET = os.getenv("S3_BUCKET", "mrbets-raw")

# Football-Data.org fallback configuration
FOOTBALLDATA_API_KEY = os.getenv("FOOTBALLDATA_API_KEY")
FOOTBALL_DATA_URL = "https://api.football-data.org/v4"


class RestFetcher:
    """Fetcher for REST API data sources"""

    def __init__(self):
        """Initialize the fetcher"""
        self.redis_client = redis.from_url(REDIS_URL)
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    async def fetch_fixture_data_fallback(self, fixture_id: int) -> Dict[str, Any]:
        """Fetch fixture data from Football-Data.org as fallback"""
        logger.warning(f"Using fallback for fixture {fixture_id}")
        headers = {"X-Auth-Token": FOOTBALLDATA_API_KEY}
        result = {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Example: get match info
                response = await client.get(f"{FOOTBALL_DATA_URL}/matches/{fixture_id}", headers=headers)
                if response.status_code == 200:
                    result["match"] = response.json()
                else:
                    logger.error(f"Football-Data.org request failed: {response.status_code}")
            except Exception as e:
                logger.error(f"Error fetching fallback data: {e}")
        return result

    async def fetch_fixture_data(self, fixture_id: int) -> Dict[str, Any]:
        """Fetch fixture data from API-Football, fallback to Football-Data.org if needed"""
        logger.info(f"Fetching data for fixture {fixture_id}")
        headers = {
            "X-RapidAPI-Key": API_FOOTBALL_KEY,
            "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
        }
        endpoints = [
            "fixtures",
            "fixtures/lineups",
            "fixtures/statistics",
            "fixtures/events",
            "odds",
        ]
        result = {}
        api_error = False
        async with httpx.AsyncClient(timeout=30.0) as client:
            for endpoint in endpoints:
                try:
                    params = {"fixture": fixture_id}
                    if endpoint == "fixtures":
                        params = {"id": fixture_id}
                    response = await client.get(
                        f"{API_FOOTBALL_URL}/{endpoint}", headers=headers, params=params
                    )
                    if response.status_code == 200:
                        data = response.json()
                        key = endpoint.split("/")[-1] if "/" in endpoint else endpoint
                        result[key] = data.get("response", [])
                    elif response.status_code == 429:
                        logger.error(f"API-Football rate limit for {endpoint}")
                        api_error = True
                        break
                    else:
                        logger.error(f"API request failed for {endpoint}: {response.status_code}")
                        api_error = True
                except Exception as e:
                    logger.error(f"Error fetching {endpoint} data: {e}")
                    api_error = True
        if not result or api_error:
            # Fallback to Football-Data.org
            fallback_data = await self.fetch_fixture_data_fallback(fixture_id)
            if fallback_data:
                result["fallback"] = fallback_data
        return result

    async def process_fixture(self, fixture_id: int) -> bool:
        """Process a fixture and add data to the raw events stream"""
        try:
            # Fetch data from API-Football (with fallback)
            data = await self.fetch_fixture_data(fixture_id)
            if not data:
                logger.warning(f"No data retrieved for fixture {fixture_id}")
                return False
            # Add to raw events stream
            event_data = {
                "match_id": str(fixture_id),
                "source": "api_football",
                "payload": json.dumps(data),
                "timestamp": str(int(datetime.now().timestamp())),
            }
            # Add to Redis stream
            message_id = self.redis_client.xadd(RAW_EVENTS_STREAM, event_data)
            logger.info(f"Added API-Football data to stream with ID {message_id}")
            # Save copy to Supabase Storage
            try:
                ts = int(datetime.now().timestamp())
                file_path = f"raw/{fixture_id}/api_football_{ts}.json"
                self.supabase.storage.from_(S3_BUCKET).upload(
                    file_path,
                    json.dumps(data).encode("utf-8"),
                    {"content-type": "application/json"}
                )
                logger.info(f"Saved copy to Supabase Storage: {file_path}")
            except Exception as e:
                logger.error(f"Error saving to Supabase Storage: {e}")
            return True
        except Exception as e:
            logger.error(f"Error processing fixture {fixture_id}: {e}")
            return False


# Singleton instance
rest_fetcher = RestFetcher()


async def fetch(fixture_id: int) -> bool:
    """Fetch data for a fixture"""
    return await rest_fetcher.process_fixture(fixture_id)
