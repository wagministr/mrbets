#!/usr/bin/env python
"""
Quick Patch Generator

Analyzes the impact of breaking news on existing AI predictions and triggers 
updates with automated Telegram notifications for real-time user engagement.

Key Features:
- Entity linking to match news with existing predictions
- LLM-powered impact analysis 
- Automated prediction update triggering
- FOMO-style Telegram post generation
- Value bets opportunity detection

Integration:
- Triggered by breaking_news_detector when score >= 7
- Uses existing Supabase tables (teams, players, ai_predictions)
- Works with worker.py priority queue system
- Generates content for Telegram bot publishing

Usage:
    # In worker.py when processing breaking news
    quick_patch = QuickPatchGenerator()
    await quick_patch.process_breaking_news_impact(breaking_analysis, event_data)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import openai
import redis
import spacy
from dotenv import load_dotenv
from supabase import create_client, Client

# Set up logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not found in environment variables")

openai.api_key = OPENAI_API_KEY

# Supabase configuration  
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY not found")

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Configuration
IMPACT_MODEL = os.getenv("QUICK_PATCH_MODEL", "gpt-4o-mini")
MAX_RETRIES = int(os.getenv("QUICK_PATCH_MAX_RETRIES", "3"))
IMPACT_THRESHOLD = float(os.getenv("IMPACT_THRESHOLD", "0.6"))  # Minimum impact to trigger update
PREDICTION_WINDOW_HOURS = int(os.getenv("PREDICTION_WINDOW_HOURS", "48"))  # Look for predictions within 48 hours

# Load spaCy model for NER
try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("Loaded spaCy model for entity recognition")
except OSError:
    logger.error("spaCy model 'en_core_web_sm' not found. Install with: python -m spacy download en_core_web_sm")
    nlp = None


class QuickPatchGenerator:
    """
    Analyzes breaking news impact on existing predictions and triggers updates
    """
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self.redis_client = redis.from_url(REDIS_URL)
        
    async def process_breaking_news_impact(self, breaking_analysis: Dict[str, Any], event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main workflow for processing breaking news impact on existing predictions
        
        Args:
            breaking_analysis: Result from breaking_news_detector
            event_data: Original event data (tweet, news article, etc.)
            
        Returns:
            Dictionary with impact analysis and actions taken
        """
        try:
            start_time = time.time()
            logger.info(f"🚀 Starting quick patch analysis for breaking news (importance: {breaking_analysis.get('importance_score', 0)})")
            
            # Step 1: Extract entities from breaking news
            entities = await self._extract_entities_from_news(event_data)
            if not entities["teams"] and not entities["players"]:
                logger.info("No relevant football entities found in breaking news")
                return {"status": "no_entities", "entities": entities}
            
            # Step 2: Find affected predictions
            affected_predictions = await self._find_affected_predictions(entities)
            if not affected_predictions:
                logger.info("No existing predictions found for affected entities")
                return {"status": "no_predictions", "entities": entities}
            
            logger.info(f"Found {len(affected_predictions)} potentially affected predictions")
            
            # Step 3: Analyze impact for each prediction
            impact_results = []
            for prediction in affected_predictions:
                impact_analysis = await self._analyze_prediction_impact(
                    event_data, prediction, entities
                )
                
                if impact_analysis["requires_update"]:
                    impact_results.append({
                        "prediction": prediction,
                        "impact": impact_analysis
                    })
            
            if not impact_results:
                logger.info("No predictions require updates based on impact analysis")
                return {"status": "no_impact", "analyzed_predictions": len(affected_predictions)}
            
            # Step 4: Trigger updates and notifications
            actions_taken = []
            for result in impact_results:
                action = await self._trigger_prediction_update(result["prediction"], result["impact"], event_data)
                actions_taken.append(action)
            
            duration = time.time() - start_time
            logger.info(f"✅ Quick patch analysis completed in {duration:.2f}s. Triggered {len(actions_taken)} updates.")
            
            return {
                "status": "success",
                "duration_seconds": duration,
                "entities": entities,
                "affected_predictions": len(affected_predictions),
                "updates_triggered": len(actions_taken),
                "actions": actions_taken
            }
            
        except Exception as e:
            logger.error(f"Error in quick patch processing: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def _extract_entities_from_news(self, event_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract football entities (teams, players) from news content using spaCy NER
        """
        try:
            # Extract content from event
            payload = event_data.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            content = payload.get("full_text", "") or payload.get("content", "")
            
            if not content or not nlp:
                return {"teams": [], "players": []}
            
            # Use spaCy for NER
            doc = nlp(content)
            
            # Extract potential team and player names
            entities = {"teams": [], "players": []}
            
            for ent in doc.ents:
                if ent.label_ in ["PERSON", "ORG"]:
                    # Try to match with teams
                    team_matches = await self._find_team_by_name(ent.text)
                    entities["teams"].extend(team_matches)
                    
                    # Try to match with players
                    player_matches = await self._find_player_by_name(ent.text)
                    entities["players"].extend(player_matches)
            
            # Deduplicate
            entities["teams"] = self._deduplicate_entities(entities["teams"])
            entities["players"] = self._deduplicate_entities(entities["players"])
            
            logger.info(f"Extracted entities: {len(entities['teams'])} teams, {len(entities['players'])} players")
            return entities
            
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return {"teams": [], "players": []}
    
    async def _find_team_by_name(self, team_name: str) -> List[Dict[str, Any]]:
        """Find teams matching the given name"""
        try:
            # Clean name for better matching
            cleaned_name = team_name.strip()
            
            response = await asyncio.to_thread(
                lambda: self.supabase.table("teams")
                .select("team_id, name, country")
                .ilike("name", f"%{cleaned_name}%")
                .limit(3)
                .execute()
            )
            
            return [{"team_id": row["team_id"], "name": row["name"], "country": row["country"]} 
                   for row in response.data]
            
        except Exception as e:
            logger.error(f"Error finding team '{team_name}': {e}")
            return []
    
    async def _find_player_by_name(self, player_name: str) -> List[Dict[str, Any]]:
        """Find players matching the given name"""
        try:
            # Clean name for better matching
            cleaned_name = player_name.strip()
            
            response = await asyncio.to_thread(
                lambda: self.supabase.table("players")
                .select("player_id, name, current_team_id")
                .ilike("name", f"%{cleaned_name}%")
                .limit(3)
                .execute()
            )
            
            return [{"player_id": row["player_id"], "name": row["name"], "team_id": row["current_team_id"]} 
                   for row in response.data if row["current_team_id"]]
            
        except Exception as e:
            logger.error(f"Error finding player '{player_name}': {e}")
            return []
    
    def _deduplicate_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate entities based on ID"""
        seen_ids = set()
        unique_entities = []
        
        for entity in entities:
            entity_id = entity.get("team_id") or entity.get("player_id")
            if entity_id and entity_id not in seen_ids:
                seen_ids.add(entity_id)
                unique_entities.append(entity)
        
        return unique_entities
    
    async def _find_affected_predictions(self, entities: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Find existing predictions that might be affected by the entities in the news
        """
        try:
            # Collect team IDs from entities and players' teams
            team_ids = set()
            
            # Direct team mentions
            for team in entities["teams"]:
                team_ids.add(team["team_id"])
            
            # Teams from player mentions
            for player in entities["players"]:
                if player.get("team_id"):
                    team_ids.add(player["team_id"])
            
            if not team_ids:
                return []
            
            # Find fixtures for these teams in next 48 hours
            cutoff_time = datetime.now(timezone.utc) + timedelta(hours=PREDICTION_WINDOW_HOURS)
            
            # Query fixtures for affected teams using proper syntax
            fixtures_response = await asyncio.to_thread(
                 lambda: self.supabase.table("fixtures")
                 .select("fixture_id, home_team_id, away_team_id, event_date")
                 .in_("home_team_id", list(team_ids))
                 .gt("event_date", datetime.now(timezone.utc).isoformat())
                 .lt("event_date", cutoff_time.isoformat())
                 .execute()
             )
            
            fixture_ids = [f["fixture_id"] for f in fixtures_response.data]
            
            if not fixture_ids:
                return []
            
            # Find predictions for these fixtures
            predictions_response = await asyncio.to_thread(
                lambda: self.supabase.table("ai_predictions")
                .select("id, fixture_id, type, final_prediction, confidence_score, value_bets_json, generated_at")
                .in_("fixture_id", fixture_ids)
                .eq("stale", False)
                .order("generated_at", desc=True)
                .execute()
            )
            
            # Enrich with fixture data
            predictions = []
            for pred in predictions_response.data:
                fixture_data = next((f for f in fixtures_response.data if f["fixture_id"] == pred["fixture_id"]), None)
                if fixture_data:
                    pred["fixture_data"] = fixture_data
                    predictions.append(pred)
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error finding affected predictions: {e}")
            return []
    
    async def _analyze_prediction_impact(self, event_data: Dict[str, Any], prediction: Dict[str, Any], entities: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Use LLM to analyze how breaking news affects an existing prediction
        """
        try:
            # Extract news content
            payload = event_data.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            news_content = payload.get("full_text", "") or payload.get("content", "")
            
            # Build context for LLM
            fixture = prediction["fixture_data"]
            prompt = self._build_impact_analysis_prompt(
                news_content, prediction, fixture, entities
            )
            
            # Analyze with LLM
            for attempt in range(MAX_RETRIES):
                try:
                    response = await asyncio.to_thread(
                        self.openai_client.chat.completions.create,
                        model=IMPACT_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert football analyst. Analyze how breaking news affects existing match predictions."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=0.3,
                        max_tokens=600
                    )
                    
                    content = response.choices[0].message.content
                    return self._parse_impact_analysis(content)
                    
                except Exception as e:
                    logger.warning(f"Impact analysis attempt {attempt + 1} failed: {e}")
                    if attempt == MAX_RETRIES - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)
        
        except Exception as e:
            logger.error(f"Error in impact analysis: {e}")
            return {
                "impact_level": "LOW",
                "requires_update": False,
                "confidence": 0.0,
                "reasoning": "Analysis failed"
            }
    
    def _build_impact_analysis_prompt(self, news_content: str, prediction: Dict[str, Any], fixture: Dict[str, Any], entities: Dict[str, List[Dict[str, Any]]]) -> str:
        """Build prompt for impact analysis"""
        
        return f"""
Analyze how this breaking news affects an existing football match prediction:

BREAKING NEWS:
{news_content}

EXISTING PREDICTION:
Match: Fixture ID {fixture['fixture_id']} ({fixture['event_date']})
Current Prediction: {prediction['final_prediction']}
Confidence: {prediction.get('confidence_score', 'Unknown')}

AFFECTED ENTITIES:
Teams: {[t['name'] for t in entities['teams']]}
Players: {[p['name'] for p in entities['players']]}

ANALYSIS REQUIRED:
1. How significantly does this news impact the match prediction?
2. Does the news change win probabilities or betting value?
3. Should the prediction be updated?
4. What's the key insight for bettors?

Provide a JSON response:
{{
    "impact_level": "HIGH|MEDIUM|LOW",
    "requires_update": true|false,
    "confidence": 0.0-1.0,
    "probability_change": "percentage change estimate",
    "key_insight": "concise explanation for users",
    "telegram_hook": "engaging content for Telegram post",
    "reasoning": "detailed analysis"
}}

Consider factors:
- Player importance (star players vs bench players)
- Timing (how close to match)
- Type of news (injury, suspension, transfer, etc.)
- Market impact potential
"""
    
    def _parse_impact_analysis(self, content: str) -> Dict[str, Any]:
        """Parse LLM impact analysis response"""
        try:
            # Extract JSON from response
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")
            
            json_str = content[start_idx:end_idx]
            analysis = json.loads(json_str)
            
            # Validate and set defaults
            analysis.setdefault("impact_level", "LOW")
            analysis.setdefault("requires_update", False)
            analysis.setdefault("confidence", 0.0)
            analysis.setdefault("reasoning", "No reasoning provided")
            
            # Convert confidence to float
            try:
                analysis["confidence"] = float(analysis["confidence"])
            except (ValueError, TypeError):
                analysis["confidence"] = 0.0
            
            # Determine requires_update based on impact level and confidence
            if analysis["impact_level"] in ["HIGH", "MEDIUM"] and analysis["confidence"] >= IMPACT_THRESHOLD:
                analysis["requires_update"] = True
            
            return analysis
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse impact analysis: {e}")
            return {
                "impact_level": "LOW",
                "requires_update": False,
                "confidence": 0.0,
                "reasoning": f"Parse error: {e}"
            }
    
    async def _trigger_prediction_update(self, prediction: Dict[str, Any], impact_analysis: Dict[str, Any], event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger prediction update and Telegram notification
        """
        try:
            fixture_id = prediction["fixture_id"]
            
            # Step 1: Mark existing prediction as stale
            await asyncio.to_thread(
                lambda: self.supabase.table("ai_predictions")
                .update({"stale": True})
                .eq("id", prediction["id"])
                .execute()
            )
            
            # Step 2: Add fixture to priority queue for full regeneration
            self.redis_client.rpush("queue:fixtures:priority", str(fixture_id))
            
            # Step 3: Store impact event for tracking
            impact_event = {
                "original_prediction_id": prediction["id"],
                "fixture_id": fixture_id,
                "breaking_news_content": json.dumps(event_data),
                "impact_analysis": impact_analysis,
                "telegram_post_generated": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Create prediction_impact_events table if needed and store
            # For now, store in ai_predictions as a breaking_update type
            breaking_update = {
                "fixture_id": fixture_id,
                "type": "breaking_update",
                "chain_of_thought": impact_analysis["reasoning"],
                "final_prediction": f"QUICK UPDATE: {impact_analysis.get('key_insight', 'Breaking news affects this match')}",
                "confidence_score": int(impact_analysis["confidence"] * 100),
                "model_version": f"quick_patch_{IMPACT_MODEL}",
                "value_bets_json": json.dumps([]),  # Will be updated by full analysis
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await asyncio.to_thread(
                lambda: self.supabase.table("ai_predictions")
                .insert(breaking_update)
                .execute()
            )
            
            # Step 4: Generate and queue Telegram notification
            telegram_post = await self._generate_telegram_post(
                impact_analysis, prediction, event_data
            )
            
            # Add to Telegram queue (Redis stream)
            telegram_event = {
                "type": "breaking_update",
                "fixture_id": str(fixture_id),
                "content": telegram_post,
                "priority": "high",
                "timestamp": str(int(time.time()))
            }
            
            self.redis_client.xadd("stream:telegram_posts", telegram_event)
            
            logger.info(f"✅ Triggered update for fixture {fixture_id}: prediction marked stale, added to priority queue, Telegram post queued")
            
            return {
                "fixture_id": fixture_id,
                "prediction_marked_stale": True,
                "added_to_priority_queue": True,
                "telegram_post_queued": True,
                "telegram_content": telegram_post
            }
            
        except Exception as e:
            logger.error(f"Error triggering prediction update: {e}")
            return {
                "fixture_id": prediction.get("fixture_id"),
                "error": str(e)
            }
    
    async def _generate_telegram_post(self, impact_analysis: Dict[str, Any], prediction: Dict[str, Any], event_data: Dict[str, Any]) -> str:
        """
        Generate engaging Telegram post with FOMO triggers
        """
        try:
            # Extract news summary
            payload = event_data.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            news_content = payload.get("full_text", "") or payload.get("content", "")
            
            # Get match info
            fixture = prediction["fixture_data"]
            match_date = datetime.fromisoformat(fixture["event_date"].replace('Z', '+00:00'))
            
            # Basic team info (we should enhance this with actual team names)
            home_team_id = fixture["home_team_id"]
            away_team_id = fixture["away_team_id"]
            
            # Generate post
            telegram_hook = impact_analysis.get("telegram_hook", "Важные новости влияют на прогноз!")
            key_insight = impact_analysis.get("key_insight", "Изменения в прогнозе")
            
            post = f"""🚨 СРОЧНОЕ ОБНОВЛЕНИЕ!

{telegram_hook}

💡 TLDR: {key_insight}

⚽ Матч: {match_date.strftime('%d.%m в %H:%M')}
📊 Обновляю прогноз с учетом новой информации...

🔥 Пока букмекеры не подстроили линии!
⏰ Окно возможностей быстро закрывается!

#BettingIntelligence #Breaking #ValueBets"""
            
            return post
            
        except Exception as e:
            logger.error(f"Error generating Telegram post: {e}")
            return f"🚨 Срочное обновление прогноза! Новая информация влияет на матч. Проверяйте обновления! #Breaking"


# Utility functions for integration
async def process_breaking_news_impact(breaking_analysis: Dict[str, Any], event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function for integration with worker.py
    """
    quick_patch = QuickPatchGenerator()
    return await quick_patch.process_breaking_news_impact(breaking_analysis, event_data)


# Testing function
async def test_quick_patch_generator():
    """Test function for development"""
    # Simulate breaking news
    test_event = {
        "payload": {
            "full_text": "🚨 BREAKING: Erling Haaland suffers injury in training, doubtful for Manchester City vs Arsenal clash tomorrow! #MCIARI",
            "author": "FabrizioRomano"
        }
    }
    
    test_breaking_analysis = {
        "importance_score": 9,
        "urgency_level": "BREAKING",
        "should_trigger_update": True,
        "affected_matches": [12345]
    }
    
    quick_patch = QuickPatchGenerator()
    result = await quick_patch.process_breaking_news_impact(test_breaking_analysis, test_event)
    
    print("Quick Patch Test Result:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    # Run test if executed directly
    asyncio.run(test_quick_patch_generator())