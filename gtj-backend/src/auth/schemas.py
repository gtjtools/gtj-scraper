from datetime import datetime
from email_validator import validate_email, EmailNotValidError
from pydantic import BaseModel, EmailStr, validator
from typing import Optional

class UserSignup(BaseModel):
  email: str
  password: str

class ConfirmationToken(BaseModel):
  token: str

class UserLogin(BaseModel):
  email: str
  password: str    

class PasswordResetRequest(BaseModel):
  email: str

class PasswordUpdateRequest(BaseModel):
  new_password: str
  token: str
  type: str
