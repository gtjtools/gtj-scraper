# src/aircraft/schemas.py
from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime

class AircraftBase(BaseModel):
  tail_number: str
  operator_id: UUID4
  make_model: str
  year: Optional[int] = None
  serial_number: Optional[str] = None
  aircraft_type: Optional[str] = None
  passenger_capacity: Optional[int] = None
  range_nautical_miles: Optional[int] = None
  cruise_speed_knots: Optional[int] = None
  current_status: str = 'AVAILABLE'
  last_maintenance: Optional[datetime] = None
  next_maintenance_due: Optional[datetime] = None
  insurance_expiry: Optional[datetime] = None
  home_base: Optional[str] = None
  hourly_rate: Optional[float] = None

class AircraftCreate(AircraftBase):
  pass

class AircraftUpdate(AircraftBase):
  tail_number: Optional[str] = None
  make_model: Optional[str] = None
  current_status: Optional[str] = 'AVAILABLE'

class Aircraft(AircraftBase):
  aircraft_id: UUID4
  created_at: datetime

  class Config:
    orm_mode = True