# 📊 MrBets.ai Data Architecture & Flow

## 🎯 **Обзор системы данных**

MrBets.ai использует многоуровневую архитектуру данных для создания экспертных прогнозов, которые недоступны обычным беттерам. Система объединяет:

1. **Живой контент** (новости, социальные сети, видео)
2. **Статистические данные** (API футбольных данных)  
3. **Рыночные данные** (коэффициенты букмекеров)
4. **Проприетарную аналитику** (AI обработка и векторный поиск)

---

## 🔄 **Поток данных (Data Pipeline)**

```
📡 SOURCES → 🔄 FETCHERS → 📊 PROCESSORS → 🧠 AI ANALYSIS → 💰 PREDICTIONS
```

### **Этап 1: Источники данных**

#### 🌐 **Живой контент (Real-time Content)**
- **BBC Sport RSS** - официальные новости ✅
- **ESPN RSS** - экспертная аналитика ✅
- **Twitter API** - мнения экспертов (@OptaJoe, @ESPN_FC) ✅ **НОВЫЙ!**
- **Telegram каналы** - инсайдерская информация (🔄 в планах)
- **YouTube** - пресс-конференции, анализ (Whisper транскрипция) ✅ **НОВЫЙ!**

#### 📈 **Статистические API**
- **API-Football**:
  - Составы команд и травмы
  - Статистика игроков (голы, передачи, рейтинги)
  - Результаты матчей и форма команд
  - Head-to-head история
  - Статистика домашних/гостевых игр
  
#### 💸 **Рыночные данные**
- **The Odds API**:
  - Live коэффициенты от множества букмекеров
  - Движение линий в реальном времени
  - Pre-match и Live odds
  - Маржа букмекеров по разным рынкам

---

### **Этап 2: Сбор данных (Fetchers)**

#### 📰 **Content Fetchers**
```python
# backend/fetchers/scraper_fetcher.py ✅
- Парсит RSS feeds каждые 15 минут
- Извлекает полный текст статей
- Определяет релевантность командам через NER
- Отправляет в Redis Stream: raw_events

# backend/fetchers/twitter_fetcher.py ✅ НОВЫЙ!
- Мониторинг экспертных аккаунтов (OptaJoe, ESPN_FC, FabrizioRomano)
- Поиск по хештегам и ключевым словам
- Engagement score для определения важности твитов
- Rate limiting и дедупликация

# backend/fetchers/youtube_fetcher.py ✅ НОВЫЙ!
- Мониторинг каналов клубов и лиг (Premier League, Arsenal, etc.)
- yt-dlp для скачивания аудио
- Whisper для транскрипции в текст
- Фильтрация по релевантности и длительности

# backend/fetchers/telegram_fetcher.py (planned)
- Bot API для мониторинга каналов
- Анализ сообщений от инсайдеров
- Проверка достоверности источников
```

#### 📊 **Statistical Fetchers**
```python
# backend/fetchers/rest_fetcher.py
- API-Football: составы, травмы, статистика
- Обновление каждые 30 минут перед матчами
- Сохранение в Supabase: teams, players, fixtures

# backend/fetchers/odds_fetcher.py
- The Odds API: live коэффициенты
- Отслеживание движения линий
- Определение value bets opportunities
```

---

### **Этап 3: Обработка контента (LLM Content Analyzer)**

#### 🧠 **Умная обработка контента**
```python
# backend/processors/llm_content_analyzer.py

1. Получает сырой контент из Redis Stream
2. LLM (GPT-4o) анализирует и разбивает на "умные чанки":
   - Определяет тип информации (травма, тактика, форма)
   - Извлекает упоминания команд и игроков  
   - Оценивает важность (1-5) и тональность
   - Прогнозирует влияние на результат матча

3. Entity Linking в Supabase:
   - Связывает команды с team_id
   - Связывает игроков с player_id
   - Создает structured metadata

4. Векторизация и хранение:
   - OpenAI Embeddings для семантического поиска
   - Сохранение в Pinecone с метаданными
   - Дублирование в Supabase для backup
```

---

### **Этап 4: Retrieval & Analysis**

#### 🔍 **Контекстный поиск (MatchContextRetriever)**
```python
# backend/processors/retriever_builder.py

1. Получает fixture_id от worker
2. Определяет home_team_id и away_team_id
3. Ищет в Pinecone релевантные чанки:
   - Фильтр по linked_team_ids
   - Фильтр по дате (последние 14 дней)
   - Semantic search по содержанию
4. Ранжирует по важности и свежести
5. Формирует структурированный контекст для LLM
```

#### 🧠 **AI Анализ (LLMReasoner)**
```python
# backend/processors/llm_reasoner.py

1. Получает контекст от Retriever
2. Добавляет live коэффициенты от Odds API
3. Применяет экспертный FOMO-промпт:
   - Техническая терминология
   - "Systematic market inefficiencies"
   - "Institutional-grade analytics"
   - Временные окна эксплуатации
4. Генерирует JSON с прогнозом и value bets
```

---

## 🗄️ **Схема хранения данных**

### **Supabase (PostgreSQL)**

#### Основные таблицы:
```sql
-- Матчи
fixtures (fixture_id, home_team_id, away_team_id, event_date, status)

-- Команды и игроки  
teams (team_id, name, league_id, venue_info)
players (player_id, name, team_id, position, statistics)

-- Обработанный контент
processed_documents (id, source, document_title, reliability_score, overall_entities)

-- AI прогнозы (ОБНОВЛЕННАЯ СХЕМА)
ai_predictions (
  id, fixture_id, type,
  chain_of_thought, final_prediction,
  confidence_score, risk_factors, key_insights,
  value_bets, context_quality, processing_time_seconds,
  model_version, generated_at
)
```

### **Pinecone (Vector Database)**
```json
{
  "vector_id": "doc_123_chunk_1",
  "embedding": [0.1, 0.2, ...], // 1536-dim
  "metadata": {
    "source": "bbc_sport|twitter|youtube",
    "chunk_type": "Injury Update", 
    "importance_score": 5,
    "linked_team_ids": ["34", "40"],
    "linked_player_ids": ["567"],
    "document_timestamp": "2024-01-15T10:00:00Z",
    "document_title": "Arsenal striker ruled out",
    "engagement_score": 125.5  // Для Twitter/YouTube контента
  }
}
```

### **Redis (Queues & Streams)**
```
Queues:
- queue:fixtures (fixture_id для обработки)

Streams:  
- stream:raw_events (сырой контент от всех fetchers)
- stream:processed_events (обработанные чанки)
```

---

## 🔑 **Переменные окружения (.env)**

```bash
# Database & Storage
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_service_key
REDIS_URL=redis://redis:6379/0

# AI & ML
OPENAI_API_KEY=sk-xxx
PINECONE_API_KEY=xxx
PINECONE_ENVIRONMENT=xxx
PINECONE_INDEX=mrbets-content-chunks

# Football Data APIs
API_FOOTBALL_KEY=xxx
ODDS_API_KEY=xxx

# Social Media APIs (НОВЫЕ!)
TWITTER_BEARER_TOKEN=xxx  # Twitter API v2 Bearer Token
YOUTUBE_API_KEY=xxx       # YouTube Data API v3 Key

# Audio Processing (НОВЫЕ!)
WHISPER_MODEL=medium      # base|small|medium|large
TEMP_AUDIO_DIR=/tmp/mrbets_audio

# Translation (planned)
YANDEX_API_KEY=xxx
YANDEX_FOLDER_ID=xxx
```

---

## ⚡ **Реальные преимущества системы**

### **Что дает FOMO пользователям:**

1. **"Proprietary Intelligence Database"** 
   - Реально: Pinecone с векторным поиском по 1000+ источникам
   - Восприятие: "Закрытая база данных, недоступная обычным беттерам"

2. **"Real-time Social Intelligence"** ✅ **НОВЫЙ!**
   - Реально: Twitter мониторинг экспертов + YouTube транскрипции  
   - Восприятие: "Мгновенный анализ инсайдерской информации"

3. **"Market Inefficiency Detection Algorithms"**
   - Реально: Сравнение AI прогнозов с букмекерскими коэффициентами  
   - Восприятие: "Алгоритмы находят ошибки букмекеров"

4. **"Institutional-Grade Analytics"**
   - Реально: GPT-4o анализ + векторный поиск релевантного контента
   - Восприятие: "Анализ уровня профессиональных инвесторов"

5. **"Temporal Exploitation Windows"**
   - Реально: Быстрое обновление прогнозов при новой информации
   - Восприятие: "Ограниченное время до изменения коэффициентов"

---

## 🔄 **Автоматизация и обновления**

### **Cron расписание:**
```bash
# Каждые 10 минут - Twitter мониторинг (НОВЫЙ!)
*/10 * * * * python -m fetchers.twitter_fetcher both 2

# Каждые 15 минут - сбор контента
*/15 * * * * python -m fetchers.scraper_fetcher

# Каждые 2 часа - YouTube мониторинг (НОВЫЙ!)
0 */2 * * * python -m fetchers.youtube_fetcher 24 2

# Каждые 30 минут - обновление статистики  
*/30 * * * * python -m fetchers.rest_fetcher

# Каждые 5 минут - live коэффициенты
*/5 * * * * python -m fetchers.odds_fetcher

# Каждый час - обновление прогнозов
0 * * * * python -m jobs.scan_fixtures
```

### **Триггеры обновления прогнозов:**
- Новые важные новости (importance_score >= 4)
- Вирусные твиты от экспертов (engagement_score > 100) ✅ **НОВЫЙ!**
- Пресс-конференции и интервью (YouTube транскрипции) ✅ **НОВЫЙ!**
- Изменения составов или травмы ключевых игроков
- Значительные движения коэффициентов (>10%)
- За 2 часа до матча (финальное обновление)

---

## 🎯 **Итоговая ценность для пользователей**

Система предоставляет **реальные аналитические преимущества**:

✅ **Скорость**: Анализ новостей и их влияния за минуты  
✅ **Полнота**: 10+ источников данных против 1-2 у конкурентов  
✅ **Социальная аналитика**: Twitter + YouTube мониторинг ✅ **НОВЫЙ!**
✅ **Интеллект**: AI понимает контекст, а не просто цифры  
✅ **Эксклюзивность**: Векторный поиск по всему контенту  
✅ **Точность**: Каждый прогноз основан на последних данных

Но **подается как**:
🔥 **"Institutional-grade proprietary analytics"**  
🔥 **"Real-time social intelligence monitoring"** ✅ **НОВЫЙ!**
🔥 **"Market inefficiency detection algorithms"**  
🔥 **"Limited temporal exploitation windows"**  
🔥 **"Systematic edge before market adjustment"**

---

Это создает **обоснованное FOMO** - пользователи получают реальную ценность, но чувствуют что имеют доступ к чему-то особенному и ограниченному во времени. 