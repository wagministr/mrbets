import asyncio
import json
import logging
import os
import uuid
import time # Добавлено для измерения времени
from datetime import datetime # <--- ДОБАВЛЕН ИМПОРТ

print("DEBUG: llm_content_analyzer.py - Script started") # Отладочный print

import httpx # Для OpenAI v1+
import redis.asyncio as redis_asyncio # Переименовываем, чтобы избежать конфликта с модулем redis
from redis.exceptions import ResponseError, TimeoutError as RedisTimeoutError, ConnectionError as RedisConnectionError # Импортируем исключения и переименовываем TimeoutError
from dotenv import load_dotenv
from openai import AsyncOpenAI, RateLimitError as OpenAIRateLimitError, APIError as OpenAIAPIError, APITimeoutError as OpenAPITimeoutError

# Импорты для Supabase и Pinecone
from supabase import create_client, Client as SupabaseClient
from pinecone import Pinecone

# --- Настройки ---
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env')) # Загрузка из .env в корне проекта
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))    # Загрузка из backend/.env (переопределит, если есть)

# --- Определение глобальных переменных из .env ДО их использования ---
# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
print(f"DEBUG: Effective REDIS_URL after .env loading: {REDIS_URL}") # Отладочный print
RAW_EVENTS_STREAM_NAME = "stream:raw_events"
CONSUMER_GROUP_NAME = "group:llm_content_analyzer"
CONSUMER_NAME_PREFIX = "consumer:llm_analyzer_"

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_LLM_MODEL = "gpt-4.1" 
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_REQUEST_TIMEOUT_SECONDS = 120  # Таймаут для запросов к OpenAI (LLM и embeddings)
OPENAI_MAX_RETRIES = 3
OPENAI_RETRY_DELAY_SECONDS = 5

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_REQUEST_TIMEOUT_SECONDS = 30 # Таймаут для операций Supabase

# Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX", "mrbets-content-chunks")
PINECONE_REQUEST_TIMEOUT_SECONDS = 30 # Таймаут для операций Pinecone

# --- MASTER PROMPT TEMPLATE ---
MASTER_PROMPT_TEMPLATE = """
You are an advanced AI assistant specializing in the analysis of sports news, particularly football (soccer) articles. Your task is to carefully read the provided article text below and perform the following steps:

**Step 1: Semantic Text Chunking**

Divide the entire article text into distinct, logically complete fragments (hereinafter "chunks"). Adhere to the following rules when creating chunks:
1.  Each chunk should describe one primary fact, event, idea, opinion, or quote.
2.  Chunks should be semantically self-contained. The information in one chunk should be understandable without necessarily reading adjacent chunks, as much as possible.
3.  Try to preserve natural paragraph and sentence boundaries. Do not break sentences or logical blocks within a paragraph without a strong reason.
4.  The approximate size of each chunk should be between 200-700 tokens. However, semantic integrity is more important than strict adherence to token count. It's better to have a slightly longer or shorter chunk if it preserves a complete thought.
5.  Very short articles (e.g., less than 150 words) might result in a single chunk if they represent a single coherent piece of information. Do NOT create multiple chunks if the article is short and about one single topic.
6.  If the article is long and complex, create multiple chunks.

**Step 2: Metadata Extraction for Each Chunk**

For **each** chunk you identified in Step 1, extract the following metadata:
*   `chunk_text`: The exact text of the chunk.
*   `summary`: A concise summary (1-2 sentences) of the main point of this specific chunk.
*   `chunk_type`: Categorize the chunk's content. Choose ONE from:
    *   "Match Result/Report": Describes the outcome or key events of a specific match that has already occurred.
    *   "Injury Update": News about a player's injury status.
    *   "Transfer News/Rumor": Information about player transfers (confirmed or rumored).
    *   "Player Performance/Praise": Focuses on a specific player's performance or accolades.
    *   "Team News/Strategy": General news about a team, tactical analysis, or upcoming match preparations.
    *   "Managerial News": News about managers (appointments, dismissals, comments).
    *   "Pre-Match Analysis/Preview": Discusses an upcoming match, predictions, or expectations.
    *   "Post-Match Reaction/Quotes": Comments, interviews, or reactions after a match.
    *   "League/Competition News": News related to a league, tournament, or general football administration.
    *   "Off-Pitch Event": News not directly related to on-field action (e.g., player's personal life if relevant to their career, club finances, etc.).
    *   "Historical Fact/Retrospective": Discusses past events or achievements.
    *   "Statistical Highlight": Focuses on a specific statistic or record.
    *   "Fan/Pundit Opinion": Presents opinions or analysis from fans or commentators (clearly distinguish from factual reporting).
    *   "Other": If none ofthe above apply (provide a brief explanation if so).
*   `tone`: The overall tone of the chunk. Choose ONE from: "Positive", "Negative", "Neutral", "Speculative", "Analytical", "Objective".
*   `importance_score`: An integer score from 1 (low importance) to 5 (very high importance) indicating how critical this chunk's information is for understanding future match outcomes or major football developments.
*   `linked_team_names`: A list of full team names mentioned in this chunk (e.g., ["Manchester United", "Liverpool FC"]). If no teams are mentioned, provide an empty list [].
*   `linked_player_names`: A list of full player names mentioned in this chunk (e.g., ["Harry Kane", "Mohamed Salah"]). If no players are mentioned, provide an empty list [].
*   `linked_coach_names`: A list of full coach/manager names mentioned in this chunk. If no coaches are mentioned, provide an empty list [].
*   `event_date_mentioned`: If the chunk refers to a specific date (or year, or month-year) for an event it describes (e.g., a match date, a transfer window), provide that date in "YYYY-MM-DD", "YYYY-MM", or "YYYY" format. If not clearly determinable, set to null.
*   `source_reference`: If the chunk attributes information to a specific source (e.g., "Sky Sports reports...", "According to the player's agent..."), briefly mention that source. Otherwise, set to null.
*   `quoted_person`: If the chunk contains a direct quote, state the name of the person quoted. Otherwise, set to null.

**Step 3: JSON Output**

Return your analysis as a JSON array, where each element of the array is an object representing one chunk and its extracted metadata.

**Example structure of a single chunk object (ensure all fields are present, using null if not applicable):**
```json
{{
  "chunk_text": "The full text of this specific chunk...",
  "summary": "A brief summary of this chunk.",
  "chunk_type": "Player Performance/Praise",
  "tone": "Positive",
  "importance_score": 4,
  "linked_team_names": ["Real Madrid"],
  "linked_player_names": ["Jude Bellingham"],
  "linked_coach_names": ["Carlo Ancelotti"],
  "event_date_mentioned": "2023-10-28",
  "source_reference": null,
  "quoted_person": null
}}
```

**IMPORTANT INSTRUCTIONS:**
*   Focus on accuracy and completeness of the metadata for each chunk.
*   If the article is very short and describes a single fact or event, you may return a single chunk object in the array.
*   If the article is longer, ensure you break it down into multiple, semantically distinct chunks. The goal is to create a granular, well-structured dataset from the article.
*   Adhere strictly to the JSON output format, ensuring it's a valid JSON array of objects. Each object must contain all the specified keys.
*   Provide an empty list `[]` for `linked_team_names`, `linked_player_names`, or `linked_coach_names` if none are mentioned in a specific chunk. Do not use `null` for these list fields.
*   Use `null` (JSON null, not the string "null") for string fields where the information is not applicable or not found (e.g., `event_date_mentioned`, `source_reference`, `quoted_person` if they don't apply to a chunk).
*   Do not invent information. If a piece of metadata cannot be reliably extracted from the chunk text, use `null` for optional string fields or an empty list for list fields.

**Article Text to Analyze:**
---
{article_text}
---
"""

# Логгирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s') # Добавлен funcName
logger = logging.getLogger(__name__)

print(f"DEBUG: Logger initialized. OPENAI_API_KEY: {OPENAI_API_KEY is not None}, SUPABASE_URL: {SUPABASE_URL is not None}, PINECONE_API_KEY: {PINECONE_API_KEY is not None}")

# --- Константы для таймаутов ---
DEFAULT_API_CALL_TIMEOUT = 60  # Общий таймаут для внешних вызовов в секундах, если не указан специфичный

# Source reliability scores
SOURCE_RELIABILITY = {
    "api-football": 0.9,
    "bbc": 0.8,
    "espn": 0.75,  
    "sky-sports": 0.75,
    "twitter": 0.6,
    "guardian": 0.8,
    "telegraph": 0.75,
    "rss-feed": 0.5,
    # "youtube": 0.7,  # Removed - processed separately on dedicated hardware
}

class LLMContentAnalyzer:
    def __init__(self):
        print("DEBUG: LLMContentAnalyzer.__init__ - Constructor started") # Отладочный print
        self.redis_client = redis_asyncio.from_url(REDIS_URL, decode_responses=True)
        
        # Инициализация OpenAI клиента
        if not OPENAI_API_KEY:
            logger.critical("OPENAI_API_KEY is not set. LLM Analyzer cannot start.")
            raise ValueError("OPENAI_API_KEY is not set.")
        self.openai_client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS 
        )
        logger.info(f"OpenAI client initialized with timeout: {OPENAI_REQUEST_TIMEOUT_SECONDS}s")
        
        # Инициализация Supabase клиента
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            logger.critical("SUPABASE_URL or SUPABASE_SERVICE_KEY is not set. LLM Analyzer cannot start.")
            raise ValueError("Supabase credentials are not set.")
        self.supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Supabase client initialized successfully.")

        # Инициализация Pinecone клиента
        if not PINECONE_API_KEY:
            logger.critical("PINECONE_API_KEY is not set. LLM Analyzer cannot start.")
            raise ValueError("PINECONE_API_KEY is not set.")
        
        try:
            # Pinecone инициализация синхронная
            self.pc = Pinecone(api_key=PINECONE_API_KEY) # Сохраняем клиент pc
            
            existing_indexes = self.pc.list_indexes()
            index_names = [index.name for index in existing_indexes.indexes] if hasattr(existing_indexes, 'indexes') else existing_indexes.names()
            
            if PINECONE_INDEX_NAME not in index_names:
                logger.error(f"Pinecone index '{PINECONE_INDEX_NAME}' not found. Available indexes: {index_names}")
                raise ValueError(f"Pinecone index '{PINECONE_INDEX_NAME}' does not exist.")
                
            self.pinecone_index = self.pc.Index(PINECONE_INDEX_NAME)
            logger.info(f"Pinecone index '{PINECONE_INDEX_NAME}' connected successfully.")
            
        except Exception as e:
            logger.critical(f"Failed to initialize Pinecone: {e}")
            raise ValueError(f"Pinecone initialization failed: {e}")

    async def _execute_blocking_io(self, func, *args_for_func, timeout: int = DEFAULT_API_CALL_TIMEOUT, **kwargs_for_func):
        """
        Выполняет блокирующую I/O операцию в отдельном потоке с таймаутом.
        """
        try:
            # logger.debug(f"Executing blocking IO for {func.__name__} with args: {args_for_func}, kwargs: {kwargs_for_func}, timeout: {timeout}s")
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args_for_func, **kwargs_for_func), # Передаем и позиционные, и именованные аргументы
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout ({timeout}s) during blocking I/O operation: {func.__name__} with args: {args_for_func}, kwargs: {kwargs_for_func}")
            raise # Перевыбрасываем, чтобы вызывающий код мог обработать
        except Exception as e:
            logger.error(f"Error during blocking I/O operation {func.__name__} with args: {args_for_func}, kwargs: {kwargs_for_func}: {e}", exc_info=True)
            raise

    async def _call_openai_llm(self, article_text: str, event_id: str) -> list | None:
        full_prompt = MASTER_PROMPT_TEMPLATE.format(article_text=article_text)
        retries = 0
        while retries < OPENAI_MAX_RETRIES:
            try:
                start_time = time.time()
                logger.info(f"Event {event_id}: Sending request to OpenAI LLM (model: {OPENAI_LLM_MODEL}, attempt {retries + 1}/{OPENAI_MAX_RETRIES}) for article (first 100 chars): {article_text[:100]}...")
                response = await self.openai_client.chat.completions.create(
                    model=OPENAI_LLM_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a helpful AI assistant specialized in football news analysis. You MUST create multiple chunks from any article longer than 500 characters. ALWAYS return a JSON array with multiple objects."},
                        {"role": "user", "content": full_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4000,
                )
                duration = time.time() - start_time
                logger.info(f"Event {event_id}: OpenAI LLM call completed in {duration:.2f} seconds.")
                
                content_str = response.choices[0].message.content
                if not content_str:
                    logger.error(f"Event {event_id}: OpenAI LLM returned empty content.")
                    return None
                
                logger.info(f"Event {event_id}: Raw LLM response content (first 500 chars): {content_str[:500]}")
                
                # Очистка от markdown-обертки, если она есть
                if content_str.startswith("```json"):
                    content_str = content_str.removeprefix("```json").removesuffix("```").strip()
                elif content_str.startswith("```"):
                    content_str = content_str.removeprefix("```").removesuffix("```").strip()

                try:
                    parsed_response = json.loads(content_str)
                except json.JSONDecodeError as e:
                    logger.error(f"Event {event_id}: Failed to decode JSON response from LLM: {e}")
                    logger.error(f"Event {event_id}: Problematic JSON string from LLM: {content_str}")
                    return None # Не повторяем при ошибке парсинга JSON - это проблема ответа, а не сети

                if isinstance(parsed_response, list):
                    chunk_list = parsed_response
                elif isinstance(parsed_response, dict):
                    if all(key in parsed_response for key in ["chunk_text", "summary", "chunk_type"]):
                        chunk_list = [parsed_response]
                        logger.info(f"Event {event_id}: LLM returned a single chunk object, wrapping it in an array.")
                    elif "chunks" in parsed_response and isinstance(parsed_response["chunks"], list):
                        chunk_list = parsed_response["chunks"]
                    elif len(parsed_response.keys()) == 1:
                        first_key = list(parsed_response.keys())[0]
                        if isinstance(parsed_response[first_key], list):
                            chunk_list = parsed_response[first_key]
                        else:
                            logger.error(f"Event {event_id}: LLM returned a JSON object, but the value under the key '{first_key}' is not a list.")
                            return None
                    else:
                        logger.error(f"Event {event_id}: LLM response is a dict but doesn't match expected patterns. Keys: {list(parsed_response.keys())}")
                        return None
                else:
                    logger.error(f"Event {event_id}: LLM response is not a list of chunks or a known wrapped format. Type: {type(parsed_response)}")
                    logger.debug(f"Event {event_id}: LLM response content for debugging: {content_str}")
                    return None

                logger.info(f"Event {event_id}: Successfully received and parsed {len(chunk_list)} chunks from LLM.")
                return chunk_list

            except OpenAIRateLimitError as e:
                logger.warning(f"Event {event_id}: OpenAI API rate limit exceeded. Retrying in {OPENAI_RETRY_DELAY_SECONDS * (2**retries)} seconds... Error: {e}")
                await asyncio.sleep(OPENAI_RETRY_DELAY_SECONDS * (2**retries))
                retries += 1
            except OpenAPITimeoutError as e:
                logger.warning(f"Event {event_id}: OpenAI API request timed out. Retrying in {OPENAI_RETRY_DELAY_SECONDS * (2**retries)} seconds... Error: {e}")
                await asyncio.sleep(OPENAI_RETRY_DELAY_SECONDS * (2**retries))
                retries += 1
            except OpenAIAPIError as e: # Более общая ошибка API OpenAI
                logger.error(f"Event {event_id}: OpenAI API error: {e}. Status code: {e.status_code if hasattr(e, 'status_code') else 'N/A'}. Retrying in {OPENAI_RETRY_DELAY_SECONDS * (2**retries)} seconds...")
                await asyncio.sleep(OPENAI_RETRY_DELAY_SECONDS * (2**retries))
                retries += 1
            except httpx.HTTPStatusError as e: # Ошибка от httpx, если OpenAI клиент не перехватил
                logger.error(f"Event {event_id}: OpenAI API HTTP error: {e.response.status_code} - {e.response.text}. Retrying...")
                await asyncio.sleep(OPENAI_RETRY_DELAY_SECONDS * (2**retries))
                retries += 1
            except Exception as e:
                logger.error(f"Event {event_id}: An unexpected error occurred while calling OpenAI LLM: {e}", exc_info=True)
                return None # Не повторяем при неизвестных ошибках
        
        logger.error(f"Event {event_id}: Failed to call OpenAI LLM after {OPENAI_MAX_RETRIES} retries.")
        return None

    async def _get_or_create_processed_document(self, source: str, document_url: str, document_title: str | None, document_timestamp: str | None, event_id: str) -> uuid.UUID | None:
        logger.info(f"Event {event_id}: Getting or creating processed document for URL: {document_url}")
        start_time = time.time()
        try:
            if document_url:
                # Оборачиваем синхронный вызов Supabase
                response = await self._execute_blocking_io(
                    self.supabase_client.table("processed_documents").select("id").eq("document_url", document_url).execute,
                    timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
                )
                if response.data and len(response.data) > 0:
                    existing_doc_id = uuid.UUID(response.data[0]['id'])
                    duration = time.time() - start_time
                    logger.info(f"Event {event_id}: Found existing document with ID: {existing_doc_id} in {duration:.2f}s.")
                    return existing_doc_id

            reliability_score = self._get_reliability_score(source)
            new_doc_data = {
                "source": source, "document_url": document_url, "document_title": document_title,
                "document_timestamp": document_timestamp, "overall_match_id": None,
                "reliability_score": reliability_score,
            }
            cleaned_data = {k: v for k, v in new_doc_data.items() if v is not None}
            
            response = await self._execute_blocking_io(
                self.supabase_client.table("processed_documents").insert(cleaned_data).execute,
                timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
            )
            
            if response.data and len(response.data) > 0:
                doc_id = uuid.UUID(response.data[0]['id'])
                duration = time.time() - start_time
                logger.info(f"Event {event_id}: Created new processed document with ID: {doc_id} in {duration:.2f}s.")
                return doc_id
            else:
                logger.error(f"Event {event_id}: Failed to create processed document. Supabase response: {response}")
                return None
        except asyncio.TimeoutError: # Перехвачен из _execute_blocking_io
             logger.error(f"Event {event_id}: Timeout during Supabase operation in _get_or_create_processed_document.")
             return None
        except Exception as e:
            logger.error(f"Event {event_id}: Error in _get_or_create_processed_document: {e}", exc_info=True)
            return None

    def _get_reliability_score(self, source: str) -> float:
        """Возвращает оценку надежности источника на основе его типа."""
        return SOURCE_RELIABILITY.get(source.lower(), 0.5)

    async def _link_entity(self, entity_name: str, entity_type: str, event_id: str, context_team_ids: list[int] | None = None) -> int | None:
        logger.debug(f"Event {event_id}: Linking {entity_type} : {entity_name}")
        if not entity_name or not entity_name.strip():
            return None
        try:
            if entity_type == "team":
                return await self._link_team(entity_name, event_id)
            elif entity_type == "player":
                return await self._link_player(entity_name, event_id, context_team_ids)
            elif entity_type == "coach":
                return await self._link_coach(entity_name, event_id, context_team_ids)
            else:
                logger.warning(f"Event {event_id}: Unknown entity type: {entity_type} for name '{entity_name}'")
                return None
        except asyncio.TimeoutError:
             logger.error(f"Event {event_id}: Timeout during Supabase entity linking for {entity_type} '{entity_name}'.")
             return None
        except Exception as e:
            logger.error(f"Event {event_id}: Error linking {entity_type} '{entity_name}': {e}", exc_info=True)
            return None

    async def _link_team(self, team_name: str, event_id: str) -> int | None:
        start_time = time.time()
        try:
            response = await self._execute_blocking_io(
                self.supabase_client.table("teams").select("team_id").ilike("name", team_name).execute,
                timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
            )
            if response.data and len(response.data) > 0:
                team_id = response.data[0]["team_id"]
                logger.debug(f"Event {event_id}: Found team '{team_name}' with ID: {team_id} in {time.time() - start_time:.2f}s (exact match).")
                return team_id
            
            response = await self._execute_blocking_io(
                self.supabase_client.table("teams").select("team_id, name").ilike("name", f"%{team_name}%").execute,
                timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
            )
            if response.data and len(response.data) > 0:
                team_id = response.data[0]["team_id"]
                actual_name = response.data[0]["name"]
                logger.debug(f"Event {event_id}: Found team '{team_name}' -> '{actual_name}' with ID: {team_id} in {time.time() - start_time:.2f}s (partial match).")
                return team_id
                
            logger.debug(f"Event {event_id}: Team not found: {team_name}. Duration: {time.time() - start_time:.2f}s.")
            return None
        except asyncio.TimeoutError: # Перехвачен из _execute_blocking_io
            logger.error(f"Event {event_id}: Timeout during Supabase operation in _link_team for '{team_name}'.")
            return None
        except Exception as e:
            logger.error(f"Event {event_id}: Error searching for team '{team_name}': {e}", exc_info=True)
            return None

    async def _link_player(self, player_name: str, event_id: str, context_team_ids: list[int] | None = None) -> int | None:
        start_time = time.time()
        try:
            processed_name = player_name
            if player_name.endswith("'s"): processed_name = player_name[:-2]
            elif player_name.endswith("'"): processed_name = player_name[:-1]
            
            query_builder = self.supabase_client.table("players").select("player_id, name, current_team_id").ilike("name", f"%{processed_name}%")
            response = await self._execute_blocking_io(query_builder.execute, timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS)
            
            if not response.data:
                logger.debug(f"Event {event_id}: Player not found: {player_name}. Duration: {time.time() - start_time:.2f}s.")
                return None
            
            if context_team_ids:
                for player in response.data:
                    if player.get("current_team_id") in context_team_ids:
                        player_id = player["player_id"]
                        logger.debug(f"Event {event_id}: Found player '{player_name}' with ID: {player_id} (team context match) in {time.time() - start_time:.2f}s.")
                        return player_id
            
            player_id = response.data[0]["player_id"]
            player_actual_name = response.data[0]["name"]
            logger.debug(f"Event {event_id}: Found player '{player_name}' -> '{player_actual_name}' with ID: {player_id} (first match) in {time.time() - start_time:.2f}s.")
            return player_id
        except asyncio.TimeoutError:
            logger.error(f"Event {event_id}: Timeout during Supabase operation in _link_player for '{player_name}'.")
            return None
        except Exception as e:
            logger.error(f"Event {event_id}: Error searching for player '{player_name}': {e}", exc_info=True)
            return None

    async def _link_coach(self, coach_name: str, event_id: str, context_team_ids: list[int] | None = None) -> int | None:
        start_time = time.time()
        try:
            query_builder = self.supabase_client.table("coaches").select("coach_id, name, current_team_id").ilike("name", f"%{coach_name}%")
            response = await self._execute_blocking_io(query_builder.execute, timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS)
            
            if not response.data:
                logger.debug(f"Event {event_id}: Coach not found: {coach_name}. Duration: {time.time() - start_time:.2f}s.")
                return None
            
            if context_team_ids:
                for coach in response.data:
                    if coach.get("current_team_id") in context_team_ids:
                        coach_id = coach["coach_id"]
                        logger.debug(f"Event {event_id}: Found coach '{coach_name}' with ID: {coach_id} (team context match) in {time.time() - start_time:.2f}s.")
                        return coach_id
            
            coach_id = response.data[0]["coach_id"] 
            coach_actual_name = response.data[0]["name"]
            logger.debug(f"Event {event_id}: Found coach '{coach_name}' -> '{coach_actual_name}' with ID: {coach_id} (first match) in {time.time() - start_time:.2f}s.")
            return coach_id
        except asyncio.TimeoutError:
            logger.error(f"Event {event_id}: Timeout during Supabase operation in _link_coach for '{coach_name}'.")
            return None
        except Exception as e:
            logger.error(f"Event {event_id}: Error searching for coach '{coach_name}': {e}", exc_info=True)
            return None

    async def _generate_embedding(self, text: str, event_id: str) -> list[float] | None:
        retries = 0
        while retries < OPENAI_MAX_RETRIES:
            try:
                start_time = time.time()
                logger.debug(f"Event {event_id}: Generating embedding (attempt {retries + 1}/{OPENAI_MAX_RETRIES}) for text (first 50 chars): {text[:50]}...")
                response = await self.openai_client.embeddings.create(
                    input=[text.strip()], model=OPENAI_EMBEDDING_MODEL
                )
                embedding = response.data[0].embedding
                duration = time.time() - start_time
                logger.debug(f"Event {event_id}: Embedding generated, dimension: {len(embedding)}, duration: {duration:.2f}s.")
                return embedding
            except OpenAIRateLimitError as e:
                logger.warning(f"Event {event_id}: OpenAI embedding rate limit. Retrying in {OPENAI_RETRY_DELAY_SECONDS * (2**retries)}s. Error: {e}")
                await asyncio.sleep(OPENAI_RETRY_DELAY_SECONDS * (2**retries))
                retries += 1
            except OpenAPITimeoutError as e:
                logger.warning(f"Event {event_id}: OpenAI embedding request timed out. Retrying in {OPENAI_RETRY_DELAY_SECONDS * (2**retries)}s. Error: {e}")
                await asyncio.sleep(OPENAI_RETRY_DELAY_SECONDS * (2**retries))
                retries += 1
            except OpenAIAPIError as e:
                logger.error(f"Event {event_id}: OpenAI embedding API error: {e}. Retrying...")
                await asyncio.sleep(OPENAI_RETRY_DELAY_SECONDS * (2**retries))
                retries += 1
            except Exception as e:
                logger.error(f"Event {event_id}: Failed to generate embedding: {e}", exc_info=True)
                return None # Не повторяем при неизвестных ошибках

        logger.error(f"Event {event_id}: Failed to generate embedding after {OPENAI_MAX_RETRIES} retries.")
        return None

    async def _upsert_to_pinecone(self, vector_id: str, embedding: list[float], metadata: dict, event_id: str):
        logger.info(f"Event {event_id}: Upserting vector to Pinecone with ID: {vector_id}")
        start_time = time.time()
        try:
            pinecone_metadata = {}
            for key, value in metadata.items():
                if value is None: continue
                elif isinstance(value, (list, dict)): pinecone_metadata[key] = json.dumps(value) if value else ""
                elif isinstance(value, uuid.UUID): pinecone_metadata[key] = str(value)
                elif isinstance(value, bool): pinecone_metadata[key] = str(value).lower()
                else: pinecone_metadata[key] = str(value)
            
            await self._execute_blocking_io(
                self.pinecone_index.upsert,
                vectors=[(vector_id, embedding, pinecone_metadata)],
                timeout=PINECONE_REQUEST_TIMEOUT_SECONDS
            )
            duration = time.time() - start_time
            logger.info(f"Event {event_id}: Successfully upserted vector {vector_id} to Pinecone in {duration:.2f}s.")
        except asyncio.TimeoutError:
            logger.error(f"Event {event_id}: Timeout during Pinecone upsert for vector {vector_id}.")
            raise # Позволяем process_event_payload обработать это
        except Exception as e:
            logger.error(f"Event {event_id}: Failed to upsert vector {vector_id} to Pinecone: {e}", exc_info=True)
            raise e # Позволяем process_event_payload обработать это

    async def _save_chunk_data_to_supabase(self, processed_document_id: uuid.UUID, chunks_data: list, event_id: str) -> bool:
        logger.info(f"Event {event_id}: Saving {len(chunks_data)} chunks to Supabase for document {processed_document_id}")
        overall_success = True
        for chunk_data in chunks_data:
            try:
                chunk_id = await self._save_single_chunk(processed_document_id, chunk_data, event_id)
                if not chunk_id:
                    logger.error(f"Event {event_id}: Failed to save chunk {chunk_data.get('chunk_index', '?')} for doc {processed_document_id}")
                    overall_success = False
                    continue 
                chunk_data["supabase_chunk_id"] = chunk_id
                await self._save_chunk_entity_links(chunk_id, chunk_data, event_id)
            except asyncio.TimeoutError:
                logger.error(f"Event {event_id}: Timeout saving chunk {chunk_data.get('chunk_index', '?')} or its links to Supabase for doc {processed_document_id}.")
                overall_success = False # Отмечаем общую неудачу, но продолжаем с другими чанками
            except Exception as e:
                logger.error(f"Event {event_id}: General error saving chunk {chunk_data.get('chunk_index', '?')} or links: {e}", exc_info=True)
                overall_success = False
        
        if overall_success:
            logger.info(f"Event {event_id}: Successfully saved all intended chunks for document {processed_document_id}")
        else:
            logger.warning(f"Event {event_id}: Some chunks or links for document {processed_document_id} failed to save.")
        return overall_success

    async def _save_single_chunk(self, processed_document_id: uuid.UUID, chunk_data: dict, event_id: str) -> uuid.UUID | None:
        start_time = time.time()
        try:
            event_date_mentioned_str = chunk_data.get("event_date_mentioned")
            event_date_to_save = None

            if event_date_mentioned_str:
                try:
                    # Попытка распознать разные форматы и привести к YYYY-MM-DD
                    if isinstance(event_date_mentioned_str, str):
                        if len(event_date_mentioned_str) == 10 and event_date_mentioned_str.count('-') == 2:
                            # Похоже на YYYY-MM-DD
                            dt_obj = datetime.strptime(event_date_mentioned_str, "%Y-%m-%d")
                            event_date_to_save = dt_obj.strftime("%Y-%m-%d")
                        elif len(event_date_mentioned_str) == 7 and event_date_mentioned_str.count('-') == 1:
                            # Похоже на YYYY-MM
                            dt_obj = datetime.strptime(event_date_mentioned_str, "%Y-%m")
                            event_date_to_save = dt_obj.strftime("%Y-%m-%d") # Сохраняем как первый день месяца
                        elif len(event_date_mentioned_str) == 4 and event_date_mentioned_str.isdigit():
                            # Похоже на YYYY
                            dt_obj = datetime.strptime(event_date_mentioned_str, "%Y")
                            event_date_to_save = dt_obj.strftime("%Y-%m-%d") # Сохраняем как 1 января этого года
                        else:
                            logger.warning(f"Event {event_id}: Unrecognized date string format for event_date_mentioned: '{event_date_mentioned_str}'. Will be set to NULL.")
                    else:
                        logger.warning(f"Event {event_id}: event_date_mentioned is not a string: '{event_date_mentioned_str}'. Will be set to NULL.")
                except ValueError as date_error: # Ошибка при strptime (некорректная дата, как 2024-25-01)
                    logger.warning(f"Event {event_id}: Invalid date value for event_date_mentioned '{event_date_mentioned_str}': {date_error}. Will be set to NULL.")
                except Exception as e_date_parse: # Другие неожиданные ошибки парсинга
                    logger.error(f"Event {event_id}: Unexpected error parsing event_date_mentioned '{event_date_mentioned_str}': {e_date_parse}. Will be set to NULL.")
            
            chunk_insert_data = {
                "processed_document_id": str(processed_document_id), "chunk_index": chunk_data.get("chunk_index", 0),
                "chunk_text": chunk_data.get("chunk_text", ""), "summary": chunk_data.get("summary"),
                "chunk_type": chunk_data.get("chunk_type"), "tone": chunk_data.get("tone"),
                "importance_score": chunk_data.get("importance_score"), "source_reference": chunk_data.get("source_reference"),
                "quoted_person": chunk_data.get("quoted_person"), "event_date_mentioned": event_date_to_save, # Используем обработанное значение
                "pinecone_vector_id": chunk_data.get("pinecone_vector_id"),
            }
            cleaned_data = {k: v for k, v in chunk_insert_data.items() if v is not None}
            
            response = await self._execute_blocking_io(
                self.supabase_client.table("document_chunks").insert(cleaned_data).execute,
                timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
            )
            
            if response.data and len(response.data) > 0:
                chunk_id = uuid.UUID(response.data[0]['id'])
                logger.debug(f"Event {event_id}: Saved chunk {chunk_data.get('chunk_index', '?')} with ID: {chunk_id} in {time.time() - start_time:.2f}s.")
                return chunk_id
            else:
                logger.error(f"Event {event_id}: Failed to save chunk. Supabase Response: {response}")
                return None
        except asyncio.TimeoutError:
            logger.error(f"Event {event_id}: Timeout during Supabase operation in _save_single_chunk for chunk {chunk_data.get('chunk_index', '?')}.")
            return None # Явный возврат при таймауте
        except Exception as e:
            logger.error(f"Event {event_id}: Error saving single chunk: {e}", exc_info=True)
            return None

    async def _save_chunk_entity_links(self, chunk_id: uuid.UUID, chunk_data: dict, event_id: str):
        start_time = time.time()
        try:
            linked_team_ids = chunk_data.get("linked_team_ids", [])
            linked_player_ids = chunk_data.get("linked_player_ids", [])
            linked_coach_ids = chunk_data.get("linked_coach_ids", [])
            
            # Оборачиваем каждый тип в отдельный try-except, чтобы одна ошибка не прервала все
            # Сохраняем связи с командами
            if linked_team_ids:
                try:
                    team_links = [{"chunk_id": str(chunk_id), "team_id": team_id} for team_id in linked_team_ids]
                    response = await self._execute_blocking_io(
                        self.supabase_client.table("chunk_linked_teams").insert(team_links).execute,
                        timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
                    )
                    if response.data: logger.debug(f"Event {event_id}: Saved {len(team_links)} team links for chunk {chunk_id}.")
                    else: logger.warning(f"Event {event_id}: Failed to save team links for chunk {chunk_id}. Response: {response}")
                except asyncio.TimeoutError:
                    logger.error(f"Event {event_id}: Timeout saving team links for chunk {chunk_id}.")
                except Exception as e_team:
                    logger.error(f"Event {event_id}: Error saving team links for chunk {chunk_id}: {e_team}", exc_info=True)

            # Сохраняем связи с игроками
            if linked_player_ids:
                try:
                    player_links = [{"chunk_id": str(chunk_id), "player_id": player_id} for player_id in linked_player_ids]
                    response = await self._execute_blocking_io(
                        self.supabase_client.table("chunk_linked_players").insert(player_links).execute,
                        timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
                    )
                    if response.data: logger.debug(f"Event {event_id}: Saved {len(player_links)} player links for chunk {chunk_id}.")
                    else: logger.warning(f"Event {event_id}: Failed to save player links for chunk {chunk_id}. Response: {response}")
                except asyncio.TimeoutError:
                    logger.error(f"Event {event_id}: Timeout saving player links for chunk {chunk_id}.")
                except Exception as e_player:
                    logger.error(f"Event {event_id}: Error saving player links for chunk {chunk_id}: {e_player}", exc_info=True)

            # Сохраняем связи с тренерами
            if linked_coach_ids:
                try:
                    coach_links = [{"chunk_id": str(chunk_id), "coach_id": coach_id} for coach_id in linked_coach_ids]
                    response = await self._execute_blocking_io(
                        self.supabase_client.table("chunk_linked_coaches").insert(coach_links).execute,
                        timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
                    )
                    if response.data: logger.debug(f"Event {event_id}: Saved {len(coach_links)} coach links for chunk {chunk_id}.")
                    else: logger.warning(f"Event {event_id}: Failed to save coach links for chunk {chunk_id}. Response: {response}")
                except asyncio.TimeoutError:
                    logger.error(f"Event {event_id}: Timeout saving coach links for chunk {chunk_id}.")
                except Exception as e_coach:
                     logger.error(f"Event {event_id}: Error saving coach links for chunk {chunk_id}: {e_coach}", exc_info=True)
            
            logger.debug(f"Event {event_id}: Finished saving entity links for chunk {chunk_id} in {time.time() - start_time:.2f}s.")

        except Exception as e: # Общий перехват, если что-то пошло не так до индивидуальных блоков
            logger.error(f"Event {event_id}: General error in _save_chunk_entity_links for chunk {chunk_id}: {e}", exc_info=True)

    async def process_event_payload(self, event_id: str, payload: dict):
        logger.info(f"Event {event_id}: Starting processing.")
        processing_start_time = time.time()
        
        article_full_text = payload.get("full_text")
        source = payload.get("source", "unknown_source")
        document_url = payload.get("url")
        document_title = payload.get("title")
        document_timestamp = payload.get("article_timestamp_iso")

        if not document_url:
            logger.warning(f"Event {event_id}: Does not have a document URL. Acknowledging and skipping.")
            return True 

        if not article_full_text:
            logger.warning(f"Event {event_id}: (URL: {document_url}) does not have full_text. Acknowledging and skipping LLM processing.")
            return True

        # 1. LLM
        logger.info(f"Event {event_id}: Calling LLM...")
        chunk_list = await self._call_openai_llm(article_full_text, event_id)
        if not chunk_list:
            logger.error(f"Event {event_id}: Failed to get chunks from LLM (URL: {document_url}). Will not acknowledge.")
            return False 

        # 2. Processed Document
        logger.info(f"Event {event_id}: Getting/creating processed document entry...")
        processed_document_id = await self._get_or_create_processed_document(
            source=source, document_url=document_url, document_title=document_title,
            document_timestamp=document_timestamp, event_id=event_id
        )
        if not processed_document_id:
            logger.error(f"Event {event_id}: Failed to get or create processed document. Will not acknowledge.")
            return False

        # 3. Process Chunks
        logger.info(f"Event {event_id}: Processing {len(chunk_list)} chunks from LLM for document {processed_document_id}...")
        processed_chunks_for_pinecone = [] # Собираем данные для Pinecone отдельно
        
        all_chunks_processed_successfully = True

        for i, chunk_data in enumerate(chunk_list):
            chunk_start_time = time.time()
            chunk_index = i
            logger.debug(f"Event {event_id}: Processing chunk {chunk_index + 1}/{len(chunk_list)}...")
            chunk_data["chunk_index"] = chunk_index
            
            # Линковка сущностей
            linked_entities_from_llm = []
            for team_name in chunk_data.get("linked_team_names", []): linked_entities_from_llm.append({"type": "team", "name": team_name})
            for player_name in chunk_data.get("linked_player_names", []): linked_entities_from_llm.append({"type": "player", "name": player_name})
            for coach_name in chunk_data.get("linked_coach_names", []): linked_entities_from_llm.append({"type": "coach", "name": coach_name})
            
            linked_team_ids, linked_player_ids, linked_coach_ids = [], [], []
            context_team_ids = []
            
            entity_linking_failed = False
            try:
                for entity in linked_entities_from_llm:
                    if entity.get("type") == "team":
                        team_id = await self._link_entity(entity.get("name", ""), "team", event_id)
                        if team_id: 
                            linked_team_ids.append(team_id)
                            context_team_ids.append(team_id)
                
                for entity in linked_entities_from_llm:
                    entity_type, entity_name = entity.get("type"), entity.get("name", "")
                    if entity_type == "player":
                        player_id = await self._link_entity(entity_name, "player", event_id, context_team_ids)
                        if player_id: linked_player_ids.append(player_id)
                    elif entity_type == "coach":
                        coach_id = await self._link_entity(entity_name, "coach", event_id, context_team_ids)
                        if coach_id: linked_coach_ids.append(coach_id)
            except asyncio.TimeoutError: # Если _link_entity выбросил таймаут
                logger.error(f"Event {event_id}, Chunk {chunk_index}: Timeout during entity linking. Skipping further processing for this chunk.")
                all_chunks_processed_successfully = False
                entity_linking_failed = True # Помечаем, чтобы не идти дальше с этим чанком
            except Exception as e_link: # Другие ошибки при линковке
                logger.error(f"Event {event_id}, Chunk {chunk_index}: Error during entity linking: {e_link}. Skipping further processing for this chunk.")
                all_chunks_processed_successfully = False
                entity_linking_failed = True
            
            if entity_linking_failed:
                continue # Переходим к следующему чанку, если линковка не удалась

            chunk_data["linked_team_ids"] = linked_team_ids
            chunk_data["linked_player_ids"] = linked_player_ids
            chunk_data["linked_coach_ids"] = linked_coach_ids
            # chunk_data["linked_entities_from_llm"] = linked_entities_from_llm # Можно сохранить для отладки, если нужно
            
            # Генерируем эмбеддинг
            text_to_embed = chunk_data.get("chunk_text", "")
            embedding = None
            if text_to_embed:
                embedding = await self._generate_embedding(text_to_embed, event_id)
            
            if not embedding:
                logger.warning(f"Event {event_id}, Chunk {chunk_index}: Failed to generate embedding. This chunk will not be added to Pinecone.")
                # Решаем, что делать: пропускать чанк или сохранять без эмбеддинга. Сейчас - не добавляем в Pinecone.
                # Но в Supabase он может быть сохранен.
                all_chunks_processed_successfully = False # Отмечаем, т.к. не все этапы пройдены
                # Продолжаем сохранять в Supabase, но не в Pinecone
            
            chunk_data["embedding"] = embedding # будет None, если не сгенерирован
            
            # Сохраняем данные для Pinecone (ID чанка из Supabase будет добавлен позже)
            if embedding: # Только если эмбеддинг есть
                pinecone_meta = {
                    "processed_document_id": str(processed_document_id), "chunk_index": chunk_index,
                    "source": source, "document_url": document_url or "", "document_title": document_title or "",
                    "chunk_type": chunk_data.get("chunk_type", ""), "tone": chunk_data.get("tone", ""),
                    "importance_score": chunk_data.get("importance_score", 3),
                    "linked_team_ids": [str(tid) for tid in linked_team_ids if tid is not None], # Преобразование в список строк
                    "linked_player_ids": [str(pid) for pid in linked_player_ids if pid is not None], # Преобразование в список строк
                    "linked_coach_ids": [str(cid) for cid in linked_coach_ids if cid is not None], # Преобразование в список строк
                }
                processed_chunks_for_pinecone.append({
                    "embedding": embedding, 
                    "metadata": pinecone_meta,
                    "original_chunk_data_ref": chunk_data # Ссылка для получения ID из Supabase
                })
            logger.debug(f"Event {event_id}: Chunk {chunk_index + 1} processed in {time.time() - chunk_start_time:.2f}s.")
            
        # 3.2. Сохраняем все чанки (которые прошли первичную обработку) в Supabase
        logger.info(f"Event {event_id}: Saving {len(chunk_list)} parsed chunks to Supabase...")
        # chunk_list содержит все чанки, даже если для каких-то не удалось сгенерировать эмбеддинг
        # или были проблемы с линковкой (в этом случае они уже пропущены выше)
        
        # Отфильтруем чанки, для которых линковка сущностей могла провалиться и они были пропущены
        valid_chunks_for_supabase = [cd for cd in chunk_list if "linked_team_ids" in cd] # Проверяем наличие ключа как индикатор успешной линковки
        
        supabase_save_successful = await self._save_chunk_data_to_supabase(processed_document_id, valid_chunks_for_supabase, event_id)
        if not supabase_save_successful:
            logger.error(f"Event {event_id}: Failed to save some/all chunks to Supabase for document {processed_document_id}. Subsequent Pinecone uploads might be incomplete.")
            all_chunks_processed_successfully = False # Обновляем общий флаг
        
        # 3.3. Загружаем эмбеддинги в Pinecone
        if processed_chunks_for_pinecone:
            logger.info(f"Event {event_id}: Upserting {len(processed_chunks_for_pinecone)} vectors to Pinecone...")
            pinecone_vectors_to_upsert = []
            for pinecone_entry in processed_chunks_for_pinecone:
                # ID чанка из Supabase должен быть в 'original_chunk_data_ref'
                supabase_chunk_id = pinecone_entry["original_chunk_data_ref"].get("supabase_chunk_id")
                if supabase_chunk_id:
                    pinecone_vectors_to_upsert.append(
                        (str(supabase_chunk_id), pinecone_entry["embedding"], pinecone_entry["metadata"])
                    )
                    # Обновляем pinecone_vector_id в Supabase (асинхронно, но без ожидания здесь, чтобы не блокировать)
                    # Важно: это "fire and forget", ошибки обновления не остановят основной процесс, но залогируются
                    async def update_pinecone_id_in_supabase(s_chunk_id, p_doc_id, ev_id):
                        try:
                            await self._execute_blocking_io(
                                self.supabase_client.table("document_chunks").update({"pinecone_vector_id": str(s_chunk_id)})
                                .eq("id", str(s_chunk_id)).execute,
                                timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS
                            )
                            logger.debug(f"Event {ev_id}: Updated pinecone_vector_id for Supabase chunk {s_chunk_id}")
                        except Exception as e_sup_update:
                            logger.warning(f"Event {ev_id}: Failed to update pinecone_vector_id for Supabase chunk {s_chunk_id}: {e_sup_update}")
                    
                    asyncio.create_task(update_pinecone_id_in_supabase(supabase_chunk_id, processed_document_id, event_id))

                else:
                    logger.warning(f"Event {event_id}: Skipping Pinecone upsert for a chunk - missing supabase_chunk_id. Original data: {pinecone_entry['original_chunk_data_ref'].get('chunk_text', '')[:50]}")
                    all_chunks_processed_successfully = False

            if pinecone_vectors_to_upsert:
                try:
                    await self._execute_blocking_io(
                        self.pinecone_index.upsert,
                        vectors=pinecone_vectors_to_upsert,
                        timeout=PINECONE_REQUEST_TIMEOUT_SECONDS * (len(pinecone_vectors_to_upsert) // 100 + 1) # Увеличиваем таймаут для батчей
                    )
                    logger.info(f"Event {event_id}: Successfully submitted {len(pinecone_vectors_to_upsert)} vectors to Pinecone.")
                except asyncio.TimeoutError:
                    logger.error(f"Event {event_id}: Timeout during batch Pinecone upsert.")
                    all_chunks_processed_successfully = False
                except Exception as e_pine_batch:
                    logger.error(f"Event {event_id}: Error during batch Pinecone upsert: {e_pine_batch}", exc_info=True)
                    all_chunks_processed_successfully = False
        else:
            logger.info(f"Event {event_id}: No vectors to upsert to Pinecone (possibly no embeddings generated or no Supabase IDs).")


        duration = time.time() - processing_start_time
        if all_chunks_processed_successfully and supabase_save_successful:
            logger.info(f"Event {event_id}: Successfully processed. Total time: {duration:.2f}s. Acknowledging message.")
            return True
        else:
            logger.warning(f"Event {event_id}: Processed with some errors. Total time: {duration:.2f}s. Will not acknowledge.")
            return False


    async def run_consumer(self):
        consumer_name = f"{CONSUMER_NAME_PREFIX}{uuid.uuid4()}"
        logger.info(f"Starting LLM Content Analyzer consumer: {consumer_name} for stream: {RAW_EVENTS_STREAM_NAME}")

        try:
            await self.redis_client.xgroup_create(
                name=RAW_EVENTS_STREAM_NAME,
                groupname=CONSUMER_GROUP_NAME,
                id="0",  # Начать с самого начала, если группа новая
                mkstream=True # Создать стрим, если его нет
            )
            logger.info(f"Consumer group {CONSUMER_GROUP_NAME} created or already exists.")
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group {CONSUMER_GROUP_NAME} already exists.")
            else:
                logger.error(f"Failed to create consumer group: {e}")
                return

        while True:
            try:
                # Лог перед вызовом xreadgroup
                logger.info(f"Consumer {consumer_name}: Polling Redis stream '{RAW_EVENTS_STREAM_NAME}' for group '{CONSUMER_GROUP_NAME}' with ID '>'. Block: 2000ms, Count: 1") # Уменьшен block time
                messages = await self.redis_client.xreadgroup(
                    groupname=CONSUMER_GROUP_NAME,
                    consumername=consumer_name,
                    streams={RAW_EVENTS_STREAM_NAME: ">"},
                    count=1,
                    block=2000  # 2 секунды, чтобы чаще проверять pending, если нет новых
                )
                # Лог сразу после вызова xreadgroup - ЧТО ИМЕННО ВЕРНУЛОСЬ?
                logger.info(f"Consumer {consumer_name}: xreadgroup call for NEW messages completed. Raw messages object: {messages}")

                if not messages:
                    logger.info(f"Consumer {consumer_name}: No NEW messages returned by xreadgroup. Checking for PENDING messages to claim.")
                    
                    # Пытаемся забрать "зависшие" сообщения
                    # Ищем до 5 сообщений, которые находятся в pending более 10 секунд
                    pending_details = await self.redis_client.xpending_range(
                        RAW_EVENTS_STREAM_NAME, CONSUMER_GROUP_NAME, 
                        count=5, idle=10000, # idle в миллисекундах (10 секунд)
                        min='-', max='+' # Любой ID, любой консьюмер
                    )
                    # pending_details: [{'message_id': '...', 'consumer': '...', 'idle_time': ..., 'delivery_count': ...}]

                    if pending_details:
                        message_ids_to_claim = [p['message_id'] for p in pending_details]
                        logger.info(f"Consumer {consumer_name}: Found {len(message_ids_to_claim)} PENDING messages (idle >10s) to potentially claim: {message_ids_to_claim}")
                        
                        # Пытаемся забрать эти сообщения
                        # min_idle_time=0 здесь означает, что если ID есть в списке, мы его забираем.
                        # Основная проверка на "старость" была в xpending_range.
                        claimed_message_data_tuples = await self.redis_client.xclaim(
                            name=RAW_EVENTS_STREAM_NAME,
                            groupname=CONSUMER_GROUP_NAME,
                            consumername=consumer_name, # Забираем на себя
                            min_idle_time=0, 
                            message_ids=message_ids_to_claim,
                        )
                        # claimed_message_data_tuples: List[Tuple[str_message_id, Dict[str_key, str_value]]] (т.к. decode_responses=True)

                        if claimed_message_data_tuples:
                            # Переформатируем в тот же вид, что и от xreadgroup, для единообразной обработки
                            messages_for_loop = [[
                                RAW_EVENTS_STREAM_NAME, # stream name (string)
                                claimed_message_data_tuples # list of (id, data) tuples
                            ]]
                            messages = messages_for_loop # Это будет обработано существующим циклом
                            num_claimed = len(claimed_message_data_tuples)
                            claimed_ids_str = [msg_id for msg_id, _ in claimed_message_data_tuples]
                            logger.info(f"Consumer {consumer_name}: Successfully CLAIMED {num_claimed} PENDING messages: {claimed_ids_str}")
                        else:
                            logger.info(f"Consumer {consumer_name}: No PENDING messages were actually claimed (could be due to concurrent claims or other reasons).")
                    else:
                        logger.info(f"Consumer {consumer_name}: No PENDING messages found (idle >10s) to claim at this time.")
                
                # Этот лог теперь отражает либо новые, либо успешно забранные pending сообщения
                if messages:
                    logger.info(f"Consumer {consumer_name}: Proceeding to process {len(messages[0][1]) if messages and messages[0] else 0} message(s).")
                else: # Если и новых нет, и pending не забрали
                    logger.info(f"Consumer {consumer_name}: No messages (neither new nor claimed pending) to process. Continuing poll.")
                    continue # Пропускаем остаток цикла и идем на новую итерацию


                for stream_name, message_list in messages:
                    # Лог количества сообщений в полученном списке для данного стрима
                    logger.info(f"Consumer {consumer_name}: Iterating stream '{stream_name}'. Message list length: {len(message_list)}")
                    for message_id, message_data in message_list:
                        logger.info(f"Consumer {consumer_name}: Received message ID: {message_id} from stream: {stream_name}")
                        
                        event_data_json_str = message_data.get("data")
                        payload = {}
                        if event_data_json_str:
                            try:
                                event_data_dict = json.loads(event_data_json_str)
                                payload["source"] = event_data_dict.get("source")
                                inner_payload = event_data_dict.get("payload", {})
                                payload["url"] = inner_payload.get("url")
                                payload["title"] = inner_payload.get("title")
                                payload["full_text"] = inner_payload.get("full_text")
                                payload["article_timestamp_iso"] = inner_payload.get("article_timestamp_iso")
                            except json.JSONDecodeError as e_json:
                                logger.error(f"Consumer {consumer_name}, Event {message_id}: Failed to decode event_data_json_str: {e_json}. Content: {event_data_json_str[:200]}... Acknowledging and skipping.")
                                await self.redis_client.xack(RAW_EVENTS_STREAM_NAME, CONSUMER_GROUP_NAME, message_id)
                                continue
                        else:
                            logger.warning(f"Consumer {consumer_name}, Event {message_id}: Message does not contain 'data' field or it's empty. Raw keys: {list(message_data.keys())}. Acknowledging and skipping.")
                            await self.redis_client.xack(RAW_EVENTS_STREAM_NAME, CONSUMER_GROUP_NAME, message_id)
                            continue

                        if not payload.get("full_text"):
                             logger.warning(f"Consumer {consumer_name}, Event {message_id}: Has no 'full_text' in payload. Acknowledging and skipping.")
                             await self.redis_client.xack(RAW_EVENTS_STREAM_NAME, CONSUMER_GROUP_NAME, message_id)
                             continue
                        
                        # Обработка сообщения с явным таймаутом на всю обработку одного сообщения
                        # Это предотвратит "зависание" всего консьюмера на одном сообщении слишком долго
                        PROCESS_EVENT_TIMEOUT_SECONDS = OPENAI_REQUEST_TIMEOUT_SECONDS + \
                                                        (SUPABASE_REQUEST_TIMEOUT_SECONDS * 10) + \
                                                        (PINECONE_REQUEST_TIMEOUT_SECONDS * 2) + 60 # Запас
                        try:
                            logger.info(f"Consumer {consumer_name}, Event {message_id}: Starting process_event_payload with timeout {PROCESS_EVENT_TIMEOUT_SECONDS}s.")
                            ack_needed = await asyncio.wait_for(
                                self.process_event_payload(message_id, payload), 
                                timeout=PROCESS_EVENT_TIMEOUT_SECONDS
                            )
                        except asyncio.TimeoutError:
                            logger.error(f"Consumer {consumer_name}, Event {message_id}: process_event_payload timed out after {PROCESS_EVENT_TIMEOUT_SECONDS}s. Will not acknowledge.")
                            ack_needed = False # Не подтверждать при общем таймауте обработки
                        except Exception as e_process:
                            logger.error(f"Consumer {consumer_name}, Event {message_id}: Unhandled exception in process_event_payload: {e_process}", exc_info=True)
                            ack_needed = False # Не подтверждать при других неожиданных ошибках

                        if ack_needed:
                            await self.redis_client.xack(RAW_EVENTS_STREAM_NAME, CONSUMER_GROUP_NAME, message_id)
                            logger.info(f"Consumer {consumer_name}, Event {message_id}: Message acknowledged.")
                        else:
                            logger.warning(f"Consumer {consumer_name}, Event {message_id}: Processing failed or incomplete. Message will NOT be acknowledged.")
                            # Здесь можно добавить логику для XPENDING или dead-letter queue в будущем.

            except RedisTimeoutError: # Это таймаут xreadgroup, не ошибка
                logger.debug(f"Consumer {consumer_name}: No new messages within Redis block timeout, continuing poll.")
                continue
            except RedisConnectionError as e_redis_conn:
                logger.error(f"Consumer {consumer_name}: Connection to Redis failed: {e_redis_conn}. Retrying in 10 seconds...")
                await asyncio.sleep(10)
            except Exception as e_loop:
                logger.error(f"Consumer {consumer_name}: An unexpected error occurred in the main consumer loop: {e_loop}", exc_info=True)
                await asyncio.sleep(5) # Пауза перед повторной попыткой

    async def test_connections(self):
        logger.info("Testing connections to external services...")
        
        # Тест Redis
        try:
            await self.redis_client.ping()
            logger.info("✅ Redis connection: OK")
        except RedisConnectionError as e:
            logger.error(f"❌ Redis connection failed: {e}")
        except Exception as e:
            logger.error(f"❌ Redis connection failed during ping: {e}")
            
        # Тест OpenAI
        try:
            # Простой тест API ключа
            models = await self.openai_client.models.list()
            logger.info("✅ OpenAI API connection: OK")
        except Exception as e:
            logger.error(f"❌ OpenAI API connection failed: {e}")
            
        # Тест Supabase
        try:
            # Простой запрос для проверки соединения
            response = self.supabase_client.table("teams").select("count", count="exact").limit(1).execute()
            logger.info("✅ Supabase connection: OK")
        except Exception as e:
            logger.error(f"❌ Supabase connection failed: {e}")
            
        # Тест Pinecone
        try:
            stats = self.pinecone_index.describe_index_stats()
            logger.info(f"✅ Pinecone connection: OK (vectors: {stats.total_vector_count})")
        except Exception as e:
            logger.error(f"❌ Pinecone connection failed: {e}")

async def main():
    print("DEBUG: llm_content_analyzer.py - __main__ block started") # Отладочный print
    logger.info("--- LLM Content Analyzer Service Starting ---")
    
    # Увеличиваем уровень логгирования для httpx, чтобы видеть запросы, если нужно для глубокой отладки
    # logging.getLogger("httpx").setLevel(logging.DEBUG) 
    # logging.getLogger("httpcore").setLevel(logging.DEBUG)

    try:
        analyzer = LLMContentAnalyzer()
        logger.info("LLM Content Analyzer initialized successfully.")
        
        # Тестируем подключения перед запуском консьюмера
        await analyzer.test_connections()
        
        logger.info("Starting consumer...")
        await analyzer.run_consumer()
    except ValueError as e:
        logger.critical(f"Failed to initialize LLM Content Analyzer: {e}")
        return
    except Exception as e:
        logger.critical(f"Unexpected error during initialization: {e}")
        return

if __name__ == "__main__":
    asyncio.run(main()) 