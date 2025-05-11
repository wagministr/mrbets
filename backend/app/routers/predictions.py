"""
Predictions router.
"""

from datetime import datetime

from fastapi import APIRouter

from app.models.common import ErrorResponse
from app.models.predictions import Prediction, PredictionStatus, ValueBet

router = APIRouter()


@router.get(
    "/{fixture_id}",
    response_model=PredictionStatus,
    responses={
        200: {"description": "Prediction retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Prediction not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_prediction(fixture_id: int):
    """
    Get prediction for a fixture.

    - **fixture_id**: Unique identifier for the fixture
    """
    # Placeholder response - will be connected to database later
    prediction = Prediction(
        fixture_id=fixture_id,
        type="pre-match",
        chain_of_thought="This is a detailed analysis of the upcoming match. The home team has shown strong performance in their recent matches, winning 4 out of their last 5 games. Their offensive line has been particularly effective, scoring an average of 2.5 goals per match. The away team, on the other hand, has struggled defensively, conceding in every away game this season.",  # noqa: E501
        final_prediction="Based on current form and historical head-to-head results, the home team is likely to win this match, potentially with a clean sheet.",  # noqa: E501
        value_bets=[
            ValueBet(market="Match Winner", selection="Home Team", odds=1.95, confidence=75),
            ValueBet(market="Total Goals", selection="Over 2.5", odds=1.80, confidence=65),
        ],
        model_version="GPT-4o",
        generated_at=datetime.utcnow(),
        stale=False,
    )

    return PredictionStatus(fixture_id=fixture_id, status="ready", prediction=prediction)
