from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class ValueBet(BaseModel):
    market: str = Field(..., description="Betting market (e.g., 'Match Winner', 'Over/Under')")
    prediction: str = Field(..., description="Specific prediction (e.g., 'Home', 'Over 2.5')")
    odds: float = Field(..., description="Current odds for this prediction")
    confidence: float = Field(..., ge=0, le=100, description="AI confidence percentage (0-100)")
    
class Prediction(BaseModel):
    id: UUID4 = Field(default_factory=uuid.uuid4, description="Unique identifier")
    fixture_id: int = Field(..., description="Fixture ID this prediction relates to")
    type: str = Field("pre-match", description="Prediction type (pre-match, in-play, etc.)")
    chain_of_thought: str = Field(..., description="Detailed AI analysis and reasoning")
    final_prediction: str = Field(..., description="Concise prediction summary")
    value_bets: List[ValueBet] = Field([], description="List of value betting opportunities")
    model_version: str = Field(..., description="AI model version used for this prediction")
    generated_at: datetime = Field(default_factory=datetime.now, description="Timestamp of generation")
    stale: bool = Field(False, description="Whether this prediction is considered stale")
    
class PredictionDB(BaseModel):
    id: UUID4
    fixture_id: int
    type: str
    chain_of_thought: str
    final_prediction: str
    value_bets_json: str
    model_version: str
    generated_at: datetime
    stale: bool
    
class PredictionCreate(BaseModel):
    fixture_id: int
    type: str = "pre-match"
    chain_of_thought: str
    final_prediction: str
    value_bets: List[ValueBet]
    model_version: str
    stale: bool = False
    
class PredictionUpdate(BaseModel):
    chain_of_thought: Optional[str] = None
    final_prediction: Optional[str] = None
    value_bets: Optional[List[ValueBet]] = None
    stale: Optional[bool] = None 