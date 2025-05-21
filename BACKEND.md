# MrBets.ai – BACKEND.md

> **Context**: This file contains technical documentation for the MrBets.ai backend system, serves as a reference during development, and helps AI assistants understand the project structure.

---

> **Current Implementation Status (May 2025):**
> - Fetcher modules `rest_fetcher.py` (API-Football), `odds_fetcher.py` (The Odds API), and `scraper_fetcher.py` (BBC Sport RSS) are implemented in `backend/fetchers/`.
> - Basic processor (`pre_processor.py`) module is implemented in `backend/processors/`.
> - Other directories like `app/`, `jobs/` may exist with basic structure but full functionality for all components is pending.
> - The `frontend/` is a Next.js 14 scaffold without business logic.
> - The `monitoring/` directory is missing.
> - The `scripts/` directory is empty or contains only stubs.
> - The `cron/` directory contains a crontab and helper scripts.
> - `.github/workflows/` provides CI/CD for both frontend and backend.
> - The `logs/` directory is used for backend logs.

## 1. Strategic Project Goal

Build a **self-sufficient backend engine** that automatically collects data about upcoming football matches every 30 minutes, analyzes them through an LLM, and stores ready-made JSON predictions in Supabase. The frontend receives pre-processed content instantly without running an LLM for each click.

**Key advantages:**
* **Speed**: Page response < 200 ms (data is pre-generated)
* **Cost efficiency**: LLM is only called once every 3 hours or when important changes occur
* **Scalability**: Redis-based architecture allows horizontal system expansion

## 2. Technology Stack

| Layer | Tool | Notes |
|-------|------|-------|
| **Runtime** | Python 3.11 | Main backend language (FastAPI + workers) |
| **Web Framework** | FastAPI | Async, OpenAPI documentation out-of-box |
| **Task Scheduler** | cron (Linux)/Celery beat | 30-min fixture scan, hourly refresh |
| **Queue/Buffer** | Redis 7 Streams | Task transport between micro-services |
| **Metadata DB** | Supabase Postgres | Metadata + predictions table |
| **File Storage** | Supabase Storage (S3 API) | Raw texts, audio, video |
| **Vector DB** | Pinecone | Semantic search over embeddings |
| **Embeddings** | OpenAI text‑embedding‑3‑large | 1536-dimensional vectors |
| **LLM Reasoner** | GPT‑4o | Reasoning and prediction generation |
| **ASR / Video** | Whisper turbo | YouTube audio transcription |
| **HTTP Requests** | `httpx` | Async client for APIs |
| **HTML Parsing** | `BeautifulSoup4` | News site parsing |
| **DevOps** | Docker + docker‑compose | Single-command deployment |
| **CI/CD** | GitHub Actions | Lint, test, deploy to VPS |

## 3. Workflow (every 30 minutes)

1. **cron scheduler** triggers the `scan-fixtures` job.
2. **fixtures-scanner** retrieves the match list for the next 48-72 hours from API‑Football and adds each `match_id` to the Redis queue `queue:fixtures`.
3. **data-collector** workers pull `match_id` from the queue and launch **fetcher micro-services**:
   - `rest_fetcher.py` (API-Football, statistics)
   - `odds_fetcher.py` (The Odds API, pre-match and live odds)
   - `scraper_fetcher.py` (BBC Sport, ESPN, sports blogs)
   - `twitter_fetcher.py` (filtered stream API v2, analyst opinions)
   - `telegram_fetcher.py` (bot in channels, expert messages)
   - `youtube_fetcher.py` (yt-dlp + Whisper, show transcription)
4. Each fetcher writes raw data to the Redis stream `stream:raw_events`.
5. **pre-processor** consumes `raw_events`, translates (if needed via Yandex), chunks, vectorizes, and calculates source reliability rating.
6. Data is saved to:
   - Originals → Supabase Storage `/raw/{match_id}/...`
   - Vectors → Pinecone (namespace by `match_id`)
   - Metadata → Postgres table `raw_events`
7. **retriever-builder** performs hybrid search (SQL + vector) and sends Top-K documents to the **llm-reasoner**.
8. **llm-reasoner** builds a chain of reasoning and returns JSON: `{analysis, bets[], confidence}`.
9. **result-writer** performs an UPSERT into the Postgres table `predictions` (PK: `match_id`).
10. **refresher-daemon** (once per hour) checks if odds or news have changed significantly → if yes, marks the record as `stale` and returns `match_id` to the queue.
11. **evaluation-module** (after the match) records prediction results for further analytics.

## 4. System Components in Detail

### 4.1 Scheduler
* **Cron** entry: `*/30 * * * * docker exec backend python -m jobs.scan_fixtures`.
* Optionally **Celery beat** for more complex tasks.

### 4.2 Fixtures-Scanner
**Implemented:** `jobs/scan_fixtures.py` is implemented and tested.
- Fetches upcoming fixtures from API-Football for a configurable list of leagues (`LEAGUES_TO_MONITOR`) and a configurable forward window (`DAYS_FORWARD`, e.g., 30 days).
- Includes a test mode (`TEST_MODE_PAST_SEASON`) to fetch data from a previous season (e.g., 2023) for development and testing during off-season periods.
- Upserts fixture data into the Supabase `fixtures` table. The stored data includes:
    - `fixture_id` (Primary Key)
    - `league_id`
    - `home_team_id`
    - `away_team_id`
    - `event_date` (UTC timestamp of the match)
    - `status_short` (e.g., "NS", "FT", "HT")
    - `status_long` (e.g., "Not Started", "Match Finished", "Halftime")
    - `score_home`
    - `score_away`
    - `api_response_fixture` (the full JSON response from API-Football for the fixture)
    - `last_updated_api_football` (timestamp of when the record was last updated from the API)
- Adds new (not recently scanned) `fixture_id`s to a Redis list specified by `FIXTURES_QUEUE_NAME` (e.g., `queue:fixtures`) for further processing by other workers.
- Uses a Redis set (`PROCESSED_FIXTURES_SET_NAME`, e.g., `set:fixtures_scanned_today`) with a TTL (`PROCESSED_FIXTURES_SET_TTL`, e.g., 24 hours) to avoid re-adding recently scanned fixtures to the queue during the same day's multiple runs.
- Handles API rate limits with a configurable delay (`REQUEST_DELAY_SECONDS`).
- Requires `API_FOOTBALL_KEY`, `REDIS_URL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_KEY` environment variables.

Example of old conceptual snippet (actual implementation is more robust):
```python
# Conceptual representation - actual script is more detailed
# resp = httpx.get(f"{API_FOOTBALL}/fixtures?from={today}&to={today+2}")
# for m in resp.json()["response"]:
#     if redis_client.sadd("set:fixtures_scanned_today", m["fixture"]["id"]):
#         redis_client.expire("set:fixtures_scanned_today", 24*60*60)
#         redis_client.lpush("queue:fixtures", m["fixture"]["id"])
```
*Stores only new IDs (Redis SET for deduplication within a time window, then LPUSH to queue).*

### 4.3 Fetcher Micro-services
**Implemented:**
- `fetchers/metadata_fetcher.py`: Fetches and stores comprehensive metadata for leagues, teams (including venue details), and players (including season-specific statistics like appearances, goals, ratings if available) from API-Football into Supabase tables `leagues`, `teams`, and `players`. It processes a configurable list of leagues (`LEAGUES_TO_PROCESS`) and a specific season (`CURRENT_SEASON_METADATA`). It also ensures `api_football_league_id` and `api_football_season` are stored for player statistics, linking them to the context in which they were recorded.
- `fetchers/rest_fetcher.py` (API-Football, statistics) - *Initial stub or basic version may exist, primarily focused on fixture-specific details beyond what `scan_fixtures` gets.*
- `fetchers/odds_fetcher.py` (The Odds API, pre-match and live odds) - *Initial stub or basic version may exist.*
- `fetchers/scraper_fetcher.py` (BBC Sport RSS) - Implemented and tested. Parses RSS feeds, extracts article content (title, text, images), performs NER with spaCy, and stores data to Redis Streams and Supabase Storage.

**Planned:** `twitter_fetcher.py`, `telegram_fetcher.py`, `youtube_fetcher.py` are not yet implemented.

| Fetcher      | Library                       | Action                                                                 | Data type                     |
|--------------|-------------------------------|------------------------------------------------------------------------|-------------------------------|
| **Metadata** | `httpx`, `supabase`           | GET leagues, teams, players from API-Football → Supabase `leagues`, `teams`, `players` tables | object (JSON)                |
| **REST**     | `httpx`                       | GET fixtures, stats, squads from API-Football → `xadd(raw_events)`     | object (JSON)                |
| **Odds**     | `httpx`                       | GET prematch & live odds from The Odds API → `xadd(raw_events)`          | object (JSON)                |
| **Scraper**  | `httpx` + `BeautifulSoup4` + `feedparser` + `spacy` | Parse HTML/RSS from BBC Sport, extract text, images, and entities → `xadd(raw_events)` | string / object (JSON/text)  |
| **Twitter**  | `twitterapi.io` (or Tweepy)   | Fetch tweets from selected authors → `xadd(raw_events)`                 | string / object (JSON/text)  |
| **Telegram** | `python-telegram-bot`         | Bot in channels → text, views → `xadd(raw_events)`                      | string / object (JSON/text)  |
| **YouTube**  | `yt-dlp` + Whisper            | Download videos, transcribe → `xadd(raw_events)`                        | string / object (JSON/text)  |

All fetchers add JSON in the format:
```json
{
  "match_id": 1234,               // int
  "team_id": 56,                  // int, optional
  "player_id": 789,               // int, optional
  "source": "twitter_opta",       // string
  "payload": "<string or object>",// string or object (main content: text, json, transcript, etc.)
  "timestamp": 1715400000,        // int (unix timestamp, seconds)
  "meta": {                       // object, optional (author, url, tweet_id, language, ...)
    "author": "OptaJoe",
    "url": "https://twitter.com/OptaJoe/status/...",
    "language": "en"
  }
}


to the `redis:stream:raw_events` stream.

### 4.4 Pre-Processor
**Implemented:** `processors/pre_processor.py` is significantly enhanced and tested.
- Consumes raw events from a Redis stream (e.g., `stream:raw_events`).
- **Translation**: Detects language of the input text (e.g., `payload.full_text`). If not English, attempts to translate to English using Yandex Translate API (requires `YANDEX_API_KEY` and `YANDEX_FOLDER_ID`).
- **Text Chunking**: Splits the (translated) full text into smaller, semantically coherent chunks using `tiktoken` (model `cl100k_base`) with a target `max_tokens` (e.g., 512). It prioritizes splitting by paragraphs.
- **Source Reliability**: Assigns a reliability score based on the event source (e.g., `bbc_sport` = 0.9) from a predefined `SOURCE_RELIABILITY` map.
- **Named Entity Recognition (NER)**:
    - Performs NER using spaCy (`en_core_web_sm`) on the entire translated document to get `overall_entities`.
    - Performs NER on each individual text chunk to get `chunk_entities`. Entities include text, label (e.g., ORG, PERSON), start, and end character offsets.
- **Entity Linking (Supabase)**:
    - For each chunk, attempts to link recognized entities to IDs in Supabase:
        - **Teams**: Matches `ORG` entities against the `teams` table (using `name` via `ilike`).
        - **Players**: Matches `PERSON` entities against the `players` table (using `name` via `ilike`). It attempts to improve relevance by:
            - Processing player names (e.g., removing possessive "'s").
            - Using `context_team_ids` (teams found in the same chunk) to filter players by checking their `current_team_id` and then by looking through `meta_data.statistics[].team.id` from the `players` table (if `meta_data` and `statistics` are present and structured as expected).
- **Embedding Generation**: For each text chunk, generates a vector embedding using OpenAI's `text-embedding-3-small` model.
- **Storage in Supabase (`processed_documents` table)**:
    - Stores a main record for the processed document with:
        - `source`, `document_url`, `document_title`, `document_timestamp`
        - `overall_match_id` (if provided in the event)
        - `overall_entities` (JSON dump of entities from the full document)
        - `reliability_score`
        - `structured_content` (JSON dump): This is an array where each element represents a processed chunk and contains:
            - `chunk_index` (int)
            - `chunk_text` (str)
            - `chunk_entities` (list of dicts: `{"text", "label", "start", "end"}`)
            - `relevant_match_ids` (list of int)
            - `relevant_team_ids` (list of int) - IDs linked from `chunk_entities`
            - `relevant_player_ids` (list of int) - IDs linked from `chunk_entities`
- **Storage in Pinecone (Vector Database)**:
    - Initializes a connection to a Pinecone index (e.g., `mrbets-content-chunks`, requires `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`, `PINECONE_INDEX_NAME`).
    - For each chunk that has a successfully generated embedding:
        - Creates a unique `chunk_id` (e.g., `{supabase_document_id}_{chunk_index}`).
        - Upserts the vector (embedding) to Pinecone along with the following metadata (all stringified where necessary):
            - `processed_document_id` (str: UUID of the parent document in Supabase)
            - `chunk_index` (int)
            - `source` (str)
            - `document_url` (str)
            - `document_title` (str)
            - `relevant_match_ids` (list of str)
            - `relevant_team_ids` (list of str)
            - `relevant_player_ids` (list of str)
- **Error Handling & Logging**: Includes logging for key operations and basic error handling for API calls and client initializations.
- **Consumer Mode**: Contains `run_consumer()` method to listen to the Redis stream, process messages, and acknowledge them.

**Planned:** Advanced reliability scoring, support for additional languages beyond Yandex's capabilities (if needed).

Old conceptual snippet of pre-processor actions (actual implementation is far more detailed):
1. **Gets** a message from the queue
2. `langdetect` → if not EN → YANDEX API translation
3. `split_text` into chunks ≤1000 tokens (tiktoken)
4. **Reliability rating**: mapping (`bbc` = 0.9, `random_tweet` = 0.3)
5. `openai.embeddings` → 1536-dimensional vector
6. Writes:
   - Storage `/{match_id}/{uuid}.txt` (Note: This part seems outdated, current pre_processor focuses on `processed_documents` and Pinecone, not direct Supabase Storage for raw text chunks in this manner)
   - Pinecone `upsert(id, vector, {meta})`
   - Postgres INSERT into `raw_events` (Note: `pre_processor` now inserts into `processed_documents`, `raw_events` is likely populated by fetchers)


### 4.5 Retriever-Builder
**Not implemented:** `retriever_builder.py` is not present yet.

### 4.6 LLM-Reasoner
**Not implemented:** `llm_reasoner.py` is not present yet.

### 4.7 Result-Writer
```sql
INSERT INTO predictions(match_id, json, updated_at, stale, model_version, confidence)
VALUES (%s, %s, now(), false, %s, %s)
ON CONFLICT (match_id) DO UPDATE 
SET json = EXCLUDED.json, updated_at = EXCLUDED.updated_at, stale = false;
```
TTL check in SQL: `updated_at > now() - interval '3 hours'`.

### 4.8 Refresher-Daemon
* Hourly cron. Compares stored odds with `odds_api.latest()` or counts new raw_events; if changes > threshold → updates status and requeues.

### 4.9 Evaluation-Module
* After the match ends, records win/loss prediction status and ROI.
* Stores in `prediction_history` for future source weight adjustments.

## 5. Environment Variables (`.env`)
```
API_FOOTBALL_KEY=...
OPENAI_API_KEY=...
YANDEX_KEY=...
REDIS_URL=redis://redis:6379/0
SUPABASE_URL=...
SUPABASE_KEY=... # Should be SUPABASE_SERVICE_KEY for backend operations
PINECONE_API_KEY=...
SUPABASE_STORAGE_URL=...
S3_BUCKET=mrbets-raw
ODDS_API_KEY=...
``` 

## 6. Docker-compose (example)
```yaml
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_SUPABASE_URL=${SUPABASE_URL}
  backend:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    volumes: ["./backend:/app"]
    depends_on: [redis]
    env_file: .env
  worker:
    build: ./backend
    command: python -m jobs.worker
    depends_on: [redis]
    env_file: .env
  redis:
    image: redis:7
    ports: ["6379:6379"]
```

## 7. Monitoring and Logs
**Planned:** Prometheus + Grafana for metrics and alerting are planned for future implementation. The `monitoring/` directory is currently missing. Logging is performed to `logs/observer.log`.

## 8. Project Timeline (May 9 → August 9)

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

## 9. Local Setup
```bash
git clone git@github.com:yourname/mrbets.git
cd mrbets
docker compose up --build
```
* `http://localhost:8000/docs` – FastAPI swagger.
* `redis-cli monitor` – queue monitoring.
* `supabase studio` – table browsing.
**Note:** The `monitoring/` directory and bash scripts for monorepo structure checks are missing.

## 10. Key Terms

| Term | What it is | In simple words |
|------|------------|----------------|
| **Redis** | In-memory data store | Ultra-fast task queue between services |
| **Embeddings** | Text vectorization | Representing text meaning as numbers for search |
| **Hybrid Search** | Filter + vector search | First by team/date, then by meaning |
| **TTL** | Time To Live | Prediction validity period (3 hours) |
| **Chain-of-Thought** | Prompting method | LLM explicitly shows reasoning process |
| **Pinecone** | Vector database | Stores and searches semantically similar texts |
| **Whisper** | Speech recognition model | Converts YouTube audio to text |

## 11. Project Structure (Current)

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
│   │   ├── rest_fetcher.py
│   │   └── odds_fetcher.py
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
│   │   ├── public/
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   ├── Dockerfile
│   │   ├── .eslintrc.json
│   │   ├── next-env.d.ts
│   │   ├── next.config.js
│   │   ├── postcss.config.js
│   │   ├── tailwind.config.js
│   │   ├── tsconfig.json
│   │   └── .vscode/
│   │
│   ├── .github/
│   │   └── workflows/
│   │       ├── ci.yml
│   │       ├── root-ci.yml
│   │       └── frontend-lint.yml
│   ├── cron/
│   │   ├── crontab
│   │   ├── run_scan.sh
│   │   └── Dockerfile
│   ├── logs/
│   │   └── observer.log
│   ├── scripts/
│   ├── node_modules/
│   ├── package.json
│   ├── package-lock.json
│   ├── docker-compose.yml
│   ├── .gitignore
│   ├── env.example
│   ├── .flake8
│   ├── README.md
│   ├── CONTEXT.md
│   └── BACKEND.md
```

---

> **Maintenance note**: This BACKEND.md is the canonical technical reference for MrBets.ai and should stay in sync with code changes.
