"""
retriever_builder.py

Извлекает релевантный контекст для конкретного матча из Pinecone и Supabase.
Основная задача: найти все "умные чанки" контента, которые релевантны командам матча.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Импорты для интеграций
from supabase import create_client, Client as SupabaseClient
from pinecone import Pinecone
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

logger = logging.getLogger(__name__)

# Константы
DEFAULT_DAYS_BACK = 14
MAX_CHUNKS_PER_SEARCH = 100
TOP_CHUNKS_LIMIT = 20
PINECONE_REQUEST_TIMEOUT = 30
SUPABASE_REQUEST_TIMEOUT = 30

class MatchContextRetriever:
    def __init__(self):
        """
        Инициализация клиентов для Supabase, Pinecone и OpenAI
        """
        # Supabase
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        
        self.supabase = create_client(self.supabase_url, self.supabase_key)
        logger.info("Supabase client initialized for retriever")
        
        # Pinecone
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.pinecone_index_name = os.getenv("PINECONE_INDEX", "mrbets-content-chunks")
        if not self.pinecone_api_key:
            raise ValueError("PINECONE_API_KEY must be set")
            
        self.pc = Pinecone(api_key=self.pinecone_api_key)
        self.pinecone_index = self.pc.Index(self.pinecone_index_name)
        logger.info(f"Pinecone index '{self.pinecone_index_name}' connected for retriever")
        
        # OpenAI (для future embeddings если понадобится)
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if self.openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
            logger.info("OpenAI client initialized for retriever")
        else:
            self.openai_client = None
            logger.warning("OpenAI client not initialized - OPENAI_API_KEY not set")

    async def get_context_for_match(self, fixture_id: int, days_back: int = DEFAULT_DAYS_BACK) -> Dict[str, Any]:
        """
        Главная функция: получить контекст для конкретного матча
        
        Args:
            fixture_id: ID матча из таблицы fixtures
            days_back: Сколько дней назад искать контент (по умолчанию 14)
            
        Returns:
            Dict с информацией о матче и релевантным контентом
        """
        logger.info(f"Getting context for fixture {fixture_id} (looking back {days_back} days)")
        start_time = time.time()
        
        try:
            # 1. Получить информацию о матче
            match_info = await self._get_match_info(fixture_id)
            if not match_info:
                logger.error(f"Match {fixture_id} not found in fixtures table")
                return {"error": f"Match {fixture_id} not found"}
                
            logger.info(f"Match info: {match_info['home_team_id']} vs {match_info['away_team_id']}")
            
            # 2. Получить названия команд для логов
            team_names = await self._get_team_names(
                match_info["home_team_id"], 
                match_info["away_team_id"]
            )
            match_info.update(team_names)
            
            # 3. Поиск релевантного контента в Pinecone
            relevant_chunks = await self._search_relevant_content(
                match_info["home_team_id"], 
                match_info["away_team_id"],
                match_info.get("event_date"),
                days_back
            )
            
            logger.info(f"Found {len(relevant_chunks)} potentially relevant chunks")
            
            # 4. Ранжирование и отбор топ чанков
            top_chunks = self._rank_and_filter_chunks(relevant_chunks, max_chunks=TOP_CHUNKS_LIMIT)
            
            # 5. Дополнительная информация из Supabase (если нужно)
            enhanced_chunks = await self._enhance_chunks_with_supabase_data(top_chunks)
            
            # 6. Формирование структурированного контекста
            context = self._format_context_for_llm(match_info, enhanced_chunks)
            
            duration = time.time() - start_time
            logger.info(f"Context retrieval completed in {duration:.2f}s. Selected {len(enhanced_chunks)} top chunks.")
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting context for fixture {fixture_id}: {e}", exc_info=True)
            return {"error": f"Failed to get context: {str(e)}"}

    async def _get_match_info(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        """Получить базовую информацию о матче из Supabase"""
        try:
            response = self.supabase.table("fixtures").select(
                "fixture_id, home_team_id, away_team_id, event_date, league_id, status_short"
            ).eq("fixture_id", fixture_id).execute()
            
            if response.data and len(response.data) > 0:
                match_data = response.data[0]
                logger.debug(f"Found match: fixture_id={match_data['fixture_id']}, "
                           f"home={match_data['home_team_id']}, away={match_data['away_team_id']}")
                return match_data
            else:
                logger.warning(f"No match found for fixture_id {fixture_id}")
                return None
        except Exception as e:
            logger.error(f"Error getting match info for fixture {fixture_id}: {e}", exc_info=True)
            return None

    async def _get_team_names(self, home_team_id: int, away_team_id: int) -> Dict[str, str]:
        """Получить названия команд"""
        try:
            response = self.supabase.table("teams").select(
                "team_id, name"
            ).in_("team_id", [home_team_id, away_team_id]).execute()
            
            team_names = {"home_team_name": "Unknown", "away_team_name": "Unknown"}
            
            if response.data:
                for team in response.data:
                    if team["team_id"] == home_team_id:
                        team_names["home_team_name"] = team["name"]
                    elif team["team_id"] == away_team_id:
                        team_names["away_team_name"] = team["name"]
                        
            return team_names
        except Exception as e:
            logger.error(f"Error getting team names: {e}")
            return {"home_team_name": "Unknown", "away_team_name": "Unknown"}

    async def _search_relevant_content(
        self, 
        home_team_id: int, 
        away_team_id: int, 
        match_date: Optional[str],
        days_back: int
    ) -> List[Dict[str, Any]]:
        """Поиск релевантного контента в Pinecone"""
        try:
            # Вычисляем временные границы
            if match_date:
                match_datetime = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                cutoff_datetime = match_datetime - timedelta(days=days_back)
            else:
                cutoff_datetime = datetime.now() - timedelta(days=days_back)
                
            # Convert to Unix timestamp for Pinecone (it expects numbers, not ISO strings)
            cutoff_timestamp = int(cutoff_datetime.timestamp())
            
            logger.info(f"Searching content from timestamp {cutoff_timestamp} ({cutoff_datetime.isoformat()}) for teams {home_team_id}, {away_team_id}")
            
            # Фильтр для Pinecone: ищем чанки связанные с любой из команд матча
            team_filter = {
                "$and": [
                    {
                        "$or": [
                            {"linked_team_ids": {"$in": [str(home_team_id)]}},
                            {"linked_team_ids": {"$in": [str(away_team_id)]}}
                        ]
                    },
                    {"document_timestamp": {"$gte": cutoff_timestamp}}
                ]
            }
            
            # Векторный поиск с фильтрацией по метаданным
            # Используем dummy vector для metadata-only поиска
            dummy_vector = [0.0] * 1536  # Размерность для text-embedding-3-small
            
            query_results = self.pinecone_index.query(
                vector=dummy_vector,
                filter=team_filter,
                top_k=MAX_CHUNKS_PER_SEARCH,
                include_metadata=True
            )
            
            logger.info(f"Pinecone returned {len(query_results.matches)} matches")
            
            return query_results.matches
            
        except Exception as e:
            logger.error(f"Error searching Pinecone: {e}", exc_info=True)
            return []

    def _rank_and_filter_chunks(self, chunks: List[Any], max_chunks: int = TOP_CHUNKS_LIMIT) -> List[Any]:
        """
        Ранжирование чанков по важности и фильтрация
        
        Критерии ранжирования:
        1. importance_score (из LLM анализа)
        2. Тип контента (приоритет важным типам новостей)
        3. Свежесть
        """
        if not chunks:
            return []
            
        logger.info(f"Ranking {len(chunks)} chunks, selecting top {max_chunks}")
        
        # Функция для вычисления score
        def calculate_rank_score(chunk) -> float:
            metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}
            
            # Базовый score от важности (LLM)
            importance = int(metadata.get("importance_score", 3))
            base_score = importance * 20  # 20-100 баллов
            
            # Бонус за тип контента
            chunk_type = metadata.get("chunk_type", "").lower()
            type_bonus = 0
            if "injury" in chunk_type:
                type_bonus = 15
            elif "transfer" in chunk_type:
                type_bonus = 10  
            elif "team news" in chunk_type or "strategy" in chunk_type:
                type_bonus = 12
            elif "pre-match" in chunk_type:
                type_bonus = 8
            elif "performance" in chunk_type:
                type_bonus = 5
                
            # Штраф за старые данные (если можем определить дату)
            age_penalty = 0
            doc_timestamp = metadata.get("document_timestamp")
            if doc_timestamp:
                try:
                    doc_date = datetime.fromisoformat(doc_timestamp.replace('Z', '+00:00'))
                    age_days = (datetime.now(doc_date.tzinfo) - doc_date).days
                    age_penalty = min(age_days * 1, 10)  # Максимум 10 баллов штрафа
                except:
                    pass
            
            final_score = base_score + type_bonus - age_penalty
            return final_score
        
        # Сортировка по убыванию score
        ranked_chunks = sorted(chunks, key=calculate_rank_score, reverse=True)
        
        # Логирование топ чанков для отладки
        for i, chunk in enumerate(ranked_chunks[:5]):
            metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}
            logger.debug(f"Top {i+1}: score={calculate_rank_score(chunk):.1f}, "
                        f"type={metadata.get('chunk_type', 'unknown')}, "
                        f"importance={metadata.get('importance_score', 'unknown')}")
        
        return ranked_chunks[:max_chunks]

    async def _enhance_chunks_with_supabase_data(self, chunks: List[Any]) -> List[Dict[str, Any]]:
        """
        Дополнить чанки информацией из Supabase (если нужно)
        Пока что просто преобразуем в удобный формат
        """
        enhanced_chunks = []
        
        for chunk in chunks:
            metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}
            
            enhanced_chunk = {
                "chunk_id": metadata.get("processed_document_id", "unknown"),
                "text": metadata.get("chunk_text", ""),
                "source": metadata.get("source", "unknown"),
                "chunk_type": metadata.get("chunk_type", "unknown"),
                "importance_score": int(metadata.get("importance_score", 3)),
                "tone": metadata.get("tone", "neutral"),
                "document_title": metadata.get("document_title", ""),
                "document_url": metadata.get("document_url", ""),
                "linked_team_ids": self._parse_list_field(metadata.get("linked_team_ids", "[]")),
                "linked_player_ids": self._parse_list_field(metadata.get("linked_player_ids", "[]")),
                "relevance_score": chunk.score if hasattr(chunk, 'score') else 0.0,
                "document_timestamp": metadata.get("document_timestamp", "")
            }
            
            enhanced_chunks.append(enhanced_chunk)
        
        return enhanced_chunks

    def _parse_list_field(self, field_value: str) -> List[str]:
        """Парсинг списков из метаданных Pinecone (они сохраняются как JSON строки)"""
        try:
            if isinstance(field_value, str):
                return json.loads(field_value)
            elif isinstance(field_value, list):
                return field_value
            else:
                return []
        except:
            return []

    def _format_context_for_llm(self, match_info: Dict[str, Any], chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Форматирование контекста в структуру удобную для LLM Reasoner
        """
        # Группировка чанков по типам для лучшей структуры
        chunks_by_type = {}
        for chunk in chunks:
            chunk_type = chunk.get("chunk_type", "other")
            if chunk_type not in chunks_by_type:
                chunks_by_type[chunk_type] = []
            chunks_by_type[chunk_type].append(chunk)
        
        # Статистика по источникам
        sources = list(set([chunk.get("source", "unknown") for chunk in chunks]))
        
        # Итоговый контекст
        context = {
            "match_info": {
                "fixture_id": match_info.get("fixture_id"),
                "home_team_id": match_info.get("home_team_id"),
                "away_team_id": match_info.get("away_team_id"),
                "home_team_name": match_info.get("home_team_name", "Unknown"),
                "away_team_name": match_info.get("away_team_name", "Unknown"),
                "event_date": match_info.get("event_date"),
                "league_id": match_info.get("league_id"),
                "status": match_info.get("status_short", "unknown")
            },
            "content_summary": {
                "total_chunks": len(chunks),
                "sources": sources,
                "content_types": list(chunks_by_type.keys()),
                "avg_importance": round(sum([c.get("importance_score", 3) for c in chunks]) / len(chunks), 1) if chunks else 0,
                "date_range": self._get_content_date_range(chunks)
            },
            "structured_content": chunks_by_type,
            "all_content": chunks  # Полный список для backward compatibility
        }
        
        logger.info(f"Formatted context: {len(chunks)} chunks from {len(sources)} sources, "
                   f"types: {list(chunks_by_type.keys())}")
        
        return context

    def _get_content_date_range(self, chunks: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        """Определить временной диапазон контента"""
        dates = []
        for chunk in chunks:
            timestamp = chunk.get("document_timestamp")
            if timestamp:
                try:
                    date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    dates.append(date)
                except:
                    pass
        
        if dates:
            return {
                "earliest": min(dates).isoformat(),
                "latest": max(dates).isoformat()
            }
        else:
            return {"earliest": None, "latest": None}

    async def test_connections(self):
        """Тестирование подключений к внешним сервисам"""
        logger.info("Testing retriever connections...")
        
        # Тест Supabase
        try:
            response = self.supabase.table("fixtures").select("count", count="exact").limit(1).execute()
            logger.info("✅ Supabase connection: OK")
        except Exception as e:
            logger.error(f"❌ Supabase connection failed: {e}")
            
        # Тест Pinecone
        try:
            stats = self.pinecone_index.describe_index_stats()
            logger.info(f"✅ Pinecone connection: OK (vectors: {stats.total_vector_count})")
        except Exception as e:
            logger.error(f"❌ Pinecone connection failed: {e}")


# Вспомогательная функция для быстрого тестирования
async def test_retriever_with_fixture(fixture_id: int):
    """Быстрый тест retriever с конкретным матчем"""
    try:
        retriever = MatchContextRetriever()
        await retriever.test_connections()
        
        context = await retriever.get_context_for_match(fixture_id)
        
        if context.get("error"):
            print(f"❌ Error: {context['error']}")
            return False
        
        print(f"✅ Successfully retrieved context for fixture {fixture_id}")
        print(f"📊 Found {context['content_summary']['total_chunks']} chunks")
        print(f"📰 Sources: {context['content_summary']['sources']}")
        print(f"📝 Content types: {context['content_summary']['content_types']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_fixture_id = int(sys.argv[1])
        print(f"🧪 Testing retriever with fixture {test_fixture_id}")
        asyncio.run(test_retriever_with_fixture(test_fixture_id))
    else:
        print("Usage: python retriever_builder.py <fixture_id>")
        print("Example: python retriever_builder.py 123456") 