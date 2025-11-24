# src/gtj/schemas.py
from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime

class TrustScoreBase(BaseModel):
	operator_id: UUID4
	overall_score: float
	safety_score: float
	financial_score: float
	regulatory_score: float
	aog_score: float
	factors: dict
	version: str
	expires_at: datetime
	confidence_level: float
	def dict(self, *args, **kwargs):
		data = super().dict(*args, **kwargs)
		data['operator_id'] = str(data['operator_id'])
		data['expires_at'] = self.expires_at.isoformat()
		return data

class TrustScoreCreate(TrustScoreBase):
	pass

class TrustScoreUpdate(TrustScoreBase):
	overall_score: Optional[float] = None
	safety_score: Optional[float] = None
	financial_score: Optional[float] = None
	regulatory_score: Optional[float] = None
	aog_score: Optional[float] = None
	factors: Optional[dict] = None
	version: Optional[str] = None
	expires_at: Optional[datetime] = None
	confidence_level: Optional[float] = None

class TrustScore(TrustScoreBase):
	trust_score_id: UUID4
	calculated_at: datetime

	class Config:
		orm_mode = True

class CalculatedTrustScore:
	trust_score: float
