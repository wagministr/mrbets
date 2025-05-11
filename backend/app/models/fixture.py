from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Team(BaseModel):
    id: int
    name: str
    logo: Optional[str] = None


class League(BaseModel):
    id: int
    name: str
    country: str
    logo: Optional[str] = None
    flag: Optional[str] = None
    season: int
    round: Optional[str] = None


class Venue(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    city: Optional[str] = None


class Score(BaseModel):
    halftime: Optional[Dict[str, Optional[int]]] = None
    fulltime: Optional[Dict[str, Optional[int]]] = None
    extratime: Optional[Dict[str, Optional[int]]] = None
    penalty: Optional[Dict[str, Optional[int]]] = None


class FixtureDetail(BaseModel):
    id: int
    referee: Optional[str] = None
    timezone: str
    date: datetime
    timestamp: int
    periods: Optional[Dict[str, Optional[int]]] = None
    venue: Optional[Venue] = None
    status: Dict[str, Any]


class Fixture(BaseModel):
    fixture: FixtureDetail
    league: League
    teams: Dict[str, Team]
    goals: Optional[Dict[str, Optional[int]]] = None
    score: Optional[Score] = None


class FixtureDB(BaseModel):
    fixture_id: int = Field(..., description="Unique identifier for the fixture")
    league_id: int = Field(..., description="League identifier")
    home_id: int = Field(..., description="Home team identifier")
    away_id: int = Field(..., description="Away team identifier")
    utc_kickoff: datetime = Field(..., description="UTC kickoff time")
    status: str = Field(..., description="Match status (e.g., NS, FT)")
    score_home: Optional[int] = Field(None, description="Home team score")
    score_away: Optional[int] = Field(None, description="Away team score")
    last_updated: datetime = Field(..., description="Last update timestamp")


class FixtureCreate(BaseModel):
    fixture_id: int
    league_id: int
    home_id: int
    away_id: int
    utc_kickoff: datetime
    status: str = "NS"  # Not Started by default


class FixtureUpdate(BaseModel):
    status: Optional[str] = None
    score_home: Optional[int] = None
    score_away: Optional[int] = None
    last_updated: Optional[datetime] = None
