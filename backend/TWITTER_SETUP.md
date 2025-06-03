# 🐦 Twitter Fetcher Setup — TwitterAPI.io Integration

Руководство по настройке и использованию Twitter fetcher с использованием TwitterAPI.io вместо официального Twitter API.

## 📋 Требования

1. **API ключ от TwitterAPI.io**: Зарегистрируйтесь на [twitterapi.io](https://twitterapi.io) и получите API ключ
2. **Redis**: Для очереди сообщений (локально или через docker-compose)
3. **Python зависимости**: Все необходимые пакеты указаны в `requirements.txt`

## 🔧 Настройка

### 1. Переменные окружения

#### Для локального тестирования:
```bash
# Twitter API через TwitterAPI.io
export TWITTERAPI_IO_KEY=ваш_ключ_от_twitterapi_io

# Redis для локального использования (опционально)
export REDIS_URL=redis://localhost:6379/0
```

#### Для Docker/Production:
```bash
# В .env файле
TWITTERAPI_IO_KEY=ваш_ключ_от_twitterapi_io
REDIS_URL=redis://redis:6379/0
```

### 2. Установка Redis (для локального тестирования)

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

#### Альтернативно через Docker:
```bash
docker run -d -p 6379:6379 --name redis-test redis:7
```

### 3. Проверка настройки

#### Быстрая проверка API (без Redis):
```bash
export TWITTERAPI_IO_KEY=ваш_ключ
python3 backend/test_twitter_fetcher.py
```

#### Полная проверка (с Redis):
```bash
# Убедитесь что Redis запущен
redis-cli ping

# Запустите тест
export TWITTERAPI_IO_KEY=ваш_ключ
python3 backend/test_twitter_fetcher.py
```

Обновленный тест автоматически:
- ✅ Проверит подключение к TwitterAPI.io
- ✅ Найдет доступный Redis (localhost/docker)  
- ✅ Протестирует мониторинг экспертов
- ✅ Протестирует поиск по ключевым словам
- ✅ Проверит интеграцию с Redis

## 🚀 Использование

### Локальное тестирование

```bash
# Из корня проекта
export TWITTERAPI_IO_KEY=ваш_ключ
python3 backend/test_twitter_fetcher.py

# Сбор данных локально (без Redis)
python3 -m backend.fetchers.twitter_fetcher both 2

# Сбор данных с Redis
export REDIS_URL=redis://localhost:6379/0
python3 -m backend.fetchers.twitter_fetcher both 2
```

### Запуск в Docker

```bash
# Через docker-compose
docker-compose up redis -d
python3 -m fetchers.twitter_fetcher both 2
```

### Программное использование

```python
import os
from fetchers.twitter_fetcher import TwitterFetcher

# Для локального использования
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

async def collect_twitter_data():
    fetcher = TwitterFetcher()
    
    try:
        await fetcher.connect_redis()
        
        # Мониторинг экспертов
        await fetcher.run_expert_monitoring(hours_back=2)
        
        # Поиск по ключевым словам
        await fetcher.run_keyword_search(hours_back=1, max_results=50)
        
    finally:
        await fetcher.close()
```

## 📊 Отслеживаемые источники

### Экспертные аккаунты
- `@OptaJoe` — Статистика и факты (надежность: 95%)
- `@ESPN_FC` — ESPN Football (надежность: 90%)
- `@FabrizioRomano` — Трансферные новости (надежность: 92%)
- `@SkySportsNews` — Sky Sports (надежность: 88%)
- `@BBCSport` — BBC Sport (надежность: 85%)
- `@SkySports` — Sky Sports (надежность: 82%)
- `@TheAthleticFC` — The Athletic (надежность: 88%)
- `@guardian_sport` — Guardian Sport (надежность: 80%)
- `@TelegraphSport` — Telegraph Sport (надежность: 78%)

### Ключевые слова и хэштеги
- `#PremierLeague`, `#UCL`, `#ChampionsLeague`
- `#transfer`, `#injury`, `#TeamNews`
- `#MatchPreview`, `#Football`, `#Soccer`
- `#UEFA`, `#FIFA`

## 📈 Метрики engagement

Система рассчитывает engagement score для каждого твита:

```python
score = (
    likes × 1.0 +
    retweets × 3.0 +
    replies × 2.0 +
    quotes × 2.5 +
    views × 0.01 +
    bookmarks × 1.5
)
```

## 🔄 Интеграция с данными

### Redis Stream

Все твиты отправляются в Redis Stream `stream:raw_events` с данными:

```json
{
  "event_type": "twitter_content",
  "source": "twitter",
  "match_id": null,
  "timestamp": 1672531200,
  "payload": {
    "tweet_id": "123456789",
    "full_text": "Arsenal confirm...",
    "author_username": "OptaJoe",
    "author_name": "OptaJoe",
    "author_followers": 2500000,
    "author_verified": true,
    "created_at": "2024-01-01T12:00:00Z",
    "engagement_score": 150.5,
    "reliability_score": 0.95,
    "hashtags": ["PremierLeague", "Arsenal"],
    "mentions": ["Arsenal"],
    "urls": ["https://..."],
    "metrics": {
      "like_count": 1000,
      "retweet_count": 50,
      "reply_count": 25,
      "quote_count": 10,
      "view_count": 50000,
      "bookmark_count": 100
    },
    "is_reply": false,
    "language": "en"
  },
  "meta": {
    "url": "https://twitter.com/OptaJoe/status/123456789",
    "source_type": "expert_account",
    "processed_at": "2024-01-01T12:05:00Z",
    "api_source": "twitterapi.io"
  }
}
```

### Дальнейшая обработка

После отправки в Redis Stream данные обрабатываются:

1. **LLM Content Analyzer** — анализирует содержание и связывает с командами/игроками
2. **Vector Search** — создает эмбеддинги для семантического поиска
3. **Match Context Retriever** — находит релевантный контент для матчей
4. **LLM Reasoner** — использует контент для генерации прогнозов

## 🛠️ Настройка экспертных аккаунтов

Для добавления новых аккаунтов отредактируйте `EXPERT_ACCOUNTS` в `twitter_fetcher.py`:

```python
EXPERT_ACCOUNTS = [
    "OptaJoe",
    "ESPN_FC",
    "YourNewExpert",  # Добавьте здесь
    # ...
]

# Добавьте рейтинг надежности
SOURCE_RELIABILITY = {
    "OptaJoe": 0.95,
    "ESPN_FC": 0.90,
    "YourNewExpert": 0.85,  # И здесь
    # ...
}
```

## 🚨 Ограничения и рекомендации

### Rate Limits
- TwitterAPI.io: ~20 твитов на запрос
- Задержка 2 секунды между запросами
- Рекомендуется запускать не чаще чем раз в 15-30 минут

### Рекомендуемое расписание cron
```bash
# Мониторинг экспертов каждые 30 минут
*/30 * * * * cd /path/to/backend && python3 -m fetchers.twitter_fetcher experts 2

# Поиск по ключевым словам каждый час
0 * * * * cd /path/to/backend && python3 -m fetchers.twitter_fetcher keywords 1
```

### Качество данных
- Tweets фильтруются по релевантности футболу
- Приоритет отдается экспертным аккаунтам (выше reliability_score)
- Автоматическое исключение ретвитов и неанглийских твитов при поиске

## 🔍 Отладка

### Проверка Redis подключения
```bash
# Локальный Redis
redis-cli ping

# Docker Redis
docker exec redis redis-cli ping
```

### Логи
Включите подробное логирование:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Проверка Redis Stream
```bash
# Локально
redis-cli XREAD STREAMS stream:raw_events 0

# Docker
docker exec redis redis-cli XREAD STREAMS stream:raw_events 0
```

### Проверка API ключа
```bash
curl -H "X-API-Key: ваш_ключ" "https://api.twitterapi.io/twitter/tweet/advanced_search?query=football"
```

## 📞 Решение проблем

### Ошибка подключения к Redis
```
Error -2 connecting to redis:6379
```

**Решения:**
1. **Локальное тестирование**: Убедитесь что Redis запущен локально
   ```bash
   sudo systemctl start redis
   # или
   docker run -d -p 6379:6379 redis:7
   ```

2. **Переопределите Redis URL**:
   ```bash
   export REDIS_URL=redis://localhost:6379/0
   python3 backend/test_twitter_fetcher.py
   ```

3. **Проверьте доступность**:
   ```bash
   redis-cli ping  # Должен ответить PONG
   ```

### API ключ TwitterAPI.io
1. Проверьте ключ на [twitterapi.io](https://twitterapi.io)
2. Убедитесь что переменная установлена:
   ```bash
   echo $TWITTERAPI_IO_KEY
   ```

### Низкое количество найденных твитов
- Это нормально для некоторых периодов времени
- Попробуйте увеличить `hours_back` параметр
- Проверьте активность экспертных аккаунтов

---

**Обновлено**: 2025-06-01  
**Статус**: Готов к использованию с локальным и Docker тестированием 