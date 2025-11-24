# src/aircraft/service.py
from sqlalchemy.orm import Session
from uuid import UUID
from src.common.models import Aircraft
from src.aircraft.schemas import AircraftCreate, AircraftUpdate

def get_aircrafts(db: Session, skip: int = 0, limit: int = 100):
  return db.query(Aircraft).offset(skip).limit(limit).all()

def get_aircraft(db: Session, aircraft_id: UUID):
  return db.query(Aircraft).filter(Aircraft.aircraft_id == aircraft_id).first()

def create_aircraft(db: Session, aircraft: AircraftCreate):
  db_aircraft = Aircraft(**aircraft.dict())
  db.add(db_aircraft)
  db.commit()
  db.refresh(db_aircraft)
  return db_aircraft

def update_aircraft(db: Session, aircraft_id: UUID, aircraft: AircraftUpdate):
  db_aircraft = db.query(Aircraft).filter(Aircraft.aircraft_id == aircraft_id).first()
  if not db_aircraft:
    return None
  for key, value in aircraft.dict(exclude_unset=True).items():
    setattr(db_aircraft, key, value)
  db.commit()
  db.refresh(db_aircraft)
  return db_aircraft
