"""
Charter Operator Schemas
Pydantic models for charter operator data validation
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class Certifications(BaseModel):
    """Certification details for a charter operator"""
    aoc_part135: Optional[str] = None
    aoc_part121: Optional[str] = None
    wyvern_certified: Optional[str] = None
    argus_rating: Optional[str] = None
    is_bao: Optional[str] = None
    acsf_ias: Optional[str] = None


class ContactInfo(BaseModel):
    """Contact information for a charter operator"""
    telephone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None


class Base(BaseModel):
    """Aircraft base information"""
    location: str
    aircraft: str
    type: Optional[str] = None


class OperatorData(BaseModel):
    """Detailed operator information from charter sources"""
    name: Optional[str] = None
    country: Optional[str] = None
    certifications: Optional[Certifications] = None
    contact: Optional[ContactInfo] = None
    bases: Optional[List[Base]] = None
    url: Optional[str] = None


class CharterOperatorBase(BaseModel):
    """Base schema for charter operator"""
    company: str
    locations: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    part135_cert: Optional[str] = None
    faa_state: Optional[str] = None  # 2-letter state code from FAA database
    score: Optional[int] = 0
    faa_data: Optional[Dict[str, Any]] = None
    data: Optional[OperatorData] = None


class CharterOperatorCreate(CharterOperatorBase):
    """Schema for creating a charter operator"""
    pass


class CharterOperatorUpdate(CharterOperatorBase):
    """Schema for updating a charter operator"""
    company: Optional[str] = None


class CharterOperator(CharterOperatorBase):
    """Full charter operator schema with database fields"""
    charter_operator_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class CharterOperatorResponse(BaseModel):
    """Response schema for charter operators list"""
    total: int
    data: List[CharterOperator]
