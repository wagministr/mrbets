"""
Pre-Processor

Handles preprocessing of raw event data:
1. Translation (if needed)
2. Text chunking
3. Source reliability scoring
4. Embedding generation
5. Storage in Pinecone and Supabase
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List

import httpx
import langdetect
import redis
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

# Set up logging
logger = logging.getLogger("pre_processor")

# Load environment variables
load_dotenv()

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RAW_EVENTS_STREAM = "stream:raw_events"

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-large"

# DeepL configuration
DEEPL_KEY = os.getenv("DEEPL_KEY")
DEEPL_URL = "https://api-free.deepl.com/v2/translate"

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_STORAGE_URL = os.getenv("SUPABASE_STORAGE_URL")
S3_BUCKET = os.getenv("S3_BUCKET", "mrbets-raw")

# Pinecone will be implemented later

# Source reliability ratings (0.0 to 1.0)
SOURCE_RELIABILITY = {
    "api_football": 1.0,  # Official data
    "bbc": 0.9,  # Reliable news source
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
        self.redis_client = redis.from_url(REDIS_URL)
        self.openai_client = OpenAI()
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # For text chunking
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    async def detect_language(self, text: str) -> str:
        """Detect the language of a text"""
        try:
            return langdetect.detect(text)
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return "en"  # Default to English if detection fails

    async def translate_text(self, text: str, target_lang: str = "EN") -> str:
        """Translate text to the target language using DeepL"""
        if not DEEPL_KEY:
            logger.warning("DeepL API key not set, skipping translation")
            return text

        # Skip if already in target language
        source_lang = await self.detect_language(text)
        if source_lang.lower() == target_lang.lower():
            return text

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPL_URL,
                    headers={"Authorization": f"DeepL-Auth-Key {DEEPL_KEY}"},
                    data={"text": text, "target_lang": target_lang},
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["translations"][0]["text"]
                else:
                    logger.error(f"Translation failed: {response.text}")
                    return text
        except Exception as e:
            logger.error(f"Error translating text: {e}")
            return text

    def chunk_text(self, text: str, max_tokens: int = 1000) -> List[str]:
        """Split text into chunks of max_tokens"""
        tokens = self.tokenizer.encode(text)
        chunks = []

        for i in range(0, len(tokens), max_tokens):
            chunk_tokens = tokens[i : i + max_tokens]
            chunk = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk)

        return chunks

    def get_reliability_score(self, source: str) -> float:
        """Get reliability score for a source"""
        return SOURCE_RELIABILITY.get(source.lower(), 0.5)  # Default to 0.5 if unknown

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI API"""
        try:
            response = self.openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []

    async def store_to_supabase(
        self,
        match_id: int,
        source: str,
        content: str,
        vector: List[float],
        reliability: float,
    ) -> str:
        """Store content and metadata in Supabase"""
        try:
            # Generate unique ID for the content
            content_id = str(uuid.uuid4())
            content_path = f"{match_id}/{content_id}.txt"

            # Upload raw content to Storage
            self.supabase.storage.from_(S3_BUCKET).upload(
                content_path, content.encode("utf-8"), {"content-type": "text/plain"}
            )

            # Create metadata record
            content_hash = str(hash(content))
            record = {
                "match_id": match_id,
                "source": source,
                "content_hash": content_hash,
                "content_path": content_path,
                "metadata": json.dumps({"length": len(content)}),
                "reliability_score": reliability,
                "created_at": datetime.now().isoformat(),
            }

            # Insert into raw_events table
            self.supabase.table("raw_events").insert(record).execute()

            # Store vector in emb_cache table (simplified, Pinecone would be used in production)
            vector_record = {
                "hash": content_hash,
                "vector": json.dumps(vector),  # In production, use proper vector type
                "created_at": datetime.now().isoformat(),
            }

            self.supabase.table("emb_cache").insert(vector_record).execute()

            return content_id
        except Exception as e:
            logger.error(f"Error storing to Supabase: {e}")
            return ""

    async def process_event(self, event_data: Dict[str, bytes]) -> bool:
        """Process a raw event"""
        try:
            # Parse event data
            match_id = int(event_data.get(b"match_id", b"0").decode("utf-8"))
            source = event_data.get(b"source", b"unknown").decode("utf-8")
            payload = event_data.get(b"payload", b"{}").decode("utf-8")

            logger.info(f"Processing event: match_id={match_id}, source={source}")

            # Extract text content from payload
            # In a real implementation, this would handle different payload types
            content = payload
            if source == "api_football":
                # For API data, we'd extract relevant parts for text analysis
                # This is simplified for demonstration
                try:
                    data = json.loads(payload)
                    # Create a summary text from the API data
                    summary_parts = []
                    if "fixtures" in data and data["fixtures"]:
                        fixture = data["fixtures"][0]
                        summary_parts.append(
                            f"Match: {fixture.get('teams', {}).get('home', {}).get('name')} vs {fixture.get('teams', {}).get('away', {}).get('name')}"  # noqa: E501
                        )
                    content = " ".join(summary_parts) or "API Football data"
                except Exception as e:
                    logger.warning(f"Failed to parse API football data: {e}")
                    content = "API Football data (json parsing failed)"

            # Translate if not in English
            content = await self.translate_text(content)

            # Split into chunks
            chunks = self.chunk_text(content)

            # Calculate reliability score
            reliability = self.get_reliability_score(source)

            # Process each chunk
            for chunk in chunks:
                # Generate embedding
                embedding = await self.generate_embedding(chunk)

                if not embedding:
                    logger.warning("Failed to generate embedding for chunk")
                    continue

                # Store in Supabase and Pinecone
                content_id = await self.store_to_supabase(
                    match_id=match_id,
                    source=source,
                    content=chunk,
                    vector=embedding,
                    reliability=reliability,
                )

                logger.info(f"Processed chunk for match {match_id}, content_id: {content_id}")

            return True
        except Exception as e:
            logger.error(f"Error processing event: {e}")
            return False


# Singleton instance
pre_processor = PreProcessor()


async def process(event_id: str, event_data: Dict[str, bytes]) -> bool:
    """Process a raw event"""
    return await pre_processor.process_event(event_data)
