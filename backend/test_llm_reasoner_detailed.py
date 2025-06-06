#!/usr/bin/env python3
"""
Detailed test for LLM Reasoner
"""
import asyncio
import json
from processors.llm_reasoner import LLMReasoner

async def test_llm_reasoner_detailed():
    """Detailed test with full output"""
    print("🧠 Детальный тест LLM Reasoner")
    print("=" * 50)
    
    reasoner = LLMReasoner()
    
    # Тест подключения
    print("📡 Проверка подключения к OpenAI...")
    connection_ok = await reasoner.test_model_connection()
    if not connection_ok:
        print("❌ Подключение к OpenAI не удалось")
        return False
    print("✅ OpenAI подключение успешно")
    
    # Реальные данные для тестирования (как из Retriever)
    mock_context = {
        "match_info": {
            "fixture_id": 1035065,
            "home_team_name": "Newcastle",
            "away_team_name": "Liverpool", 
            "home_team_id": 34,
            "away_team_id": 40,
            "event_date": "2023-08-27T15:30:00Z",
            "league_id": 39,
            "status": "NS"
        },
        "content_summary": {
            "total_chunks": 13,
            "sources": ["bbc_sport"],
            "content_types": ["Player Performance/Praise", "Match Result/Report", "League/Competition News", "Transfer News/Rumor"],
            "avg_importance": 4.3,
            "date_range": {
                "earliest": "2023-08-20T10:00:00Z",
                "latest": "2023-08-26T18:30:00Z"
            }
        },
        "structured_content": {
            "Player Performance/Praise": [
                {
                    "text": "Mohamed Salah has scored in 8 of his last 10 Premier League appearances against Newcastle, showing exceptional consistency against this opponent.",
                    "source": "bbc_sport",
                    "chunk_type": "Player Performance/Praise",
                    "importance_score": 5,
                    "tone": "positive",
                    "document_title": "Salah's Newcastle record"
                }
            ],
            "Transfer News/Rumor": [
                {
                    "text": "Newcastle United have strengthened their squad with key signings in the summer transfer window, adding depth in midfield and attack.",
                    "source": "bbc_sport", 
                    "chunk_type": "Transfer News/Rumor",
                    "importance_score": 4,
                    "tone": "positive",
                    "document_title": "Newcastle transfer activity"
                }
            ],
            "League/Competition News": [
                {
                    "text": "Liverpool's Champions League qualification hopes depend on maintaining consistency in their remaining Premier League fixtures.",
                    "source": "bbc_sport",
                    "chunk_type": "League/Competition News", 
                    "importance_score": 4,
                    "tone": "analytical",
                    "document_title": "Liverpool season objectives"
                }
            ]
        },
        "all_content": [
            {
                "text": "Mohamed Salah has scored in 8 of his last 10 Premier League appearances against Newcastle, showing exceptional consistency against this opponent.",
                "source": "bbc_sport",
                "chunk_type": "Player Performance/Praise",
                "importance_score": 5,
                "linked_team_ids": ["40"],
                "linked_player_ids": ["306"]
            }
        ]
    }
    
    mock_odds = {
        "1X2": {"home": 3.20, "draw": 3.40, "away": 2.30},
        "Over/Under 2.5": {"over": 1.90, "under": 1.95},
        "Both Teams to Score": {"yes": 1.85, "no": 2.00},
        "Double Chance": {"1X": 1.80, "X2": 1.45, "12": 1.25}
    }
    
    print("\n🎯 Генерация прогноза...")
    prediction = await reasoner.generate_prediction(mock_context, mock_odds)
    
    if not prediction:
        print("❌ Не удалось создать прогноз")
        return False
    
    print("\n✅ Прогноз успешно создан!")
    print("=" * 60)
    
    # Основная информация
    print(f"🎯 Матч: {mock_context['match_info']['home_team_name']} vs {mock_context['match_info']['away_team_name']}")
    print(f"📊 Уверенность: {prediction.get('confidence_score', 'unknown')}%")
    print(f"🕒 Время обработки: {prediction.get('processing_time_seconds', 'unknown')}s")
    print(f"🤖 Модель: {prediction.get('model_version', 'unknown')}")
    
    # Финальный прогноз
    print(f"\n🔮 Финальный прогноз:")
    print(f"   {prediction.get('final_prediction', 'Не указан')}")
    
    # Chain of Thought
    chain_of_thought = prediction.get('chain_of_thought', '')
    if chain_of_thought:
        print(f"\n🧠 Аналитическое рассуждение:")
        print(f"   {chain_of_thought[:300]}..." if len(chain_of_thought) > 300 else f"   {chain_of_thought}")
    
    # Value Bets
    value_bets = prediction.get('value_bets', [])
    print(f"\n💰 Value Bets ({len(value_bets)} найдено):")
    for i, bet in enumerate(value_bets, 1):
        print(f"   {i}. {bet.get('market', 'Unknown')}")
        print(f"      🎯 Рекомендуемая вероятность: {bet.get('recommended_probability', 'N/A')}")
        print(f"      📊 Коэффициент букмекера: {bet.get('bookmaker_odds', 'N/A')}")
        print(f"      📈 Подразумеваемая вероятность: {bet.get('implied_probability', 'N/A')}")
        print(f"      ✅ Уверенность: {bet.get('confidence', 'N/A')}%")
        print(f"      💵 Доля банка: {bet.get('stake_percentage', 'N/A')}%")
        reasoning = bet.get('reasoning', 'Не указано')
        print(f"      🔍 Обоснование: {reasoning[:150]}...")
        print()
    
    # Ключевые инсайты
    insights = prediction.get('key_insights', [])
    if insights:
        print(f"💡 Ключевые инсайты:")
        for insight in insights:
            print(f"   • {insight}")
    
    # Факторы риска
    risk_factors = prediction.get('risk_factors', [])
    if risk_factors:
        print(f"\n⚠️ Факторы риска:")
        for risk in risk_factors:
            print(f"   • {risk}")
    
    # Качество контекста
    context_quality = prediction.get('context_quality', {})
    if context_quality:
        print(f"\n📊 Качество контекста:")
        for key, value in context_quality.items():
            print(f"   {key}: {value}")
    
    print(f"\n🎉 Тест завершен успешно!")
    return True

if __name__ == "__main__":
    asyncio.run(test_llm_reasoner_detailed()) 