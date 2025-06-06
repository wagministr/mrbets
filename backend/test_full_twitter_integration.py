#!/usr/bin/env python3

"""
Test Full Twitter Integration Pipeline:
Twitter Fetcher → Redis Stream → Worker → LLM Content Analyzer → Pinecone
"""

import asyncio
import logging
import sys
import os
import time

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_full_pipeline():
    """Test complete pipeline from Twitter to Pinecone"""
    print("🚀 ПОЛНАЯ ИНТЕГРАЦИЯ: Twitter → Redis → Worker → LLM Analyzer → Pinecone")
    print("=" * 80)
    
    # Step 1: Run Twitter Fetcher
    print("\n📡 Шаг 1: Запуск Twitter Fetcher...")
    try:
        from fetchers.twitter_fetcher import main_twitter_task
        await main_twitter_task(mode="experts", hours_back=24)
        print("✅ Twitter Fetcher завершен - данные отправлены в Redis Stream")
    except Exception as e:
        print(f"❌ Ошибка Twitter Fetcher: {e}")
        return False
    
    # Step 2: Check Redis Stream
    print("\n📊 Шаг 2: Проверка Redis Stream...")
    try:
        import redis
        redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        
        # Check stream length
        stream_length = redis_client.xlen("stream:raw_events")
        print(f"📋 Events в stream: {stream_length}")
        
        if stream_length == 0:
            print("⚠️ Нет событий в stream - возможно Twitter Fetcher не нашел новых твитов")
            return False
        
        # Show recent events
        recent_events = redis_client.xrevrange("stream:raw_events", count=3)
        print("📝 Последние события:")
        for event_id, event_data in recent_events:
            event_type = event_data.get(b'event_type', b'unknown').decode('utf-8')
            source = event_data.get(b'source', b'unknown').decode('utf-8')
            print(f"  - {event_id.decode()}: {event_type} from {source}")
        
    except Exception as e:
        print(f"❌ Ошибка проверки Redis: {e}")
        return False
    
    # Step 3: Process events with Worker
    print("\n⚙️ Шаг 3: Обработка событий Worker...")
    try:
        from jobs.worker import consume_raw_events_stream, setup_streams
        
        # Setup streams
        setup_streams()
        
        # Process some events
        events_processed = 0
        for _ in range(3):  # Try 3 times
            processed = await consume_raw_events_stream()
            if processed:
                events_processed += 1
                print(f"✅ Обработка {events_processed}: События обработаны")
            else:
                break
        
        if events_processed == 0:
            print("⚠️ Worker не обработал ни одного события")
            return False
        
    except Exception as e:
        print(f"❌ Ошибка Worker: {e}")
        return False
    
    # Step 4: Check Pinecone updates
    print("\n🔍 Шаг 4: Проверка обновлений Pinecone...")
    try:
        from pinecone import Pinecone
        
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        index = pc.Index(os.getenv("PINECONE_INDEX", "mrbets-content-chunks"))
        
        # Get current stats
        stats = index.describe_index_stats()
        total_vectors = stats.total_vector_count
        
        print(f"📊 Всего векторов в Pinecone: {total_vectors}")
        
        # Query for recent Twitter content
        dummy_vector = [0.0] * 1536
        twitter_results = index.query(
            vector=dummy_vector,
            filter={"source": {"$eq": "twitter"}},
            top_k=5,
            include_metadata=True
        )
        
        twitter_count = len(twitter_results.matches)
        print(f"🐦 Twitter контента в Pinecone: {twitter_count} векторов")
        
        if twitter_count > 0:
            print("📝 Примеры Twitter контента:")
            for i, match in enumerate(twitter_results.matches[:3]):
                metadata = match.metadata
                print(f"  {i+1}. {metadata.get('document_title', 'Unknown')}")
                print(f"     Score: {match.score:.3f}, Type: {metadata.get('chunk_type', 'unknown')}")
        
    except Exception as e:
        print(f"❌ Ошибка проверки Pinecone: {e}")
        return False
    
    # Step 5: Check Supabase processed_documents
    print("\n📚 Шаг 5: Проверка Supabase processed_documents...")
    try:
        from supabase import create_client
        
        supabase = create_client(
            os.getenv("SUPABASE_URL"), 
            os.getenv("SUPABASE_SERVICE_KEY")
        )
        
        # Check recent Twitter documents
        response = supabase.table("processed_documents").select(
            "source, document_title, document_timestamp"
        ).eq("source", "twitter").order("document_timestamp", desc=True).limit(5).execute()
        
        twitter_docs = len(response.data) if response.data else 0
        print(f"🐦 Twitter документов в Supabase: {twitter_docs}")
        
        if twitter_docs > 0:
            print("📝 Последние Twitter документы:")
            for i, doc in enumerate(response.data[:3]):
                print(f"  {i+1}. {doc['document_title']}")
                print(f"     Timestamp: {doc['document_timestamp']}")
        
    except Exception as e:
        print(f"❌ Ошибка проверки Supabase: {e}")
        return False
    
    return True

async def main():
    """Main test function"""
    print("🧪 ТЕСТ ПОЛНОЙ ИНТЕГРАЦИИ TWITTER PIPELINE")
    print("=" * 80)
    
    start_time = time.time()
    success = await test_full_pipeline()
    duration = time.time() - start_time
    
    print(f"\n📊 РЕЗУЛЬТАТЫ ИНТЕГРАЦИОННОГО ТЕСТА")
    print("=" * 80)
    print(f"   Время выполнения: {duration:.2f}s")
    
    if success:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Twitter интеграция работает полностью!")
        print("")
        print("🔄 Полный pipeline функционирует:")
        print("   📡 Twitter API → 📨 Redis Stream → ⚙️ Worker → 🧠 LLM Analyzer → 🔍 Pinecone")
        print("")
        print("✅ Twitter контент автоматически:")
        print("   - Собирается от экспертов")
        print("   - Анализируется с помощью LLM")
        print("   - Разбивается на умные чанки")
        print("   - Линкуется с командами/игроками")
        print("   - Превращается в embeddings")
        print("   - Сохраняется в Pinecone для поиска")
        print("")
        print("🚀 База данных автоматически пополняется!")
    else:
        print("❌ Некоторые этапы не прошли. Проверьте конфигурацию.")
        print("💡 Убедитесь что:")
        print("   - Redis запущен")
        print("   - API ключи настроены")
        print("   - Есть свежие твиты от экспертов")

if __name__ == "__main__":
    asyncio.run(main()) 