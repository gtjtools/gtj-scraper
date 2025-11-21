# src/operator/service.py
from pydantic import UUID4
from sqlalchemy.orm import Session
from src.common.models import Operator
from src.operator.schemas import OperatorCreate, OperatorUpdate

def get_operators(db: Session, skip: int = 0, limit: int = 100):
  return db.query(Operator).offset(skip).limit(limit).all()

def get_operator(db: Session, operator_id: UUID4):
  return db.query(Operator).filter(Operator.operator_id == operator_id).first()

def create_operator(db: Session, operator: OperatorCreate):
  db_operator = Operator(**operator.dict())
  db.add(db_operator)
  db.commit()
  db.refresh(db_operator)
  return db_operator

def update_operator(db: Session, operator_id: UUID4, operator: OperatorUpdate):
  db_operator = db.query(Operator).filter(Operator.operator_id == operator_id).first()
  if not db_operator:
    return None
  for key, value in operator.dict(exclude_unset=True).items():
    setattr(db_operator, key, value)
  db.commit()
  db.refresh(db_operator)
  return db_operator
