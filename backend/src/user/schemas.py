from datetime import datetime
from email_validator import validate_email, EmailNotValidError
from pydantic import BaseModel, EmailStr, validator, UUID4
from typing import Optional
from src.common.constants import HTTP_400_BAD_REQUEST
from src.common.error import HTTPError

class UserBase(BaseModel):
	email: EmailStr
	role: str
	org_id: UUID4
	first_name: Optional[str] = None
	last_name: Optional[str] = None
	phone: Optional[str] = None
	preferences: Optional[dict] = None

class UserCreate(UserBase):
	pass
	@validator('email')
	def email_must_be_valid(cls, v):
		try:
			validate_email(v)
			return v
		except EmailNotValidError:
			raise HTTPError(detail="Invalid email address")

class UserUpdate(UserBase):
	email: Optional[EmailStr] = None
	role: Optional[str] = None
	org_id: Optional[UUID4] = None
	is_active: Optional[bool] = None
	mfa_enabled: Optional[bool] = None

class UserInDB(UserBase):
	userprofile_id: UUID4
	last_login: Optional[datetime] = None
	is_active: bool
	created_at: datetime
	mfa_enabled: bool

	class Config:
		orm_mode = True

class UserRoleBase(BaseModel):
	user_profile_id: UUID4
	role: str
	is_active: Optional[bool] = True

class UserRoleCreate(UserRoleBase):
	pass

class UserRoleUpdate(UserRoleBase):
	pass

class UserRoleInDB(UserRoleBase):
	user_role_id: UUID4
	created_at: datetime

	class Config:
		orm_mode = True