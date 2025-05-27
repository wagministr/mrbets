import asyncio
import httpx
import feedparser # feedparser library for parsing RSS feeds
import json
import os
import logging
import time # Added for time.mktime
from datetime import datetime, timezone
from bs4 import BeautifulSoup # For parsing HTML
import spacy # Import spaCy

# Attempt to load .env file for direct script execution
try:
    from dotenv import load_dotenv
    load_dotenv()
    # You can add a log here to confirm if .env was loaded, e.g.:
    # logging.info(".env file loaded successfully by dotenv.") 
except ImportError:
    # dotenv not installed, environment variables should be set externally
    # logging.warning("python-dotenv not found. Skipping .env file loading.")
    pass

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- spaCy Model Loading ---
NLP = None
try:
    NLP = spacy.load("en_core_web_sm")
    logger.info("Successfully loaded spaCy model 'en_core_web_sm'.")
except OSError:
    logger.error("spaCy model 'en_core_web_sm' not found. Please download it by running: python -m spacy download en_core_web_sm")
    # Depending on the desired behavior, you might want to exit or disable NER functionality
    # For now, NER will be skipped if the model is not available.
except Exception as e:
    logger.error(f"An unexpected error occurred while loading spaCy model: {e}")


# --- Constants ---
MAX_ARTICLES_PER_FEED = 3 # Limit the number of articles processed per feed for testing

# --- Environment Variables & Configuration ---
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_STREAM_NAME = "stream:raw_events"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") # Use service key for backend operations
SUPABASE_BUCKET_NAME = os.getenv("SUPABASE_BUCKET_NAME", "mrbets-raw") # Or a more specific one like 'bbc-articles'
DEEPL_API_KEY = os.getenv("DEEPL_KEY")

BBC_RSS_FEEDS = {
    "football_main": "http://feeds.bbci.co.uk/sport/football/rss.xml", # Specific football RSS
    "football_premier_league": "http://feeds.bbci.co.uk/sport/football/premier-league/rss.xml", # Example, may need verification
    # Add more specific league feeds if found and reliable
}

# --- Redis Client ---
try:
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Successfully connected to Redis.")
except ImportError:
    logger.warning("redis library not found, Redis functionality will be disabled.")
    redis_client = None
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

# --- Supabase Client ---
try:
    from supabase import create_client, Client
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Successfully initialized Supabase client.")
    else:
        logger.warning("Supabase URL or Key not provided. Supabase functionality will be disabled.")
        supabase = None
except ImportError:
    logger.warning("supabase library not found, Supabase functionality will be disabled.")
    supabase = None
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    supabase = None

# --- Deduplication Helpers ---
PROCESSED_URL_KEY_PREFIX = "processed_url:"
DEFAULT_URL_TTL = 7 * 24 * 60 * 60  # 7 days in seconds

async def is_url_processed(url: str) -> bool:
    """Checks if a URL has already been processed based on Redis cache."""
    if not redis_client:
        logger.warning("Redis client not available, cannot check if URL is processed.")
        return False
    try:
        key = f"{PROCESSED_URL_KEY_PREFIX}{url}"
        exists = await redis_client.exists(key)
        if exists:
            logger.info(f"URL already processed (found in Redis): {url}")
            return True
        return False
    except Exception as e:
        logger.error(f"Redis error checking if URL {url} is processed: {e}")
        return False # Treat as not processed in case of error to avoid missing data

async def mark_url_as_processed(url: str, ttl: int = DEFAULT_URL_TTL):
    """Marks a URL as processed in Redis with a TTL."""
    if not redis_client:
        logger.warning("Redis client not available, cannot mark URL as processed.")
        return
    try:
        key = f"{PROCESSED_URL_KEY_PREFIX}{url}"
        await redis_client.setex(key, ttl, "1")
        logger.info(f"Marked URL as processed in Redis: {url} with TTL {ttl}s")
    except Exception as e:
        logger.error(f"Redis error marking URL {url} as processed: {e}")

async def fetch_article_html(url: str) -> str | None:
    """Fetches the HTML content of a given URL."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.text
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching article {url}: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error fetching article {url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching article {url}: {e}")
    return None

def parse_article_text(html_content: str, source_url: str) -> dict | None:
    """
    Parses the main article title, text, and images from BBC Sport HTML content
    based on semantic structure.
    """
    if not html_content:
        return None
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        article_element = soup.find('article')
        if not article_element:
            logger.warning(f"No <article> tag found in {source_url}. Cannot parse content.")
            return None

        title = "N/A"
        title_element = article_element.find('h1')
        if title_element:
            title = title_element.get_text(strip=True)
        else:
            logger.warning(f"No <h1> tag found within <article> in {source_url}.")

        paragraphs_text = []
        for p_tag in article_element.find_all('p'):
            paragraphs_text.append(p_tag.get_text(separator=" ", strip=True))
        
        full_text = "\n".join(paragraphs_text)

        images = []
        for fig_tag in article_element.find_all('figure'):
            img_tag = fig_tag.find('img')
            if img_tag and img_tag.get('src'):
                image_data = {"src": img_tag['src']}
                if img_tag.get('alt'):
                    image_data["alt"] = img_tag['alt']
                
                caption_tag = fig_tag.find('figcaption')
                if caption_tag:
                    image_data["caption"] = caption_tag.get_text(strip=True)
                images.append(image_data)

        if not full_text and not title == "N/A":
             logger.warning(f"Could not extract main article text from {source_url}, though a title was found. HTML structure might be unusual.")
        elif not full_text and title == "N/A":
            logger.warning(f"Could not extract any meaningful content (title or text) from {source_url}.")
            return None # Or return with empty fields if partial data is acceptable

        logger.info(f"Successfully parsed article content from {source_url}")
        return {
            "title": title,
            "full_text": full_text.strip(),
            "images": images
        }
            
    except Exception as e:
        logger.error(f"Error parsing HTML content from {source_url}: {e}")
        return None


def extract_entities_with_spacy(text: str) -> list:
    """Extracts named entities from text using spaCy."""
    if not NLP or not text:
        return []
    try:
        doc = NLP(text)
        entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
        logger.info(f"Extracted {len(entities)} entities using spaCy.")
        return entities
    except Exception as e:
        logger.error(f"Error extracting entities with spaCy: {e}")
        return []


async def fetch_and_parse_rss_feed(feed_url: str, feed_name: str):
    """Fetches and parses an RSS feed, then processes its entries up to a limit."""
    logger.info(f"Fetching RSS feed: {feed_name} from {feed_url}")
    try:
        # Using httpx to fetch the feed content first for async compatibility
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
            feed_content = response.text

        # feedparser is synchronous, so run it in a separate thread
        parsed_feed = await asyncio.to_thread(feedparser.parse, feed_content)

        if parsed_feed.bozo:
            logger.warning(f"Feed {feed_name} from {feed_url} might be ill-formed. Bozo bit set with exception: {parsed_feed.bozo_exception}")

        logger.info(f"Found {len(parsed_feed.entries)} entries in {feed_name} feed. Will process up to {MAX_ARTICLES_PER_FEED} entries.")
        
        processed_count = 0
        for entry in parsed_feed.entries:
            if processed_count >= MAX_ARTICLES_PER_FEED:
                logger.info(f"Reached processing limit of {MAX_ARTICLES_PER_FEED} articles for feed {feed_name}.")
                break

            title = entry.get("title", "N/A")
            link = entry.get("link", "N/A")
            summary = entry.get("summary") # Might contain HTML
            
            # Deduplication check
            if await is_url_processed(link):
                continue

            published_parsed = entry.get("published_parsed")
            article_timestamp_iso = None
            if published_parsed:
                # Convert struct_time to datetime object, then to ISO 8601 string
                # mktime expects local time, but feedparser usually gives UTC in published_parsed
                # We'll assume it's UTC and convert directly if possible, or via timestamp if it's naive
                try:
                    dt_object = datetime(*published_parsed[:6], tzinfo=timezone.utc) # Directly create timezone-aware datetime
                except TypeError:
                    # Fallback if published_parsed is not a full struct_time or mktime is preferred
                    dt_object = datetime.fromtimestamp(time.mktime(published_parsed), tz=timezone.utc)
                article_timestamp_iso = dt_object.isoformat()

            logger.info(f"Processing entry: '{title}' from {link}")

            # 1. Fetch full article HTML
            html_content = await fetch_article_html(link)
            if not html_content:
                logger.warning(f"Skipping entry '{title}' due to failed HTML fetch from {link}")
                continue

            # 2. Parse article text
            parsed_content = parse_article_text(html_content, link) # Now returns a dict or None
            if not parsed_content or not parsed_content.get("full_text"): # Ensure full_text is present
                logger.warning(f"Skipping entry '{title}' (original from RSS) due to failed or incomplete article content parsing from {link}")
                continue
            
            # Use parsed title if available, otherwise fallback to RSS title
            article_title = parsed_content.get("title", title) 
            full_text = parsed_content["full_text"]
            article_images = parsed_content.get("images", [])

            # 2.5 Extract Entities using spaCy
            entities = []
            if NLP and full_text: # Check if NLP model is loaded and text is available
                # Run spaCy processing in a separate thread to avoid blocking asyncio loop
                entities = await asyncio.to_thread(extract_entities_with_spacy, full_text)
            elif not NLP:
                logger.warning(f"spaCy NLP model not available. Skipping entity extraction for '{article_title}'.")
            
            # 3. TODO: Implement match_id linking
            # This is a complex step and will require a list of upcoming fixtures
            # For now, we can use a placeholder or skip if no match_id can be determined.
            match_id = None # Placeholder
            
            # Example of how you might get fixture data (needs actual implementation)
            # upcoming_fixtures = await get_upcoming_fixtures_from_db_or_cache() 
            # identified_match_id = link_article_to_fixture(title + " " + full_text, upcoming_fixtures)

            if match_id is None: # For now, we'll process all articles without strict match_id linking for demonstration
                logger.info(f"No match_id identified for '{title}'. Processing as general news or skipping based on policy.")
                # For now, let's assign a generic ID or skip. For actual use, this needs a robust solution.
                # If you want to save all news regardless of match_id, you might use a different logic for 'identifier'
                # For this example, we'll skip if no match_id.
                # continue 
                pass # Allowing to proceed without match_id for now for testing purposes


            # 4. Form JSON payload
            payload = {
                "title": article_title, # Use parsed title
                "summary": BeautifulSoup(summary, "html.parser").get_text(separator=" ", strip=True) if summary else None, # Clean summary
                "url": link,
                "full_text": full_text,
                "article_timestamp_iso": article_timestamp_iso,
                "feed_source_name": feed_name,
                "images": article_images, # Add parsed images
                "entities_spacy": entities # Add extracted entities
            }
            
            event_data = {
                "match_id": match_id, # Can be None if not linked
                "source": "bbc_sport",
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # 5. Put into Redis Stream (этот блок был выше, теперь логика объединена)
            event_successfully_stored_to_redis = False # Флаг для отслеживания успеха
            if redis_client:
                try:
                    # event_data уже сформирован ранее и содержит все необходимое, включая payload
                    # message_id = entry.get("id", link) # entry.id может быть полезнее для уникальности чем link, если доступен
                    await redis_client.xadd(REDIS_STREAM_NAME, {"data": json.dumps(event_data)}, id="*")
                    logger.info(f"Successfully added event for '{article_title}' to Redis stream '{REDIS_STREAM_NAME}'.")
                    event_successfully_stored_to_redis = True
                except Exception as e:
                    logger.error(f"Failed to add event for '{article_title}' to Redis: {e}")
            else:
                logger.warning("Redis client not available, cannot send event to Redis.")


            # 6. Save to Supabase Storage (этот блок остается как есть, но убедимся, что он после Redis)
            if supabase and (match_id or True): # Saving even if no match_id for now
                # Create a unique name, e.g., based on article ID or hash
                # Sanitize link to be a valid path component
                sanitized_link_for_path = link.split("/")[-1] if link.split("/")[-1] else link.split("/")[-2]
                sanitized_link_for_path = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in sanitized_link_for_path)
                
                storage_folder = f"match_{match_id}" if match_id else "general_bbc_news"
                file_name = f"bbc_{sanitized_link_for_path}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.txt"
                full_storage_path = f"raw/{storage_folder}/{file_name}"
                
                try:
                    text_content_bytes = full_text.encode('utf-8')
                    await asyncio.to_thread(
                        supabase.storage.from_(SUPABASE_BUCKET_NAME).upload,
                        path=full_storage_path,
                        file=text_content_bytes,
                        file_options={"content-type": "text/plain;charset=utf-8", "upsert": "true"}
                    )
                    logger.info(f"Successfully saved article '{article_title}' to Supabase Storage: {full_storage_path}")
                except Exception as e:
                    logger.error(f"Failed to save article '{article_title}' to Supabase Storage: {e}. Path: {full_storage_path}")
                    if hasattr(e, 'message'): logger.error(f"Supabase error details: {e.message}")
            
            # Mark URL as processed and increment count only if successfully stored to Redis
            if event_successfully_stored_to_redis:
                await mark_url_as_processed(link) 
                processed_count += 1 
            else:
                logger.error(f"Failed to store event for article {link} from feed {feed_name} to Redis. URL will not be marked as processed.")

            await asyncio.sleep(1) # Small delay to be polite to the server

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching RSS feed {feed_url}: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error fetching RSS feed {feed_url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error processing RSS feed {feed_url}: {e}")


# --- Placeholder for match linking logic ---
# This would involve fetching fixture data (e.g., from Supabase or a shared cache)
# and then using NLP or keyword matching to link articles to fixtures.

# async def get_upcoming_fixtures():
#     """Placeholder: Fetches upcoming fixtures (team names, dates, fixture_id)."""
#     # Example: 
#     # if supabase:
#     #     response = await supabase.table("fixtures").select("fixture_id, home_team_name, away_team_name, kickoff_date") \
#     # красивые команды                            .filter("kickoff_date", "gte", datetime.now(timezone.utc).isoformat()) \
#     # красивые команды                            .limit(100).execute() # Fetch fixtures for the near future
#     #     return response.data
#     return [
#         {"fixture_id": 123, "teams": ["Team A", "Team B"], "date": "2025-05-25"},
#         {"fixture_id": 456, "teams": ["Liverpool", "Chelsea"], "date": "2025-05-26"},
#     ]

# def link_article_to_fixture(article_text: str, fixtures: list) -> int | None:
#     """
#     Placeholder: Links an article to a fixture_id based on content.
#     A more robust implementation would use NLP, NER, and fuzzy matching.
#     """
#     article_text_lower = article_text.lower()
#     for fixture in fixtures:
#         # Simple check: if both team names are in the article text
#         team1_name = fixture["teams"][0].lower()
#         team2_name = fixture["teams"][1].lower()
#         if team1_name in article_text_lower and team2_name in article_text_lower:
#             # Further checks could involve date proximity if article_timestamp is available
#             logger.info(f"Article tentatively linked to fixture {fixture['fixture_id']} ({fixture['teams'][0]} vs {fixture['teams'][1]})")
#             return fixture["fixture_id"]
#     return None

async def main_scraper_task():
    """Main task to fetch news from all configured BBC RSS feeds."""
    tasks = []
    for feed_name, feed_url in BBC_RSS_FEEDS.items():
        tasks.append(fetch_and_parse_rss_feed(feed_url, feed_name))
    
    if not tasks:
        logger.info("No RSS feeds configured. Exiting.")
        return

    await asyncio.gather(*tasks)
    logger.info("Finished processing all BBC RSS feeds.")

if __name__ == "__main__":
    # This allows running the scraper directly for testing
    # Environment variables should now be loaded by load_dotenv() if .env file exists and dotenv is installed.

    # The check below will now reflect variables loaded from .env or the environment
    # Re-evaluate them here to ensure the check is accurate after dotenv load, 
    # or rely on the fact that global os.getenv calls picked them up.
    # For clarity, let's re-check os.environ directly or rely on original global definitions.
    
    # Check if critical variables are set (SUPABASE_URL and SUPABASE_KEY are for supabase client init)
    # REDIS_URL is also critical for redis_client.
    # The global variables REDIS_URL, SUPABASE_URL, SUPABASE_KEY were defined using os.getenv()
    # which should have picked up values from .env if load_dotenv() worked.

    # Log current state of these specific env vars for debugging
    logger.info(f"DEBUG: SUPABASE_URL is {os.getenv('SUPABASE_URL')}")
    logger.info(f"DEBUG: SUPABASE_KEY is {os.getenv('SUPABASE_SERVICE_KEY')}")
    logger.info(f"DEBUG: REDIS_URL is {os.getenv('REDIS_URL')}")

    if not all([os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"), os.getenv("REDIS_URL")]) :
         logger.warning("One or more critical environment variables (SUPABASE_URL, SUPABASE_SERVICE_KEY, REDIS_URL) are not set. Some functionalities might be disabled or fail.")

    asyncio.run(main_scraper_task()) 