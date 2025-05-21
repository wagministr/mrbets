import asyncio
import httpx
import json
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
ODDS_API_URL = "https://api.the-odds-api.com/v4"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_STREAM_NAME = "raw_events"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") # Service key for backend operations
SUPABASE_BUCKET_NAME = "mrbets-raw"


# Redis connection
try:
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
except ImportError:
    logger.warning("redis library not found, Redis functionality will be disabled.")
    redis_client = None
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

# Supabase client
try:
    from supabase import create_client, Client
    if SUPABASE_URL and SUPABASE_KEY:
        supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        logger.warning("Supabase URL or Key not provided. Supabase functionality will be disabled.")
        supabase_client = None
except ImportError:
    logger.warning("supabase library not found, Supabase functionality will be disabled.")
    supabase_client = None
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    supabase_client = None

# In-memory cache for previous odds to detect changes
# For a production system, this should be persisted (e.g., in Redis) if monitoring across script runs is needed.
previous_odds_cache = {}

async def fetch_odds_for_sport(sport_key: str, regions: str = "eu", markets: str = "h2h,spreads,totals", odds_format: str = "decimal"):
    """
    Fetches odds for a given sport_key from The Odds API.
    """
    if not ODDS_API_KEY:
        logger.error("ODDS_API_KEY is not set. Cannot fetch odds.")
        return []

    url = f"{ODDS_API_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
        "dateFormat": "iso",
    }

    async with httpx.AsyncClient(timeout=30.0) as client: # Added timeout
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            logger.info(f"Successfully fetched odds for sport: {sport_key}. "
                        f"Requests remaining: {response.headers.get('x-requests-remaining', 'N/A')}, "
                        f"Requests used: {response.headers.get('x-requests-used', 'N/A')}")
            
            odds_data = response.json()
            
            for event in odds_data:
                await process_event_odds(event)
            
            return odds_data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while fetching odds for {sport_key}: {e.response.status_code} - {e.response.text}")
            # Potential Fallback: if e.response.status_code in [429, 500, 503]: try another_source()
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error occurred while fetching odds for {sport_key}: {e}")
            # Potential Fallback: try another_source()
        except httpx.RequestError as e:
            logger.error(f"Request error occurred while fetching odds for {sport_key}: {e}")
            # Potential Fallback: try another_source()
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response for {sport_key}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching odds for {sport_key}: {e}")
    
    return []


async def process_event_odds(event_data: dict):
    """
    Processes and stores the odds data for a single event.
    Monitors for odds changes for h2h markets.
    """
    try:
        event_id = event_data.get("id") 
        if not event_id:
            logger.warning(f"Event data missing 'id': {event_data}")
            return

        timestamp = datetime.utcnow().isoformat()
        
        payload_to_store = {
            "match_id": event_id, 
            "source": "the_odds_api",
            "payload": event_data,
            "timestamp": timestamp,
        }

        # Monitor odds changes (simple example for h2h market)
        if "bookmakers" in event_data:
            for bookmaker in event_data["bookmakers"]:
                bookmaker_key = bookmaker.get("key")
                if "markets" in bookmaker:
                    for market in bookmaker["markets"]:
                        market_key = market.get("key")
                        if market_key == "h2h": # Example: Monitor H2H market
                            outcomes = market.get("outcomes")
                            if outcomes and len(outcomes) >= 2: # Expect at least home/away or home/draw/away
                                current_h2h_odds = tuple(o.get("price") for o in outcomes)
                                cache_key = f"{event_id}_{bookmaker_key}_{market_key}"
                                
                                if cache_key in previous_odds_cache and previous_odds_cache[cache_key] != current_h2h_odds:
                                    logger.info(f"ODDS CHANGE DETECTED for event {event_id}, bookmaker {bookmaker_key}, market {market_key}: "
                                                f"OLD: {previous_odds_cache[cache_key]}, NEW: {current_h2h_odds}")
                                    # Here you could trigger alerts or specific actions
                                
                                previous_odds_cache[cache_key] = current_h2h_odds
        
        if redis_client:
            try:
                await redis_client.xadd(REDIS_STREAM_NAME, {"data": json.dumps(payload_to_store)})
                logger.info(f"Successfully added odds for match {event_id} to Redis Stream {REDIS_STREAM_NAME}.")
            except Exception as e:
                logger.error(f"Failed to add odds for match {event_id} to Redis: {e}")
        else:
            logger.warning("Redis client not available. Skipping sending to Redis.")

        if supabase_client:
            try:
                # Use event_id (which is the match_id from The Odds API) in the path
                file_path = f"raw/{event_id}/odds_the_odds_api_{datetime.utcnow().strftime('%Y%m%d%H%M%S%Z')}.json" # Added Z for UTC indication
                await supabase_client.storage.from_(SUPABASE_BUCKET_NAME).upload(
                    path=file_path, # Corrected parameter name
                    file=json.dumps(payload_to_store, indent=4).encode('utf-8'), # Corrected parameter name
                    file_options={"contentType": "application/json"} # Corrected parameter name
                )
                logger.info(f"Successfully saved odds snapshot for match {event_id} to Supabase Storage: {file_path}")
            except Exception as e:
                # Log the actual error from Supabase if available
                error_message = str(e)
                if hasattr(e, 'message'): # Supabase client sometimes has a message attribute
                    error_message = e.message
                logger.error(f"Failed to save odds for match {event_id} to Supabase Storage: {error_message}")
        else:
            logger.warning("Supabase client not available. Skipping saving to Supabase Storage.")
        
        if not redis_client and not supabase_client:
            logger.info(f"Processed odds for match_id: {event_id}. Data (logging only): {json.dumps(payload_to_store, indent=2)}")

    except Exception as e:
        logger.error(f"Error processing event odds for event {event_data.get('id', 'N/A')}: {e}", exc_info=True)


async def get_available_sports():
    """
    Fetches the list of available sports from The Odds API.
    """
    if not ODDS_API_KEY:
        logger.error("ODDS_API_KEY is not set. Cannot fetch sports.")
        return []
    
    url = f"{ODDS_API_URL}/sports"
    params = {"apiKey": ODDS_API_KEY}
    
    async with httpx.AsyncClient(timeout=30.0) as client: # Added timeout
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            sports = response.json()
            logger.info(f"Successfully fetched {len(sports)} sports.")
            # Log details of a few sports for review
            # for sport in sports[:3]: 
            #     logger.info(f"Sport details: Key: {sport.get('key')}, Title: {sport.get('title')}, Group: {sport.get('group')}, Active: {sport.get('active')}")
            return sports
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while fetching sports: {e.response.status_code} - {e.response.text}")
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error occurred while fetching sports: {e}")
        except httpx.RequestError as e:
            logger.error(f"Request error occurred while fetching sports: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response for sports: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching sports: {e}")
    return []

async def main():
    """
    Main function to orchestrate fetching odds.
    """
    sports = await get_available_sports()
    # Filter for soccer initially, can be configured via env var or config file later
    target_sport_groups = {"soccer"} 
    # One can also add specific sport_keys: e.g. {"soccer_epl", "soccer_uefa_champs_league"}
    
    selected_sports = [s for s in sports if s.get("group", "").lower() in target_sport_groups or s.get("key") in target_sport_groups]

    if not selected_sports:
        logger.warning(f"No sports matching target groups/keys found in The Odds API. Searched for: {target_sport_groups}. Exiting.")
        return

    all_fetched_odds_events = []
    for sport in selected_sports:
        if sport.get("active"):
            sport_key = sport.get("key")
            logger.info(f"Fetching odds for active league: {sport.get('title')} ({sport_key})")
            # For soccer, h2h (head-to-head/moneyline) and totals (over/under) are common.
            # Pinnacle often offers 'h2h', 'spreads', 'totals'. The Odds API might have similar conventions.
            # We use regions='eu' (Europe), but this can be made configurable.
            # Common markets for soccer: h2h, totals. Spreads are less common in EU for soccer.
            # For initial implementation, focusing on primary markets.
            odds_events = await fetch_odds_for_sport(sport_key, regions="eu", markets="h2h,totals")
            if odds_events:
                all_fetched_odds_events.extend(odds_events)
        else:
            logger.info(f"Skipping inactive sport: {sport.get('title')} ({sport.get('key')})")
    
    if not all_fetched_odds_events:
        logger.info("No odds data fetched for any targeted sports.")
    else:
        logger.info(f"Successfully fetched and initiated processing for odds from {len(all_fetched_odds_events)} events in total.")

    # Gracefully close Redis client if it was initialized
    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed.")

if __name__ == "__main__":
    if not ODDS_API_KEY:
        print("Error: ODDS_API_KEY environment variable is not set.")
        print("Please set it before running the script.")
        print("Example: export ODDS_API_KEY='your_key_here'")
    elif not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables are not set.")
        print("Please set them for Supabase integration.")
    else:
        asyncio.run(main()) 