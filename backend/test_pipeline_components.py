#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новых компонентов pipeline:
- MatchContextRetriever  
- LLMReasoner

Использование:
    python test_pipeline_components.py retriever <fixture_id>
    python test_pipeline_components.py reasoner 
    python test_pipeline_components.py full <fixture_id>
"""

import asyncio
import sys
import logging
import os

# Добавляем текущую директорию в PATH для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from processors.retriever_builder import MatchContextRetriever, test_retriever_with_fixture
from processors.llm_reasoner import LLMReasoner, test_llm_reasoner_standalone

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_retriever_component(fixture_id: int):
    """Тест компонента Retriever"""
    print(f"🔍 Тестирование Retriever с fixture_id: {fixture_id}")
    print("=" * 50)
    
    try:
        retriever = MatchContextRetriever()
        
        # Тест подключений
        print("📡 Проверка подключений...")
        await retriever.test_connections()
        
        # Получение контекста
        print(f"\n🎯 Получение контекста для матча {fixture_id}...")
        context = await retriever.get_context_for_match(fixture_id)
        
        if context.get("error"):
            print(f"❌ Ошибка: {context['error']}")
            return False
            
        # Вывод результатов
        match_info = context.get("match_info", {})
        content_summary = context.get("content_summary", {})
        
        print(f"\n✅ Контекст успешно получен!")
        print(f"🏆 Матч: {match_info.get('home_team_name', 'Unknown')} vs {match_info.get('away_team_name', 'Unknown')}")
        print(f"📅 Дата: {match_info.get('event_date', 'Unknown')}")
        print(f"📊 Найдено чанков: {content_summary.get('total_chunks', 0)}")
        print(f"📰 Источники: {', '.join(content_summary.get('sources', []))}")
        print(f"📝 Типы контента: {', '.join(content_summary.get('content_types', []))}")
        print(f"⭐ Средняя важность: {content_summary.get('avg_importance', 0)}/5")
        
        # Примеры контента
        all_content = context.get("all_content", [])
        if all_content:
            print(f"\n📖 Примеры контента (топ 3):")
            for i, chunk in enumerate(all_content[:3], 1):
                print(f"{i}. [{chunk.get('source', 'unknown')}] {chunk.get('chunk_type', 'unknown')}")
                print(f"   Важность: {chunk.get('importance_score', 0)}/5")
                print(f"   Текст: {chunk.get('text', '')[:100]}...")
                print()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании Retriever: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_reasoner_component():
    """Тест компонента LLM Reasoner"""
    print("🧠 Тестирование LLM Reasoner...")
    print("=" * 50)
    
    try:
        reasoner = LLMReasoner()
        
        # Тест подключения
        print("📡 Проверка подключения к OpenAI...")
        connection_ok = await reasoner.test_model_connection()
        if not connection_ok:
            print("❌ Подключение к OpenAI не удалось")
            return False
            
        # Мок данные для теста
        mock_context = {
            "match_info": {
                "fixture_id": 123456,
                "home_team_name": "Arsenal",
                "away_team_name": "Manchester City",
                "home_team_id": 42,
                "away_team_id": 50,
                "event_date": "2024-01-20T15:00:00Z",
                "league_id": 39,
                "status": "NS"
            },
            "content_summary": {
                "total_chunks": 8,
                "sources": ["bbc_sport", "espn", "sky_sports"],
                "content_types": ["Team News/Strategy", "Injury Update", "Pre-Match Analysis/Preview"],
                "avg_importance": 4.3,
                "date_range": {
                    "earliest": "2024-01-15T10:00:00Z",
                    "latest": "2024-01-19T18:30:00Z"
                }
            },
            "structured_content": {
                "Injury Update": [
                    {
                        "text": "Arsenal midfielder Thomas Partey ruled out for 3-4 weeks with ankle injury sustained in training. Manager confirms backup options ready.",
                        "source": "bbc_sport",
                        "chunk_type": "Injury Update",
                        "importance_score": 5,
                        "tone": "neutral",
                        "document_title": "Partey injury blow for Arsenal"
                    }
                ],
                "Team News/Strategy": [
                    {
                        "text": "Manchester City manager confirms rotation policy ahead of Champions League fixture. Key players may be rested for Premier League clash.",
                        "source": "sky_sports", 
                        "chunk_type": "Team News/Strategy",
                        "importance_score": 4,
                        "tone": "analytical",
                        "document_title": "City rotation plans revealed"
                    }
                ]
            },
            "all_content": [
                {
                    "text": "Arsenal midfielder Thomas Partey ruled out for 3-4 weeks with ankle injury sustained in training. Manager confirms backup options ready.",
                    "source": "bbc_sport",
                    "chunk_type": "Injury Update", 
                    "importance_score": 5,
                    "tone": "neutral",
                    "document_title": "Partey injury blow for Arsenal"
                },
                {
                    "text": "Manchester City manager confirms rotation policy ahead of Champions League fixture. Key players may be rested for Premier League clash.",
                    "source": "sky_sports",
                    "chunk_type": "Team News/Strategy",
                    "importance_score": 4,
                    "tone": "analytical", 
                    "document_title": "City rotation plans revealed"
                }
            ]
        }
        
        mock_odds = {
            "1X2": {"home": 3.20, "draw": 3.40, "away": 2.30},
            "Over/Under 2.5": {"over": 1.90, "under": 1.95},
            "Both Teams to Score": {"yes": 1.85, "no": 2.00}
        }
        
        print("🎯 Генерация прогноза с мок-данными...")
        prediction = await reasoner.generate_prediction(mock_context, mock_odds)
        
        if prediction:
            print("✅ Прогноз успешно создан!")
            print(f"📊 Уверенность: {prediction.get('confidence_score', 'unknown')}%")
            print(f"🎯 Value bets: {len(prediction.get('value_bets', []))}")
            print(f"⏱️ Время обработки: {prediction.get('processing_time_seconds', 'unknown')}s")
            print(f"📝 Модель: {prediction.get('model_version', 'unknown')}")
            
            # Показать прогноз
            print(f"\n🔮 Финальный прогноз:")
            print(f"   {prediction.get('final_prediction', 'Не указан')}")
            
            # Показать value bets
            value_bets = prediction.get('value_bets', [])
            if value_bets:
                print(f"\n💰 Value Bets:")
                for i, bet in enumerate(value_bets, 1):
                    print(f"   {i}. {bet.get('market', 'Unknown')}")
                    print(f"      Коэффициент: {bet.get('bookmaker_odds', 'N/A')}")
                    print(f"      Уверенность: {bet.get('confidence', 'N/A')}%")
                    print(f"      Доля банка: {bet.get('stake_percentage', 'N/A')}%")
                    print(f"      Обоснование: {bet.get('reasoning', 'Не указано')[:100]}...")
                    print()
            else:
                print("\n💰 Value Bets: Не найдено")
            
            # Ключевые инсайты
            insights = prediction.get('key_insights', [])
            if insights:
                print(f"\n💡 Ключевые инсайты:")
                for insight in insights:
                    print(f"   • {insight}")
            
            return True
        else:
            print("❌ Не удалось создать прогноз")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании Reasoner: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_full_pipeline(fixture_id: int):
    """Тест полного pipeline: Retriever -> Reasoner"""
    print(f"🚀 Тестирование полного pipeline с fixture_id: {fixture_id}")
    print("=" * 60)
    
    try:
        # 1. Retriever
        print("🔍 Шаг 1: Получение контекста...")
        retriever = MatchContextRetriever()
        context = await retriever.get_context_for_match(fixture_id)
        
        if context.get("error"):
            print(f"❌ Ошибка в Retriever: {context['error']}")
            return False
            
        match_info = context.get("match_info", {})
        print(f"✅ Контекст получен для: {match_info.get('home_team_name', 'Unknown')} vs {match_info.get('away_team_name', 'Unknown')}")
        print(f"📊 Чанков найдено: {context.get('content_summary', {}).get('total_chunks', 0)}")
        
        # 2. Mock odds (в реальной ситуации здесь будет odds_fetcher)
        print("\n💰 Шаг 2: Получение коэффициентов (мок-данные)...")
        mock_odds = {
            "1X2": {"home": 2.10, "draw": 3.30, "away": 3.50},
            "Over/Under 2.5": {"over": 1.95, "under": 1.90}
        }
        
        # 3. Reasoner
        print("\n🧠 Шаг 3: Генерация прогноза...")
        reasoner = LLMReasoner()
        prediction = await reasoner.generate_prediction(context, mock_odds)
        
        if prediction:
            print("✅ Полный pipeline выполнен успешно!")
            print(f"🎯 Результат:")
            print(f"   • Fixture ID: {prediction.get('fixture_id', 'unknown')}")
            print(f"   • Уверенность: {prediction.get('confidence_score', 'unknown')}%")
            print(f"   • Value bets: {len(prediction.get('value_bets', []))}")
            print(f"   • Время обработки: {prediction.get('processing_time_seconds', 'unknown')}s")
            print(f"   • Чанков использовано: {prediction.get('context_chunks_used', 'unknown')}")
            
            return True
        else:
            print("❌ Ошибка в Reasoner")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка в полном pipeline: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python test_pipeline_components.py retriever <fixture_id>")
        print("  python test_pipeline_components.py reasoner")
        print("  python test_pipeline_components.py full <fixture_id>")
        print("")
        print("Примеры:")
        print("  python test_pipeline_components.py retriever 12345")
        print("  python test_pipeline_components.py reasoner")
        print("  python test_pipeline_components.py full 12345")
        return
    
    command = sys.argv[1].lower()
    
    if command == "retriever":
        if len(sys.argv) < 3:
            print("❌ Необходимо указать fixture_id для теста retriever")
            return
        fixture_id = int(sys.argv[2])
        success = await test_retriever_component(fixture_id)
        
    elif command == "reasoner":
        success = await test_reasoner_component()
        
    elif command == "full":
        if len(sys.argv) < 3:
            print("❌ Необходимо указать fixture_id для полного теста")
            return
        fixture_id = int(sys.argv[2])
        success = await test_full_pipeline(fixture_id)
        
    else:
        print(f"❌ Неизвестная команда: {command}")
        return
    
    if success:
        print("\n🎉 Тест завершен успешно!")
    else:
        print("\n💥 Тест завершен с ошибками!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 