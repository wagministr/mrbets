"""
twitter_fetcher.py

Собирает релевантные твиты от экспертов и по ключевым словам используя TwitterAPI.io.
Отправляет обработанные данные в Redis Stream для дальнейшей обработки.

Updated: 2025-01-XX - Адаптирован для TwitterAPI.io
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import httpx
import redis.asyncio as redis
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

logger = logging.getLogger(__name__)

# Конфигурация TwitterAPI.io
TWITTERAPI_IO_BASE_URL = "https://api.twitterapi.io"
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_RATE_LIMIT_DELAY = 2  # Секунды между запросами
MAX_TWEETS_PER_REQUEST = 20  # TwitterAPI.io возвращает ~20 твитов на страницу

# Экспертные аккаунты для мониторинга
EXPERT_ACCOUNTS = [
    "OptaJoe",
    "ESPN_FC", 
    "FabrizioRomano",
    "SkySportsNews",
    "BBCSport",
    "SkySports",
    "TheAthleticFC",
    "guardian_sport",
    "TelegraphSport"
]

# Ключевые слова и хэштеги для поиска
FOOTBALL_KEYWORDS = [
    "#PremierLeague",
    "#UCL", 
    "#ChampionsLeague",
    "#transfer",
    "#injury",
    "#TeamNews",
    "#MatchPreview",
    "#Football",
    "#Soccer",
    "#UEFA",
    "#FIFA"
]

# Рейтинги важности источников
SOURCE_RELIABILITY = {
    "OptaJoe": 0.95,
    "ESPN_FC": 0.90,
    "FabrizioRomano": 0.92,
    "SkySportsNews": 0.88,
    "BBCSport": 0.85,
    "SkySports": 0.82,
    "TheAthleticFC": 0.88,
    "guardian_sport": 0.80,
    "TelegraphSport": 0.78
}

# Redis настройки
REDIS_STREAM_NAME = "stream:raw_events"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class TwitterAPIClient:
    """Клиент для работы с TwitterAPI.io"""
    
    def __init__(self):
        self.api_key = os.getenv("TWITTERAPI_IO_KEY")
        if not self.api_key:
            raise ValueError("TWITTERAPI_IO_KEY environment variable must be set")
            
        self.base_url = TWITTERAPI_IO_BASE_URL
        self.session = None
        
    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            timeout=DEFAULT_REQUEST_TIMEOUT,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
    
    async def advanced_search(
        self, 
        query: str, 
        query_type: str = "Latest",
        cursor: str = "",
        max_results: int = 20
    ) -> Dict[str, Any]:
        """
        Выполняет продвинутый поиск твитов
        
        Args:
            query: Поисковый запрос (см. Twitter advanced search syntax)
            query_type: "Latest" или "Top"
            cursor: Курсор для пагинации
            max_results: Максимальное количество результатов (не используется в API, но для логики)
        """
        endpoint = f"{self.base_url}/twitter/tweet/advanced_search"
        
        params = {
            "query": query,
            "queryType": query_type
        }
        
        if cursor:
            params["cursor"] = cursor
        
        try:
            logger.debug(f"TwitterAPI.io request: {endpoint} with query: {query}")
            response = await self.session.get(endpoint, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Добавляем задержку для соблюдения rate limits
            await asyncio.sleep(DEFAULT_RATE_LIMIT_DELAY)
            
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"TwitterAPI.io HTTP error {e.response.status_code}: {e.response.text}")
            return {"tweets": [], "has_next_page": False, "error": str(e)}
        except Exception as e:
            logger.error(f"TwitterAPI.io request error: {e}")
            return {"tweets": [], "has_next_page": False, "error": str(e)}


class TwitterFetcher:
    """Основной класс для сбора данных из Twitter через TwitterAPI.io"""
    
    def __init__(self):
        self.redis_client = None
        
    async def connect_redis(self):
        """Подключение к Redis"""
        try:
            self.redis_client = redis.from_url(REDIS_URL)
            await self.redis_client.ping()
            logger.info("✅ Подключение к Redis установлено")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Redis: {e}")
            raise

    async def fetch_expert_tweets(self, hours_back: int = 2) -> List[Dict[str, Any]]:
        """
        Получает последние твиты от экспертных аккаунтов
        
        Args:
            hours_back: Сколько часов назад искать твиты
        """
        logger.info(f"Получение твитов от {len(EXPERT_ACCOUNTS)} экспертных аккаунтов за последние {hours_back} часов")
        
        # Формируем временные ограничения
        since_time = datetime.now() - timedelta(hours=hours_back)
        since_str = since_time.strftime("%Y-%m-%d_%H:%M:%S_UTC")
        
        all_tweets = []
        
        async with TwitterAPIClient() as client:
            for username in EXPERT_ACCOUNTS:
                try:
                    # Формируем поисковый запрос для конкретного пользователя
                    query = f"from:{username} since:{since_str}"
                    
                    logger.debug(f"Поиск твитов для @{username}")
                    
                    response = await client.advanced_search(
                        query=query,
                        query_type="Latest"
                    )
                    
                    if "error" in response:
                        logger.warning(f"Ошибка получения твитов для @{username}: {response['error']}")
                        continue
                    
                    tweets = response.get("tweets", [])
                    if tweets:
                        processed_tweets = []
                        for tweet in tweets:
                            processed_tweet = self._process_tweet(tweet, username)
                            if processed_tweet:
                                processed_tweets.append(processed_tweet)
                        
                        all_tweets.extend(processed_tweets)
                        logger.info(f"Получено {len(processed_tweets)} релевантных твитов от @{username}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при получении твитов от @{username}: {e}")
                    continue
        
        logger.info(f"Всего получено {len(all_tweets)} твитов от экспертов")
        return all_tweets

    async def search_keyword_tweets(self, hours_back: int = 1, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Поиск твитов по ключевым словам
        
        Args:
            hours_back: Сколько часов назад искать
            max_results: Максимальное количество результатов
        """
        logger.info(f"Поиск твитов по ключевым словам за последние {hours_back} часов")
        
        # Формируем временные ограничения
        since_time = datetime.now() - timedelta(hours=hours_back)
        since_str = since_time.strftime("%Y-%m-%d_%H:%M:%S_UTC")
        
        all_tweets = []
        
        async with TwitterAPIClient() as client:
            # Объединяем ключевые слова в один запрос для эффективности
            keywords_query = " OR ".join(FOOTBALL_KEYWORDS)
            query = f"({keywords_query}) since:{since_str} lang:en"
            
            try:
                logger.debug(f"Поиск по ключевым словам: {query}")
                
                response = await client.advanced_search(
                    query=query,
                    query_type="Latest"
                )
                
                if "error" in response:
                    logger.warning(f"Ошибка поиска по ключевым словам: {response['error']}")
                    return []
                
                tweets = response.get("tweets", [])
                
                # Обрабатываем твиты
                for tweet in tweets[:max_results]:
                    processed_tweet = self._process_tweet(tweet)
                    if processed_tweet and self._is_football_relevant(tweet.get("text", "")):
                        all_tweets.append(processed_tweet)
                
                logger.info(f"Найдено {len(all_tweets)} релевантных твитов по ключевым словам")
                
            except Exception as e:
                logger.error(f"Ошибка поиска по ключевым словам: {e}")
        
        return all_tweets

    def _process_tweet(self, tweet: Dict[str, Any], expected_username: str = None) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает один твит в стандартный формат
        
        Args:
            tweet: Данные твита от TwitterAPI.io
            expected_username: Ожидаемое имя пользователя (для проверки)
        """
        try:
            # Извлекаем данные автора
            author = tweet.get("author", {})
            username = author.get("userName", "unknown")
            
            # Проверяем соответствие ожидаемому username (если задан)
            if expected_username and username.lower() != expected_username.lower():
                return None
            
            # Извлекаем основные данные твита
            tweet_id = tweet.get("id")
            text = tweet.get("text", "")
            created_at = tweet.get("createdAt")
            url = tweet.get("url", f"https://twitter.com/{username}/status/{tweet_id}")
            
            # Извлекаем метрики engagement
            metrics = {
                "retweet_count": tweet.get("retweetCount", 0),
                "reply_count": tweet.get("replyCount", 0),
                "like_count": tweet.get("likeCount", 0),
                "quote_count": tweet.get("quoteCount", 0),
                "view_count": tweet.get("viewCount", 0),
                "bookmark_count": tweet.get("bookmarkCount", 0)
            }
            
            # Рассчитываем engagement score
            engagement_score = self._calculate_engagement_score(metrics)
            
            # Определяем надежность источника
            reliability_score = SOURCE_RELIABILITY.get(username, 0.5)
            
            # Извлекаем дополнительные данные автора
            author_data = {
                "name": author.get("name", username),
                "username": username,
                "followers": author.get("followers", 0),
                "following": author.get("following", 0),
                "verified": author.get("isBlueVerified", False),
                "profile_picture": author.get("profilePicture"),
                "description": author.get("description", "")
            }
            
            # Извлекаем entities (hashtags, mentions, URLs)
            entities = tweet.get("entities", {})
            hashtags = [tag.get("text", "") for tag in entities.get("hashtags", [])]
            mentions = [mention.get("screen_name", "") for mention in entities.get("user_mentions", [])]
            urls = [url_obj.get("expanded_url", "") for url_obj in entities.get("urls", [])]
            
            return {
                "tweet_id": tweet_id,
                "text": text,
                "author": author_data,
                "created_at": created_at,
                "url": url,
                "metrics": metrics,
                "engagement_score": engagement_score,
                "reliability_score": reliability_score,
                "hashtags": hashtags,
                "mentions": mentions,
                "urls": urls,
                "language": tweet.get("lang", "en"),
                "is_reply": tweet.get("isReply", False),
                "source": tweet.get("source", "Twitter Web App")
            }
            
        except Exception as e:
            logger.error(f"Ошибка обработки твита {tweet.get('id', 'unknown')}: {e}")
            return None

    def _calculate_engagement_score(self, metrics: Dict[str, int]) -> float:
        """
        Рассчитывает score engagement на основе метрик
        Формула учитывает разные веса для разных типов взаимодействий
        """
        weights = {
            "like_count": 1.0,
            "retweet_count": 3.0,  # Ретвиты важнее лайков
            "reply_count": 2.0,
            "quote_count": 2.5,
            "view_count": 0.01,     # Просмотры имеют малый вес
            "bookmark_count": 1.5
        }
        
        score = 0.0
        for metric, count in metrics.items():
            if metric in weights and count > 0:
                score += count * weights[metric]
        
        return round(score, 2)

    def _is_football_relevant(self, text: str) -> bool:
        """
        Проверяет, релевантен ли твит футболу
        Более строгая проверка для keyword search результатов
        """
        text_lower = text.lower()
        
        # Футбольные термины
        football_terms = [
            "goal", "goals", "match", "game", "player", "team", "coach", "manager",
            "transfer", "injury", "injured", "lineup", "squad", "formation",
            "premier league", "champions league", "uefa", "fifa", "football", "soccer",
            "striker", "midfielder", "defender", "goalkeeper", "penalty", "free kick",
            "corner", "offside", "var", "referee", "yellow card", "red card",
            "stadium", "fixture", "league", "tournament", "championship"
        ]
        
        # Названия лиг
        leagues = [
            "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
            "ucl", "europa league", "champions league", "world cup", "euros"
        ]
        
        # Проверяем наличие футбольных терминов
        for term in football_terms + leagues:
            if term in text_lower:
                return True
        
        return False

    async def send_to_redis_stream(self, tweets: List[Dict[str, Any]]):
        """Отправляет обработанные твиты в Redis Stream"""
        if not tweets:
            logger.info("Нет твитов для отправки в Redis")
            return
        
        if not self.redis_client:
            await self.connect_redis()
        
        success_count = 0
        
        for tweet in tweets:
            try:
                # Формируем событие для Redis Stream
                event_data = {
                    "event_type": "twitter_content",
                    "source": "twitter",
                    "match_id": tweet.get("match_id") or "",  # Исправляем None
                    "timestamp": int(time.time()),
                    "payload": json.dumps({
                        "tweet_id": tweet["tweet_id"],
                        "full_text": tweet["text"],
                        "author_username": tweet["author"]["username"],
                        "author_name": tweet["author"]["name"],
                        "author_followers": tweet["author"]["followers"],
                        "author_verified": tweet["author"]["verified"],
                        "created_at": tweet["created_at"],
                        "engagement_score": tweet["engagement_score"],
                        "reliability_score": tweet["reliability_score"],
                        "hashtags": tweet["hashtags"],
                        "mentions": tweet["mentions"],
                        "urls": tweet["urls"],
                        "metrics": tweet["metrics"],
                        "is_reply": tweet["is_reply"],
                        "language": tweet["language"]
                    }),
                    "meta": json.dumps({
                        "url": tweet["url"],
                        "source_type": "expert_account" if tweet["author"]["username"] in EXPERT_ACCOUNTS else "keyword_search",
                        "processed_at": datetime.now().isoformat(),
                        "api_source": "twitterapi.io"
                    })
                }
                
                # Отправляем в Redis Stream
                stream_id = await self.redis_client.xadd(REDIS_STREAM_NAME, event_data)
                success_count += 1
                
                logger.debug(f"Твит {tweet['tweet_id']} отправлен в Redis с ID: {stream_id}")
                
            except Exception as e:
                logger.error(f"Ошибка отправки твита {tweet.get('tweet_id', 'unknown')} в Redis: {e}")
        
        logger.info(f"✅ {success_count}/{len(tweets)} твитов успешно отправлено в Redis Stream")

    async def run_expert_monitoring(self, hours_back: int = 2):
        """Запускает мониторинг экспертных аккаунтов"""
        logger.info(f"🚀 Запуск мониторинга экспертов (период: {hours_back} часов)")
        
        tweets = await self.fetch_expert_tweets(hours_back)
        
        if tweets:
            await self.send_to_redis_stream(tweets)
            logger.info(f"✅ Мониторинг экспертов завершен: обработано {len(tweets)} твитов")
        else:
            logger.info("ℹ️ Мониторинг экспертов завершен: новых твитов не найдено")

    async def run_keyword_search(self, hours_back: int = 1, max_results: int = 50):
        """Запускает поиск по ключевым словам"""
        logger.info(f"🔍 Запуск поиска по ключевым словам (период: {hours_back} часов)")
        
        tweets = await self.search_keyword_tweets(hours_back, max_results)
        
        if tweets:
            await self.send_to_redis_stream(tweets)
            logger.info(f"✅ Поиск по ключевым словам завершен: обработано {len(tweets)} твитов")
        else:
            logger.info("ℹ️ Поиск по ключевым словам завершен: новых твитов не найдено")

    async def close(self):
        """Закрытие соединений"""
        if self.redis_client:
            await self.redis_client.close()


async def main_twitter_task(mode: str = "both", hours_back: int = 2):
    """
    Основная функция для запуска Twitter fetcher
    
    Args:
        mode: "experts", "keywords", или "both"
        hours_back: Период поиска в часах
    """
    fetcher = TwitterFetcher()
    
    try:
        await fetcher.connect_redis()
        
        if mode in ["experts", "both"]:
            await fetcher.run_expert_monitoring(hours_back)
        
        if mode in ["keywords", "both"]:
            await fetcher.run_keyword_search(hours_back, max_results=50)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в main_twitter_task: {e}")
        raise
    finally:
        await fetcher.close()


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Режим можно передать как аргумент командной строки
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    hours_back = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    
    print(f"🐦 Запуск Twitter Fetcher (TwitterAPI.io)")
    print(f"Режим: {mode}")
    print(f"Период: {hours_back} часов")
    
    asyncio.run(main_twitter_task(mode, hours_back)) 