#!/usr/bin/env python3
"""
Simple test for Retriever Builder
"""
import asyncio
from processors.retriever_builder import MatchContextRetriever

async def test_retriever_content():
    """Test what content is available in Pinecone"""
    print("🔍 Тестирование содержимого Retriever...")
    
    retriever = MatchContextRetriever()
    
    # Статистика Pinecone
    print("📊 Статистика Pinecone:")
    stats = retriever.pinecone_index.describe_index_stats()
    print(f"   Всего векторов: {stats.total_vector_count}")
    
    # Простой поиск векторов
    print("\n🔍 Поиск доступного контента:")
    dummy_vector = [0.0] * 1536
    results = retriever.pinecone_index.query(
        vector=dummy_vector, 
        top_k=10, 
        include_metadata=True
    )
    
    print(f"   Найдено {len(results.matches)} векторов")
    
    # Показать примеры
    for i, match in enumerate(results.matches[:5]):
        meta = match.metadata
        print(f"\n{i+1}. Контент:")
        print(f"   Источник: {meta.get('source', 'unknown')}")
        print(f"   Тип: {meta.get('chunk_type', 'unknown')}")
        print(f"   Команды: {meta.get('linked_team_ids', '[]')}")
        print(f"   Игроки: {meta.get('linked_player_ids', '[]')}")
        print(f"   Важность: {meta.get('importance_score', 'unknown')}/5")
        print(f"   Дата: {meta.get('document_timestamp', 'unknown')}")
        text = meta.get('chunk_text', '')[:100]
        print(f"   Текст: {text}...")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_retriever_content()) 