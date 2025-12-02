"""
Charter Operator Service
Business logic for charter operator operations using Supabase RPC functions
"""

from typing import List, Optional
from src.common.supabase import get_supabase_client
from src.operator.charter_schemas import (
    CharterOperator,
    CharterOperatorCreate,
    CharterOperatorUpdate,
    CharterOperatorResponse
)


async def get_charter_operators(
    skip: int = 0,
    limit: int = None,
    search: Optional[str] = None
) -> CharterOperatorResponse:
    """
    Get all charter operators with optional search and pagination
    Uses RPC function to access gtj.operators table

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        search: Optional search query for company name or locations

    Returns:
        CharterOperatorResponse with total count and data
    """
    try:
        supabase = get_supabase_client()

        # Call RPC function
        response = supabase.rpc(
            'get_charter_operators',
            {
                'p_skip': skip,
                'p_limit': limit,
                'p_search': search
            }
        ).execute()

        # RPC function returns JSON with 'total' and 'data' keys
        result = response.data

        return CharterOperatorResponse(
            total=result.get('total', 0),
            data=result.get('data', [])
        )

    except Exception as e:
        print(f"Error fetching charter operators: {e}")
        raise


async def get_charter_operator_by_id(charter_operator_id: str) -> Optional[CharterOperator]:
    """
    Get a single charter operator by ID
    Uses RPC function to access gtj.operators table

    Args:
        charter_operator_id: UUID of the charter operator

    Returns:
        CharterOperator or None if not found
    """
    try:
        supabase = get_supabase_client()

        response = supabase.rpc(
            'get_charter_operator',
            {'p_operator_id': charter_operator_id}
        ).execute()

        return CharterOperator(**response.data) if response.data else None

    except Exception as e:
        print(f"Error fetching charter operator {charter_operator_id}: {e}")
        return None


async def create_charter_operator(operator: CharterOperatorCreate) -> CharterOperator:
    """
    Create a new charter operator
    Uses RPC function to insert into gtj.operators table

    Args:
        operator: CharterOperatorCreate schema

    Returns:
        Created CharterOperator
    """
    try:
        supabase = get_supabase_client()

        response = supabase.rpc(
            'create_charter_operator',
            {
                'p_company': operator.company,
                'p_locations': operator.locations,
                'p_url': operator.url,
                'p_part135_cert': operator.part135_cert,
                'p_score': operator.score or 0,
                'p_faa_data': operator.faa_data,
                'p_data': operator.data.model_dump() if operator.data else None
            }
        ).execute()

        return CharterOperator(**response.data)

    except Exception as e:
        print(f"Error creating charter operator: {e}")
        raise


async def update_charter_operator(
    charter_operator_id: str,
    operator: CharterOperatorUpdate
) -> Optional[CharterOperator]:
    """
    Update an existing charter operator
    Note: No RPC function available yet - needs to be created in Supabase

    Args:
        charter_operator_id: UUID of the charter operator
        operator: CharterOperatorUpdate schema

    Returns:
        Updated CharterOperator or None if not found
    """
    # TODO: Create update_charter_operator RPC function in Supabase
    raise NotImplementedError("Update operation requires RPC function to be created in Supabase")


async def delete_charter_operator(charter_operator_id: str) -> bool:
    """
    Delete a charter operator
    Note: No RPC function available yet - needs to be created in Supabase

    Args:
        charter_operator_id: UUID of the charter operator

    Returns:
        True if deleted, False otherwise
    """
    # TODO: Create delete_charter_operator RPC function in Supabase
    raise NotImplementedError("Delete operation requires RPC function to be created in Supabase")


async def filter_charter_operators(
    cert_type: Optional[str] = None,
    min_score: Optional[int] = None
) -> CharterOperatorResponse:
    """
    Filter charter operators by certification type and minimum score

    Args:
        cert_type: Certification type to filter (argus, wyvern, is-bao)
        min_score: Minimum score threshold

    Returns:
        CharterOperatorResponse with filtered results
    """
    try:
        supabase = get_supabase_client()

        # Call RPC function
        response = supabase.rpc(
            'filter_charter_operators',
            {
                'p_cert_type': cert_type,
                'p_min_score': min_score
            }
        ).execute()

        # RPC function returns JSON with 'total' and 'data' keys
        result = response.data

        return CharterOperatorResponse(
            total=result.get('total', 0),
            data=result.get('data', [])
        )

    except Exception as e:
        print(f"Error filtering charter operators: {e}")
        raise
