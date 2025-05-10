from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import httpx
import os
from datetime import datetime, timedelta

router = APIRouter()

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
API_FOOTBALL_URL = "https://api-football-v1.p.rapidapi.com/v3"

# Helper function to make API-Football requests
async def api_football_request(endpoint: str, params: dict = {}):
    headers = {
        "X-RapidAPI-Key": API_FOOTBALL_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_FOOTBALL_URL}/{endpoint}", 
            headers=headers, 
            params=params
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"API-Football request failed: {response.text}"
            )
            
        return response.json()

@router.get("/")
async def get_fixtures(
    date: Optional[str] = None,
    league: Optional[int] = None,
    team: Optional[int] = None,
    days: int = Query(default=3, ge=1, le=7)
):
    """
    Get upcoming fixtures with optional filtering
    """
    # Calculate date range if not provided
    if not date:
        today = datetime.now().strftime("%Y-%m-%d")
        date = today
    
    # Build parameters
    params = {"from": date, "to": (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")}
    
    if league:
        params["league"] = league
    if team:
        params["team"] = team
        
    # Make API request
    try:
        result = await api_football_request("fixtures", params)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{fixture_id}")
async def get_fixture_by_id(fixture_id: int):
    """
    Get detailed information about a specific fixture
    """
    try:
        result = await api_football_request("fixtures", {"id": fixture_id})
        
        if not result["response"]:
            raise HTTPException(status_code=404, detail=f"Fixture with ID {fixture_id} not found")
            
        return result["response"][0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{fixture_id}/statistics")
async def get_fixture_statistics(fixture_id: int):
    """
    Get statistics for a specific fixture
    """
    try:
        result = await api_football_request("fixtures/statistics", {"fixture": fixture_id})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{fixture_id}/events")
async def get_fixture_events(fixture_id: int):
    """
    Get events for a specific fixture (goals, cards, etc.)
    """
    try:
        result = await api_football_request("fixtures/events", {"fixture": fixture_id})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{fixture_id}/odds")
async def get_fixture_odds(fixture_id: int, bookmaker: Optional[int] = None):
    """
    Get betting odds for a specific fixture
    """
    params = {"fixture": fixture_id}
    if bookmaker:
        params["bookmaker"] = bookmaker
        
    try:
        result = await api_football_request("odds", params)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 