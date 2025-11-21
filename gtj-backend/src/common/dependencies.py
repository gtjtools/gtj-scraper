from fastapi import Depends, HTTPException, Request
from src.common.config import SessionLocal
from src.common.utils import get_supabase_client
from src.common.constants import HTTP_401_UNAUTHORIZED

async def get_db():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()
