"""
Data models for AI predictions on football fixtures.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ValueBet(BaseModel):
    """Represents a value betting opportunity identified by the AI."""

    market: str = Field(..., description="Betting market (e.g., 'Match Winner', 'Over/Under')")
    selection: str = Field(..., description="Selected outcome")
    odds: float = Field(..., description="Decimal odds for the selection")
    confidence: int = Field(..., ge=0, le=100, description="AI confidence level (0-100%)")


class Prediction(BaseModel):
    """Full AI prediction for a football fixture."""

    fixture_id: int = Field(..., description="ID of the fixture this prediction is for")
    type: str = Field(..., description="Type of prediction (pre-match, in-play)")
    chain_of_thought: str = Field(..., description="Detailed analysis and reasoning")
    final_prediction: str = Field(..., description="Summary of the prediction")
    value_bets: List[ValueBet] = Field(
        [], description="List of identified value betting opportunities"
    )
    model_version: str = Field(..., description="Version of the AI model used")
    generated_at: datetime = Field(..., description="When this prediction was generated")
    stale: bool = Field(False, description="Whether this prediction is considered outdated")


class PredictionStatus(BaseModel):
    """Status of a prediction request."""

    fixture_id: int
    status: str = Field(..., description="Status of prediction (pending, ready, error)")
    message: Optional[str] = None
    prediction: Optional[Prediction] = None
