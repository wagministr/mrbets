#!/usr/bin/env python
"""
Simple test for Breaking News Detector
"""

import asyncio
import json
from processors.breaking_news_detector import BreakingNewsDetector

async def test_breaking_news_detector():
    """Test breaking news detection functionality"""
    print("🧪 Testing Breaking News Detector...")
    
    detector = BreakingNewsDetector()
    
    # Test cases
    test_cases = [
        {
            "name": "High importance breaking news",
            "event": {
                "payload": {
                    "full_text": "🚨 BREAKING: Haaland injured in training, doubtful for Manchester City vs Arsenal tomorrow! #MCIARI",
                    "author": "FabrizioRomano"
                }
            },
            "expected_trigger": True
        },
        {
            "name": "Normal content",
            "event": {
                "payload": {
                    "full_text": "Nice weather today for football training",
                    "author": "random_fan"
                }
            },
            "expected_trigger": False
        },
        {
            "name": "Important transfer news",
            "event": {
                "payload": {
                    "full_text": "🔴 CONFIRMED: Salah signs new 3-year contract with Liverpool! Here we go! ✅",
                    "author": "FabrizioRomano"
                }
            },
            "expected_trigger": True  # Should be above threshold
        }
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\n📋 Test {i+1}: {case['name']}")
        try:
            result = await detector.analyze_tweet(case["event"])
            
            print(f"   Score: {result['importance_score']}/10")
            print(f"   Urgency: {result['urgency_level']}")
            print(f"   Trigger: {result['should_trigger_update']}")
            print(f"   Reason: {result['impact_reason']}")
            
            # Check if result matches expectation
            if result["should_trigger_update"] == case["expected_trigger"]:
                print("   ✅ Expected result!")
            else:
                print(f"   ⚠️  Expected trigger={case['expected_trigger']}, got {result['should_trigger_update']}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n🎯 Breaking News Detector test completed!")

if __name__ == "__main__":
    asyncio.run(test_breaking_news_detector()) 