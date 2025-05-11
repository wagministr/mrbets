"""
Data models for football fixtures (matches).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Fixture(BaseModel):
    """Model representing a football match."""

    fixture_id: int = Field(..., description="Unique identifier for the fixture")
    league_id: int = Field(..., description="ID of the league/competition")
    home_id: int = Field(..., description="ID of the home team")
    away_id: int = Field(..., description="ID of the away team")
    utc_kickoff: datetime = Field(..., description="UTC timestamp of match kickoff")
    status: str = Field(..., description="Match status (Not Started, In Play, Finished)")
    score_home: Optional[int] = Field(None, description="Number of goals scored by home team")
    score_away: Optional[int] = Field(None, description="Number of goals scored by away team")


class FixtureList(BaseModel):
    """List of fixtures with metadata."""

    fixtures: List[Fixture]
    count: int = Field(..., description="Total number of fixtures in the response")
    has_more: bool = Field(False, description="Whether there are more fixtures available")


class FixtureStatistic(BaseModel):
    """Statistical data for a team in a fixture."""

    team_id: int
    shots_total: Optional[int] = None
    shots_on_target: Optional[int] = None
    possession: Optional[float] = None
    passes: Optional[int] = None
    pass_accuracy: Optional[float] = None
    fouls: Optional[int] = None
    corners: Optional[int] = None
    offsides: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
