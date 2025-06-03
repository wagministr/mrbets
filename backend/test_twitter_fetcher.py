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

from fetchers.twitter_fetcher import TwitterFetcher, TwitterAPIClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_twitter_api_connection():
    """Тестирует подключение к TwitterAPI.io"""
    print("🔧 Тестирование подключения к TwitterAPI.io...")
    
    try:
        async with TwitterAPIClient() as client:
            # Простой тестовый запрос
            response = await client.advanced_search("football", max_results=5)
            
            if "error" in response:
                print(f"❌ Ошибка подключения: {response['error']}")
                return False
            
            tweets = response.get("tweets", [])
            print(f"✅ Подключение успешно! Найдено {len(tweets)} тестовых твитов")
            
            if tweets:
                first_tweet = tweets[0]
                print(f"📝 Пример твита: {first_tweet.get('text', '')[:100]}...")
            
            return True
            
    except Exception as e:
        print(f"❌ Ошибка тестирования API: {e}")
        return False


async def test_expert_monitoring():
    """Тестирует мониторинг экспертных аккаунтов"""
    print("\n👑 Тестирование мониторинга экспертов...")
    
    fetcher = TwitterFetcher()
    
    try:
        # Пытаемся получить твиты от экспертов
        tweets = await fetcher.fetch_expert_tweets(hours_back=24)  # 24 часа для большей вероятности найти что-то
        
        print(f"📊 Найдено {len(tweets)} твитов от экспертов")
        
        # Показываем статистику по источникам
        sources = {}
        for tweet in tweets:
            username = tweet["author"]["username"]
            sources[username] = sources.get(username, 0) + 1
        
        if sources:
            print("📈 Статистика по источникам:")
            for username, count in sources.items():
                print(f"  @{username}: {count} твитов")
                
        # Показываем пример твита с лучшим engagement
        if tweets:
            best_tweet = max(tweets, key=lambda t: t["engagement_score"])
            print(f"\n🏆 Твит с лучшим engagement ({best_tweet['engagement_score']}):")
            print(f"  @{best_tweet['author']['username']}: {best_tweet['text'][:150]}...")
        
        return len(tweets) > 0
        
    except Exception as e:
        print(f"❌ Ошибка тестирования экспертов: {e}")
        return False
    finally:
        await fetcher.close()


async def test_keyword_search():
    """Тестирует поиск по ключевым словам"""
    print("\n🔍 Тестирование поиска по ключевым словам...")
    
    fetcher = TwitterFetcher()
    
    try:
        tweets = await fetcher.search_keyword_tweets(hours_back=12, max_results=20)
        
        print(f"📊 Найдено {len(tweets)} релевантных твитов")
        
        # Анализируем найденные хэштеги
        all_hashtags = []
        for tweet in tweets:
            all_hashtags.extend(tweet["hashtags"])
        
        if all_hashtags:
            from collections import Counter
            popular_hashtags = Counter(all_hashtags).most_common(5)
            print("🏷️ Популярные хэштеги:")
            for hashtag, count in popular_hashtags:
                print(f"  #{hashtag}: {count}")
        
        return len(tweets) > 0
        
    except Exception as e:
        print(f"❌ Ошибка тестирования поиска: {e}")
        return False
    finally:
        await fetcher.close()


async def check_redis_availability():
    """Проверяет доступность Redis на разных адресах"""
    import redis.asyncio as redis
    
    # Список возможных Redis URLs для тестирования
    redis_urls = [
        "redis://localhost:6379/0",  # Локальный Redis
        "redis://127.0.0.1:6379/0",  # Альтернативный localhost
        "redis://redis:6379/0"       # Docker контейнер
    ]
    
    for redis_url in redis_urls:
        try:
            client = redis.from_url(redis_url)
            await client.ping()
            await client.close()
            print(f"✅ Redis доступен на: {redis_url}")
            return redis_url
        except Exception as e:
            print(f"❌ Redis недоступен на {redis_url}: {e}")
    
    return None


async def test_redis_integration():
    """Тестирует интеграцию с Redis"""
    print("\n📡 Тестирование интеграции с Redis...")
    
    # Сначала проверяем доступность Redis
    available_redis_url = await check_redis_availability()
    
    if not available_redis_url:
        print("❌ Redis недоступен ни на одном из стандартных адресов")
        print("💡 Для локального тестирования запустите Redis:")
        print("   sudo apt install redis-server && sudo systemctl start redis")
        print("   или через Docker: docker run -d -p 6379:6379 redis:7")
        return False
    
    # Временно переопределяем REDIS_URL для тестирования
    original_redis_url = os.getenv("REDIS_URL")
    os.environ["REDIS_URL"] = available_redis_url
    
    fetcher = TwitterFetcher()
    
    try:
        await fetcher.connect_redis()
        print("✅ Подключение к Redis успешно")
        
        # Создаем тестовый твит
        test_tweet = {
            "tweet_id": "test_123",
            "text": "Test tweet for Redis integration",
            "author": {
                "username": "test_user",
                "name": "Test User",
                "followers": 1000,
                "verified": False
            },
            "created_at": datetime.now().isoformat(),
            "url": "https://twitter.com/test_user/status/test_123",
            "metrics": {
                "like_count": 10,
                "retweet_count": 5,
                "reply_count": 2,
                "quote_count": 1,
                "view_count": 100,
                "bookmark_count": 3
            },
            "engagement_score": 25.5,
            "reliability_score": 0.7,
            "hashtags": ["test"],
            "mentions": [],
            "urls": [],
            "language": "en",
            "is_reply": False,
            "source": "Twitter Web App"
        }
        
        await fetcher.send_to_redis_stream([test_tweet])
        print("✅ Тестовое сообщение отправлено в Redis Stream")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования Redis: {e}")
        return False
    finally:
        # Восстанавливаем оригинальный REDIS_URL
        if original_redis_url:
            os.environ["REDIS_URL"] = original_redis_url
        elif "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        
        await fetcher.close()


async def main():
    """Основная функция тестирования"""
    print("🐦 Запуск тестирования Twitter Fetcher (TwitterAPI.io)")
    print("=" * 60)
    
    # Проверяем наличие API ключа
    api_key = os.getenv("TWITTERAPI_IO_KEY")
    if not api_key:
        print("❌ ОШИБКА: Переменная TWITTERAPI_IO_KEY не установлена!")
        print("   Установите ключ API от TwitterAPI.io в переменную окружения")
        print("   export TWITTERAPI_IO_KEY=ваш_ключ")
        return
    
    print(f"🔑 API ключ найден: {api_key[:10]}...{api_key[-5:]}")
    
    # Показываем текущую настройку Redis
    current_redis = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"🔧 Текущая настройка Redis: {current_redis}")
    
    tests = [
        ("API Connection", test_twitter_api_connection),
        ("Expert Monitoring", test_expert_monitoring),
        ("Keyword Search", test_keyword_search),
        ("Redis Integration", test_redis_integration)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте {test_name}: {e}")
            results.append((test_name, False))
    
    # Итоговая сводка
    print("\n" + "="*60)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{test_name:.<30} {status}")
        if result:
            passed += 1
    
    print(f"\nОбщий результат: {passed}/{len(results)} тестов пройдено")
    
    if passed == len(results):
        print("🎉 ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ!")
        print("Twitter Fetcher готов к использованию с TwitterAPI.io")
    elif passed >= 3:
        print("✅ Основная функциональность работает!")
        print("Twitter Fetcher готов к использованию (без Redis интеграции)")
    else:
        print("⚠️ Некоторые тесты провалены. Проверьте конфигурацию.")


if __name__ == "__main__":
    asyncio.run(main()) 