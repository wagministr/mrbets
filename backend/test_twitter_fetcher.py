#!/usr/bin/env python3
"""
test_twitter_fetcher.py

Тестовый скрипт для проверки работы Twitter fetcher с TwitterAPI.io
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fetchers.twitter_fetcher import TwitterFetcher, TwitterAPIClient, main_twitter_task

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_twitter_api_connection():
    """Тестирует подключение к TwitterAPI.io"""
    print("🔌 Тест подключения к TwitterAPI.io...")
    
    try:
        async with TwitterAPIClient() as client:
            # Простой тест поиска
            response = await client.advanced_search(
                query="football",
                query_type="Latest"
            )
            
            if "error" in response:
                print(f"❌ Ошибка API: {response['error']}")
                return False
            
            tweets = response.get("tweets", [])
            print(f"✅ API подключение успешно. Найдено {len(tweets)} твитов для тестового запроса")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False


async def test_twitter_fetcher_basic():
    """Базовый тест Twitter Fetcher"""
    print("\n🧪 Базовый тест Twitter Fetcher...")
    
    fetcher = TwitterFetcher()
    
    try:
        # Тест подключения к Redis
        await fetcher.connect_redis()
        print("✅ Redis подключение успешно")
        
        # Тест получения экспертных твитов
        print("📊 Тест мониторинга экспертов (15 минут)...")
        expert_tweets = await fetcher.fetch_expert_tweets(hours_back=0.25)  # 15 минут
        print(f"✅ Получено {len(expert_tweets)} экспертных твитов")
        
        # Показать примеры
        if expert_tweets:
            print("\n📝 Примеры экспертных твитов:")
            for i, tweet in enumerate(expert_tweets[:3]):
                print(f"  {i+1}. @{tweet['author']['username']}: {tweet['text'][:100]}...")
                print(f"     Engagement: {tweet['engagement_score']}, Reliability: {tweet['reliability_score']}")
        
        # Тест поиска по ключевым словам
        print("\n🔍 Тест поиска по ключевым словам (15 минут)...")
        keyword_tweets = await fetcher.search_keyword_tweets(hours_back=0.25, max_results=10)
        print(f"✅ Найдено {len(keyword_tweets)} твитов по ключевым словам")
        
        if keyword_tweets:
            print("\n📝 Примеры твитов по ключевым словам:")
            for i, tweet in enumerate(keyword_tweets[:3]):
                print(f"  {i+1}. @{tweet['author']['username']}: {tweet['text'][:100]}...")
                print(f"     Хэштеги: {tweet['hashtags']}")
        
        await fetcher.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        await fetcher.close()
        return False


async def test_expert_accounts():
    """Тест экспертных аккаунтов"""
    print("\n👥 Тест доступности экспертных аккаунтов...")
    
    from fetchers.twitter_fetcher import EXPERT_ACCOUNTS
    
    print(f"📋 Настроено {len(EXPERT_ACCOUNTS)} экспертных аккаунтов:")
    for i, account in enumerate(EXPERT_ACCOUNTS, 1):
        print(f"  {i}. @{account}")
    
    async with TwitterAPIClient() as client:
        working_accounts = 0
        
        for account in EXPERT_ACCOUNTS[:3]:  # Тестируем первые 3 для экономии лимитов
            try:
                response = await client.advanced_search(
                    query=f"from:{account}",
                    query_type="Latest"
                )
                
                if "error" not in response and response.get("tweets"):
                    working_accounts += 1
                    print(f"  ✅ @{account} доступен")
                else:
                    print(f"  ⚠️ @{account} временно недоступен")
                    
            except Exception as e:
                print(f"  ❌ @{account} ошибка: {e}")
        
        print(f"\n📊 Доступно {working_accounts}/3 протестированных аккаунтов")


async def test_redis_integration():
    """Тест интеграции с Redis"""
    print("\n🔄 Тест интеграции с Redis...")
    
    fetcher = TwitterFetcher()
    
    try:
        await fetcher.connect_redis()
        
        # Создаем тестовые твиты
        test_tweets = [
            {
                "tweet_id": "test_123",
                "text": "Test tweet for Redis integration #football",
                "author": {
                    "username": "test_user",
                    "name": "Test User",
                    "followers": 1000,
                    "verified": False
                },
                "created_at": "2025-01-01T12:00:00Z",
                "engagement_score": 50.0,
                "reliability_score": 0.8,
                "hashtags": ["football"],
                "mentions": [],
                "urls": [],
                "metrics": {"like_count": 10, "retweet_count": 5},
                "is_reply": False,
                "language": "en",
                "url": "https://twitter.com/test_user/status/test_123"
            }
        ]
        
        # Отправляем в Redis
        await fetcher.send_to_redis_stream(test_tweets)
        print("✅ Тест твит успешно отправлен в Redis Stream")
        
        await fetcher.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Redis интеграции: {e}")
        await fetcher.close()
        return False


async def main():
    """Главная функция тестирования"""
    print("🐦 TWITTER FETCHER TESTING SUITE")
    print("=" * 50)
    
    tests = [
        ("API Connection", test_twitter_api_connection),
        ("Expert Accounts", test_expert_accounts),
        ("Redis Integration", test_redis_integration),
        ("Basic Functionality", test_twitter_fetcher_basic),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        print("-" * 40)
        
        try:
            success = await test_func()
            if success:
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
    
    print(f"\n📊 TWITTER FETCHER TEST RESULTS")
    print("=" * 50)
    print(f"   Passed: {passed}/{total}")
    print(f"   Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Twitter Fetcher ready for production!")
    else:
        print("⚠️ Some tests failed. Check configuration and API limits.")


if __name__ == "__main__":
    asyncio.run(main()) 