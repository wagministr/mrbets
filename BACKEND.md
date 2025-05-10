# MrBets.ai – BACKEND.md

> **Context**: This file contains technical documentation for the MrBets.ai backend system, serves as a reference during development, and helps AI assistants understand the project structure.

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
| **ASR / Video** | Whisper medium/large-v3 | YouTube audio transcription |
| **HTTP Requests** | `httpx` | Async client for APIs |
| **HTML Parsing** | `BeautifulSoup4` | News site parsing |
| **DevOps** | Docker + docker‑compose | Single-command deployment |
| **CI/CD** | GitHub Actions | Lint, test, deploy to VPS |

## 3. Workflow (every 30 minutes)

1. **cron scheduler** triggers the `scan-fixtures` job.
2. **fixtures-scanner** retrieves the match list for the next 48-72 hours from API‑Football and adds each `match_id` to the Redis queue `queue:fixtures`.
3. **data-collector** workers pull `match_id` from the queue and launch **fetcher micro-services**:
   - `rest_fetcher` (API-Football, statistics and odds)
   - `scraper_fetcher` (BBC Sport, ESPN, sports blogs)
   - `twitter_fetcher` (filtered stream API v2, analyst opinions)
   - `telegram_fetcher` (bot in channels, expert messages)
   - `youtube_fetcher` (yt-dlp + Whisper, show transcription)
4. Each fetcher writes raw data to the Redis stream `stream:raw_events`.
5. **pre-processor** consumes `raw_events`, translates (if needed via DeepL), chunks, vectorizes, and calculates source reliability rating.
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
```python
resp = httpx.get(f"{API_FOOTBALL}/fixtures?from={today}&to={today+2}")
for m in resp.json()["response"]:
    redis.lpush("queue:fixtures", m["fixture"]["id"])
```
*Stores only new IDs (Redis SET for deduplication).*

### 4.3 Fetcher Micro-services
| Fetcher | Library | Action |
|---------|---------|--------|
| **REST** | `httpx` | GET stats & odds → `xadd(raw_events)` |
| **Scraper** | `httpx` + `BeautifulSoup4` | Parse HTML from BBC/ESPN |
| **Twitter** | `tweepy` (v2 filtered stream) | Listen to selected authors' tweets |
| **Telegram** | `python-telegram-bot` | Bot in channels → text, views |
| **YouTube** | `yt-dlp` + Whisper | Downloads videos, transcribes |

All fetchers add JSON in the format:
```json
{
  "match_id": 1234,
  "source": "twitter",
  "payload": "<text or path>",
  "timestamp": 1715400000
}
```
to the `redis:stream:raw_events` stream.

### 4.4 Pre-Processor
1. **Gets** a message from the queue  
2. `langdetect` → if not EN → DeepL API translation
3. `split_text` into chunks ≤1000 tokens (tiktoken)
4. **Reliability rating**: mapping (`bbc` = 0.9, `random_tweet` = 0.3)
5. `openai.embeddings` → 1536-dimensional vector
6. Writes:
   - Storage `/{match_id}/{uuid}.txt`
   - Pinecone `upsert(id, vector, {meta})`
   - Postgres INSERT into `raw_events`

### 4.5 Retriever-Builder
```python
vector_hits = pinecone.query(vector=q_vec, top_k=100, namespace=match_id)
meta_hits = supabase.sql("""SELECT ... WHERE match_id = %s AND ts > now()-'7 days'""")
joined = deduplicate(vector_hits + meta_hits)[:TOP_K]
```
Returns a list of fragments for the prompt.

### 4.6 LLM-Reasoner
* Prompt with sections: **Facts**, **Chain-of-Thought**, **Final Tips**.
* Injects current odds (`odds_api.latest(match_id)`).
* Calls `openai.chat.completions` → returns JSON with analysis and tips.

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
DEEPL_KEY=...
REDIS_URL=redis://redis:6379/0
SUPABASE_URL=...
SUPABASE_KEY=...
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
* **Prometheus + Grafana** via Docker for CPU, queue length, latency.
* **Sentry** for backend exceptions.
* JSON log format → sent to Logtail.

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

---

> **Maintenance note**: This BACKEND.md is the canonical technical reference for MrBets.ai and should stay in sync with code changes.
