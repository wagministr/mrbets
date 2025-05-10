"""
REST API Fetcher

Fetches data from REST APIs (e.g., API-Football) and adds it to the raw events stream.
"""

import os
import json
import logging
import httpx
import redis
from datetime import datetime
from typing import Dict, Any, Optional, List

# Set up logging
logger = logging.getLogger("rest_fetcher")

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RAW_EVENTS_STREAM = "stream:raw_events"

# API configuration
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
API_FOOTBALL_URL = "https://api-football-v1.p.rapidapi.com/v3"


class RestFetcher:
    """Fetcher for REST API data sources"""
    
    def __init__(self):
        """Initialize the fetcher"""
        self.redis_client = redis.from_url(REDIS_URL)
        
    async def fetch_fixture_data(self, fixture_id: int) -> Dict[str, Any]:
        """Fetch fixture data from API-Football"""
        logger.info(f"Fetching data for fixture {fixture_id}")
        
        headers = {
            "X-RapidAPI-Key": API_FOOTBALL_KEY,
            "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
        }
        
        # Fetch basic fixture data
        endpoints = [
            "fixtures",  # Basic match info
            "fixtures/statistics",  # Team statistics
            "fixtures/events",  # Match events (goals, cards)
            "odds"  # Betting odds
        ]
        
        result = {}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for endpoint in endpoints:
                try:
                    params = {"fixture": fixture_id}
                    if endpoint == "fixtures":
                        params = {"id": fixture_id}
                    
                    response = await client.get(
                        f"{API_FOOTBALL_URL}/{endpoint}",
                        headers=headers,
                        params=params
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        key = endpoint.split("/")[-1] if "/" in endpoint else endpoint
                        result[key] = data.get("response", [])
                    else:
                        logger.error(f"API request failed for {endpoint}: {response.status_code}")
                except Exception as e:
                    logger.error(f"Error fetching {endpoint} data: {e}")
        
        return result
    
    async def process_fixture(self, fixture_id: int) -> bool:
        """Process a fixture and add data to the raw events stream"""
        try:
            # Fetch data from API-Football
            data = await self.fetch_fixture_data(fixture_id)
            
            if not data:
                logger.warning(f"No data retrieved for fixture {fixture_id}")
                return False
                
            # Add to raw events stream
            event_data = {
                "match_id": str(fixture_id),
                "source": "api_football",
                "payload": json.dumps(data),
                "timestamp": str(int(datetime.now().timestamp()))
            }
            
            # Add to Redis stream
            message_id = self.redis_client.xadd(RAW_EVENTS_STREAM, event_data)
            
            logger.info(f"Added API-Football data to stream with ID {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing fixture {fixture_id}: {e}")
            return False


# Singleton instance
rest_fetcher = RestFetcher()

async def fetch(fixture_id: int) -> bool:
    """Fetch data for a fixture"""
    return await rest_fetcher.process_fixture(fixture_id)