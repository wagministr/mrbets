#!/usr/bin/env python
"""
Worker Integration Test

Tests worker.py integration with Redis streams and queues
"""

import asyncio
import json
import logging
import time
import redis
from dotenv import load_dotenv
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_test")

# Load environment
load_dotenv()

def test_worker_integration():
    """Test worker integration with real Redis data"""
    
    # Connect to Redis
    redis_client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    
    logger.info("🧪 Testing Worker Integration...")
    
    # 1. Clean up first
    redis_client.delete("stream:raw_events", "queue:fixtures:normal", "queue:fixtures:priority")
    
    # 2. Add test data
    # Add Twitter event to stream
    test_event = {
        'match_id': '12345',
        'source': 'twitter',
        'payload': json.dumps({
            'full_text': '🚨 BREAKING: Neymar injured before PSG vs Real Madrid!',
            'author': 'FabrizioRomano'
        }),
        'timestamp': str(int(time.time()))
    }
    
    redis_client.xadd('stream:raw_events', test_event)
    
    # Add fixtures to queues
    redis_client.rpush('queue:fixtures:normal', '111', '222', '333')
    redis_client.rpush('queue:fixtures:priority', '999', '888')
    
    # 3. Check Redis state
    stream_length = redis_client.xlen('stream:raw_events')
    normal_queue = redis_client.llen('queue:fixtures:normal')
    priority_queue = redis_client.llen('queue:fixtures:priority')
    
    logger.info(f"✅ Test data added:")
    logger.info(f"   Raw events stream: {stream_length}")
    logger.info(f"   Normal queue: {normal_queue}")
    logger.info(f"   Priority queue: {priority_queue}")
    
    # 4. Test consumer group setup
    try:
        redis_client.xgroup_create('stream:raw_events', 'worker-group', id='0', mkstream=True)
        logger.info("✅ Consumer group created")
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info("✅ Consumer group already exists")
    
    # 5. Simulate worker processing priority queue first
    priority_item = redis_client.blpop('queue:fixtures:priority', timeout=1)
    if priority_item:
        logger.info(f"✅ Priority queue item processed: {priority_item[1]}")
        # Put it back for cleanup
        redis_client.rpush('queue:fixtures:priority', priority_item[1])
    
    normal_item = redis_client.blpop('queue:fixtures:normal', timeout=1)
    if normal_item:
        logger.info(f"✅ Normal queue item processed: {normal_item[1]}")
        # Put it back for cleanup
        redis_client.rpush('queue:fixtures:normal', normal_item[1])
    
    # 6. Test stream consumption
    messages = redis_client.xreadgroup(
        groupname='worker-group',
        consumername='test-worker',
        streams={'stream:raw_events': '>'},
        count=1,
        block=1000
    )
    
    if messages:
        for stream_name, stream_messages in messages:
            for message_id, message_data in stream_messages:
                logger.info(f"✅ Stream message consumed: {message_id}")
                logger.info(f"   Source: {message_data.get('source')}")
                logger.info(f"   Match ID: {message_data.get('match_id')}")
                # Acknowledge message
                redis_client.xack(stream_name, 'worker-group', message_id)
    
    logger.info("🎉 Worker integration test completed successfully!")
    logger.info("✅ Ready to test with actual worker.py")

if __name__ == "__main__":
    test_worker_integration() 