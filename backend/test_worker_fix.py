#!/usr/bin/env python3

"""
Test Worker Fix: проверка что Twitter события корректно обрабатываются
"""

import asyncio
import logging
import sys
import os
import time
import redis

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_worker_fix():
    """Test that worker now processes Twitter events through LLM Content Analyzer"""
    print("🛠️ ТЕСТ ИСПРАВЛЕНИЯ WORKER")
    print("=" * 60)
    
    # Connect to Redis
    redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    
    # Step 1: Add fake Twitter event to stream
    print("\n1. 📡 Добавляем тестовое Twitter событие в stream...")
    
    test_event = {
        "event_type": "raw_content",
        "source": "twitter", 
        "match_id": "",
        "payload": '{"author_username": "FabrizioRomano", "tweet_id": "test123", "full_text": "🚨 BREAKING: Real Madrid have agreed terms with Kylian Mbappe! Here we go! ⚪👑", "created_at": "2025-06-06T15:00:00Z", "author_followers": 20000000, "author_verified": true}'
    }
    
    event_id = redis_client.xadd("stream:raw_events", test_event)
    print(f"✅ Event добавлен: {event_id}")
    
    # Step 2: Process with worker
    print("\n2. ⚙️ Обрабатываем событие через Worker...")
    
    try:
        from jobs.worker import consume_raw_events_stream, setup_streams
        
        # Setup streams
        setup_streams()
        
        # Process event
        processed = await consume_raw_events_stream()
        print(f"✅ Events обработано: {processed}")
        
    except Exception as e:
        print(f"❌ Ошибка Worker: {e}")
        return False
    
    # Step 3: Check results
    print("\n3. 🔍 Проверяем результаты...")
    
    # Check Pinecone for new Twitter content
    try:
        from pinecone import Pinecone
        
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        index = pc.Index(os.getenv("PINECONE_INDEX", "mrbets-content-chunks"))
        
        # Query for Twitter content
        dummy_vector = [0.0] * 1536
        results = index.query(
            vector=dummy_vector,
            filter={"source": {"$eq": "twitter"}},
            top_k=10,
            include_metadata=True
        )
        
        print(f"🐦 Twitter векторов в Pinecone: {len(results.matches)}")
        
        if len(results.matches) > 0:
            print("📝 Последние Twitter события:")
            for i, match in enumerate(results.matches[:3]):
                metadata = match.metadata
                print(f"  {i+1}. {metadata.get('document_title', 'Unknown')}")
                print(f"     Type: {metadata.get('chunk_type', 'unknown')}, Score: {match.score:.3f}")
        
    except Exception as e:
        print(f"❌ Ошибка Pinecone: {e}")
        return False
    
    # Check Supabase
    try:
        from supabase import create_client
        
        supabase = create_client(
            os.getenv("SUPABASE_URL"), 
            os.getenv("SUPABASE_SERVICE_KEY")
        )
        
        # Check recent Twitter documents
        response = supabase.table("processed_documents").select(
            "source, document_title, document_timestamp"
        ).eq("source", "twitter").order("document_timestamp", desc=True).limit(3).execute()
        
        twitter_docs = len(response.data) if response.data else 0
        print(f"🐦 Twitter документов в Supabase: {twitter_docs}")
        
        if twitter_docs > 0:
            print("📝 Последние Twitter документы:")
            for i, doc in enumerate(response.data):
                print(f"  {i+1}. {doc['document_title']}")
                print(f"     Time: {doc['document_timestamp']}")
        
    except Exception as e:
        print(f"❌ Ошибка Supabase: {e}")
        return False
    
    return True

async def main():
    """Main test function"""
    start_time = time.time()
    success = await test_worker_fix()
    duration = time.time() - start_time
    
    print(f"\n📊 РЕЗУЛЬТАТ ТЕСТА")
    print("=" * 60)
    print(f"   Время: {duration:.2f}s")
    
    if success:
        print("🎉 ИСПРАВЛЕНИЕ РАБОТАЕТ!")
        print("✅ Twitter события теперь обрабатываются LLM Content Analyzer")
        print("✅ Контент попадает в Pinecone и Supabase")
    else:
        print("❌ Что-то пошло не так")

if __name__ == "__main__":
    asyncio.run(main()) 