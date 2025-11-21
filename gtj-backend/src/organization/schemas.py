# src/organization/schemas.py
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

class OrganizationBase(BaseModel):
	name: str
	type: str
	subscription_tier: str
	billing_email: Optional[str] = None
	tax_id: Optional[str] = None
	address: Optional[dict] = None
	settings: Optional[dict] = None

class OrganizationCreate(OrganizationBase):
	pass

class OrganizationUpdate(OrganizationBase):
	pass

class Organization(OrganizationBase):
	organization_id: UUID
	created_at: datetime
	updated_at: datetime

	class Config:
		orm_mode = True