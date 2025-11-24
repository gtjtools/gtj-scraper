# src/organization/service.py
from sqlalchemy.orm import Session
from uuid import UUID
from src.common.models import Organization
from src.organization.schemas import OrganizationCreate, OrganizationUpdate

def get_organizations(db: Session, skip: int = 0, limit: int = 100):
  return db.query(Organization).offset(skip).limit(limit).all()

def get_organization(db: Session, organization_id: UUID):
  return db.query(Organization).filter(Organization.organization_id == organization_id).first()

def create_organization(db: Session, organization: OrganizationCreate):
  db_organization = Organization(**organization.dict())
  db.add(db_organization)
  db.commit()
  db.refresh(db_organization)
  return db_organization

def update_organization(db: Session, organization_id: UUID, organization: OrganizationUpdate):
  db_organization = db.query(Organization).filter(Organization.organization_id == organization_id).first()
  if not db_organization:
    return None
  for key, value in organization.dict(exclude_unset=True).items():
    setattr(db_organization, key, value)
  db.commit()
  db.refresh(db_organization)
  return db_organization
