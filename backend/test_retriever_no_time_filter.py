#!/usr/bin/env python3
"""
Test Retriever without time filtering (for debugging)
"""
import asyncio
from processors.retriever_builder import MatchContextRetriever

class TestMatchContextRetriever(MatchContextRetriever):
    """Test version without time filtering"""
    
    async def _search_relevant_content(
        self, 
        home_team_id: int, 
        away_team_id: int, 
        match_date, 
        days_back: int
    ):
        """Override to skip time filtering"""
        try:
            print(f"🔍 Поиск контента для команд {home_team_id} vs {away_team_id} (БЕЗ временного фильтра)")
            
            # Фильтр только по командам (без времени)
            team_filter = {
                "$or": [
                    {"linked_team_ids": {"$in": [str(home_team_id)]}},
                    {"linked_team_ids": {"$in": [str(away_team_id)]}}
                ]
            }
            
            # Векторный поиск
            dummy_vector = [0.0] * 1536
            
            query_results = self.pinecone_index.query(
                vector=dummy_vector,
                filter=team_filter,
                top_k=20,  # Больше результатов для тестирования
                include_metadata=True
            )
            
            print(f"   Pinecone вернул {len(query_results.matches)} совпадений")
            
            return query_results.matches
            
        except Exception as e:
            print(f"❌ Ошибка поиска в Pinecone: {e}")
            return []

async def test_retriever_without_time_filter():
    """Test retriever without time constraints"""
    print("🧪 Тест Retriever БЕЗ временной фильтрации")
    print("=" * 50)
    
    retriever = TestMatchContextRetriever()
    
    # Тест с матчем Newcastle vs Liverpool (34 vs 40)
    fixture_id = 1035065
    
    print(f"🎯 Получение контекста для матча {fixture_id}...")
    context = await retriever.get_context_for_match(fixture_id)
    
    if context.get("error"):
        print(f"❌ Ошибка: {context['error']}")
        return False
    
    # Результаты
    match_info = context.get("match_info", {})
    content_summary = context.get("content_summary", {})
    
    print(f"\n✅ Контекст получен!")
    print(f"🏆 Матч: {match_info.get('home_team_name')} vs {match_info.get('away_team_name')}")
    print(f"📊 Найдено чанков: {content_summary.get('total_chunks', 0)}")
    print(f"📰 Источники: {', '.join(content_summary.get('sources', []))}")
    print(f"📝 Типы контента: {', '.join(content_summary.get('content_types', []))}")
    print(f"⭐ Средняя важность: {content_summary.get('avg_importance', 0)}/5")
    
    # Примеры контента
    all_content = context.get("all_content", [])
    if all_content:
        print(f"\n📖 Топ контент:")
        for i, chunk in enumerate(all_content[:3], 1):
            print(f"{i}. [{chunk.get('source')}] {chunk.get('chunk_type')}")
            print(f"   Важность: {chunk.get('importance_score')}/5, Команды: {chunk.get('linked_team_ids')}")
            print(f"   Текст: {chunk.get('text', '')[:150]}...")
            print()
    
    return len(all_content) > 0

if __name__ == "__main__":
    asyncio.run(test_retriever_without_time_filter()) 