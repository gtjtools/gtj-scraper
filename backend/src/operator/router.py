# src/operator/routers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.operator.schemas import Operator, OperatorCreate, OperatorUpdate
from src.operator.service import get_operators, get_operator, create_operator, update_operator
from src.common.dependencies import get_db
from src.auth.service import authentication
from uuid import UUID

operator_router = APIRouter()

@operator_router.get(
  "/operators",
  summary="List all operators",
  description="Retrieve a list of all operators with pagination support.",
  response_description="A list of operators",
  tags=["operators"]
)
def get_operators_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a list of all operators.

  - **skip**: Number of operators to skip (for pagination).
  - **limit**: Maximum number of operators to return (for pagination).

  Returns:
    list[Operator]: A list of operator objects.

  Raises:
    HTTPException: If no operators are found.
  """
  operators = get_operators(db, skip=skip, limit=limit)
  return operators

@operator_router.get(
  "/operators/{operator_id}",
  summary="Get an operator by ID",
  description="Retrieve a specific operator by its unique ID.",
  response_description="The operator object",
  tags=["operators"]
)
def get_operator_endpoint(operator_id: UUID, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a specific operator by its unique ID.

  - **operator_id**: The unique ID of the operator.

  Returns:
    Operator: The operator object.

  Raises:
    HTTPException: If the operator is not found.
  """
  db_operator = get_operator(db, operator_id)
  if db_operator is None:
    raise HTTPException(status_code=404, detail="Operator not found")
  return db_operator

@operator_router.post(
  "/operators",
  summary="Create a new operator",
  description="Create a new operator with the provided details.",
  response_description="The created operator object",
  tags=["operators"]
)
def post_operator_endpoint(operator: OperatorCreate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Create a new operator with the provided details.

  - **operator**: The details of the operator to create.

  Returns:
    Operator: The created operator object.

  Raises:
    HTTPException: If the operator cannot be created.
  """
  return create_operator(db, operator)

@operator_router.put(
  "/operators/{operator_id}",
  summary="Update an operator",
  description="Update an existing operator by its unique ID.",
  response_description="The updated operator object",
  tags=["operators"]
)
def put_operator_endpoint(operator_id: UUID, operator: OperatorUpdate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Update an existing operator by its unique ID.

  - **operator_id**: The unique ID of the operator.
  - **operator**: The updated details of the operator.

  Returns:
    Operator: The updated operator object.

  Raises:
    HTTPException: If the operator is not found or cannot be updated.
  """
  db_operator = update_operator(db, operator_id, operator)
  if db_operator is None:
    raise HTTPException(status_code=404, detail="Operator not found")
  return db_operator