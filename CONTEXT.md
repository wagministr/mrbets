# 📘 CONTEXT.md — Project Overview for MrBets.ai
_Last updated: 2025-04-29_

---

## 🎯 Project Evolution: MrBets.ai (Formerly WinPulse)

MrBets.ai is an AI-powered sports prediction platform that delivers pre-analyzed football match insights based on comprehensive data collection, advanced AI reasoning, and betting value assessment.

The project is evolving from a Next.js-only application with serverless functions to a robust monorepo architecture with a dedicated FastAPI backend for enhanced data processing capabilities.

---

## 🏗️ Architecture Overview

### Current Architecture
- **Frontend**: Next.js 14 with App Router deployed on Vercel
- **Database**: Supabase (PostgreSQL)
- **API Integrations**: API-Football, OpenAI
- **Automation**: Vercel Cron Jobs

### Planned Architecture
- **Frontend**: Next.js 14 (unchanged)
- **Backend**: FastAPI with microservices architecture
- **Data Processing**: Redis Streams for distributed processing
- **Vector Search**: Pinecone for semantic retrieval
- **Storage**: Supabase Storage for raw data
- **Additional Data Sources**: News sites, social media, video content

---

## 🧩 Key Functional Components

### 1. 🔄 **Fixtures Sync**
- Uses `API-Football` to fetch upcoming matches from select leagues (e.g., Premier League, La Liga)
- **Current**: Script: `/scripts/updateFixtures.ts`
- **Planned**: Python service: `/backend/jobs/scan_fixtures.py`
- Stores match data into `Supabase.fixtures`
- Triggered via cron job

### 2. 🧠 **AI Prediction Generation**
- Each match is processed by:
  - Fetching live stats & odds
  - Formatting a structured prompt
  - Sending to OpenAI (model: `o4-mini`, planned upgrade to `GPT-4o`)
  - Parsing AI response into:
    - `CHAIN OF THOUGHT`
    - `FINAL PREDICTION`
    - `VALUE BETS`
- **Current**: Script: `/scripts/generatePrediction.ts`
- **Planned**: Pipeline: 
  - Data collection via various fetchers
  - Pre-processing via `/backend/processors/pre_processor.py`
  - Retrieval via `/backend/processors/retriever_builder.py`
  - LLM reasoning via `/backend/processors/llm_reasoner.py`
- All results are stored in `Supabase.ai_predictions`

### 3. 📅 **Automated Processing**
- **Current**: Nightly cron job (4:00 AM UTC) runs two steps:
  - `run-update.js` → Updates fixtures
  - `run-all-predictions.js` → Generates predictions for unprocessed matches
  - Cron route: `/api/cron/daily-update`
  - Deployment: Vercel with `vercel.json` cron support
- **Planned**: Continuous processing:
  - Data collection every 30 minutes via cron
  - Redis Streams for distributed processing
  - Auto-refresh when significant changes detected (odds shifts, new content)

### 4. 💬 **User-Facing /ai Page**
- Users visit `/ai`
- See horizontally scrollable cards of upcoming matches
- Clicking a card:
  - Opens the prediction display
  - Loads prediction from `Supabase.ai_predictions`
  - Displays:
    - Chain of Thought
    - Final Prediction
    - List of Top 3 Value Bets
- If no prediction exists:
  - Fallback message: "AI prediction is being prepared..."

### 5. 🔐 **Auth & Visibility**
- Top matches in `/ai` preview are blurred unless the user logs in
- Login is email-based (OTP) using Supabase Auth
- After login, full dashboard unlocked

---

## 🔒 Database Structure (Supabase)

### Current Tables

#### `fixtures`
- `fixture_id`: integer (primary key)
- `league_id`: integer
- `home_id`: integer
- `away_id`: integer
- `utc_kickoff`: timestamp
- `status`: text
- `score_home`: integer
- `score_away`: integer
- `last_updated`: timestamp

#### `ai_predictions`
- `id`: uuid (primary key)
- `fixture_id`: integer (foreign key)
- `type`: text (e.g., "pre-match")
- `chain_of_thought`: text
- `final_prediction`: text
- `value_bets_json`: string (stringified array)
- `model_version`: text
- `generated_at`: timestamp
- `stale`: boolean (default: false)

### Planned Additional Tables

#### `raw_events`
- `id`: uuid (primary key)
- `match_id`: integer (foreign key)
- `source`: text (e.g., "twitter", "bbc", "youtube")
- `content_hash`: text (for deduplication)
- `content_path`: text (path in Supabase Storage)
- `metadata`: jsonb
- `reliability_score`: float
- `created_at`: timestamp

#### `emb_cache`
- `hash`: text (primary key)
- `vector`: vector (1536d)
- `created_at`: timestamp

---

## 📡 External APIs & Models

### Current Integrations

#### ✅ API-Football
- Used for: Fixtures, live odds, team data, predictions
- Called via `lib/apiFootball.ts`
- Rate-limited API with key-based access

#### ✅ OpenAI
- Used for: Text generation (reasoning, summary, betting logic)
- Model: `o4-mini`
- Called via `generatePrediction.ts` → OpenAI Chat Completion endpoint
- Responses are split into 3 sections and stored

### Planned Integrations

#### ⏳ OpenAI Embeddings
- Use: Vectorizing text for semantic search
- Model: `text-embedding-3-large`
- Will be called via: `/backend/processors/pre_processor.py`

#### ⏳ Pinecone
- Use: Vector database for similar document retrieval
- Will store all processed text embeddings
- Will be queried for context retrieval for each match

#### ⏳ BeautifulSoup + Requests
- Use: Scraping news sites and sports blogs
- Will extract clean text from HTML

#### ⏳ DeepL API
- Use: Translation services for non-English content
- Will ensure all analysis happens on English text

#### ⏳ Whisper
- Use: Transcription of YouTube videos and podcasts
- Model: medium or large-v3
- Will convert audio analysis to searchable text

#### ⏳ Twitter/Telegram APIs
- Use: Gathering expert opinions and community insights
- Will capture real-time discussions about upcoming matches

---

## 📊 Data Flow Pipeline (Planned)

```
[CRON] → scan_fixtures.py → redis:queue:fixtures (LIST) → worker_manager
                                       │ POP
                                       ▼
                   «data-collector workflow» (fan-out 5 fetcher tasks)
┌─────────────────────────────────────────────────────────────────────┐
│ rest_fetcher.py (API-Football)       → raw_events (STREAM)          │
│ scraper_fetcher.py (BBC/ESPN)        → raw_events (STREAM)          │
│ twitter_fetcher.py (filtered stream) → raw_events (STREAM)          │
│ telegram_fetcher.py (bot getUpdates) → raw_events (STREAM)          │
│ youtube_fetcher.py (yt-dlp+Whisper)  → raw_events (STREAM)          │
└─────────────────────────────────────────────────────────────────────┘
                     ▼ consumer-group:pre_processor (parallel workers)
     translate → split_chunks → reliability_score → embeddings → Storage/Pinecone/Postgres
                     ▼
           retriever_builder.py (sql filter + pinecone topK + dedup)
                     ▼
           llm_reasoner.py (prompt + live odds → GPT-4o) → JSON
                     ▼
           result_writer.py (UPSERT predictions, TTL 3h)
```

This pipeline will run automatically every 30 minutes, constantly updating the data store with fresh information and generating new predictions when needed.

---

## 🧪 Development Environment

### Current Environment
- Project is developed on Windows 11 + PowerShell
- Local script execution via `ts-node`
- Supabase MCP enabled for Cursor integration
- `.env` stores all API keys & model info

### Planned Environment
- Development on Windows 11 with WSL 2
- Docker + docker-compose for full system simulation
- Backend development in Python 3.11
- Frontend continues with Next.js/TypeScript
- Environment variables split between frontend and backend needs

---

## 💻 Repository Structure (Planned)

```
mrbets/                         # Repository name
├── frontend/                    # Current Next.js project
│   ├── src/                     # Frontend source code
│   ├── public/                  # Static files 
│   ├── package.json             # Frontend dependencies
│   └── ...                      # Other Next.js files
│
├── backend/                     # New FastAPI backend
│   ├── app/                     # Main FastAPI code
│   │   ├── main.py              # FastAPI entry point
│   │   ├── routers/             # API routes
│   │   └── models/              # Data schemas
│   ├── jobs/                    # Scripts for cron tasks
│   │   ├── scan_fixtures.py
│   │   └── worker.py
│   ├── fetchers/                # Data collection microservices
│   ├── processors/              # Data processors
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml           # For running the entire system
├── .github/                     # GitHub Actions
├── BACKEND.md                   # Backend documentation
└── CONTEXT.md                   # This file
```

---

## 🔜 Project Timeline (May 9 → August 9)

| Period | Goal | Deliverables |
|--------|------|--------------|
| May 09–15 | Dev environment + CI | docker-compose, GitHub Actions |
| May 16–22 | Queue demo | fixtures-scanner, Redis with tasks |
| May 23–29 | REST/Scraper fetchers | BBC + API-Football data in DB |
| May 30–Jun 05 | Whisper pipeline | YouTube texts in Storage/Postgres |
| Jun 06–12 | Pre-processor | Translation, chunks, embeddings |
| Jun 13–19 | Vector search | Pinecone Top-K API ready |
| Jun 20–26 | Retriever API | `/context/{match_id}` returns facts |
| Jun 27–Jul 03 | LLM draft | First JSON prediction saved |
| Jul 04–10 | TTL cache | Reading `predictions` on frontend |
| Jul 11–17 | Odds module | Live odds in prompt |
| Jul 18–24 | Frontend integration | Next.js match page shows prediction |
| Jul 25–31 | Affiliate links | Smart links + GTM events |
| Aug 01–07 | Load testing | 100 matches, <2 sec latency |
| Aug 08–09 | UI polish and release | Landing, animation, prod deploy |

---

## 🔑 Key Terms

| Term | What it is | In simple words |
|------|------------|----------------|
| **Redis** | In-memory data store | Ultra-fast task queue between services |
| **Redis Streams** | Message broker pattern | Ordered message queue with consumer groups |
| **Embeddings** | Text vectorization | Representing text meaning as numbers for search |
| **Hybrid Search** | Filter + vector search | First by team/date, then by meaning |
| **TTL** | Time To Live | Prediction validity period (3 hours) |
| **Chain-of-Thought** | Prompting method | LLM explicitly shows reasoning process |
| **Pinecone** | Vector database | Stores and searches semantically similar texts |
| **Whisper** | Speech recognition model | Converts YouTube audio to text |
| **FastAPI** | Python web framework | High-performance API with automatic documentation |
| **BeautifulSoup** | HTML parser | Extracts text from web pages |

---

## 📋 First Tasks (By May 9)

1. Set up monorepo structure (frontend/ and backend/ directories)
2. Create docker-compose.yml for three services (frontend, backend, redis)
3. Install WSL 2 and Docker Desktop on Windows
4. Set up Supabase project with initial tables
5. Create `.env.example` template with all required API keys
6. Implement `scan_fixtures.py` script for fetching matches
7. Create demo worker to validate Redis queue functionality
8. Ensure documentation (BACKEND.md) is up to date

---

This file is the **single source of truth** for how the platform is designed to work.  
Keep it updated when functionality evolves.

## 📝 Update: 2025-05-10 - Монорепозиторий с FastAPI Backend

Реорганизация проекта в монорепозиторий с выделенным FastAPI бэкендом:

### 1. Новая структура проекта

```
mrbets/
├── frontend/            # Next.js frontend
│   ├── src/             # React компоненты и страницы
│   ├── public/          # Статические файлы
│   └── package.json     # Frontend зависимости
│
├── backend/             # FastAPI backend
│   ├── app/             # FastAPI код
│   │   ├── main.py      # Основная точка входа
│   │   ├── routers/     # API маршруты
│   │   ├── models/      # Схемы данных 
│   │   └── utils/       # Утилиты
│   ├── jobs/            # Cron задачи
│   │   ├── scan_fixtures.py
│   │   └── worker.py
│   ├── fetchers/        # Сборщики данных
│   ├── processors/      # Обработчики данных
│   └── requirements.txt # Backend зависимости
│
├── monitoring/          # Prometheus и Grafana
├── docker-compose.yml   # Запуск всей системы
└── .env.example         # Пример переменных окружения
```

### 2. Структура бэкенда (FastAPI)

- **FastAPI App**: REST API с эндпоинтами для получения данных о матчах и прогнозах
- **Fixture Router**: `/fixtures` эндпоинты для работы с матчами
- **Worker Process**: Обработка задач из очереди Redis
- **Scan Fixtures Job**: Периодическое сканирование новых матчей

### 3. Компоненты мониторинга

- **Prometheus**: Сбор метрик со всех компонентов
- **Grafana**: Визуализация метрик и алертинг

### 4. Docker окружение

- Docker Compose для запуска всех компонентов:
  - frontend
  - backend
  - worker
  - redis
  - prometheus
  - grafana

Это изменение упрощает локальную разработку и улучшает масштабируемость системы для поддержки большего количества матчей и более сложной логики анализа.

## 📝 Update: 2025-05-10 - Настройка Монорепозитория

Сегодня были реализованы следующие улучшения для поддержки монорепозитория:

### 1. Корневой package.json с управлением скриптами

Создан корневой `package.json` с набором скриптов для управления обоими проектами:

```json
{
  "name": "mrbets",
  "version": "1.0.0",
  "scripts": {
    "dev:frontend": "cd frontend && npm run dev",
    "dev:backend": "cd backend && uvicorn app.main:app --reload",
    "dev:all": "concurrently \"npm run dev:frontend\" \"npm run dev:backend\"",
    "build:frontend": "cd frontend && npm run build",
    "start:frontend": "cd frontend && npm run start",
    "docker:up": "docker-compose up -d",
    "docker:down": "docker-compose down",
    "check-monorepo": "bash ./scripts/check-monorepo.sh"
  }
}
```

### 2. Обновленный .gitignore для монорепозитория

Расширен файл `.gitignore` для корректной работы с Python и Node.js:

```
# Python
__pycache__/
*.py[cod]
/backend/.venv/
/backend/*.egg-info/
/backend/.pytest_cache/

# Node.js
/node_modules/
/frontend/node_modules/
/frontend/.next/

# Логи и временные файлы
*.log
.docker/
dump.rdb
```

### 3. Диагностический скрипт для проверки структуры

Создан bash-скрипт `scripts/check-monorepo.sh` для проверки структуры монорепозитория:
- Проверяет наличие всех критических файлов
- Валидирует скрипты в package.json
- Проверяет переменные окружения
- Выводит цветное резюме состояния проекта

### 4. Обновленная документация

Обновлен `README.md` с инструкциями по установке и запуску, а также описанием новой структуры монорепозитория.

Эти изменения обеспечивают более удобную разработку и управление проектом с разделением фронтенда и бэкенда.
