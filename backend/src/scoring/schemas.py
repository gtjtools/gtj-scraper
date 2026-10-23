# src/scoring/schemas.py
from pydantic import BaseModel, UUID4
from typing import Optional, List, Any
from datetime import datetime

class NTSBQueryRequest(BaseModel):
    """Request schema for NTSB score calculation"""
    operator_id: UUID4

class NTSBIncident(BaseModel):
    """Individual NTSB incident data"""
    event_id: Optional[str] = None
    event_date: Optional[str] = None
    location: Optional[str] = None
    aircraft_damage: Optional[str] = None
    injury_level: Optional[str] = None
    investigation_type: Optional[str] = None
    event_type: Optional[str] = None

class NTSBQueryResponse(BaseModel):
    """Response schema for NTSB query"""
    operator_name: str
    total_incidents: int
    incidents: List[NTSBIncident]
    query_timestamp: datetime
    raw_data: Optional[Any] = None

class ScoreCalculationResponse(BaseModel):
    """Response schema for score calculation"""
    operator_id: Optional[UUID4] = None
    operator_name: str
    ntsb_score: float
    total_incidents: int
    incidents: List[NTSBIncident]
    # datetime, not str: ScoringService.run_score_calculation returns
    # datetime.utcnow(). Declaring this `str` made Pydantic v2 reject every
    # successful response with a validation error — json_encoders below does
    # not help, because validation runs before encoding and a datetime is not
    # a str. FastAPI serialises datetime to an ISO-8601 string on the way out.
    calculated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
