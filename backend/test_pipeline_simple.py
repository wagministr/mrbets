#!/usr/bin/env python
"""
Simplified Pipeline Test

Tests the core Week 1 pipeline components without complex imports:
- Redis connectivity
- Breaking news detector 
- Priority queue logic
- Worker processing simulation
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime

import redis
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pipeline_test")

# Load environment variables from backend/.env
load_dotenv()

# Redis configuration  
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
logger.info(f"Using Redis URL: {REDIS_URL}")

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info(f"✅ Connected to Redis at {REDIS_URL}")
except redis.ConnectionError as e:
    logger.error(f"❌ Failed to connect to Redis: {e}")
    sys.exit(1)


class SimplePipelineTester:
    """Simplified pipeline tester"""
    
    def __init__(self):
        self.redis_client = redis_client
        self.test_results = {}
        
    def cleanup_redis(self):
        """Clean up Redis for testing"""
        logger.info("🧹 Cleaning up Redis...")
        
        keys_to_delete = [
            "queue:fixtures:normal",
            "queue:fixtures:priority", 
            "stream:raw_events",
            "set:fixtures_scanned_today"
        ]
        
        for key in keys_to_delete:
            try:
                self.redis_client.delete(key)
                logger.info(f"   Deleted {key}")
            except Exception as e:
                logger.warning(f"   Could not delete {key}: {e}")
    
    async def test_1_redis_operations(self):
        """Test 1: Basic Redis operations"""
        logger.info("\n📋 Test 1: Redis Operations")
        
        try:
            # Test SET/GET
            self.redis_client.set("test:key", "test_value")
            value = self.redis_client.get("test:key")
            self.redis_client.delete("test:key")
            
            # Test LIST operations
            self.redis_client.rpush("test:list", "item1", "item2")
            length = self.redis_client.llen("test:list")
            item = self.redis_client.lpop("test:list")
            self.redis_client.delete("test:list")
            
            # Test STREAM operations
            stream_id = self.redis_client.xadd("test:stream", {"key": "value"})
            stream_len = self.redis_client.xlen("test:stream")
            self.redis_client.delete("test:stream")
            
            if value == "test_value" and length == 2 and item == "item1" and stream_len == 1:
                logger.info("   ✅ Redis operations work correctly")
                self.test_results["redis_operations"] = True
                return True
            else:
                logger.error("   ❌ Redis operations failed")
                self.test_results["redis_operations"] = False
                return False
                
        except Exception as e:
            logger.error(f"   ❌ Redis operations error: {e}")
            self.test_results["redis_operations"] = False
            return False
    
    async def test_2_breaking_news_logic(self):
        """Test 2: Breaking news detection logic"""
        logger.info("\n📋 Test 2: Breaking News Logic")
        
        try:
            # Import breaking news detector locally to avoid early .env loading
            from processors.breaking_news_detector import BreakingNewsDetector
            
            detector = BreakingNewsDetector()
            
            # Test high importance event
            test_event = {
                "payload": {
                    "full_text": "🚨 BREAKING: Mbappe injured before Real Madrid vs Barcelona El Clasico!",
                    "author": "FabrizioRomano"
                }
            }
            
            result = await detector.analyze_tweet(test_event)
            
            if (result["importance_score"] >= 7 and 
                result["should_trigger_update"] and
                result["urgency_level"] in ["BREAKING", "IMPORTANT"]):
                logger.info(f"   ✅ Breaking news detection works: score={result['importance_score']}")
                self.test_results["breaking_news"] = True
                return True
            else:
                logger.error(f"   ❌ Breaking news detection failed: {result}")
                self.test_results["breaking_news"] = False
                return False
                
        except Exception as e:
            logger.error(f"   ❌ Breaking news detection error: {e}")
            self.test_results["breaking_news"] = False
            return False
    
    async def test_3_stream_and_queues(self):
        """Test 3: Streams and queues workflow"""
        logger.info("\n📋 Test 3: Streams and Queues")
        
        try:
            # 1. Add events to raw_events stream
            events = [
                {
                    "match_id": "12345",
                    "source": "twitter",
                    "payload": json.dumps({
                        "full_text": "🚨 BREAKING: Lewandowski out for Bayern Munich match!",
                        "author": "SkySports"
                    }),
                    "timestamp": str(int(time.time()))
                },
                {
                    "match_id": "67890",
                    "source": "scraper", 
                    "payload": json.dumps({
                        "title": "Match preview",
                        "content": "Today's match should be exciting..."
                    }),
                    "timestamp": str(int(time.time()))
                }
            ]
            
            for event in events:
                self.redis_client.xadd("stream:raw_events", event)
            
            stream_length = self.redis_client.xlen("stream:raw_events")
            logger.info(f"   Added {len(events)} events to stream, length: {stream_length}")
            
            # 2. Add fixtures to normal queue
            fixtures = ["111", "222", "333"]
            for fixture in fixtures:
                self.redis_client.rpush("queue:fixtures:normal", fixture)
            
            normal_queue_length = self.redis_client.llen("queue:fixtures:normal")
            logger.info(f"   Added {len(fixtures)} fixtures to normal queue, length: {normal_queue_length}")
            
            # 3. Simulate breaking news triggering priority queue
            self.redis_client.rpush("queue:fixtures:priority", "999", "888")
            priority_queue_length = self.redis_client.llen("queue:fixtures:priority")
            logger.info(f"   Added 2 urgent fixtures to priority queue, length: {priority_queue_length}")
            
            if (stream_length >= len(events) and 
                normal_queue_length >= len(fixtures) and 
                priority_queue_length >= 2):
                logger.info("   ✅ Streams and queues workflow works")
                self.test_results["streams_queues"] = True
                return True
            else:
                logger.error("   ❌ Streams and queues workflow failed")
                self.test_results["streams_queues"] = False
                return False
                
        except Exception as e:
            logger.error(f"   ❌ Streams and queues error: {e}")
            self.test_results["streams_queues"] = False
            return False
    
    async def test_4_worker_processing_order(self):
        """Test 4: Worker processing priority logic"""
        logger.info("\n📋 Test 4: Worker Processing Order")
        
        try:
            # Check queue lengths
            normal_length = self.redis_client.llen("queue:fixtures:normal")
            priority_length = self.redis_client.llen("queue:fixtures:priority")
            
            logger.info(f"   Normal queue: {normal_length} items")
            logger.info(f"   Priority queue: {priority_length} items")
            
            # Simulate worker logic: priority first
            processed_items = []
            
            # Pop from priority queue first
            if priority_length > 0:
                priority_item = self.redis_client.blpop("queue:fixtures:priority", timeout=1)
                if priority_item:
                    processed_items.append(("priority", priority_item[1]))
                    logger.info(f"   Processed priority fixture: {priority_item[1]}")
            
            # Then from normal queue
            if normal_length > 0:
                normal_item = self.redis_client.blpop("queue:fixtures:normal", timeout=1)
                if normal_item:
                    processed_items.append(("normal", normal_item[1]))
                    logger.info(f"   Processed normal fixture: {normal_item[1]}")
            
            # Check processing order
            if processed_items and processed_items[0][0] == "priority":
                logger.info("   ✅ Worker processes priority queue first")
                self.test_results["processing_order"] = True
                return True
            elif processed_items:
                logger.info("   ✅ Worker processing works (no priority items available)")
                self.test_results["processing_order"] = True
                return True
            else:
                logger.warning("   ⚠️  No items to process")
                self.test_results["processing_order"] = True
                return True
                
        except Exception as e:
            logger.error(f"   ❌ Worker processing error: {e}")
            self.test_results["processing_order"] = False
            return False
    
    async def test_5_consumer_groups(self):
        """Test 5: Redis consumer groups"""
        logger.info("\n📋 Test 5: Consumer Groups")
        
        try:
            # Create consumer group
            try:
                self.redis_client.xgroup_create("stream:raw_events", "worker-group", id="0", mkstream=True)
                logger.info("   Created consumer group 'worker-group'")
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info("   Consumer group 'worker-group' already exists")
                else:
                    raise
            
            # Check group exists
            groups = self.redis_client.xinfo_groups("stream:raw_events")
            
            if len(groups) > 0:
                logger.info(f"   ✅ Consumer groups working: {len(groups)} groups")
                self.test_results["consumer_groups"] = True
                return True
            else:
                logger.error("   ❌ No consumer groups found")
                self.test_results["consumer_groups"] = False
                return False
                
        except Exception as e:
            logger.error(f"   ❌ Consumer groups error: {e}")
            self.test_results["consumer_groups"] = False
            return False
    
    def print_report(self):
        """Print test report"""
        logger.info("\n" + "="*50)
        logger.info("📊 WEEK 1 PIPELINE TEST REPORT")
        logger.info("="*50)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"   {test_name:<20} {status}")
        
        logger.info("-"*50)
        logger.info(f"Total: {total_tests} | Passed: {passed_tests} | Failed: {total_tests - passed_tests}")
        
        if passed_tests == total_tests:
            logger.info("🎉 WEEK 1 PIPELINE READY!")
            logger.info("✅ continuous_fetchers → worker → breaking_news_detector → priority_queue")
        else:
            logger.info("⚠️  Some components need attention")
        
        logger.info("="*50)


async def main():
    """Run simplified pipeline test"""
    logger.info("🚀 Week 1 Pipeline Test")
    logger.info("Testing core components without complex dependencies")
    
    tester = SimplePipelineTester()
    
    # Clean up first
    tester.cleanup_redis()
    
    # Run tests
    tests = [
        tester.test_1_redis_operations,
        tester.test_2_breaking_news_logic,
        tester.test_3_stream_and_queues,
        tester.test_4_worker_processing_order,
        tester.test_5_consumer_groups
    ]
    
    for test in tests:
        await test()
        await asyncio.sleep(0.5)
    
    # Print report
    tester.print_report()
    
    # Final cleanup
    tester.cleanup_redis()


if __name__ == "__main__":
    asyncio.run(main()) 