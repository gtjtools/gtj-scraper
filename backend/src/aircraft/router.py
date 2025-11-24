# src/aircraft/routers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.aircraft.schemas import Aircraft, AircraftCreate, AircraftUpdate
from src.aircraft.service import get_aircrafts, get_aircraft, create_aircraft, update_aircraft
from src.common.dependencies import get_db
from src.auth.service import authentication
from uuid import UUID

aircraft_router = APIRouter()

@aircraft_router.get(
  "/aircrafts",
  summary="List all aircrafts",
  description="Retrieve a list of all aircrafts with pagination support.",
  response_description="A list of aircrafts",
  tags=["aircrafts"]
)
def read_aircrafts_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a list of all aircrafts.

  - **skip**: Number of aircrafts to skip (for pagination).
  - **limit**: Maximum number of aircrafts to return (for pagination).

  Returns:
    list[Aircraft]: A list of aircraft objects.

  Raises:
    HTTPException: If no aircrafts are found.
  """
  aircrafts = get_aircrafts(db, skip=skip, limit=limit)
  return aircrafts

@aircraft_router.get(
  "/aircrafts/{aircraft_id}",
  summary="Get an aircraft by ID",
  description="Retrieve a specific aircraft by its unique ID.",
  response_description="The aircraft object",
  tags=["aircrafts"]
)
def read_aircraft_endpoint(aircraft_id: UUID, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a specific aircraft by its unique ID.

  - **aircraft_id**: The unique ID of the aircraft.

  Returns:
    Aircraft: The aircraft object.

  Raises:
    HTTPException: If the aircraft is not found.
  """
  db_aircraft = get_aircraft(db, aircraft_id)
  if db_aircraft is None:
    raise HTTPException(status_code=404, detail="Aircraft not found")
  return db_aircraft

@aircraft_router.post(
  "/aircrafts",
  summary="Create a new aircraft",
  description="Create a new aircraft with the provided details.",
  response_description="The created aircraft object",
  tags=["aircrafts"]
)
def create_aircraft_endpoint(aircraft: AircraftCreate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Create a new aircraft with the provided details.

  - **aircraft**: The details of the aircraft to create.

  Returns:
    Aircraft: The created aircraft object.

  Raises:
    HTTPException: If the aircraft cannot be created.
  """
  return create_aircraft(db, aircraft)

@aircraft_router.put(
  "/aircrafts/{aircraft_id}",
  summary="Update an aircraft",
  description="Update an existing aircraft by its unique ID.",
  response_description="The updated aircraft object",
  tags=["aircrafts"]
)
def update_aircraft_endpoint(aircraft_id: UUID, aircraft: AircraftUpdate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Update an existing aircraft by its unique ID.

  - **aircraft_id**: The unique ID of the aircraft.
  - **aircraft**: The updated details of the aircraft.

  Returns:
    Aircraft: The updated aircraft object.

  Raises:
    HTTPException: If the aircraft is not found or cannot be updated.
  """
  db_aircraft = update_aircraft(db, aircraft_id, aircraft)
  if db_aircraft is None:
    raise HTTPException(status_code=404, detail="Aircraft not found")
  return db_aircraft