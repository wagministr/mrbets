"""
Fixtures router.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter

from app.models.common import ErrorResponse
from app.models.fixtures import Fixture, FixtureList

router = APIRouter()


@router.get(
    "/",
    response_model=FixtureList,
    responses={
        200: {"description": "List of fixtures matching the criteria"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_fixtures(
    league_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """
    Get fixtures list with optional filtering.

    - **league_id**: Filter by league/competition ID
    - **from_date**: Start date in ISO format (YYYY-MM-DD)
    - **to_date**: End date in ISO format (YYYY-MM-DD)
    """
    # Placeholder response for now - will be connected to actual data later
    fixture = Fixture(
        fixture_id=1234,
        league_id=39,
        home_id=40,
        away_id=41,
        utc_kickoff=datetime.fromisoformat("2025-05-20T15:00:00+00:00"),
        status="Not Started",
        score_home=None,
        score_away=None,
    )

    return FixtureList(fixtures=[fixture], count=1, has_more=False)


@router.get(
    "/{fixture_id}",
    response_model=Fixture,
    responses={
        200: {"description": "Fixture details"},
        404: {"model": ErrorResponse, "description": "Fixture not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_fixture_by_id(fixture_id: int):
    """
    Get fixture by ID.

    - **fixture_id**: Unique identifier for the fixture
    """
    # Placeholder response for now - will be connected to actual data later
    return Fixture(
        fixture_id=fixture_id,
        league_id=39,
        home_id=40,
        away_id=41,
        utc_kickoff=datetime.fromisoformat("2025-05-20T15:00:00+00:00"),
        status="Not Started",
        score_home=None,
        score_away=None,
    )
