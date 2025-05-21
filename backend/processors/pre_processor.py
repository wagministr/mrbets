"""
Pre-Processor

Handles preprocessing of raw event data:
1. Translation (if needed)
2. Text chunking
3. Source reliability scoring
4. Embedding generation
5. Storage in Pinecone and Supabase
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import langdetect
import redis
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client as SupabaseClient
import spacy
from pinecone import Pinecone

# Set up logging
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RAW_EVENTS_STREAM = "stream:raw_events"

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"

# Yandex Translate configuration
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_TRANSLATE_URL = "https://translate.api.cloud.yandex.net/translate/v2/translate"
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
S3_BUCKET = os.getenv("SUPABASE_BUCKET_NAME", "mrbets-raw")

# Pinecone configuration
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "mrbets-content-chunks")

# Source reliability ratings (0.0 to 1.0)
SOURCE_RELIABILITY = {
    "api_football": 1.0,  # Official data
    "bbc_sport": 0.9,
    "espn": 0.85,  # Reliable sports media
    "twitter": 0.6,  # Social media, mixed reliability
    "telegram": 0.6,  # Social media, mixed reliability
    "youtube": 0.7,  # Video content, depends on channel
    "reddit": 0.5,  # Community content
    # Add more sources as needed
}


class PreProcessor:
    """Preprocesses raw event data"""

    def __init__(self):
        """Initialize the preprocessor"""
        try:
            self.redis_client = redis.from_url(REDIS_URL)
            logger.info("Successfully connected to Redis for PreProcessor.")
        except ImportError:
            self.redis_client = None
            logger.warning("redis library not found. Redis functionality disabled for PreProcessor.")
        except Exception as e:
            self.redis_client = None
            logger.error(f"Failed to connect to Redis for PreProcessor: {e}")

        if OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("Successfully initialized OpenAI client for PreProcessor.")
        else:
            self.openai_client = None
            logger.warning("OPENAI_API_KEY not provided. OpenAI functionality disabled for PreProcessor.")
        
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # For text chunking
        
        if SUPABASE_URL and SUPABASE_KEY:
            self.supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Successfully initialized Supabase client for PreProcessor.")
        else:
            self.supabase = None
            logger.warning("Supabase URL or Key not provided. Supabase functionality disabled for PreProcessor.")

        self.nlp = None
        try:
            self.nlp = spacy.load("en_core_web_sm")
            logger.info("Successfully loaded spaCy model 'en_core_web_sm'.")
        except OSError:
            logger.error("spaCy model 'en_core_web_sm' not found. Please download it: python -m spacy download en_core_web_sm")
            self.nlp = None # Ensure nlp is None if model fails to load
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading spaCy model: {e}")
            self.nlp = None

        self.pinecone_index = None
        if PINECONE_API_KEY and PINECONE_ENVIRONMENT and PINECONE_INDEX_NAME:
            try:
                pc = Pinecone(api_key=PINECONE_API_KEY, environment=PINECONE_ENVIRONMENT)
                index_list = pc.list_indexes()
                if PINECONE_INDEX_NAME not in [index_info.name for index_info in index_list]:
                    logger.error(f"Pinecone index '{PINECONE_INDEX_NAME}' does not exist. Please create it.")
                else:
                    self.pinecone_index = pc.Index(PINECONE_INDEX_NAME)
                    logger.info(f"Successfully connected to Pinecone index '{PINECONE_INDEX_NAME}'.")
            except Exception as e:
                logger.error(f"Failed to initialize Pinecone: {e}", exc_info=True)
        else:
            logger.warning("Pinecone API Key, Environment, or Index Name not provided. Pinecone functionality disabled.")

    async def detect_language(self, text: str) -> str:
        """Detect the language of a text"""
        if not text: return "en"
        try:
            return await asyncio.to_thread(langdetect.detect, text)
        except Exception as e:
            logger.warning(f"Language detection failed for text snippet '{text[:50]}...': {e}")
            return "en"

    async def translate_text(self, text: str, target_lang: str = "en") -> str:
        """Translate text to the target language using Yandex Translate"""
        if not YANDEX_API_KEY:
            logger.warning("Yandex API key not set, skipping translation")
            return text
        if not text:
            return ""

        source_lang = await self.detect_language(text)
        if source_lang.lower() == target_lang.lower():
            return text

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    YANDEX_TRANSLATE_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Api-Key {YANDEX_API_KEY}",
                    },
                    json={
                        "texts": [text],
                        "targetLanguageCode": target_lang,
                        "folderId": YANDEX_FOLDER_ID,
                    },
                    timeout=10.0 
                )
                response.raise_for_status()
                data = response.json()
                translated_text = data["translations"][0]["text"]
                logger.info(f"Translated text from {source_lang} to {target_lang}. Snippet: '{translated_text[:50]}...'")
                return translated_text
        except httpx.HTTPStatusError as e:
            logger.error(f"Translation API request failed: {e.response.status_code} - {e.response.text}")
            return text
        except Exception as e:
            logger.error(f"Error translating text '{text[:50]}...': {e}")
            return text

    def chunk_text(self, text: str, max_tokens: int = 512) -> List[str]:
        """Split text into chunks of roughly max_tokens using tiktoken logic."""
        if not text: return []
        
        paragraphs = text.split('\n\n')
        final_chunks = []
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            
            paragraph_tokens = self.tokenizer.encode(paragraph)
            if len(paragraph_tokens) <= max_tokens:
                final_chunks.append(self.tokenizer.decode(paragraph_tokens))
            else:
                for i in range(0, len(paragraph_tokens), max_tokens):
                    chunk_tokens = paragraph_tokens[i : i + max_tokens]
                    chunk = self.tokenizer.decode(chunk_tokens)
                    final_chunks.append(chunk.strip())
        
        logger.info(f"Chunked text into {len(final_chunks)} chunks.")
        return final_chunks

    def get_reliability_score(self, source: str) -> float:
        """Get reliability score for a source"""
        return SOURCE_RELIABILITY.get(source.lower(), 0.5)

    async def _get_entities_for_chunk(self, chunk_text: str) -> List[Dict]:
        """Extracts named entities from a text chunk using spaCy. Internal method."""
        if not self.nlp or not chunk_text:
            return []
        try:
            # spaCy NLP processing can be CPU-bound, run in a separate thread
            doc = await asyncio.to_thread(self.nlp, chunk_text)
            entities = [{"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char} for ent in doc.ents]
            logger.debug(f"Extracted {len(entities)} entities from chunk: '{chunk_text[:50]}...'")
            return entities
        except Exception as e:
            logger.error(f"Error extracting entities with spaCy from chunk '{chunk_text[:50]}...': {e}")
            return []

    async def _find_team_ids_from_entities(self, entities: List[Dict]) -> List[int]:
        """Finds team IDs from Supabase based on ORG entities."""
        if not self.supabase or not entities:
            return []
        
        team_names = [entity["text"] for entity in entities if entity["label"] == "ORG"]
        if not team_names:
            return []

        found_team_ids = set()
        try:
            for name in team_names:
                # Search by name and common name patterns
                response = await asyncio.to_thread(
                    self.supabase.table("teams")
                    .select("team_id")
                    .ilike("name", f"%{name}%") # Using ilike for case-insensitive partial match
                    .execute
                )
                if response.data:
                    for team in response.data:
                        found_team_ids.add(team["team_id"])
                # Optionally, search in an 'alternate_names' column if it exists
                # response_alt = await asyncio.to_thread(
                #     self.supabase.table("teams")
                #     .select("team_id")
                #     .ilike("alternate_names", f"%{name}%") # Assuming 'alternate_names' column
                #     .execute
                # )
                # if response_alt.data:
                #     for team in response_alt.data:
                #         found_team_ids.add(team["team_id"])
            
            if found_team_ids:
                logger.info(f"Found team IDs for ORG entities '{team_names}': {list(found_team_ids)}")
            return list(found_team_ids)
        except Exception as e:
            logger.error(f"Error querying Supabase for team IDs with entities {team_names}: {e}")
            return []

    async def _find_player_ids_from_entities(self, entities: List[Dict], context_team_ids: Optional[List[int]] = None) -> List[int]:
        """Finds player IDs from Supabase based on PERSON entities, optionally filtered by team IDs."""
        if not self.supabase or not entities:
            return []

        player_names = [entity["text"] for entity in entities if entity["label"] == "PERSON"]
        if not player_names:
            return []

        found_player_ids = set()
        try:
            for name in player_names:
                # Now using current_team_id and meta_data.statistics for context filtering
                query = self.supabase.table("players").select("player_id, name, nationality, photo_url, current_team_id, meta_data")
                
                name_parts = name.split()
                processed_name = name
                if name.endswith("'s"):
                    processed_name = name[:-2]
                elif name.endswith("'"):
                    processed_name = name[:-1]

                if len(name_parts) > 1:
                    query = query.ilike("name", f"%{processed_name}%")
                else:
                    query = query.ilike("name", f"%{processed_name}%")

                response = await asyncio.to_thread(query.execute)

                if response.data:
                    for player_record in response.data:
                        player_id = player_record["player_id"]
                        
                        if context_team_ids:
                            is_in_context_team = False
                            # Priority 1: Check current_team_id
                            player_current_team_id = player_record.get("current_team_id")
                            if player_current_team_id is not None and player_current_team_id in context_team_ids:
                                is_in_context_team = True
                            
                            # Priority 2: If not found in current_team_id, check meta_data.statistics
                            if not is_in_context_team: # Only check meta_data if not already confirmed by current_team_id
                                player_meta_data = player_record.get("meta_data")
                                if isinstance(player_meta_data, dict):
                                    statistics_list = player_meta_data.get("statistics") # Matches the example structure
                                    if isinstance(statistics_list, list):
                                        for stat_entry in statistics_list:
                                            # Check if stat_entry itself is a dict and team is a dict within it
                                            if isinstance(stat_entry, dict) and isinstance(stat_entry.get("team"), dict):
                                                if stat_entry.get("team", {}).get("id") in context_team_ids:
                                                    is_in_context_team = True
                                                    break # Found a match in statistics
                            
                            if is_in_context_team:
                                found_player_ids.add(player_id)
                            # else:
                                # logger.debug(f"Player {player_record.get('name')} ({player_id}) found, but not in context teams {context_team_ids} via current_team_id or meta_data.statistics.")
                        else: # No context team IDs, add if name matches
                            found_player_ids.add(player_id)
            
            if found_player_ids:
                 logger.info(f"Found player IDs for PERSON entities '{player_names}' (processed: '{processed_name}'): {list(found_player_ids)} (Context teams: {context_team_ids})")
            return list(found_player_ids)
        except Exception as e:
            logger.error(f"Error querying Supabase for player IDs with entities {player_names}: {e}")
            return []

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI API"""
        if not self.openai_client or not text:
            return None
        try:
            response = await asyncio.to_thread(
                self.openai_client.embeddings.create,
                input=[text.replace("\n", " ")],
                model=EMBEDDING_MODEL
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding for text '{text[:50]}...': {e}")
            return None

    async def store_to_supabase_processed_document(
        self,
        source: str,
        document_url: Optional[str],
        document_title: Optional[str],
        document_timestamp_str: Optional[str],
        overall_match_id: Optional[int],
        overall_entities: List[Dict],
        processed_chunks_for_db: List[Dict],
        reliability_score: float
    ) -> Optional[str]:
        """Stores the processed document with its chunks into the 'processed_documents' table."""
        if not self.supabase:
            logger.warning("Supabase client not available. Skipping store_to_supabase_processed_document.")
            return None

        document_to_insert = {
            "source": source,
            "document_url": document_url,
            "document_title": document_title,
            "document_timestamp": document_timestamp_str,
            "overall_match_id": overall_match_id,
            "overall_entities": json.dumps(overall_entities), 
            "structured_content": json.dumps(processed_chunks_for_db), 
            "reliability_score": reliability_score
        }
        try:
            response = await asyncio.to_thread(
                self.supabase.table("processed_documents").insert(document_to_insert).execute
            )
            if getattr(response, 'error', None):
                 logger.error(f"Failed to insert processed document into Supabase: {response.error}")
                 return None
            else:
                inserted_id = response.data[0]['id'] if response.data and len(response.data) > 0 else None
                logger.info(f"Successfully inserted processed document for {document_url} into Supabase with ID: {inserted_id}.")
                return inserted_id
        except Exception as e:
            logger.error(f"Supabase insert to processed_documents failed: {e}", exc_info=True)
            return None

    async def store_chunk_to_pinecone(self, chunk_id: str, vector: List[float], metadata: Dict) -> bool:
        """Stores a single chunk vector and its metadata to Pinecone."""
        if not self.pinecone_index:
            logger.warning("Pinecone index not available. Skipping store_chunk_to_pinecone.")
            return False
        
        try:
            # Ensure all metadata values are suitable for Pinecone (strings, numbers, booleans, or lists of strings)
            # Pinecone doesn't support nested dicts directly in metadata for some clients/versions. Flatten if necessary.
            # For now, assuming metadata structure is simple.
            
            # Convert lists of numbers to lists of strings if necessary, or ensure they are simple lists.
            # Example: metadata["relevant_match_ids"] = [str(mid) for mid in metadata.get("relevant_match_ids", [])]
            
            await asyncio.to_thread(
                self.pinecone_index.upsert,
                vectors=[(chunk_id, vector, metadata)]
            )
            logger.info(f"Successfully upserted chunk {chunk_id} to Pinecone.")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert chunk {chunk_id} to Pinecone: {e}", exc_info=True)
            return False

    async def process_event(self, event_data_bytes: Dict[str, bytes]) -> bool:
        """Process a raw event"""
        try:
            match_id_bytes = event_data_bytes.get(b"match_id")
            match_id_str = match_id_bytes.decode("utf-8") if match_id_bytes else None
            
            current_match_id: Optional[int] = None
            if match_id_str and match_id_str.lower() != 'none':
                try:
                    current_match_id = int(match_id_str)
                except ValueError:
                    logger.warning(f"Could not convert match_id '{match_id_str}' to int. Treating as None.")

            source = event_data_bytes.get(b"source", b"unknown").decode("utf-8")
            
            payload_json = event_data_bytes.get(b"payload", b"{}").decode("utf-8")
            payload = json.loads(payload_json)

            logger.info(f"PreProcessor processing event: match_id={current_match_id}, source={source}, payload URL: {payload.get('url')}")

            full_text = payload.get("full_text")
            document_url = payload.get("url")
            document_title = payload.get("title")
            article_timestamp_iso = payload.get("article_timestamp_iso")
            document_timestamp_str = article_timestamp_iso or payload.get("timestamp")

            if not full_text:
                logger.warning(f"No full_text in payload for source {source}, URL {document_url}. Skipping.")
                return False

            translated_full_text = await self.translate_text(full_text)

            text_chunks = self.chunk_text(translated_full_text)
            if not text_chunks:
                logger.warning(f"Text chunking resulted in no chunks for source {source}, URL {document_url}. Skipping.")
                return False

            reliability = self.get_reliability_score(source)
            overall_entities = await self._get_entities_for_chunk(translated_full_text)

            processed_chunks_for_supa_structured_content = []
            embeddings_for_pinecone_upsert = [] # Store tuples of (chunk_index, embedding, team_ids, player_ids)

            for i, chunk_txt in enumerate(text_chunks):
                if not chunk_txt.strip(): 
                    continue

                chunk_entities = await self._get_entities_for_chunk(chunk_txt)
                
                # Entity Linking for the chunk
                chunk_team_ids = await self._find_team_ids_from_entities(chunk_entities)
                # Pass chunk_team_ids to player search for better context, if applicable by player search logic
                chunk_player_ids = await self._find_player_ids_from_entities(chunk_entities, context_team_ids=chunk_team_ids) 

                embedding = await self.generate_embedding(chunk_txt)
                if embedding:
                    embeddings_for_pinecone_upsert.append(
                        (i, embedding, chunk_team_ids, chunk_player_ids, chunk_txt[:50]) # chunk_txt for logging
                    )
                else:
                    logger.warning(f"Failed to generate embedding for chunk {i} of {document_url}")

                current_chunk_match_ids = [current_match_id] if current_match_id is not None else []

                chunk_data_for_supa = {
                    "chunk_index": i,
                    "chunk_text": chunk_txt,
                    "chunk_entities": chunk_entities, # Entities specific to this chunk
                    "relevant_match_ids": current_chunk_match_ids,
                    "relevant_team_ids": chunk_team_ids,
                    "relevant_player_ids": chunk_player_ids,
                }
                processed_chunks_for_supa_structured_content.append(chunk_data_for_supa)
                logger.info(f"Prepared chunk {i+1}/{len(text_chunks)} for Supabase storage (URL: {document_url}). Teams: {chunk_team_ids}, Players: {chunk_player_ids}")
            
            # Step 1: Store the main document and its textual/entity-linked chunks to Supabase
            inserted_doc_id = await self.store_to_supabase_processed_document(
                source=source,
                document_url=document_url,
                document_title=document_title,
                document_timestamp_str=document_timestamp_str,
                overall_match_id=current_match_id,
                overall_entities=overall_entities, # Overall entities for the whole document
                processed_chunks_for_db=processed_chunks_for_supa_structured_content, # This becomes `structured_content`
                reliability_score=reliability
            )

            if not inserted_doc_id:
                logger.error(f"Failed to store base processed document for {document_url} in Supabase. Aborting Pinecone upserts.")
                return False

            # Step 2: If Supabase store was successful, store embeddings to Pinecone
            if self.pinecone_index and embeddings_for_pinecone_upsert:
                pinecone_upsert_count = 0
                for chunk_idx, emb, team_ids, player_ids, chunk_text_log_snippet in embeddings_for_pinecone_upsert:
                    pinecone_chunk_id = f"{inserted_doc_id}_{chunk_idx}"
                    
                    # Ensure all IDs are native Python ints if they come from numpy or elsewhere
                    pinecone_metadata = {
                        "processed_document_id": str(inserted_doc_id), # Ensure it's a string
                        "chunk_index": int(chunk_idx),
                        "source": str(source),
                        "document_url": str(document_url) if document_url else "",
                        "document_title": str(document_title) if document_title else "",
                        # Store lists of IDs as lists of strings for Pinecone compatibility
                        "relevant_match_ids": [str(m_id) for m_id in processed_chunks_for_supa_structured_content[chunk_idx]["relevant_match_ids"]],
                        "relevant_team_ids": [str(t_id) for t_id in team_ids],
                        "relevant_player_ids": [str(p_id) for p_id in player_ids],
                    }
                    
                    success_pinecone = await self.store_chunk_to_pinecone(pinecone_chunk_id, emb, pinecone_metadata)
                    if success_pinecone:
                        pinecone_upsert_count +=1
                logger.info(f"Attempted to upsert {len(embeddings_for_pinecone_upsert)} embeddings to Pinecone for document {inserted_doc_id}. Successful: {pinecone_upsert_count}.")
            elif not self.pinecone_index:
                 logger.warning(f"Pinecone client not available, skipping embedding storage for document {inserted_doc_id}.")
            elif not embeddings_for_pinecone_upsert:
                logger.info(f"No embeddings were generated or available to store in Pinecone for document {inserted_doc_id}.")


            logger.info(f"Successfully processed event for {document_url}. Stored as document ID: {inserted_doc_id}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON payload: {e}. Payload: {event_data_bytes.get(b'payload', b'').decode('utf-8', 'ignore')}")
            return False
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            return False

    async def process(self, event_id: str, event_data: Dict[str, bytes]) -> bool:
        """Process an event from the raw events stream. Called by consumer."""
        logger.info(f"PreProcessor instance ({id(self)}) processing event_id: {event_id}")
        return await self.process_event(event_data)

    async def run_consumer(self, group_name: str = "preprocessor-group", consumer_name: str = f"consumer-{uuid.uuid4()}" ):
        """Run as a consumer in a consumer group for RAW_EVENTS_STREAM"""
        if not self.redis_client:
            logger.error("Redis client not initialized. Cannot run consumer.")
            return

        try:
            try:
                self.redis_client.xgroup_create(RAW_EVENTS_STREAM, group_name, "0", mkstream=True)
                logger.info(f"Created Redis consumer group '{group_name}' for stream '{RAW_EVENTS_STREAM}'.")
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"Consumer group '{group_name}' already exists.")
                else:
                    logger.error(f"Failed to create consumer group '{group_name}': {e}")
                    raise

            logger.info(f"Starting consumer '{consumer_name}' in group '{group_name}' for stream '{RAW_EVENTS_STREAM}'.")

            while True:
                response = self.redis_client.xreadgroup( 
                    groupname=group_name, 
                    consumername=consumer_name, 
                    streams={RAW_EVENTS_STREAM: ">"},
                    count=1, 
                    block=1000
                )

                if not response:
                    await asyncio.sleep(0.1)
                    continue

                for stream_name, events in response:
                    for event_id_bytes, event_data_bytes_dict in events:
                        event_id = event_id_bytes.decode("utf-8")
                        logger.info(f"Received event {event_id} from stream {stream_name.decode('utf-8')}")
                        success = await self.process(event_id, event_data_bytes_dict)
                        if success:
                            self.redis_client.xack(RAW_EVENTS_STREAM, group_name, event_id)
                            logger.info(f"Acknowledged event {event_id}.")
                        else:
                            logger.error(f"Failed to process event {event_id}. It will be retried by another consumer or after timeout.")

        except Exception as e:
            logger.error(f"Critical error in Redis consumer '{consumer_name}': {e}", exc_info=True)
            await asyncio.sleep(5)


if __name__ == "__main__":
    logger.info("Pre-processor module running directly.")
    
    async def main_test():
        logger.info("Starting PreProcessor direct test...")
        test_processor = PreProcessor()

        if not all([test_processor.nlp, test_processor.supabase, test_processor.openai_client, test_processor.pinecone_index]):
            logger.warning("One or more clients (spaCy, Supabase, OpenAI, Pinecone) are not initialized. Test might be limited or fail.")

        sample_payload_dict = {
            "title": "Sample Test: Liverpool vs Chelsea Pre-match Analysis",
            "summary": "A detailed look at the upcoming match between Liverpool and Chelsea, featuring star players like Mohamed Salah and Cole Palmer.",
            "url": "http://example.com/test_liverpool_chelsea_analysis_0123",
            "full_text": "The much anticipated clash between Liverpool FC and Chelsea is just around the corner. Jurgen Klopp's Liverpool team has been in fine form. Key player Mohamed Salah is expected to make a significant impact. \n\nOn the other side, Chelsea, managed by Mauricio Pochettino, will be relying on their young talent Cole Palmer, who has been a revelation this season. The match will be played at Anfield. Some say Manchester City might also be interested in the outcome.",
            "article_timestamp_iso": datetime.now().isoformat(),
            "feed_source_name": "test_feed_preproc",
            "images": [],
            "entities_spacy": [] # This will be populated by scraper_fetcher, pre_processor will re-extract
        }
        
        sample_event_data_bytes = {
            # b"match_id": b"1001", # Example match_id if known
            b"match_id": None, # For testing case where it's a general article not yet tied to a specific upcoming match
            b"source": b"bbc_sport", # A source with high reliability
            b"payload": json.dumps(sample_payload_dict).encode('utf-8')
        }
        
        logger.info(f"Test event payload: {sample_payload_dict}")

        # Ensure Supabase has some test data for "Liverpool" (team), "Chelsea" (team), "Mohamed Salah" (player), "Cole Palmer" (player) for entity linking to work.
        # e.g. Team Liverpool with team_id=40, Team Chelsea with team_id=49
        # Player Mohamed Salah with player_id=123, Player Cole Palmer with player_id=456
        # These IDs are hypothetical and depend on your metadata_fetcher's output.

        success = await test_processor.process_event(sample_event_data_bytes)
        logger.info(f"Direct test of process_event completed. Success: {success}")

    asyncio.run(main_test())
