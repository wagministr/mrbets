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
from typing import Optional, List

import redis
from dotenv import load_dotenv

# NEW IMPORT: Add scraper_fetcher
from fetchers.scraper_fetcher import main_scraper_task as scraper_main_task
# NEW IMPORT: Breaking news detector
from processors.breaking_news_detector import BreakingNewsDetector
# NEW IMPORT: Quick patch generator for impact analysis
from processors.quick_patch_generator import QuickPatchGenerator
# TODO: Add imports for other processors when ready
# from processors.llm_content_analyzer import LLMContentAnalyzer

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
FIXTURES_QUEUE = "queue:fixtures:normal"  # Normal queue for scheduled fixtures
FIXTURES_PRIORITY_QUEUE = "queue:fixtures:priority"  # NEW: Priority queue
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


async def add_to_priority_queue(match_ids: List[int]):
    """Add match IDs to priority queue for immediate processing"""
    try:
        for match_id in match_ids:
            await asyncio.to_thread(redis_client.rpush, FIXTURES_PRIORITY_QUEUE, str(match_id))
            logger.info(f"Added match {match_id} to priority queue for urgent processing")
    except Exception as e:
        logger.error(f"Error adding matches to priority queue: {e}")


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
        logger.info(f"Calling scraper_fetcher for fixture_id: {current_fixture_id} (scraper will run its general scan)")
        # scraper_main_task doesn't accept fixture_id parameter - it's a general scanner
        await scraper_main_task()
        logger.info(f"scraper_fetcher task completed for fixture_id: {current_fixture_id}")
        
        # TODO: In the future, trigger other fetchers like rest_fetcher, odds_fetcher for this specific fixture_id
        # Example: await rest_fetcher.fetch_and_store_data(current_fixture_id)
        #          await odds_fetcher.fetch_and_store_data(current_fixture_id)

        # TODO: Implement full prediction pipeline:
        # 1. MatchContextRetriever().get_context_for_match(current_fixture_id)
        # 2. LLMReasoner().generate_prediction(context)
        # 3. Save prediction to Supabase
        # 4. Trigger Telegram posting

        # Simulate some base processing time or await actual fetcher completion
        # The scraper_main_task is awaited, so its own delays are handled there.
        
        return True
    except Exception as e:
        logger.error(f"Error processing fixture {fixture_id_str} by calling scraper: {e}", exc_info=True)
        return False


async def process_raw_event(event_id, event_data):
    """Process a raw event from the stream with breaking news detection"""
    try:
        logger.info(f"Processing raw event: {event_id}")

        # Parse event data
        match_id = event_data.get(b"match_id", b"").decode("utf-8")
        source = event_data.get(b"source", b"").decode("utf-8")
        payload = event_data.get(b"payload", b"").decode("utf-8")

        logger.info(f"Event data: match_id={match_id}, source={source}")

        # Convert to dict format for processing
        event_dict = {
            "match_id": match_id if match_id else None,
            "source": source,
            "payload": payload,
            "timestamp": datetime.utcnow().timestamp()
        }

        # 1) Existing logic - LLM content analyzer (TODO: implement when ready)
        # await llm_content_analyzer.process_event(event_dict)

        # 2) NEW: Breaking news detection for Twitter content
        if source == "twitter":
            logger.info(f"Analyzing Twitter content for breaking news: {event_id}")
            
            breaking_detector = BreakingNewsDetector()
            breaking_analysis = await breaking_detector.analyze_tweet(event_dict)
            
            logger.info(f"Breaking news analysis result: {breaking_analysis}")
            
            # If important news detected, trigger comprehensive impact analysis
            if breaking_analysis["should_trigger_update"]:
                affected_matches = breaking_analysis.get("affected_matches", [])
                if affected_matches:
                    logger.info(f"Breaking news detected! Adding {len(affected_matches)} matches to priority queue")
                    await add_to_priority_queue(affected_matches)
                    
                    # TODO: Store breaking news in Supabase for future reference
                    # await store_breaking_news(breaking_analysis, event_dict)
                else:
                    logger.info("Breaking news detected but no specific matches affected")
                
                # NEW: Quick Patch Generator - analyze impact on existing predictions
                logger.info(f"🚀 Triggering Quick Patch analysis for breaking news (score: {breaking_analysis.get('importance_score', 0)})")
                try:
                    quick_patch = QuickPatchGenerator()
                    patch_result = await quick_patch.process_breaking_news_impact(breaking_analysis, event_dict)
                    logger.info(f"Quick patch result: {patch_result.get('status')} - {patch_result.get('updates_triggered', 0)} updates triggered")
                except Exception as e:
                    logger.error(f"Error in quick patch processing: {e}", exc_info=True)

        # Process different event types based on source
        # For backward compatibility, check both event_type and source
        event_type = event_dict.get("event_type", "unknown")
        source = event_dict.get("source", "")
        
        if event_type == "twitter_content" or source == "twitter":
            await process_twitter_content_event(event_dict)
        elif event_type == "scraper_content" or source in ["scraper", "bbc_sport"]:
            await process_scraper_content_event(event_dict)
        else:
            logger.debug(f"Unknown event type: {event_type}, source: {source}, skipping LLM processing")

        # Small delay to avoid overwhelming downstream services
        await asyncio.sleep(0.1)

        return True
    except Exception as e:
        logger.error(f"Error processing raw event {event_id}: {e}", exc_info=True)
        return False


async def process_twitter_content_event(event_dict):
    """Process Twitter content for storage in Pinecone"""
    try:
        logger.info("Processing Twitter content for Pinecone storage")
        
        # Parse payload
        payload_str = event_dict.get("payload", "{}")
        payload = json.loads(payload_str) if payload_str else {}
        
        # Extract Twitter data in format expected by LLM Content Analyzer
        tweet_data = {
            "source": "twitter",
            "url": payload.get("author_username", "") and f"https://twitter.com/{payload.get('author_username')}/status/{payload.get('tweet_id', '')}",
            "title": f"Tweet by @{payload.get('author_username', 'unknown')}",
            "full_text": payload.get("full_text", ""),
            "article_timestamp_iso": payload.get("created_at", datetime.utcnow().isoformat()),
            # Additional metadata for reference
            "reliability_score": payload.get("reliability_score", 0.5),
            "engagement_score": payload.get("engagement_score", 0),
            "author_username": payload.get("author_username", ""),
            "author_name": payload.get("author_name", ""),
            "author_followers": payload.get("author_followers", 0),
            "author_verified": payload.get("author_verified", False),
            "hashtags": payload.get("hashtags", []),
            "mentions": payload.get("mentions", []),
            "metrics": payload.get("metrics", {}),
            "is_reply": payload.get("is_reply", False)
        }
        
        # Send to LLM Content Analyzer for processing and Pinecone storage
        await send_to_llm_content_analyzer(tweet_data)
        
        logger.info(f"Twitter content sent to LLM Content Analyzer: @{payload.get('author_username', 'unknown')}")
        
    except Exception as e:
        logger.error(f"Error processing Twitter content: {e}", exc_info=True)


async def process_scraper_content_event(event_dict):
    """Process scraper content for storage in Pinecone"""
    try:
        logger.info("Processing scraper content for Pinecone storage")
        
        # Parse payload
        payload_str = event_dict.get("payload", "{}")
        payload = json.loads(payload_str) if payload_str else {}
        
        # Extract scraper data in format expected by LLM Content Analyzer  
        scraper_data = {
            "source": payload.get("source", "scraper"),
            "url": payload.get("url", ""),
            "title": payload.get("title", ""),
            "full_text": payload.get("full_text", ""),
            "article_timestamp_iso": payload.get("published", datetime.utcnow().isoformat()),
            # Additional metadata for reference
            "reliability_score": 0.8,  # BBC Sport is generally reliable
            "category": payload.get("category", ""),
            "tags": payload.get("tags", []),
            "word_count": len(payload.get("full_text", "").split()),
            "summary": payload.get("summary", "")
        }
        
        # Send to LLM Content Analyzer for processing and Pinecone storage
        await send_to_llm_content_analyzer(scraper_data)
        
        logger.info(f"Scraper content sent to LLM Content Analyzer: {payload.get('title', 'unknown')}")
        
    except Exception as e:
        logger.error(f"Error processing scraper content: {e}", exc_info=True)


async def send_to_llm_content_analyzer(content_data):
    """Send content to LLM Content Analyzer for processing and storage"""
    try:
        # Import LLM Content Analyzer here to avoid circular imports
        from processors.llm_content_analyzer import LLMContentAnalyzer
        
        logger.debug(f"Sending content to LLM Content Analyzer: {content_data.get('document_title', 'unknown')}")
        
        # Create analyzer instance and process
        analyzer = LLMContentAnalyzer()
        
        # Generate a unique event ID
        import uuid
        event_id = str(uuid.uuid4())
        
        # Call analyzer to handle LLM analysis, chunking, embeddings, and Pinecone storage
        success = await analyzer.process_event_payload(event_id, content_data)
        
        if success:
            logger.info(f"✅ Content successfully processed by LLM Content Analyzer")
            return {"success": True, "event_id": event_id}
        else:
            logger.error(f"❌ LLM Content Analyzer failed to process content")
            return {"success": False, "error": "Processing failed"}
        
    except Exception as e:
        logger.error(f"Error sending to LLM Content Analyzer: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def consume_fixtures_queue():
    """Consume fixtures from both priority and normal queues"""
    try:
        # First, check priority queue
        logger.debug("Checking priority queue for urgent fixtures...")
        priority_result = await asyncio.to_thread(redis_client.blpop, FIXTURES_PRIORITY_QUEUE, timeout=1)
        
        if priority_result:
            _, fixture_id_bytes = priority_result
            fixture_id = fixture_id_bytes.decode("utf-8")
            logger.info(f"Got PRIORITY fixture {fixture_id} from queue '{FIXTURES_PRIORITY_QUEUE}'")
            
            # Process the priority fixture
            success = await process_fixture(fixture_id)
            
            if not success:
                logger.warning(f"Failed to process priority fixture {fixture_id}, requeuing...")
                await asyncio.to_thread(redis_client.rpush, FIXTURES_PRIORITY_QUEUE, fixture_id)
            
            return True

        # If no priority fixtures, check normal queue
        queue_length = await asyncio.to_thread(redis_client.llen, FIXTURES_QUEUE)
        logger.debug(f"Checking normal queue '{FIXTURES_QUEUE}', current length: {queue_length}")

        if queue_length == 0:
            logger.debug(f"No fixtures in '{FIXTURES_QUEUE}'. Skipping pop attempt.")
            return False

        # Get a fixture from the normal queue (blocking pop with timeout)
        result = await asyncio.to_thread(redis_client.blpop, FIXTURES_QUEUE, timeout=1)
        logger.debug(f"blpop result from '{FIXTURES_QUEUE}': {result}")

        if not result:
            logger.debug(f"'{FIXTURES_QUEUE}' blpop returned None (timeout or empty).")
            return False

        _, fixture_id_bytes = result
        fixture_id = fixture_id_bytes.decode("utf-8")

        logger.info(f"Got fixture {fixture_id} from normal queue '{FIXTURES_QUEUE}'")

        # Process the fixture
        success = await process_fixture(fixture_id)

        # If processing failed, we could requeue it
        if not success:
            logger.warning(f"Failed to process fixture {fixture_id}, requeuing to '{FIXTURES_QUEUE}'...")
            await asyncio.to_thread(redis_client.rpush, FIXTURES_QUEUE, fixture_id)

        return True
    except Exception as e:
        logger.error(f"Error consuming from fixtures queues: {e}", exc_info=True)
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
    """Main worker loop with priority handling"""
    logger.info("Worker loop started with priority queue support")
    while running:
        try:
            logger.debug("Worker loop iteration: trying to consume fixtures (priority first)...")
            fixtures_processed = await consume_fixtures_queue()
            logger.debug(f"Worker loop iteration: fixtures_processed = {fixtures_processed}")

            logger.debug("Worker loop iteration: trying to consume raw events...")
            events_processed = await consume_raw_events_stream()
            logger.debug(f"Worker loop iteration: events_processed = {events_processed}")

            # If nothing was processed, sleep a bit to avoid CPU spinning
            if not fixtures_processed and not events_processed:
                logger.debug(f"Nothing processed, sleeping for {POLLING_INTERVAL} seconds...")
                await asyncio.sleep(POLLING_INTERVAL)
            else:
                logger.debug("Something was processed, looping again immediately...")
                await asyncio.sleep(0.1) # Short sleep to yield control
        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            await asyncio.sleep(POLLING_INTERVAL)
    logger.info("Worker loop stopped because 'running' is False.")


async def main():
    """Main function"""
    logger.info("Starting worker with breaking news detection")

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
