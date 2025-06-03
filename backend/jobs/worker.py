#!/usr/bin/env python
"""
Worker Manager

This is the main worker process that consumes tasks from Redis queues
and coordinates data processing pipeline steps.

Usage:
    python -m jobs.worker

Environment variables:
    - REDIS_URL: Redis connection URL
    - SUPABASE_URL: Supabase URL
    - SUPABASE_KEY: Supabase API key
    - API_FOOTBALL_KEY: API-Football API key
    - OPENAI_API_KEY: OpenAI API key
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Optional

import redis
from dotenv import load_dotenv

# NEW IMPORT: Add scraper_fetcher
from fetchers.scraper_fetcher import main_scraper_task as scraper_main_task

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("worker")

# Load environment variables
load_dotenv()

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()  # Check connection
    logger.info("Connected to Redis")
except redis.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {e}")
    sys.exit(1)

# Worker configuration
FIXTURES_QUEUE = "queue:fixtures"
RAW_EVENTS_STREAM = "stream:raw_events"
CONSUMER_GROUP = "worker-group"
CONSUMER_NAME = f"worker-{os.getpid()}"
POLLING_INTERVAL = 5  # seconds

# Flag to control worker loop
running = True


def signal_handler(sig, frame):
    """Handle signals to gracefully shut down the worker"""
    global running
    logger.info("Shutdown signal received, finishing current tasks...")
    running = False


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def setup_streams():
    """Create consumer groups for Redis streams if they don't exist"""
    try:
        # Create consumer group for raw events stream
        try:
            redis_client.xgroup_create(RAW_EVENTS_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
            logger.info(f"Created consumer group {CONSUMER_GROUP} for stream {RAW_EVENTS_STREAM}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group {CONSUMER_GROUP} already exists")
            else:
                raise
    except Exception as e:
        logger.error(f"Error setting up streams: {e}")
        return False
    return True


async def process_fixture(fixture_id_str: str):
    """Process a fixture from the queue by triggering scraper fetcher"""
    logger.info(f"Processing fixture: {fixture_id_str} - by triggering scraper_fetcher")

    try:
        current_fixture_id: Optional[int] = None
        if fixture_id_str:
            try:
                current_fixture_id = int(fixture_id_str)
            except ValueError:
                logger.warning(f"Could not convert fixture_id_str '{fixture_id_str}' to int. Proceeding without specific fixture_id for scraper.")

        # Call the main task of scraper_fetcher, passing the specific fixture_id
        logger.info(f"Calling scraper_fetcher for fixture_id: {current_fixture_id} (scraper will run its general scan but pass this ID)")
        # Pass the integer fixture_id to the scraper task
        await scraper_main_task(fixture_id=current_fixture_id)
        logger.info(f"scraper_fetcher task completed for fixture_id: {current_fixture_id}")
        
        # TODO: In the future, trigger other fetchers like rest_fetcher, odds_fetcher for this specific fixture_id
        # Example: await rest_fetcher.fetch_and_store_data(current_fixture_id)
        #          await odds_fetcher.fetch_and_store_data(current_fixture_id)

        # Simulate some base processing time or await actual fetcher completion
        # The scraper_main_task is awaited, so its own delays are handled there.
        
        return True
    except Exception as e:
        logger.error(f"Error processing fixture {fixture_id_str} by calling scraper: {e}", exc_info=True)
        return False


async def process_raw_event(event_id, event_data):
    """Process a raw event from the stream - placeholder implementation"""
    try:
        logger.info(f"Processing raw event: {event_id}")

        # Parse event data
        match_id = event_data.get(b"match_id", b"").decode("utf-8")
        source = event_data.get(b"source", b"").decode("utf-8")
        event_data.get(b"payload", b"").decode("utf-8")

        logger.info(f"Event data: match_id={match_id}, source={source}")

        # Here we would process the event:
        # 1. Translate if needed
        # 2. Split into chunks
        # 3. Calculate reliability score
        # 4. Create embeddings
        # 5. Store in Pinecone/Supabase

        # Simulate processing delay
        await asyncio.sleep(1)

        return True
    except Exception as e:
        logger.error(f"Error processing raw event {event_id}: {e}")
        return False


async def consume_fixtures_queue():
    """Consume fixtures from the Redis queue"""
    try:
        queue_length = await asyncio.to_thread(redis_client.llen, FIXTURES_QUEUE)
        logger.info(f"Checking '{FIXTURES_QUEUE}', current length: {queue_length}") # DEBUG LOG

        if queue_length == 0:
            logger.debug(f"No fixtures in '{FIXTURES_QUEUE}'. Skipping pop attempt.")
            return False

        # Get a fixture from the queue (blocking pop with timeout)
        # redis-py's blpop is synchronous, so run it in a thread to avoid blocking asyncio loop
        result = await asyncio.to_thread(redis_client.blpop, FIXTURES_QUEUE, timeout=1)
        logger.info(f"blpop result from '{FIXTURES_QUEUE}': {result}") # DEBUG LOG

        if not result:
            logger.info(f"'{FIXTURES_QUEUE}' blpop returned None (timeout or empty).") # DEBUG LOG
            return False

        _, fixture_id_bytes = result
        fixture_id = fixture_id_bytes.decode("utf-8")

        logger.info(f"Got fixture {fixture_id} from queue '{FIXTURES_QUEUE}'")

        # Process the fixture
        success = await process_fixture(fixture_id)

        # If processing failed, we could requeue it
        if not success:
            logger.warning(f"Failed to process fixture {fixture_id}, requeuing to '{FIXTURES_QUEUE}'...")
            await asyncio.to_thread(redis_client.rpush, FIXTURES_QUEUE, fixture_id)

        return True
    except Exception as e:
        logger.error(f"Error consuming from fixtures queue '{FIXTURES_QUEUE}': {e}", exc_info=True)
        return False


async def consume_raw_events_stream():
    """Consume events from the raw events stream"""
    try:
        # Read new messages from the stream
        messages = redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={RAW_EVENTS_STREAM: ">"},
            count=10,
            block=1000,  # 1 second timeout
        )

        if not messages:
            return False

        # Process each message
        processed_count = 0
        for stream_name, stream_messages in messages:
            for message_id, message_data in stream_messages:
                # Process the message
                success = await process_raw_event(message_id, message_data)

                # Acknowledge the message if processed successfully
                if success:
                    redis_client.xack(stream_name, CONSUMER_GROUP, message_id)
                    processed_count += 1
                else:
                    logger.warning(f"Failed to process message {message_id}, will be redelivered")

        if processed_count > 0:
            logger.info(f"Processed {processed_count} raw events")

        return processed_count > 0
    except Exception as e:
        logger.error(f"Error consuming from raw events stream: {e}")
        return False


async def worker_loop():
    """Main worker loop"""
    logger.info("Worker loop started.") # DEBUG LOG
    while running:
        try:
            logger.info("Worker loop iteration: trying to consume fixtures.") # DEBUG LOG
            fixtures_processed = await consume_fixtures_queue()
            logger.info(f"Worker loop iteration: fixtures_processed = {fixtures_processed}") # DEBUG LOG

            logger.info("Worker loop iteration: trying to consume raw events.") # DEBUG LOG
            events_processed = await consume_raw_events_stream()
            logger.info(f"Worker loop iteration: events_processed = {events_processed}") # DEBUG LOG

            # If nothing was processed, sleep a bit to avoid CPU spinning
            if not fixtures_processed and not events_processed:
                logger.info(f"Nothing processed, sleeping for {POLLING_INTERVAL} seconds.") # DEBUG LOG
                await asyncio.sleep(POLLING_INTERVAL)
            else:
                logger.info("Something was processed, looping again immediately.") # DEBUG LOG
                await asyncio.sleep(0.1) # Short sleep to yield control
        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            await asyncio.sleep(POLLING_INTERVAL)
    logger.info("Worker loop stopped because 'running' is False.") # DEBUG LOG


async def main():
    """Main function"""
    logger.info("Starting worker")

    # Setup streams and consumer groups
    if not setup_streams():
        logger.error("Failed to set up streams, exiting")
        return

    # Run the worker loop
    await worker_loop()

    logger.info("Worker shutdown complete")


async def store_prediction_in_supabase(fixture_id: int, prediction: dict):
    """Store AI prediction in Supabase ai_predictions table"""
    try:
        # Prepare data for storage according to new schema
        prediction_data = {
            "fixture_id": fixture_id,
            "type": "ai_analysis",
            "chain_of_thought": prediction.get("chain_of_thought", ""),
            "final_prediction": prediction.get("final_prediction", ""),
            "confidence_score": prediction.get("confidence_score", 0),
            "risk_factors": prediction.get("risk_factors", []),
            "key_insights": prediction.get("key_insights", []),
            "context_quality": prediction.get("context_quality", {}),
            "processing_time_seconds": prediction.get("processing_time_seconds", 0.0),
            "context_chunks_used": prediction.get("context_chunks_used", 0),
            "value_bets": prediction.get("value_bets", []),
            "model_version": prediction.get("model_version", "unknown")
            # generated_at will be set automatically by database default
        }
        
        # Check if prediction already exists for this fixture
        existing = supabase.table("ai_predictions").select("id").eq("fixture_id", fixture_id).execute()
        
        if existing.data:
            # Update existing prediction
            response = supabase.table("ai_predictions").update(prediction_data).eq("fixture_id", fixture_id).execute()
            logger.info(f"Updated existing AI prediction for fixture {fixture_id} in Supabase")
        else:
            # Insert new prediction
            response = supabase.table("ai_predictions").insert(prediction_data).execute()
            logger.info(f"Inserted new AI prediction for fixture {fixture_id} in Supabase")
        
        if response.data:
            logger.info(f"Successfully stored AI prediction for fixture {fixture_id} in Supabase")
        else:
            logger.error(f"Failed to store AI prediction for fixture {fixture_id}: {response}")
            
    except Exception as e:
        logger.error(f"Error storing prediction in Supabase for fixture {fixture_id}: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
