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

import os
import sys
import time
import json
import logging
import redis
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio
import signal

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
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

async def process_fixture(fixture_id):
    """Process a fixture from the queue - placeholder implementation"""
    logger.info(f"Processing fixture: {fixture_id}")
    
    try:
        # Here we would call the different fetchers to collect data
        # For demonstration, we'll simulate data collection with dummy data
        
        # Simulate a REST API fetcher
        rest_data = {
            "match_id": fixture_id,
            "source": "api_football",
            "payload": json.dumps({"stats": {"possession": {"home": 55, "away": 45}}}),
            "timestamp": int(datetime.now().timestamp())
        }
        
        # Add data to raw events stream
        redis_client.xadd(RAW_EVENTS_STREAM, rest_data)
        logger.info(f"Added API data to {RAW_EVENTS_STREAM} for fixture {fixture_id}")
        
        # Simulate delay for data processing
        await asyncio.sleep(1)
        
        # In a real implementation, we would launch multiple fetchers:
        # - REST fetcher (API-Football)
        # - Scraper fetcher (BBC, ESPN)
        # - Twitter fetcher
        # - Telegram fetcher
        # - YouTube fetcher (with Whisper transcription)
        
        return True
    except Exception as e:
        logger.error(f"Error processing fixture {fixture_id}: {e}")
        return False

async def process_raw_event(event_id, event_data):
    """Process a raw event from the stream - placeholder implementation"""
    try:
        logger.info(f"Processing raw event: {event_id}")
        
        # Parse event data
        match_id = event_data.get(b'match_id', b'').decode('utf-8')
        source = event_data.get(b'source', b'').decode('utf-8')
        payload = event_data.get(b'payload', b'').decode('utf-8')
        
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
        # Check if there are items in the queue
        queue_length = redis_client.llen(FIXTURES_QUEUE)
        
        if queue_length == 0:
            logger.debug("No fixtures in queue")
            return False
            
        # Get a fixture from the queue (blocking pop with timeout)
        result = redis_client.blpop(FIXTURES_QUEUE, timeout=1)
        
        if not result:
            return False
            
        _, fixture_id_bytes = result
        fixture_id = fixture_id_bytes.decode('utf-8')
        
        logger.info(f"Got fixture {fixture_id} from queue")
        
        # Process the fixture
        success = await process_fixture(fixture_id)
        
        # If processing failed, we could requeue it
        if not success:
            logger.warning(f"Failed to process fixture {fixture_id}, requeuing...")
            redis_client.rpush(FIXTURES_QUEUE, fixture_id)
            
        return True
    except Exception as e:
        logger.error(f"Error consuming from fixtures queue: {e}")
        return False

async def consume_raw_events_stream():
    """Consume events from the raw events stream"""
    try:
        # Read new messages from the stream
        messages = redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={RAW_EVENTS_STREAM: '>'},
            count=10,
            block=1000  # 1 second timeout
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
    while running:
        try:
            # Process fixtures queue
            fixtures_processed = await consume_fixtures_queue()
            
            # Process raw events stream
            events_processed = await consume_raw_events_stream()
            
            # If nothing was processed, sleep a bit to avoid CPU spinning
            if not fixtures_processed and not events_processed:
                await asyncio.sleep(POLLING_INTERVAL)
        except Exception as e:
            logger.error(f"Error in worker loop: {e}")
            await asyncio.sleep(POLLING_INTERVAL)

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

if __name__ == "__main__":
    asyncio.run(main()) 