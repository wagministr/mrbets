#!/usr/bin/env python
"""
Breaking News Detector

Analyzes tweets and other content to detect breaking news that might affect match predictions.
Uses LLM to evaluate importance, urgency, and potential impact on specific matches.

Key features:
- Evaluates importance score (1-10)
- Determines urgency level (BREAKING/IMPORTANT/NORMAL)
- Identifies affected matches
- Decides whether prediction updates are needed
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import openai
from dotenv import load_dotenv

# Set up logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not found in environment variables")
    
openai.api_key = OPENAI_API_KEY

# Configuration
BREAKING_NEWS_THRESHOLD = int(os.getenv("BREAKING_NEWS_THRESHOLD", "7"))  # Minimum score to trigger update
IMPORTANCE_MODEL = os.getenv("BREAKING_NEWS_MODEL", "gpt-4o-mini")
MAX_RETRIES = int(os.getenv("BREAKING_NEWS_MAX_RETRIES", "3"))


class BreakingNewsDetector:
    """Detects and analyzes breaking news from social media content"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
    async def analyze_tweet(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a tweet for breaking news potential
        
        Args:
            event_data: Tweet data from twitter_fetcher
            
        Returns:
            Dictionary with analysis results:
            {
                "importance_score": int,      # 1-10
                "urgency_level": str,         # "BREAKING"/"IMPORTANT"/"NORMAL"
                "impact_reason": str,         # Explanation
                "should_trigger_update": bool,
                "affected_matches": List[int] # Match IDs that might be affected
            }
        """
        try:
            # Extract tweet content
            payload = event_data.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            tweet_text = payload.get("full_text", "")
            author = payload.get("author", "unknown")
            
            if not tweet_text:
                logger.warning("No tweet text found in event data")
                return self._create_default_response()
            
            # Analyze with LLM
            analysis = await self._analyze_with_llm(tweet_text, author)
            
            # Determine if update should be triggered
            should_trigger = analysis["importance_score"] >= BREAKING_NEWS_THRESHOLD
            
            result = {
                "importance_score": analysis["importance_score"],
                "urgency_level": analysis["urgency_level"],
                "impact_reason": analysis["impact_reason"],
                "should_trigger_update": should_trigger,
                "affected_matches": analysis.get("affected_matches", []),
                "analyzed_at": datetime.utcnow().isoformat(),
                "tweet_text": tweet_text[:200] + "..." if len(tweet_text) > 200 else tweet_text,
                "author": author
            }
            
            logger.info(f"Breaking news analysis: score={result['importance_score']}, "
                       f"urgency={result['urgency_level']}, trigger={should_trigger}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing tweet for breaking news: {e}", exc_info=True)
            return self._create_default_response()
    
    async def _analyze_with_llm(self, tweet_text: str, author: str) -> Dict[str, Any]:
        """Use LLM to analyze tweet importance"""
        
        prompt = self._build_analysis_prompt(tweet_text, author)
        
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=IMPORTANCE_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert football news analyst. Analyze social media posts for breaking news potential."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,
                    max_tokens=500
                )
                
                content = response.choices[0].message.content
                return self._parse_llm_response(content)
                
            except Exception as e:
                logger.warning(f"LLM analysis attempt {attempt + 1} failed: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    def _build_analysis_prompt(self, tweet_text: str, author: str) -> str:
        """Build the analysis prompt for LLM"""
        
        return f"""
Analyze this football-related social media post for breaking news potential:

AUTHOR: {author}
TEXT: {tweet_text}

Evaluate the post and provide a JSON response with these fields:

1. importance_score (1-10):
   - 1-3: Routine content (opinions, general updates)
   - 4-6: Newsworthy but not urgent (transfer rumors, tactical analysis)
   - 7-8: Important news affecting teams/players (confirmed transfers, injuries)
   - 9-10: Breaking news with immediate match impact (last-minute injuries, suspensions)

2. urgency_level: "BREAKING" (9-10), "IMPORTANT" (7-8), or "NORMAL" (1-6)

3. impact_reason: Brief explanation of why this matters

4. affected_matches: List of potential match IDs (empty if general news)

Consider these factors:
- Source credibility (Fabrizio Romano, official clubs = high; random accounts = low)
- Timing relative to upcoming matches
- Direct impact on team performance (injuries, suspensions, key player news)
- Market-moving potential (odds changes)

Return ONLY valid JSON:
{{
    "importance_score": <number>,
    "urgency_level": "<BREAKING|IMPORTANT|NORMAL>",
    "impact_reason": "<explanation>",
    "affected_matches": [<match_ids>]
}}
"""
    
    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response and validate format"""
        try:
            # Extract JSON from response
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")
            
            json_str = content[start_idx:end_idx]
            analysis = json.loads(json_str)
            
            # Validate required fields
            required_fields = ["importance_score", "urgency_level", "impact_reason"]
            for field in required_fields:
                if field not in analysis:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate score range
            score = analysis["importance_score"]
            if not isinstance(score, int) or score < 1 or score > 10:
                raise ValueError(f"Invalid importance_score: {score}")
            
            # Validate urgency level
            valid_levels = ["BREAKING", "IMPORTANT", "NORMAL"]
            if analysis["urgency_level"] not in valid_levels:
                raise ValueError(f"Invalid urgency_level: {analysis['urgency_level']}")
            
            # Ensure affected_matches is a list
            if "affected_matches" not in analysis:
                analysis["affected_matches"] = []
            elif not isinstance(analysis["affected_matches"], list):
                analysis["affected_matches"] = []
            
            return analysis
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response content: {content}")
            
            # Return fallback analysis
            return {
                "importance_score": 5,
                "urgency_level": "NORMAL",
                "impact_reason": "Failed to parse LLM analysis",
                "affected_matches": []
            }
    
    def _create_default_response(self) -> Dict[str, Any]:
        """Create default response for error cases"""
        return {
            "importance_score": 1,
            "urgency_level": "NORMAL",
            "impact_reason": "Analysis failed or no content",
            "should_trigger_update": False,
            "affected_matches": [],
            "analyzed_at": datetime.utcnow().isoformat(),
            "tweet_text": "",
            "author": "unknown"
        }
    
    async def analyze_content(self, content: str, source: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Generic content analysis (not just tweets)
        
        Args:
            content: Text content to analyze
            source: Source of content (e.g., "bbc_sport", "telegram")
            metadata: Additional context information
            
        Returns:
            Same format as analyze_tweet
        """
        try:
            if not content.strip():
                return self._create_default_response()
            
            # Create event-like structure for consistency
            event_data = {
                "payload": {
                    "full_text": content,
                    "author": source,
                    "metadata": metadata or {}
                }
            }
            
            return await self.analyze_tweet(event_data)
            
        except Exception as e:
            logger.error(f"Error analyzing content from {source}: {e}", exc_info=True)
            return self._create_default_response()


# Utility functions
async def detect_breaking_news(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function for breaking news detection"""
    detector = BreakingNewsDetector()
    return await detector.analyze_tweet(event_data)


# Example usage and testing
async def test_breaking_news_detector():
    """Test function for development"""
    detector = BreakingNewsDetector()
    
    # Test data
    test_events = [
        {
            "payload": {
                "full_text": "🚨 BREAKING: Haaland injured in training, doubtful for Manchester City vs Arsenal tomorrow! #MCIARI",
                "author": "FabrizioRomano"
            }
        },
        {
            "payload": {
                "full_text": "Nice weather today for football training",
                "author": "random_fan"
            }
        },
        {
            "payload": {
                "full_text": "🔴 CONFIRMED: Salah signs new 3-year contract with Liverpool! Here we go! ✅",
                "author": "FabrizioRomano"
            }
        }
    ]
    
    for i, event in enumerate(test_events):
        print(f"\nTest {i+1}:")
        result = await detector.analyze_tweet(event)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    # Run test if executed directly
    asyncio.run(test_breaking_news_detector()) 