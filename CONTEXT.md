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
- **Frontend**: Next.js 14 (unchanged) + Telegram Bot 
- **Backend**: FastAPI with microservices architecture
- **Data Processing**: Redis Streams for distributed processing. **Pre-processor (`pre_processor.py`) now handles translation, chunking, NER, entity linking (teams, players to Supabase IDs), OpenAI embeddings, and storage of processed documents to Supabase (`processed_documents` table) and chunk vectors to Pinecone.**
- **Vector Search**: Pinecone for semantic retrieval. **The `pre_processor.py` now actively populates the Pinecone index.**
- **Storage**: Supabase Storage for raw data (still relevant for original large files if needed, though `pre_processor` focuses on structured DB entries).
- **Additional Data Sources**: News sites, social media, video content

---

## 🧩 Key Functional Components

### 1. 🔄 **Fixtures Sync**
- Uses `API-Football` to fetch upcoming matches from select leagues (e.g., Premier League, La Liga)
- **Current**: Script: `/scripts/updateFixtures.ts` (Legacy frontend script, to be deprecated)
- **Implemented (Backend)**: Python service: `backend/jobs/scan_fixtures.py`
  - Fetches upcoming fixtures from API-Football for a configurable list of leagues and a defined forward window (e.g., 30 days).
  - Stores detailed fixture data in Supabase `fixtures` table (includes IDs, teams, event date, status, scores, and full API response).
  - Adds new `fixture_id`s to a Redis queue (`queue:fixtures`) for further processing.
  - Employs a Redis set for de-duplication to prevent re-processing recently scanned fixtures within a TTL (e.g., 24 hours).
  - Supports a test mode for fetching data from a past season to aid development during off-seasons.
- Stores match data into `Supabase.fixtures`
- Triggered via cron job

### 1.A. 🧑‍🤝‍🧑 **Metadata Sync (Teams & Players)**
- **Implemented (Backend)**: Python service `backend/fetchers/metadata_fetcher.py`
  - Fetches comprehensive data for teams (including name, country, venue details like name, city, capacity, image) and players (name, nationality, age, height, photo, and season-specific stats like appearances, goals, rating if provided by API) from API-Football.
  - Populates/updates the Supabase tables `teams` and `players`.
  - Operates on a configurable list of leagues and a specified season to ensure contextual relevance of player statistics.
  - This script is typically run on-demand or less frequently than fixture scanning, to build and maintain a local cache of team/player metadata.

### 2. 🧠 **AI Prediction Generation**
- Each match is processed by:
  - Fetching live stats & odds
  - Formatting a structured prompt
  - Sending to OpenAI (model: `o4-mini`, planned upgrade to `GPT-4o`)
  - Parsing AI response into:
    - `CHAIN OF THOUGHT`
    - `FINAL PREDICTION`
    - `VALUE BETS`

- **Planned**: Pipeline: 
  - Data collection via various fetchers
  - Pre-processing via `/backend/processors/pre_processor.py`
  - Retrieval via `/backend/processors/retriever_builder.py`
  - LLM reasoning via `/backend/processors/llm_reasoner.py`
- All results are stored in `Supabase.ai_predictions`

### 3. 📅 **Automated Processing**

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
- Used for: Fixtures, live odds, team data, predictions, league standings, player statistics, venue information.
- Called via `lib/apiFootball.ts` (Legacy Frontend) and backend Python scripts (`backend/jobs/scan_fixtures.py`, `backend/fetchers/metadata_fetcher.py`, `backend/fetchers/rest_fetcher.py`).
- Rate-limited API with key-based access

#### ✅ The Odds API
- Used for: Fetching pre-match and live odds from multiple bookmakers.
- Called via: `backend/fetchers/odds_fetcher.py`
- Rate-limited API with key-based access (`ODDS_API_KEY`).
- Integrated with Redis Streams for `raw_events` and Supabase Storage for snapshots.

#### ✅ Scraper Fetcher (BBC Sport RSS)
- Use: Scraping news articles from BBC Sport RSS feeds.
- Called via: `backend/fetchers/scraper_fetcher.py`
- Uses `httpx`, `BeautifulSoup4`, `feedparser` for fetching and parsing HTML/RSS.
- Uses `spacy` for Named Entity Recognition (NER) from article text.
- Extracts article title, full text, images, and entities.
- Pushes structured data to Redis Streams (`raw_events`) and saves raw text to Supabase Storage.

### Planned Integrations

#### ⏳ OpenAI
- Used for: Text generation (reasoning, summary, betting logic)
- Model: `o4-mini`
- Called via `generatePrediction.ts` → OpenAI Chat Completion endpoint
- Responses are split into 3 sections and stored

#### ⏳ OpenAI Embeddings
- Use: Vectorizing text for semantic search
- Model: `text-embedding-3-small` (as implemented in `pre_processor.py`)
- Will be called via: `/backend/processors/pre_processor.py` (**Implemented**)

#### ⏳ Pinecone
- Use: Vector database for similar document retrieval
- Will store all processed text embeddings. **Populated by `pre_processor.py`.**
- Will be queried for context retrieval for each match

#### ⏳ BeautifulSoup + Requests
- Use: Scraping news sites and sports blogs
- Will extract clean text from HTML

#### ⏳ Yandex Cloud API
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

## 📊 Data Flow Pipeline 

```
[CRON] → scan_fixtures.py → redis:queue:fixtures (LIST) → worker_manager
                                       │ POP
                                       ▼
                   «data-collector workflow» (fan-out fetcher tasks)
┌─────────────────────────────────────────────────────────────────────┐
│ rest_fetcher.py (API-Football)       → raw_events (STREAM)          │
│ odds_fetcher.py (The Odds API)       → raw_events (STREAM)          │
│ scraper_fetcher.py (BBC/ESPN)        → raw_events (STREAM)          │
│ twitter_fetcher.py (filtered stream) → raw_events (STREAM)          │
│ telegram_fetcher.py (bot getUpdates) → raw_events (STREAM)          │
│ youtube_fetcher.py (yt-dlp+Whisper)  → raw_events (STREAM)          │
└─────────────────────────────────────────────────────────────────────┘
                     ▼ consumer-group:pre_processor (parallel workers)
-    translate → split_chunks → reliability_score → embeddings → Storage/Pinecone/Postgres
+    (pre_processor.py: translate → chunk → NER → link entities (Supabase) → embeddings (OpenAI) → store (Supabase `processed_documents`, Pinecone vectors))
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
- Project is developed on Windows 11 + Linux WSL
- Docker + docker-compose for full system simulation
- Backend development in Python 3.11
- Frontend continues with Next.js/TypeScript
- Environment variables split between frontend and backend needs

---

## 💻 Repository Structure (Planned)

```
mrbets/                         # Repository root
├── backend/                    # FastAPI backend
│   ├── app/                    # Main FastAPI code
│   │   ├── main.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── common.py
│   │   │   ├── fixture.py
│   │   │   ├── fixtures.py
│   │   │   ├── prediction.py
│   │   │   └── predictions.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── fixtures.py
│   │   │   └── predictions.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── config.py
│   │       ├── exceptions.py
│   │       └── logger.py
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── metadata_fetcher.py
│   │   ├── rest_fetcher.py
│   │   ├── odds_fetcher.py
│   │   └── scraper_fetcher.py
│   ├── jobs/
│   │   ├── scan_fixtures.py
│   │   └── worker.py
│   ├── processors/
│   │   ├── __init__.py
│   │   └── pre_processor.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── Dockerfile
│   ├── env.example
│   ├── .gitignore
│   ├── .flake8
│   ├── pyproject.toml
│   ├── observer.py
│   ├── check_fixtures.py
│   ├── test_services.py
│   └── tests/
│
├── frontend/                   # Next.js 14 frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx
│   ├── public/
│   ├── package.json
│   ├── package-lock.json
│   ├── Dockerfile
│   ├── .eslintrc.json
│   ├── next-env.d.ts
│   ├── next.config.js
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── .vscode/
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── root-ci.yml
│       └── frontend-lint.yml
├── cron/
│   ├── crontab
│   ├── run_scan.sh
│   └── Dockerfile
├── logs/
│   └── observer.log
├── scripts/
├── node_modules/
├── package.json
├── package-lock.json
├── docker-compose.yml
├── .gitignore
├── env.example
├── .flake8
├── README.md
├── CONTEXT.md
└── BACKEND.md
---

Only basic fetcher and processor modules are implemented in backend/; other directories exist but are currently empty.
Specifically, `rest_fetcher.py`, `odds_fetcher.py`, and `scraper_fetcher.py` are now available.
The frontend/ is a Next.js 14 scaffold without business logic.
The monitoring/ directory is missing.
The scripts/ directory is empty or contains only stubs.
The cron/ directory contains a crontab and helper scripts.
.github/workflows/ provides CI/CD for both frontend and backend.
The logs/ directory is used for backend logs.


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
│   │   ├── app/
│   │   │   ├── globals.css
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx
│   │   ├── public/          # Статические файлы
│   │   └── package.json     # Frontend зависимости
│   ├── backend/             # FastAPI backend
│   │   ├── app/             # FastAPI код
│   │   │   ├── main.py      # Основная точка входа
│   │   │   ├── routers/     # API маршруты
│   │   │   ├── models/      # Схемы данных 
│   │   │   └── utils/       # Утилиты
│   │   ├── jobs/            # Cron задачи
│   │   │   ├── scan_fixtures.py
│   │   │   └── worker.py
│   │   ├── fetchers/        # Сборщики данных
│   │   └── requirements.txt # Backend зависимости
│   ├── monitoring/          # Prometheus и Grafana
│   ├── docker-compose.yml   # Запуск всей системы
│   └── .env.example         # Пример переменных окружения
```

### 2. Структура бэкенда (FastAPI)

- **FastAPI App**: REST API с эндпоинтами для получения данных о матчах и прогнозах
- **Fixture Router**: `/fixtures` эндпоинты для работы с матчами
- **Worker Process**: Обработка задач из очереди Redis
- **Scan Fixtures Job**: Периодическое сканирование новых матчей (`backend/jobs/scan_fixtures.py`)
- **Fetcher Modules**: Scripts like `backend/fetchers/metadata_fetcher.py` (teams, players), `backend/fetchers/rest_fetcher.py` (API-Football fixture details), `backend/fetchers/scraper_fetcher.py` (news), and `backend/fetchers/odds_fetcher.py` (The Odds API) for data collection.

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
