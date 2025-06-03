#!/usr/bin/env python3
"""
test_isolated_twitter.py

Изолированный тест Twitter Fetcher без Docker-зависимостей
Используется только для проверки TwitterAPI.io интеграции
"""

import asyncio
import os
import sys
import logging
from datetime import datetime

# Добавляем путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_twitterapi_direct():
    """Прямой тест TwitterAPI.io без Redis"""
    print("🐦 Тестирование TwitterAPI.io (изолированно)")
    print("=" * 50)
    
    try:
        from fetchers.twitter_fetcher import TwitterAPIClient
        
        # Проверка API ключа
        api_key = os.getenv("TWITTERAPI_IO_KEY")
        if not api_key:
            print("❌ TWITTERAPI_IO_KEY не установлен")
            print("💡 Экспортируйте переменную: export TWITTERAPI_IO_KEY=your_key")
            return False
        
        print(f"✅ API ключ найден (длина: {len(api_key)} символов)")
        
        # Тест подключения
        async with TwitterAPIClient() as client:
            print("\n🔍 Тестирование поиска твитов...")
            
            # Простой поиск
            query = "from:OptaJoe"
            response = await client.advanced_search(query, query_type="Latest")
            
            if "error" in response:
                print(f"❌ Ошибка API: {response['error']}")
                return False
            
            tweets = response.get("tweets", [])
            print(f"✅ Получено {len(tweets)} твитов от OptaJoe")
            
            # Показать один пример твита
            if tweets:
                tweet = tweets[0]
                author = tweet.get("author", {})
                print(f"\n📝 Пример твита:")
                print(f"   Автор: {author.get('name', 'Unknown')} (@{author.get('userName', 'unknown')})")
                print(f"   Текст: {tweet.get('text', 'No text')[:100]}...")
                print(f"   Лайки: {tweet.get('likeCount', 0)}")
                print(f"   Ретвиты: {tweet.get('retweetCount', 0)}")
            
            return True
            
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("💡 Убедитесь что установлены зависимости: pip install httpx python-dotenv")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

async def test_twitter_fetcher_mock():
    """Тест Twitter Fetcher с mock Redis"""
    print("\n🔄 Тестирование Twitter Fetcher с mock Redis")
    print("=" * 50)
    
    try:
        # Mock Redis client
        class MockRedis:
            async def ping(self):
                return True
            
            async def xadd(self, stream_name, data):
                print(f"📨 Mock Redis: добавлен твит в stream {stream_name}")
                return f"mock-stream-id-{datetime.now().timestamp()}"
            
            async def close(self):
                pass
        
        from fetchers.twitter_fetcher import TwitterFetcher
        
        # Создаем fetcher с mock Redis
        fetcher = TwitterFetcher()
        fetcher.redis_client = MockRedis()
        
        print("✅ Mock Redis подключен")
        
        # Тест получения твитов экспертов
        print("\n🔍 Тестирование мониторинга экспертов...")
        tweets = await fetcher.fetch_expert_tweets(hours_back=24)  # 24 часа для больших шансов найти твиты
        
        if tweets:
            print(f"✅ Получено {len(tweets)} твитов от экспертов")
            
            # Отправляем в mock Redis
            await fetcher.send_to_redis_stream(tweets)
            
            # Статистика по экспертам
            expert_stats = {}
            for tweet in tweets:
                username = tweet["author"]["username"]
                expert_stats[username] = expert_stats.get(username, 0) + 1
            
            print("\n📊 Статистика по экспертам:")
            for expert, count in expert_stats.items():
                print(f"   @{expert}: {count} твитов")
        else:
            print("⚠️ Твиты от экспертов не найдены (возможно они не публиковали недавно)")
        
        await fetcher.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Twitter Fetcher: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    print("🧪 Изолированное тестирование Twitter Fetcher")
    print("Проверяет работу без Docker и Redis зависимостей")
    print()
    
    # Проверка переменных окружения
    from dotenv import load_dotenv
    load_dotenv()
    
    success_count = 0
    total_tests = 2
    
    # Тест 1: Прямой API
    if await test_twitterapi_direct():
        success_count += 1
    
    # Тест 2: Fetcher с mock
    if await test_twitter_fetcher_mock():
        success_count += 1
    
    # Результаты
    print("\n" + "=" * 50)
    print(f"📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 50)
    print(f"Пройдено: {success_count}/{total_tests} тестов")
    
    if success_count == total_tests:
        print("🎉 Все тесты пройдены! TwitterAPI.io работает корректно")
        print("💡 Проблема скорее всего в Docker сетевых настройках")
    elif success_count > 0:
        print("⚠️ Частичный успех - проверьте конфигурацию")
    else:
        print("❌ Все тесты провалились - проверьте API ключ и соединение")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1) 