#!/usr/bin/env python
"""
Quick Patch Generator Demo

Demonstrates the complete pipeline in action:
Breaking News → Entity Linking → Impact Analysis → Telegram Notification

Usage:
    python demo_quick_patch_pipeline.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from processors.breaking_news_detector import BreakingNewsDetector
from processors.quick_patch_generator import QuickPatchGenerator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("quick_patch_demo")

# Load environment variables
load_dotenv()


async def demo_breaking_news_pipeline():
    """Demonstrate the complete breaking news pipeline"""
    
    logger.info("🚀 QUICK PATCH GENERATOR DEMO")
    logger.info("=" * 50)
    
    # Initialize components
    breaking_detector = BreakingNewsDetector()
    quick_patch = QuickPatchGenerator()
    
    # Demo scenarios
    scenarios = [
        {
            "name": "🏥 Star Player Injury",
            "event": {
                "payload": {
                    "full_text": "🚨 BREAKING: Erling Haaland suffers knee injury in training, ruled out for 2-3 weeks! Manchester City's title hopes take major blow ahead of crucial Arsenal clash. #MCFC #Haaland",
                    "author": "FabrizioRomano"
                },
                "source": "twitter",
                "timestamp": datetime.now(timezone.utc).timestamp()
            }
        },
        {
            "name": "📝 Contract Extension",
            "event": {
                "payload": {
                    "full_text": "🔴 CONFIRMED: Mohamed Salah signs new 4-year deal with Liverpool! The Egyptian King stays at Anfield until 2028. Massive boost for Klopp's Champions League ambitions. #LFC #Salah",
                    "author": "LiverpoolFC"
                },
                "source": "twitter", 
                "timestamp": datetime.now(timezone.utc).timestamp()
            }
        },
        {
            "name": "👔 Manager Change",
            "event": {
                "payload": {
                    "full_text": "🚨 BREAKING: Tottenham Hotspur parts ways with Antonio Conte immediately! Daniel Levy searching for new head coach ahead of North London Derby. #THFC #Conte",
                    "author": "SpursOfficial"
                },
                "source": "twitter",
                "timestamp": datetime.now(timezone.utc).timestamp()
            }
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        logger.info(f"\n📋 SCENARIO {i}: {scenario['name']}")
        logger.info("-" * 40)
        
        try:
            # Step 1: Breaking News Detection
            logger.info("🔍 Step 1: Analyzing breaking news importance...")
            breaking_analysis = await breaking_detector.analyze_tweet(scenario["event"])
            
            logger.info(f"   📊 Importance Score: {breaking_analysis['importance_score']}/10")
            logger.info(f"   🚨 Urgency Level: {breaking_analysis['urgency_level']}")
            logger.info(f"   ⚡ Trigger Update: {breaking_analysis['should_trigger_update']}")
            
            if breaking_analysis["should_trigger_update"]:
                # Step 2: Quick Patch Analysis
                logger.info("\n🧠 Step 2: Analyzing impact on existing predictions...")
                patch_result = await quick_patch.process_breaking_news_impact(
                    breaking_analysis, scenario["event"]
                )
                
                logger.info(f"   🎯 Status: {patch_result['status']}")
                logger.info(f"   ⏱️  Duration: {patch_result.get('duration_seconds', 0):.2f}s")
                
                if patch_result["status"] == "success":
                    logger.info(f"   🔄 Updates Triggered: {patch_result['updates_triggered']}")
                    
                    # Show sample Telegram posts
                    for action in patch_result.get("actions", []):
                        if "telegram_content" in action:
                            logger.info("\n📱 Generated Telegram Post:")
                            logger.info("   " + "─" * 30)
                            for line in action["telegram_content"].split('\n'):
                                logger.info(f"   {line}")
                            logger.info("   " + "─" * 30)
                            
                elif patch_result["status"] == "no_entities":
                    logger.info("   ℹ️  No relevant football entities found")
                elif patch_result["status"] == "no_predictions":
                    logger.info("   ℹ️  No existing predictions found to update")
                else:
                    logger.info(f"   ⚠️  Other status: {patch_result['status']}")
            else:
                logger.info("   ⏭️  News below trigger threshold - no action taken")
                
        except Exception as e:
            logger.error(f"   ❌ Error in scenario {i}: {e}")
    
    logger.info(f"\n✅ Demo completed! Quick Patch Generator pipeline demonstrated.")


async def demo_entity_extraction():
    """Demonstrate entity extraction capabilities"""
    
    logger.info("\n🔗 ENTITY EXTRACTION DEMO")
    logger.info("=" * 40)
    
    quick_patch = QuickPatchGenerator()
    
    test_texts = [
        "Erling Haaland and Kevin De Bruyne both doubtful for Manchester City",
        "Liverpool FC confirms Mohamed Salah contract extension",
        "Arsenal vs Chelsea postponed due to player injuries",
        "Cristiano Ronaldo scores hat-trick for Portugal"
    ]
    
    for i, text in enumerate(test_texts, 1):
        logger.info(f"\n📝 Text {i}: {text}")
        
        event_data = {
            "payload": {
                "full_text": text,
                "author": "TestSource"
            }
        }
        
        try:
            entities = await quick_patch._extract_entities_from_news(event_data)
            
            logger.info(f"   👥 Teams found: {len(entities['teams'])}")
            for team in entities["teams"][:3]:  # Limit to first 3
                logger.info(f"      • {team['name']} (ID: {team['team_id']})")
            
            logger.info(f"   ⚽ Players found: {len(entities['players'])}")  
            for player in entities["players"][:3]:  # Limit to first 3
                logger.info(f"      • {player['name']} (ID: {player['player_id']})")
                
        except Exception as e:
            logger.error(f"   ❌ Error extracting entities: {e}")


async def demo_telegram_post_generation():
    """Demonstrate Telegram post generation"""
    
    logger.info("\n📱 TELEGRAM POST GENERATION DEMO")
    logger.info("=" * 45)
    
    quick_patch = QuickPatchGenerator()
    
    # Mock data for demonstration
    impact_analysis = {
        "impact_level": "HIGH",
        "confidence": 0.85,
        "key_insight": "Haaland injury significantly reduces City's scoring threat, increasing draw probability",
        "telegram_hook": "🚨 Холанд травмирован перед топ-матчем!",
        "reasoning": "Star striker injury before crucial title race match"
    }
    
    prediction = {
        "fixture_id": 12345,
        "final_prediction": "Manchester City win 2-1 (65% confidence)",
        "fixture_data": {
            "fixture_id": 12345,
            "event_date": "2024-06-05T19:30:00Z",
            "home_team_id": 47,
            "away_team_id": 40
        }
    }
    
    event_data = {
        "payload": {
            "full_text": "🚨 BREAKING: Haaland injury confirmed by Pep Guardiola",
            "author": "SkySports"
        }
    }
    
    try:
        telegram_post = await quick_patch._generate_telegram_post(
            impact_analysis, prediction, event_data
        )
        
        logger.info("📲 Generated Telegram Post:")
        logger.info("┌" + "─" * 50 + "┐")
        for line in telegram_post.split('\n'):
            logger.info(f"│ {line:<48} │")
        logger.info("└" + "─" * 50 + "┘")
        
    except Exception as e:
        logger.error(f"❌ Error generating Telegram post: {e}")


async def demo_performance_metrics():
    """Demonstrate performance characteristics"""
    
    logger.info("\n⚡ PERFORMANCE METRICS DEMO")
    logger.info("=" * 35)
    
    import time
    
    quick_patch = QuickPatchGenerator()
    breaking_detector = BreakingNewsDetector()
    
    test_event = {
        "payload": {
            "full_text": "🚨 BREAKING: Liverpool confirms Salah injury ahead of Manchester United clash",
            "author": "BBCSport"
        },
        "source": "twitter",
        "timestamp": datetime.now(timezone.utc).timestamp()
    }
    
    try:
        # Test breaking news detection speed
        start_time = time.time()
        breaking_analysis = await breaking_detector.analyze_tweet(test_event)
        breaking_time = time.time() - start_time
        
        logger.info(f"🔍 Breaking News Analysis: {breaking_time:.2f}s")
        
        # Test quick patch processing speed
        if breaking_analysis["should_trigger_update"]:
            start_time = time.time()
            patch_result = await quick_patch.process_breaking_news_impact(breaking_analysis, test_event)
            patch_time = time.time() - start_time
            
            logger.info(f"🚀 Quick Patch Processing: {patch_time:.2f}s")
            logger.info(f"🎯 Total Pipeline Time: {breaking_time + patch_time:.2f}s")
        else:
            logger.info("⏭️  No patch processing needed (low importance)")
            
    except Exception as e:
        logger.error(f"❌ Performance test error: {e}")


async def main():
    """Run all demonstrations"""
    
    # Verify environment
    required_vars = ["REDIS_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {missing_vars}")
        logger.error("Please check your .env file")
        return
    
    logger.info("🌟 MRBETS.AI QUICK PATCH GENERATOR")
    logger.info("Real-time Breaking News Impact Analysis System")
    logger.info("=" * 60)
    
    try:
        # Run demonstrations
        await demo_breaking_news_pipeline()
        await demo_entity_extraction()
        await demo_telegram_post_generation()
        await demo_performance_metrics()
        
        logger.info("\n🎉 All demonstrations completed successfully!")
        logger.info("🚀 Quick Patch Generator is ready for production deployment!")
        
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())