# src/operator/routers.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from src.operator.schemas import Operator, OperatorCreate, OperatorUpdate
from src.operator.service import get_operators, get_operator, create_operator, update_operator
from src.operator.charter_schemas import (
    CharterOperator,
    CharterOperatorCreate,
    CharterOperatorUpdate,
    CharterOperatorResponse
)
from src.operator.charter_service import (
    get_charter_operators,
    get_charter_operator_by_id,
    create_charter_operator,
    update_charter_operator,
    delete_charter_operator,
    filter_charter_operators
)
from src.common.dependencies import get_db
from src.common.supabase import get_supabase_client
from src.auth.service import authentication
from uuid import UUID
from typing import Optional, Any, Dict

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


# ===== CHARTER OPERATORS ENDPOINTS =====

@operator_router.get(
  "/charter/operators",
  response_model=CharterOperatorResponse,
  summary="List all charter operators",
  description="Retrieve a list of charter operators with optional search and pagination.",
  tags=["charter-operators"]
)
async def get_charter_operators_endpoint(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: Optional[int] = Query(None, ge=1, description="Maximum number of records to return (no limit if not specified)"),
    search: Optional[str] = Query(None, description="Search query for company name or locations")
):
  """
  Retrieve a list of charter operators from Supabase.

  - **skip**: Number of records to skip (for pagination)
  - **limit**: Maximum number of records to return (for pagination)
  - **search**: Optional search query to filter by company name or locations

  Returns:
    CharterOperatorResponse: Object containing total count and list of charter operators
  """
  try:
    return await get_charter_operators(skip=skip, limit=limit, search=search)
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error fetching charter operators: {str(e)}")


@operator_router.get(
  "/charter/operators/{charter_operator_id}",
  response_model=CharterOperator,
  summary="Get a charter operator by ID",
  description="Retrieve a specific charter operator by its unique ID.",
  tags=["charter-operators"]
)
async def get_charter_operator_endpoint(charter_operator_id: str):
  """
  Retrieve a specific charter operator by its unique ID.

  - **charter_operator_id**: The unique UUID of the charter operator

  Returns:
    CharterOperator: The charter operator object

  Raises:
    HTTPException: If the charter operator is not found
  """
  operator = await get_charter_operator_by_id(charter_operator_id)
  if operator is None:
    raise HTTPException(status_code=404, detail="Charter operator not found")
  return operator


@operator_router.post(
  "/charter/operators",
  response_model=CharterOperator,
  summary="Create a new charter operator",
  description="Create a new charter operator with the provided details.",
  tags=["charter-operators"]
)
async def create_charter_operator_endpoint(operator: CharterOperatorCreate):
  """
  Create a new charter operator.

  - **operator**: The charter operator details to create

  Returns:
    CharterOperator: The created charter operator object

  Raises:
    HTTPException: If the charter operator cannot be created
  """
  try:
    return await create_charter_operator(operator)
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error creating charter operator: {str(e)}")


@operator_router.put(
  "/charter/operators/{charter_operator_id}",
  response_model=CharterOperator,
  summary="Update a charter operator",
  description="Update an existing charter operator by its unique ID.",
  tags=["charter-operators"]
)
async def update_charter_operator_endpoint(
    charter_operator_id: str,
    operator: CharterOperatorUpdate
):
  """
  Update an existing charter operator.

  - **charter_operator_id**: The unique UUID of the charter operator
  - **operator**: The updated charter operator details

  Returns:
    CharterOperator: The updated charter operator object

  Raises:
    HTTPException: If the charter operator is not found
  """
  db_operator = await update_charter_operator(charter_operator_id, operator)
  if db_operator is None:
    raise HTTPException(status_code=404, detail="Charter operator not found")
  return db_operator


@operator_router.delete(
  "/charter/operators/{charter_operator_id}",
  summary="Delete a charter operator",
  description="Delete a charter operator by its unique ID.",
  tags=["charter-operators"]
)
async def delete_charter_operator_endpoint(charter_operator_id: str):
  """
  Delete a charter operator.

  - **charter_operator_id**: The unique UUID of the charter operator

  Returns:
    dict: Success message

  Raises:
    HTTPException: If the charter operator is not found
  """
  success = await delete_charter_operator(charter_operator_id)
  if not success:
    raise HTTPException(status_code=404, detail="Charter operator not found")
  return {"message": "Charter operator deleted successfully"}


@operator_router.get(
  "/charter/filter",
  response_model=CharterOperatorResponse,
  summary="Filter charter operators",
  description="Filter charter operators by certification type and minimum score.",
  tags=["charter-operators"]
)
async def filter_charter_operators_endpoint(
    cert: Optional[str] = Query(None, description="Certification type filter (argus, wyvern, is-bao)"),
    minScore: Optional[int] = Query(None, ge=0, description="Minimum score threshold")
):
  """
  Filter charter operators by certification and score.

  - **cert**: Certification type to filter by (argus, wyvern, is-bao, etc.)
  - **minScore**: Minimum score threshold

  Returns:
    CharterOperatorResponse: Filtered list of charter operators
  """
  try:
    return await filter_charter_operators(cert_type=cert, min_score=minScore)
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error filtering charter operators: {str(e)}")


# ===== TEST/DEBUG ENDPOINTS =====

@operator_router.get(
  "/test/operators-data",
  summary="Test endpoint - Get operators data via RPC",
  description="Test endpoint to fetch operators from gtj schema using Supabase RPC",
  tags=["test"]
)
async def test_get_operators_data():
  """
  Test endpoint that demonstrates how to use Supabase client with RPC functions.

  This calls the 'get_operators_data' RPC function in Supabase which accesses gtj.operators table.

  Returns:
    dict: Raw data from the RPC function including total count, columns, and sample data
  """
  try:
    # Get Supabase client
    supabase = get_supabase_client()

    # Call RPC function
    result = supabase.rpc('get_operators_data').execute()

    # Return the data
    return {
      "success": True,
      "data": result.data,
      "message": "Successfully fetched operators data via RPC"
    }

  except Exception as e:
    error_msg = str(e)

    if 'Could not find' in error_msg or 'does not exist' in error_msg:
      raise HTTPException(
        status_code=404,
        detail="RPC function 'get_operators_data' not found. Please create it in Supabase SQL Editor first."
      )

    raise HTTPException(status_code=500, detail=f"Error calling RPC function: {error_msg}")


@operator_router.post(
  "/test/rpc-call",
  summary="Test endpoint - Call any RPC function",
  description="Generic endpoint to test calling any Supabase RPC function with parameters",
  tags=["test"]
)
async def test_rpc_call(
    function_name: str = Query(..., description="Name of the RPC function to call"),
    params: Optional[Dict[str, Any]] = None
):
  """
  Generic test endpoint to call any Supabase RPC function.

  Examples:
  - GET /test/rpc-call?function_name=get_operators_data
  - POST /test/rpc-call with body: {"function_name": "test_function", "params": {"p_id": 123}}

  Args:
    function_name: Name of the RPC function in Supabase
    params: Optional parameters to pass to the function

  Returns:
    dict: Result from the RPC function
  """
  try:
    supabase = get_supabase_client()

    # Call RPC function with or without parameters
    if params:
      result = supabase.rpc(function_name, params).execute()
    else:
      result = supabase.rpc(function_name).execute()

    return {
      "success": True,
      "function": function_name,
      "params": params,
      "data": result.data
    }

  except Exception as e:
    error_msg = str(e)
    raise HTTPException(status_code=500, detail=f"RPC call failed: {error_msg}")