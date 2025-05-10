from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Optional, List, Dict, Any
import os
import json
from datetime import datetime
import httpx

# Import Supabase client
from supabase import create_client, Client

router = APIRouter()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

def get_supabase() -> Client:
    return create_client(supabase_url, supabase_key)

@router.get("/{fixture_id}")
async def get_prediction(fixture_id: int, supabase: Client = Depends(get_supabase)):
    """
    Get AI prediction for a specific fixture
    """
    try:
        # Query the prediction from Supabase
        response = supabase.table("ai_predictions") \
            .select("*") \
            .eq("fixture_id", fixture_id) \
            .eq("type", "pre-match") \
            .order("generated_at", desc=True) \
            .limit(1) \
            .execute()
        
        # Check if prediction exists
        if not response.data:
            return {
                "fixture_id": fixture_id,
                "status": "pending",
                "message": "AI prediction is being prepared..."
            }
        
        prediction = response.data[0]
        
        # Parse value bets JSON if it exists
        if prediction.get("value_bets_json"):
            try:
                prediction["value_bets"] = json.loads(prediction["value_bets_json"])
            except json.JSONDecodeError:
                prediction["value_bets"] = []
                
        # Remove the JSON string to avoid duplication
        if "value_bets_json" in prediction:
            del prediction["value_bets_json"]
            
        return {
            "fixture_id": fixture_id,
            "status": "ready",
            "prediction": prediction
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{fixture_id}/generate")
async def generate_prediction(
    fixture_id: int, 
    background_tasks: BackgroundTasks,
    force: bool = False,
    supabase: Client = Depends(get_supabase)
):
    """
    Trigger generation of a new prediction for a fixture
    """
    # Check if prediction already exists and is not stale
    if not force:
        response = supabase.table("ai_predictions") \
            .select("id, generated_at, stale") \
            .eq("fixture_id", fixture_id) \
            .eq("type", "pre-match") \
            .order("generated_at", desc=True) \
            .limit(1) \
            .execute()
            
        # If prediction exists and is fresh (less than 3 hours old and not marked stale)
        if response.data:
            prediction = response.data[0]
            generated_at = datetime.fromisoformat(prediction["generated_at"].replace("Z", "+00:00"))
            hours_old = (datetime.now() - generated_at).total_seconds() / 3600
            
            if hours_old < 3 and not prediction["stale"]:
                return {
                    "message": "Recent prediction already exists",
                    "prediction_id": prediction["id"]
                }
    
    # Add fixture to the Redis queue for processing
    # This is a placeholder - in a real implementation we would add to Redis
    # For now, we'll just return a success message
    
    # In a real implementation:
    # redis_client.lpush("queue:fixtures", fixture_id)
    
    return {
        "message": "Prediction generation queued",
        "fixture_id": fixture_id
    }

@router.get("/latest")
async def get_latest_predictions(
    limit: int = 10,
    supabase: Client = Depends(get_supabase)
):
    """
    Get the latest predictions
    """
    try:
        # Get current timestamp in ISO format
        now = datetime.now().isoformat()
        
        # Query fixtures that have predictions and are in the future
        response = supabase.table("fixtures") \
            .select("fixture_id, league_id, home_id, away_id, utc_kickoff") \
            .gt("utc_kickoff", now) \
            .order("utc_kickoff") \
            .limit(limit) \
            .execute()
            
        fixtures = response.data
        
        # For each fixture, check if it has a prediction
        result = []
        for fixture in fixtures:
            fixture_id = fixture["fixture_id"]
            
            # Query prediction for this fixture
            pred_response = supabase.table("ai_predictions") \
                .select("id, generated_at") \
                .eq("fixture_id", fixture_id) \
                .eq("type", "pre-match") \
                .order("generated_at", desc=True) \
                .limit(1) \
                .execute()
                
            has_prediction = len(pred_response.data) > 0
            
            result.append({
                **fixture,
                "has_prediction": has_prediction,
                "prediction_id": pred_response.data[0]["id"] if has_prediction else None
            })
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 