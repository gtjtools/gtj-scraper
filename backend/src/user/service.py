from src.common.models import UserProfile, UserRole
from src.user.schemas import UserCreate, UserUpdate, UserRoleCreate, UserRoleUpdate
from sqlalchemy.orm import Session
from src.common.dependencies import get_db

def create_user(db: Session, user: UserCreate):
  db_user = UserProfile(org_id=user.org_id, email=user.email, role=user.role, first_name=user.first_name, last_name=user.last_name, phone=user.phone, preferences=user.preferences)
  db.add(db_user)
  db.commit()
  db.refresh(db_user)
  return db_user

def get_user(db: Session, user_id: str):
  return db.query(UserProfile).filter(UserProfile.userprofile_id == user_id).first()

def update_user(db: Session, user_id: str, user_update: UserUpdate):
  db_user = db.query(UserProfile).filter(UserProfile.userprofile_id == user_id).first()
  if db_user:
    db_user.org_id = user_update.org_id or db_user.org_id
    db_user.email = user_update.email or db_user.email
    db_user.first_name = user_update.first_name or db_user.first_name
    db_user.last_name = user_update.last_name or db_user.last_name
    db_user.phone = user_update.phone or db_user.phone
    db_user.preferences = user_update.preferences or db_user.preferences
    db_user.is_active = user_update.is_active or db_user.is_active
    db_user.mfa_enabled = user_update.mfa_enabled or db_user.mfa_enabled
    db.commit()
    db.refresh(db_user)
  return db_user

def create_user_role(db: Session, user_role: UserRoleCreate):
  db_user_role = UserRole(**user_role.dict())
  db.add(db_user_role)
  db.commit()
  db.refresh(db_user_role)
  return db_user_role

def get_user_roles(db: Session, skip: int = 0, limit: int = 100):
  return db.query(UserRole).offset(skip).limit(limit).all()

def get_user_role(db: Session, user_role_id: str):
  return db.query(UserRole).filter(UserRole.user_role_id == user_role_id).first()

def update_user_role(db: Session, user_role_id: str, user_role_update: UserRoleUpdate):
  db_user_role = db.query(UserRole).filter(UserRole.user_role_id == user_role_id).first()
  if not db_user_role:
    return None
  for key, value in user_role_update.dict(exclude_unset=True).items():
    setattr(db_user_role, key, value)
  db.commit()
  db.refresh(db_user_role)
  return db_user_role
