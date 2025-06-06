#!/usr/bin/env python3
"""
Debug script for Retriever timestamp filtering
"""
import asyncio
from datetime import datetime, timedelta
from processors.retriever_builder import MatchContextRetriever

async def debug_timestamp_filtering():
    """Debug timestamp filtering issues"""
    print("🐛 Отладка временной фильтрации Retriever...")
    
    retriever = MatchContextRetriever()
    
    # 1. Проверим все векторы без временного фильтра
    print("\n1. Все векторы для команд 34 и 40:")
    dummy_vector = [0.0] * 1536
    
    # Фильтр только по командам (без времени)
    team_filter = {
        "$or": [
            {"linked_team_ids": {"$in": ["34"]}},
            {"linked_team_ids": {"$in": ["40"]}}
        ]
    }
    
    results = retriever.pinecone_index.query(
        vector=dummy_vector,
        filter=team_filter,
        top_k=10,
        include_metadata=True
    )
    
    print(f"   Найдено {len(results.matches)} векторов для команд 34, 40")
    
    for i, match in enumerate(results.matches):
        meta = match.metadata
        print(f"   {i+1}. Команды: {meta.get('linked_team_ids', [])}")
        print(f"       Timestamp: {meta.get('document_timestamp', 'None')}")
        print(f"       Тип: {meta.get('chunk_type', 'unknown')}")
        print()
    
    # 2. Проверим временные метки
    print("2. Анализ временных меток:")
    all_results = retriever.pinecone_index.query(
        vector=dummy_vector, 
        top_k=50, 
        include_metadata=True
    )
    
    timestamps = []
    for match in all_results.matches:
        ts = match.metadata.get('document_timestamp')
        if ts and ts != 'None':
            timestamps.append(ts)
    
    print(f"   Всего векторов с timestamp: {len(timestamps)}")
    if timestamps:
        print(f"   Пример timestamps: {timestamps[:5]}")
    else:
        print("   ⚠️ Нет векторов с корректными timestamp!")
    
    # 3. Тест с очень широким временным окном
    print("\n3. Тест с широким временным окном:")
    
    # Текущая дата минус год
    cutoff_timestamp = int((datetime.now() - timedelta(days=365)).timestamp())
    
    wide_filter = {
        "$and": [
            {
                "$or": [
                    {"linked_team_ids": {"$in": ["34"]}},
                    {"linked_team_ids": {"$in": ["40"]}}
                ]
            },
            {"document_timestamp": {"$gte": cutoff_timestamp}}
        ]
    }
    
    wide_results = retriever.pinecone_index.query(
        vector=dummy_vector,
        filter=wide_filter,
        top_k=10,
        include_metadata=True
    )
    
    print(f"   С широким фильтром (от {cutoff_timestamp}): {len(wide_results.matches)} векторов")
    
    return True

if __name__ == "__main__":
    asyncio.run(debug_timestamp_filtering()) 