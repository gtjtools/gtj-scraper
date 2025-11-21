# src/operator/schemas.py
from pydantic import BaseModel, UUID4
from typing import Optional
from uuid import UUID
from datetime import datetime

class OperatorBase(BaseModel):
  name: str
  dba_name: Optional[str] = None
  certificate_number: Optional[str] = None
  ops_specs: Optional[str] = None
  base_airport: Optional[str] = None
  trust_score: Optional[float] = None
  trust_score_updated_at: Optional[datetime] = None
  financial_health_score: Optional[float] = None
  regulatory_status: str
  is_verified: bool = False
  def dict(self, *args, **kwargs):
    data = super().dict(*args, **kwargs)
    data['trust_score_updated_at'] = self.trust_score_updated_at.isoformat()
    return data

class OperatorCreate(OperatorBase):
  pass

class OperatorUpdate(OperatorBase):
  pass

class Operator(OperatorBase):
  operator_id: UUID4
  created_at: datetime
  updated_at: datetime

  class Config:
    orm_mode = True