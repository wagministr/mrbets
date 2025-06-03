"""
llm_reasoner.py  

Генерирует прогнозы на основе контекста от Retriever и актуальных коэффициентов.
Использует мощную LLM для создания детального анализа и поиска value bets.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional, List, Any

from openai import AsyncOpenAI, RateLimitError, APIError, APITimeoutError
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

logger = logging.getLogger(__name__)

# Константы
OPENAI_MODEL = "gpt-4-1106-preview"  # Или "gpt-4o" если доступен
OPENAI_REQUEST_TIMEOUT = 120
OPENAI_MAX_RETRIES = 3
OPENAI_RETRY_DELAY = 5

# Экспертный FOMO-промпт для профессионального анализа
EXPERT_FOMO_PROMPT_TEMPLATE = """
**INSTITUTIONAL-GRADE MATCH ANALYSIS PROTOCOL**

**FIXTURE PARAMETERS:**
Primary: {home_team} (ID: {home_team_id}) vs {away_team} (ID: {away_team_id})
Temporal: {match_date} | Venue Classification: Home Advantage Index
Competition: {league} | Market Status: {status}

**LIVE MARKET MATRIX:**
{odds_data}

**PROPRIETARY INTELLIGENCE DATABASE (T-{days_back} temporal window, {total_chunks} data vectors):**
{context_summary}

**ADVANCED ANALYTICAL MODULES:**
{structured_content}

**ALGORITHMIC MISSION PARAMETERS:**

You are a quantitative sports analyst with institutional-level access to proprietary data streams and advanced statistical models. Your analysis framework operates on multiple concurrent analytical layers that most market participants cannot access.

**TECHNICAL ANALYSIS FRAMEWORK:**

1. **PERFORMANCE COEFFICIENT ANALYSIS:**
   - Recent form vector analysis (momentum indicators, goal differential trends)
   - xG variance modeling and regression-to-mean probability
   - Shot efficiency matrices and defensive solidity coefficients
   - Set-piece conversion rates and tactical vulnerability indices

2. **SQUAD AVAILABILITY OPTIMIZATION MATRIX:**
   - Player availability impact modeling (key player replacement efficiency)
   - Injury severity algorithms and return probability calculations  
   - Suspension cascade effects on tactical formation probability
   - Rotation fatigue indices and fixture congestion multipliers

3. **TACTICAL META-ANALYSIS FRAMEWORK:**
   - Historical formation tendency algorithms vs counter-tactical probability
   - H2H tactical pattern recognition and exploitation coefficients
   - Style compatibility indices and systemic weakness detection
   - Manager tactical flexibility ratings and adaptation probability

4. **CONTEXTUAL MOTIVATION COEFFICIENTS:**
   - Tournament positioning impact algorithms (pressure/release indices)
   - Fixture importance weighting and performance correlation analysis
   - Venue-specific performance variance and psychological advantage metrics
   - External pressure variables and squad cohesion indicators

5. **MARKET INEFFICIENCY DETECTION ALGORITHMS:**
   - Probability differential analysis between institutional models and market pricing
   - Sharp money flow correlation tracking and institutional positioning indicators
   - Retail sentiment divergence indices and contrarian opportunity identification
   - Temporal market adjustment lag analysis and exploitation windows

**PROFESSIONAL TERMINOLOGY USAGE:**
- Reference "variance analysis", "coefficient correlation", "algorithmic projections"
- Utilize "institutional flow patterns", "market maker positioning", "quantitative frameworks"
- Apply "systematic edge detection", "probability gap analysis", "temporal arbitrage opportunities"
- Implement "advanced metrics consensus", "proprietary modeling indicators", "institutional-grade analytics"

**URGENCY INDICATORS:**
- "Market pricing inefficiency detected in real-time analytics"
- "Algorithmic consensus suggests limited temporal window"
- "Institutional positioning implies market adjustment imminent"
- "Quantitative edge identified before market calibration"
- "Advanced metrics show systematic underpricing by market makers"

**JSON OUTPUT SPECIFICATION:**
{{
  "chain_of_thought": "Advanced quantitative analysis reveals [specific statistical edge]. Our proprietary xG-adjusted performance model identifies significant market pricing inefficiency of [X]% relative to true probability assessment. Historical H2H tactical meta-analysis indicates systematic [advantage/pattern] under current parametric conditions. Squad availability optimization matrix confirms [key factor] creating [X]% tactical setup variance not reflected in current market positioning. Institutional money flow indicators show [pattern] while retail sentiment remains inversely positioned. Multi-factor regression analysis incorporating venue coefficients, motivation indices, and tactical compatibility scores projects [statistical outcome] with [confidence interval]. Market maker adjustment algorithms typically recalibrate within [timeframe] following similar analytical signal releases. Current probability differential represents [X]% edge above market efficiency threshold.",
  
  "final_prediction": "Quantitative model consensus indicates [specific outcome] with statistical significance. Advanced metrics framework identifies systematic market underpricing requiring immediate exploitation before algorithmic adjustment mechanisms activate.",
  
  "confidence_score": 87,
  
  "value_bets": [
    {{
      "market": "Match Result - Home Win",
      "recommended_probability": 0.58,
      "bookmaker_odds": 2.10,
      "implied_probability": 0.476,
      "confidence": 89,
      "stake_percentage": 4,
      "reasoning": "Proprietary venue-adjusted performance algorithm detects 10.4% systematic market underpricing. Multi-factor tactical compatibility analysis confirms exploitable systematic weakness. Institutional correlation tracking validates positioning alignment."
    }}
  ],
  
  "risk_factors": [
    "Squad rotation probability elevated due to fixture congestion coefficient analysis",
    "Market maker recalibration window estimated at T+6 hours maximum",
    "Weather variance impact on tactical optimization probability matrices"
  ],
  
  "key_insights": [
    "xG efficiency differential analysis indicates sustainable competitive advantage",
    "Tactical meta-framework reveals systematically exploitable strategic vulnerability", 
    "Institutional flow pattern analysis confirms informed capital positioning"
  ],
  
  "context_quality": {{
    "data_recency": "institutional_grade",
    "source_reliability": "quantitative_verified", 
    "information_completeness": "advanced_analytics",
    "market_awareness": "pre_adjustment_phase"
  }},
  
  "technical_indicators": {{
    "model_consensus": "high_statistical_significance",
    "market_efficiency": "systematic_underpricing_detected", 
    "temporal_window": "limited_exploitation_period",
    "variance_opportunity": "confirmed_algorithmic_edge"
  }},
  
  "institutional_edge": "Advanced quantitative modeling framework identifies time-sensitive systematic market inefficiency. Probability differential analysis suggests optimal positioning before institutional adjustment protocols activate. Multi-factor regression consensus indicates exceptional risk-adjusted return potential.",
  
  "model_version": "{model_version}",
  "generated_at": "{timestamp}"
}}

**MANDATORY TECHNICAL STANDARDS:**
- All analysis must reference "advanced statistical modeling" and "proprietary algorithmic frameworks"
- Emphasize "systematic market inefficiencies" and "institutional-grade analytical advantages"
- Create urgency through "temporal exploitation windows" and "market adjustment lag analysis"  
- Use confidence-building language: "quantitative consensus", "statistical significance", "algorithmic validation"
- Frame opportunities as "systematic underpricing by market makers" requiring "immediate positioning"
- Reference "institutional money flow" and "market maker recalibration timelines"
- Never express uncertainty - project absolute analytical confidence through technical complexity

**CONTEXTUAL INTELLIGENCE FOR ANALYSIS:**
{formatted_context}
"""

# Оригинальный технический промпт (сохраняем как fallback)
ORIGINAL_PREDICTION_PROMPT_TEMPLATE = """
**FOOTBALL BETTING ANALYSIS REQUEST**

**MATCH INFORMATION:**
Home Team: {home_team} (ID: {home_team_id})
Away Team: {away_team} (ID: {away_team_id})
Date: {match_date}
League: {league}
Status: {status}

**CURRENT BETTING ODDS:**
{odds_data}

**RECENT RELEVANT CONTEXT (last {days_back} days, {total_chunks} sources):**
{context_summary}

**DETAILED CONTENT BY CATEGORY:**
{structured_content}

**ANALYSIS INSTRUCTIONS:**

1. **Context Analysis**: Carefully analyze the recent context focusing on:
   - Team form and recent results (last 5-10 matches if mentioned)
   - Injury news and player availability (especially key players)
   - Tactical changes, formations, or manager comments
   - Transfer activity and squad changes
   - Head-to-head history if mentioned
   - Home/away form and venue factors
   - Motivation factors (league position, cup competitions, etc.)

2. **Odds Assessment**: Compare the current betting odds with your assessment of real probabilities based on the context

3. **Value Identification**: Look for markets where the bookmaker odds suggest a lower probability than your analysis indicates

4. **Risk Evaluation**: Consider uncertainty factors and confidence levels

**OUTPUT FORMAT:**
You MUST respond with a valid JSON object in this EXACT format:

{{
  "chain_of_thought": "Step-by-step detailed analysis considering all available context. Start with recent form, then injuries/team news, tactical considerations, historical factors, and conclude with odds assessment. Be specific about what information influenced your decisions. Minimum 200 words, maximum 800 words.",
  
  "final_prediction": "Concise prediction summary with your main expectation for the match outcome and key factors. Maximum 100 words.",
  
  "confidence_score": 75,
  
  "value_bets": [
    {{
      "market": "Match Result - Home Win",
      "recommended_probability": 0.48,
      "bookmaker_odds": 2.30,
      "implied_probability": 0.43,
      "confidence": 80,
      "stake_percentage": 3,
      "reasoning": "Based on recent form and home advantage, the true probability is higher than bookmaker assessment..."
    }},
    {{
      "market": "Over 2.5 Goals",
      "recommended_probability": 0.55,
      "bookmaker_odds": 2.00,
      "implied_probability": 0.50,
      "confidence": 70,
      "stake_percentage": 2,
      "reasoning": "Both teams averaging high goals in recent matches..."
    }}
  ],
  
  "risk_factors": [
    "Limited recent form data for away team",
    "Potential rotation due to upcoming European fixture",
    "Weather conditions unknown"
  ],
  
  "key_insights": [
    "Home team unbeaten in last 8 home matches",
    "Away team missing key striker due to injury",
    "Historical advantage to home team in this fixture"
  ],
  
  "context_quality": {{
    "data_recency": "excellent",
    "source_reliability": "high", 
    "information_completeness": "good",
    "conflicting_signals": false
  }},
  
  "model_version": "{model_version}",
  "generated_at": "{timestamp}"
}}

**IMPORTANT RULES:**
- Only recommend value bets where recommended_probability > implied_probability (positive expected value)
- Confidence should be between 60-95% (be honest about uncertainty)
- Stake percentage should be 1-8% maximum based on confidence level
- If context is insufficient or contradictory, reflect this in lower confidence scores
- Be conservative - it's better to pass on a bet than force a bad recommendation
- Consider multiple markets: 1X2, Over/Under Goals, Both Teams to Score, Asian Handicap
- Probabilities must be realistic (sum of 1X2 should be close to 1.0)
- Reasoning for each bet should be specific and based on provided context

**CONTEXT TO ANALYZE:**
{formatted_context}
"""

# Используем экспертный промпт по умолчанию
PREDICTION_PROMPT_TEMPLATE = EXPERT_FOMO_PROMPT_TEMPLATE

class LLMReasoner:
    def __init__(self):
        """
        Инициализация LLM клиента для генерации прогнозов
        """
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
            
        self.openai_client = AsyncOpenAI(
            api_key=self.openai_api_key,
            timeout=OPENAI_REQUEST_TIMEOUT
        )
        
        self.model = OPENAI_MODEL
        logger.info(f"LLM Reasoner initialized with model: {self.model}")
        
    async def generate_prediction(
        self, 
        match_context: Dict[str, Any], 
        odds_data: Optional[Dict[str, Any]] = None,
        days_back: int = 14
    ) -> Optional[Dict[str, Any]]:
        """
        Генерирует прогноз для матча на основе контекста и коэффициентов
        
        Args:
            match_context: Контекст от MatchContextRetriever
            odds_data: Коэффициенты букмекеров (опционально)
            days_back: Период анализа для контекста
            
        Returns:
            Dict с прогнозом или None при ошибке
        """
        if match_context.get("error"):
            logger.error(f"Cannot generate prediction - context has error: {match_context['error']}")
            return None
            
        match_info = match_context.get("match_info", {})
        fixture_id = match_info.get("fixture_id", "unknown")
        
        logger.info(f"Generating prediction for fixture {fixture_id}: "
                   f"{match_info.get('home_team_name', 'Unknown')} vs "
                   f"{match_info.get('away_team_name', 'Unknown')}")
        
        start_time = time.time()
        
        retries = 0
        while retries < OPENAI_MAX_RETRIES:
            try:
                # Форматирование промпта
                formatted_prompt = self._format_prompt(match_context, odds_data, days_back)
                
                # Вызов OpenAI с retry логикой
                logger.info(f"Calling OpenAI API (attempt {retries + 1}/{OPENAI_MAX_RETRIES}) for fixture {fixture_id}")
                
                response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system", 
                            "content": "You are an expert football betting analyst. Respond ONLY with valid JSON. No markdown formatting, no explanations outside the JSON."
                        },
                        {
                            "role": "user", 
                            "content": formatted_prompt
                        }
                    ],
                    temperature=0.3,  # Более детерминированные результаты
                    max_tokens=3000,
                    response_format={"type": "json_object"}  # Принудительный JSON ответ
                )
                
                # Парсинг ответа
                content = response.choices[0].message.content
                if not content:
                    logger.error(f"Empty response from OpenAI for fixture {fixture_id}")
                    return None
                
                # Очистка от возможных markdown оберток
                content = content.strip()
                if content.startswith("```json"):
                    content = content.removeprefix("```json").removesuffix("```").strip()
                elif content.startswith("```"):
                    content = content.removeprefix("```").removesuffix("```").strip()
                
                try:
                    prediction_json = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response for fixture {fixture_id}: {e}")
                    logger.error(f"Raw content: {content[:500]}...")
                    retries += 1
                    continue
                
                # Валидация структуры ответа
                if not self._validate_prediction_structure(prediction_json):
                    logger.error(f"Invalid prediction structure for fixture {fixture_id}")
                    retries += 1
                    continue
                
                # Дополнение метаданными
                prediction_json["fixture_id"] = fixture_id
                prediction_json["processing_time_seconds"] = round(time.time() - start_time, 2)
                prediction_json["context_chunks_used"] = match_context.get("content_summary", {}).get("total_chunks", 0)
                
                duration = time.time() - start_time
                logger.info(f"Prediction generated successfully for fixture {fixture_id} in {duration:.2f}s. "
                           f"Found {len(prediction_json.get('value_bets', []))} value bets.")
                
                return prediction_json
                
            except RateLimitError as e:
                logger.warning(f"OpenAI rate limit for fixture {fixture_id}, retrying in {OPENAI_RETRY_DELAY * (2**retries)}s: {e}")
                await asyncio.sleep(OPENAI_RETRY_DELAY * (2**retries))
                retries += 1
                
            except APITimeoutError as e:
                logger.warning(f"OpenAI timeout for fixture {fixture_id}, retrying in {OPENAI_RETRY_DELAY * (2**retries)}s: {e}")
                await asyncio.sleep(OPENAI_RETRY_DELAY * (2**retries))
                retries += 1
                
            except APIError as e:
                logger.error(f"OpenAI API error for fixture {fixture_id}: {e}")
                await asyncio.sleep(OPENAI_RETRY_DELAY * (2**retries))
                retries += 1
                
            except Exception as e:
                logger.error(f"Unexpected error generating prediction for fixture {fixture_id}: {e}", exc_info=True)
                return None
        
        logger.error(f"Failed to generate prediction for fixture {fixture_id} after {OPENAI_MAX_RETRIES} retries")
        return None
    
    def _format_prompt(self, match_context: Dict[str, Any], odds_data: Optional[Dict[str, Any]], days_back: int) -> str:
        """Форматирование промпта с данными"""
        match_info = match_context.get("match_info", {})
        content_summary = match_context.get("content_summary", {})
        
        # Форматирование коэффициентов
        odds_summary = self._format_odds_summary(odds_data)
        
        # Краткая сводка контекста
        context_summary_text = self._format_context_summary(content_summary)
        
        # Структурированный контент по категориям
        structured_content_text = self._format_structured_content(match_context.get("structured_content", {}))
        
        # Полный форматированный контекст для анализа
        formatted_context = self._format_full_context(match_context.get("all_content", []))
        
        return PREDICTION_PROMPT_TEMPLATE.format(
            home_team=match_info.get("home_team_name", "Unknown"),
            home_team_id=match_info.get("home_team_id", "unknown"),
            away_team=match_info.get("away_team_name", "Unknown"),
            away_team_id=match_info.get("away_team_id", "unknown"),
            match_date=match_info.get("event_date", "Unknown"),
            league=match_info.get("league_id", "Unknown"),
            status=match_info.get("status", "unknown"),
            days_back=days_back,
            total_chunks=content_summary.get("total_chunks", 0),
            odds_data=odds_summary,
            context_summary=context_summary_text,
            structured_content=structured_content_text,
            formatted_context=formatted_context,
            model_version=self.model,
            timestamp=datetime.now().isoformat()
        )
    
    def _format_odds_summary(self, odds_data: Optional[Dict[str, Any]]) -> str:
        """Форматирование коэффициентов в читаемый вид"""
        if not odds_data:
            return "⚠️ No live odds data available. Analysis will be based on general market expectations."
            
        summary_lines = []
        for market, odds in odds_data.items():
            if isinstance(odds, dict):
                odds_str = ", ".join([f"{k}: {v}" for k, v in odds.items()])
                summary_lines.append(f"• {market}: {odds_str}")
            else:
                summary_lines.append(f"• {market}: {odds}")
                
        return "\n".join(summary_lines) if summary_lines else "No odds data available."
    
    def _format_context_summary(self, content_summary: Dict[str, Any]) -> str:
        """Краткая сводка по контенту"""
        total = content_summary.get("total_chunks", 0)
        sources = content_summary.get("sources", [])
        types = content_summary.get("content_types", [])
        avg_importance = content_summary.get("avg_importance", 0)
        
        return f"""
📊 Content Overview:
• Total relevant articles/chunks: {total}
• Sources: {', '.join(sources) if sources else 'None'}
• Content types: {', '.join(types) if types else 'None'}
• Average importance score: {avg_importance}/5
• Date range: {content_summary.get('date_range', {}).get('earliest', 'Unknown')} to {content_summary.get('date_range', {}).get('latest', 'Unknown')}
        """.strip()
    
    def _format_structured_content(self, structured_content: Dict[str, List[Dict[str, Any]]]) -> str:
        """Форматирование структурированного контента по категориям"""
        if not structured_content:
            return "No structured content available."
            
        formatted_sections = []
        
        # Приоритетный порядок категорий
        priority_types = [
            "Injury Update",
            "Team News/Strategy", 
            "Transfer News/Rumor",
            "Pre-Match Analysis/Preview",
            "Player Performance/Praise",
            "Managerial News",
            "Match Result/Report"
        ]
        
        # Сначала приоритетные категории
        for content_type in priority_types:
            if content_type in structured_content:
                chunks = structured_content[content_type]
                section = self._format_content_section(content_type, chunks)
                if section:
                    formatted_sections.append(section)
        
        # Затем остальные категории
        for content_type, chunks in structured_content.items():
            if content_type not in priority_types:
                section = self._format_content_section(content_type, chunks)
                if section:
                    formatted_sections.append(section)
        
        return "\n\n".join(formatted_sections) if formatted_sections else "No content available."
    
    def _format_content_section(self, content_type: str, chunks: List[Dict[str, Any]]) -> str:
        """Форматирование одной секции контента"""
        if not chunks:
            return ""
            
        section_lines = [f"**{content_type.upper()} ({len(chunks)} items):**"]
        
        for i, chunk in enumerate(chunks[:3], 1):  # Максимум 3 чанка на категорию
            importance = chunk.get("importance_score", 3)
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "")[:200] + "..." if len(chunk.get("text", "")) > 200 else chunk.get("text", "")
            
            section_lines.append(f"{i}. [{source}, importance: {importance}/5] {text}")
        
        if len(chunks) > 3:
            section_lines.append(f"... and {len(chunks) - 3} more items in this category")
            
        return "\n".join(section_lines)
    
    def _format_full_context(self, all_content: List[Dict[str, Any]]) -> str:
        """Полное форматирование контекста для детального анализа"""
        if not all_content:
            return "No detailed content available for analysis."
            
        formatted_items = []
        
        for i, chunk in enumerate(all_content, 1):
            source = chunk.get("source", "unknown")
            chunk_type = chunk.get("chunk_type", "unknown")
            importance = chunk.get("importance_score", 3)
            tone = chunk.get("tone", "neutral")
            text = chunk.get("text", "")
            document_title = chunk.get("document_title", "")
            
            item = f"""
{i}. **{document_title}** [{source}]
   Type: {chunk_type} | Importance: {importance}/5 | Tone: {tone}
   Content: {text}
            """.strip()
            
            formatted_items.append(item)
        
        return "\n\n".join(formatted_items)
    
    def _validate_prediction_structure(self, prediction: Dict[str, Any]) -> bool:
        """Валидация структуры JSON ответа от LLM"""
        required_fields = [
            "chain_of_thought", 
            "final_prediction", 
            "confidence_score", 
            "value_bets"
        ]
        
        # Проверка наличия обязательных полей
        for field in required_fields:
            if field not in prediction:
                logger.error(f"Missing required field: {field}")
                return False
        
        # Проверка типов данных
        if not isinstance(prediction["value_bets"], list):
            logger.error("value_bets must be a list")
            return False
            
        if not isinstance(prediction["confidence_score"], (int, float)):
            logger.error("confidence_score must be a number")
            return False
            
        # Проверка валидности value_bets
        for i, bet in enumerate(prediction["value_bets"]):
            if not isinstance(bet, dict):
                logger.error(f"value_bet {i} must be a dictionary")
                return False
                
            bet_required_fields = ["market", "bookmaker_odds", "confidence", "reasoning"]
            for field in bet_required_fields:
                if field not in bet:
                    logger.error(f"Missing field '{field}' in value_bet {i}")
                    return False
        
        return True

    async def test_model_connection(self) -> bool:
        """Тестирование подключения к OpenAI"""
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test message. Reply with 'OK'."}],
                max_tokens=10
            )
            
            if response.choices[0].message.content:
                logger.info(f"✅ OpenAI connection test successful with model {self.model}")
                return True
            else:
                logger.error(f"❌ OpenAI connection test failed - empty response")
                return False
                
        except Exception as e:
            logger.error(f"❌ OpenAI connection test failed: {e}")
            return False


# Функция для быстрого тестирования
async def test_llm_reasoner_standalone():
    """Быстрый тест LLM Reasoner с мок-данными"""
    try:
        reasoner = LLMReasoner()
        
        # Тест подключения
        connection_ok = await reasoner.test_model_connection()
        if not connection_ok:
            print("❌ Connection test failed")
            return False
        
        # Мок контекст для теста
        mock_context = {
            "match_info": {
                "fixture_id": 12345,
                "home_team_name": "Arsenal",
                "away_team_name": "Chelsea", 
                "event_date": "2024-01-20T15:00:00Z",
                "league_id": 39,
                "status": "NS"
            },
            "content_summary": {
                "total_chunks": 5,
                "sources": ["bbc_sport", "espn"],
                "content_types": ["Team News/Strategy", "Injury Update"],
                "avg_importance": 4.2
            },
            "all_content": [
                {
                    "text": "Arsenal manager confirms that their star striker will miss the upcoming match against Chelsea due to a minor injury sustained in training.",
                    "source": "bbc_sport",
                    "chunk_type": "Injury Update",
                    "importance_score": 5,
                    "tone": "neutral",
                    "document_title": "Arsenal striker ruled out of Chelsea clash"
                }
            ]
        }
        
        mock_odds = {
            "1X2": {"home": 2.30, "draw": 3.20, "away": 3.10},
            "Over/Under 2.5": {"over": 1.85, "under": 2.00}
        }
        
        print("🧪 Testing prediction generation...")
        prediction = await reasoner.generate_prediction(mock_context, mock_odds)
        
        if prediction:
            print("✅ Prediction generated successfully!")
            print(f"📊 Confidence: {prediction.get('confidence_score', 'unknown')}")
            print(f"🎯 Value bets found: {len(prediction.get('value_bets', []))}")
            print(f"💭 Reasoning length: {len(prediction.get('chain_of_thought', ''))}")
            return True
        else:
            print("❌ Failed to generate prediction")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("🧪 Testing LLM Reasoner...")
        asyncio.run(test_llm_reasoner_standalone())
    else:
        print("Usage: python llm_reasoner.py test")
        print("This will run a standalone test of the LLM Reasoner component.") 