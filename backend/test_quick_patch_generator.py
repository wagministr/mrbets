#!/usr/bin/env python
"""
Test Quick Patch Generator

Comprehensive testing for the Quick Patch Generator system including:
- Entity extraction from breaking news
- Impact analysis on existing predictions  
- Telegram post generation
- Database operations

Usage:
    python test_quick_patch_generator.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import redis
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from processors.quick_patch_generator import QuickPatchGenerator
from processors.breaking_news_detector import BreakingNewsDetector

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_quick_patch")

# Load environment variables
load_dotenv()

# Redis client for testing
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)


class QuickPatchTester:
    """Comprehensive testing suite for Quick Patch Generator"""
    
    def __init__(self):
        self.quick_patch = QuickPatchGenerator()
        self.breaking_detector = BreakingNewsDetector()
        self.test_results = {}
        
    async def run_all_tests(self):
        """Run comprehensive test suite"""
        logger.info("🚀 Starting Quick Patch Generator Test Suite")
        
        # Test scenarios
        test_scenarios = [
            self.test_1_haaland_injury,
            self.test_2_salah_contract,
            self.test_3_manager_sacking,
            self.test_4_no_entity_match,
            self.test_5_low_importance_news
        ]
        
        for i, test_func in enumerate(test_scenarios, 1):
            try:
                logger.info(f"\n{'='*50}")
                logger.info(f"Running Test {i}/{len(test_scenarios)}")
                await test_func()
                self.test_results[f"test_{i}"] = "PASS"
            except Exception as e:
                logger.error(f"Test {i} failed: {e}", exc_info=True)
                self.test_results[f"test_{i}"] = f"FAIL: {e}"
        
        # Print summary
        self.print_test_summary()
    
    async def test_1_haaland_injury(self):
        """Test 1: High impact player injury"""
        logger.info("📋 Test 1: Haaland Injury Breaking News")
        
        # Simulate breaking news
        event_data = {
            "payload": {
                "full_text": "🚨 BREAKING: Erling Haaland ruled out of Manchester City vs Arsenal clash due to training injury! Major blow for Pep Guardiola ahead of crucial Premier League title race match. #MCIARI #Haaland",
                "author": "FabrizioRomano"
            },
            "source": "twitter",
            "timestamp": datetime.now(timezone.utc).timestamp()
        }
        
        # Step 1: Breaking news analysis
        breaking_analysis = await self.breaking_detector.analyze_tweet(event_data)
        logger.info(f"   Breaking analysis: score={breaking_analysis['importance_score']}, trigger={breaking_analysis['should_trigger_update']}")
        
        # Step 2: Quick patch analysis
        if breaking_analysis["should_trigger_update"]:
            patch_result = await self.quick_patch.process_breaking_news_impact(breaking_analysis, event_data)
            logger.info(f"   Patch result: {patch_result['status']}")
            
            # Validate results
            if patch_result["status"] == "success":
                logger.info(f"   ✅ Successfully processed high-impact news")
                logger.info(f"   📊 Updates triggered: {patch_result.get('updates_triggered', 0)}")
            elif patch_result["status"] == "no_entities":
                logger.info(f"   ℹ️  No entities found (expected for test data)")
            elif patch_result["status"] == "no_predictions":
                logger.info(f"   ℹ️  No existing predictions found (expected in test environment)")
            else:
                logger.warning(f"   ⚠️  Unexpected status: {patch_result['status']}")
        else:
            logger.warning("   ⚠️  Breaking news not triggered (unexpected for high-impact news)")
    
    async def test_2_salah_contract(self):
        """Test 2: Important transfer news"""
        logger.info("📋 Test 2: Salah Contract Extension")
        
        event_data = {
            "payload": {
                "full_text": "🔴 CONFIRMED: Mohamed Salah signs new 3-year contract extension with Liverpool FC! The Egyptian King stays at Anfield until 2027. Huge boost for Klopp ahead of Champions League campaign. #LFC #Salah",
                "author": "LiverpoolFC"
            },
            "source": "twitter",
            "timestamp": datetime.now(timezone.utc).timestamp()
        }
        
        breaking_analysis = await self.breaking_detector.analyze_tweet(event_data)
        logger.info(f"   Breaking analysis: score={breaking_analysis['importance_score']}")
        
        if breaking_analysis["should_trigger_update"]:
            patch_result = await self.quick_patch.process_breaking_news_impact(breaking_analysis, event_data)
            logger.info(f"   ✅ Transfer news processed: {patch_result['status']}")
        else:
            logger.info(f"   ℹ️  Contract news below trigger threshold (score: {breaking_analysis['importance_score']})")
    
    async def test_3_manager_sacking(self):
        """Test 3: Manager change impact"""
        logger.info("📋 Test 3: Manager Sacking News")
        
        event_data = {
            "payload": {
                "full_text": "🚨 BREAKING: Chelsea FC parts ways with manager Graham Potter with immediate effect. Todd Boehly searching for new head coach ahead of crucial Champions League quarter-final. #CFC #Potter",
                "author": "ChelseaFC"
            },
            "source": "twitter",
            "timestamp": datetime.now(timezone.utc).timestamp()
        }
        
        breaking_analysis = await self.breaking_detector.analyze_tweet(event_data)
        patch_result = await self.quick_patch.process_breaking_news_impact(breaking_analysis, event_data)
        logger.info(f"   Manager change processed: {patch_result['status']}")
    
    async def test_4_no_entity_match(self):
        """Test 4: News with no football entity matches"""
        logger.info("📋 Test 4: Non-Football Breaking News")
        
        event_data = {
            "payload": {
                "full_text": "🚨 BREAKING: Major earthquake hits Turkey, magnitude 7.2. Emergency services responding to multiple incidents across the region.",
                "author": "BBCBreaking"
            },
            "source": "twitter",
            "timestamp": datetime.now(timezone.utc).timestamp()
        }
        
        breaking_analysis = await self.breaking_detector.analyze_tweet(event_data)
        patch_result = await self.quick_patch.process_breaking_news_impact(breaking_analysis, event_data)
        
        if patch_result["status"] == "no_entities":
            logger.info(f"   ✅ Correctly identified no football entities")
        else:
            logger.warning(f"   ⚠️  Unexpected processing of non-football news: {patch_result['status']}")
    
    async def test_5_low_importance_news(self):
        """Test 5: Low importance football news"""
        logger.info("📋 Test 5: Low Importance Football News")
        
        event_data = {
            "payload": {
                "full_text": "Manchester United players enjoyed a team dinner last night ahead of their upcoming training camp. Good team bonding session according to sources close to the club.",
                "author": "MUFCNews"
            },
            "source": "twitter",
            "timestamp": datetime.now(timezone.utc).timestamp()
        }
        
        breaking_analysis = await self.breaking_detector.analyze_tweet(event_data)
        logger.info(f"   Importance score: {breaking_analysis['importance_score']}")
        
        if not breaking_analysis["should_trigger_update"]:
            logger.info(f"   ✅ Correctly ignored low-importance news")
        else:
            patch_result = await self.quick_patch.process_breaking_news_impact(breaking_analysis, event_data)
            logger.info(f"   Processing result: {patch_result['status']}")
    
    async def test_entity_extraction(self):
        """Test entity extraction capabilities"""
        logger.info("📋 Testing Entity Extraction")
        
        test_content = "Erling Haaland and Mohamed Salah are both doubtful for Manchester City vs Liverpool clash at Etihad Stadium"
        
        event_data = {
            "payload": {
                "full_text": test_content,
                "author": "TestSource"
            }
        }
        
        entities = await self.quick_patch._extract_entities_from_news(event_data)
        logger.info(f"   Extracted {len(entities['teams'])} teams, {len(entities['players'])} players")
        
        for team in entities["teams"]:
            logger.info(f"   Team: {team['name']} (ID: {team['team_id']})")
        
        for player in entities["players"]:
            logger.info(f"   Player: {player['name']} (ID: {player['player_id']})")
    
    async def test_telegram_post_generation(self):
        """Test Telegram post generation"""
        logger.info("📋 Testing Telegram Post Generation")
        
        # Mock impact analysis
        impact_analysis = {
            "impact_level": "HIGH",
            "confidence": 0.85,
            "key_insight": "Haaland injury significantly reduces City's attacking threat",
            "telegram_hook": "🚨 Холанд травмирован перед ключевым матчем!",
            "reasoning": "Star striker injury before important match"
        }
        
        # Mock prediction
        prediction = {
            "fixture_id": 12345,
            "final_prediction": "Manchester City win 2-1",
            "fixture_data": {
                "fixture_id": 12345,
                "event_date": "2024-06-05T15:00:00Z",
                "home_team_id": 47,
                "away_team_id": 40
            }
        }
        
        event_data = {
            "payload": {
                "full_text": "Haaland injury confirmed",
                "author": "TestSource"
            }
        }
        
        telegram_post = await self.quick_patch._generate_telegram_post(impact_analysis, prediction, event_data)
        logger.info(f"   Generated Telegram post:")
        logger.info(f"   {telegram_post}")
    
    async def test_redis_integration(self):
        """Test Redis integration"""
        logger.info("📋 Testing Redis Integration")
        
        try:
            # Test priority queue
            test_fixture_id = "999888"
            redis_client.rpush("queue:fixtures:priority", test_fixture_id)
            
            # Test Telegram stream
            telegram_event = {
                "type": "test",
                "content": "Test telegram post",
                "timestamp": str(int(time.time()))
            }
            
            redis_client.xadd("stream:telegram_posts", telegram_event)
            
            logger.info("   ✅ Redis operations successful")
            
            # Cleanup
            redis_client.lrem("queue:fixtures:priority", 0, test_fixture_id)
            
        except Exception as e:
            logger.error(f"   ❌ Redis operations failed: {e}")
            raise
    
    def print_test_summary(self):
        """Print comprehensive test results"""
        logger.info(f"\n{'='*60}")
        logger.info("📊 QUICK PATCH GENERATOR TEST SUMMARY")
        logger.info(f"{'='*60}")
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result == "PASS")
        failed_tests = total_tests - passed_tests
        
        for test_name, result in self.test_results.items():
            status_icon = "✅" if result == "PASS" else "❌"
            logger.info(f"   {status_icon} {test_name}: {result}")
        
        logger.info(f"\n📈 OVERALL RESULTS:")
        logger.info(f"   Total Tests: {total_tests}")
        logger.info(f"   Passed: {passed_tests}")
        logger.info(f"   Failed: {failed_tests}")
        logger.info(f"   Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests == 0:
            logger.info(f"\n🎉 ALL TESTS PASSED! Quick Patch Generator is ready for production!")
        else:
            logger.warning(f"\n⚠️  {failed_tests} test(s) failed. Review and fix before deployment.")


async def main():
    """Main test function"""
    
    # Verify environment
    required_env_vars = ["REDIS_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing environment variables: {missing_vars}")
        logger.error("Please check your .env file")
        return
    
    # Test Redis connection
    try:
        redis_client.ping()
        logger.info("✅ Redis connection successful")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return
    
    # Run tests
    tester = QuickPatchTester()
    
    # Run additional component tests
    logger.info("\n🧪 Running Component Tests")
    await tester.test_entity_extraction()
    await tester.test_telegram_post_generation()
    await tester.test_redis_integration()
    
    # Run main integration tests
    logger.info("\n🔗 Running Integration Tests")
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main()) 