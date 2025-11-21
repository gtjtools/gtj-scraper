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
    calculated_at: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
