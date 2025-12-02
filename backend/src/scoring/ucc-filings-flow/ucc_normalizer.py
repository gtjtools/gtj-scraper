"""
UCC Filing Data Normalizer
Standardizes UCC filing data from different state formats into a consistent structure
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import re


def normalize_ucc_filings(flow_result: Dict[str, Any], state: str) -> List[Dict[str, Any]]:
    """
    Normalize UCC filing data from any state into a standard format.

    Args:
        flow_result: The flow_result dict from visited_states
        state: The state name for logging purposes

    Returns:
        List of normalized filing records with standard fields:
        - filing_date: Date the UCC was recorded (extracted from various sources)
        - status: Active, Lapsed, Inactive, or Terminated
        - debtor_name: Name of the debtor
        - file_number: UCC filing number (optional)
        - secured_party: Creditor name (optional)
        - collateral: Description of collateral (optional)
    """
    normalized_filings = []

    # State-specific normalization
    if state == "Florida":
        normalized_filings = _normalize_florida(flow_result)
    else:
        # Generic normalization for other states
        normalized_filings = _normalize_generic(flow_result)

    return normalized_filings


def _normalize_florida(flow_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize Florida UCC API response

    Florida API response structure:
    {
        "raw_response": {
            "payload": {
                "debtors": [
                    {
                        "name": "COMPANY NAME",
                        "uccNumber": "980000085041",
                        "status": "Lapsed",
                        ...
                    }
                ]
            }
        }
    }
    """
    normalized = []

    raw_response = flow_result.get("raw_response", {})
    payload = raw_response.get("payload", {})
    debtors = payload.get("debtors", [])

    for debtor in debtors:
        # Extract filing date from UCC number (e.g., "980000085041" -> 1998)
        ucc_number = debtor.get("uccNumber", "")
        filing_date = _extract_date_from_ucc_number(ucc_number)

        # Normalize status
        status = _normalize_status(debtor.get("status", "Unknown"))

        # Build address string
        address_parts = [
            debtor.get("address", ""),
            debtor.get("city", ""),
            debtor.get("state", ""),
            debtor.get("zipCode", "")
        ]
        full_address = ", ".join([p for p in address_parts if p]).strip()

        normalized.append({
            "filing_date": filing_date,
            "status": status,
            "debtor_name": debtor.get("name", "Unknown"),
            "file_number": ucc_number,
            "address": full_address,
            "secured_party": None,  # Not available in Florida compact response
            "collateral": None  # Not available in Florida compact response
        })

    return normalized


def _normalize_generic(flow_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generic normalization for states that return data in 'filings' array

    Expected structure:
    {
        "filings": [
            {
                "file_number": "...",
                "debtor_name": "...",
                "filing_date": "...",
                "status": "...",
                "secured_party": "...",
                "collateral": "..."
            }
        ]
    }
    """
    normalized = []

    filings = flow_result.get("filings", [])

    for filing in filings:
        # Normalize date
        filing_date = filing.get("filing_date", "Unknown")
        if filing_date and filing_date != "Unknown":
            filing_date = _normalize_date(filing_date)

        # Normalize status
        status = _normalize_status(filing.get("status", "Unknown"))

        normalized.append({
            "filing_date": filing_date,
            "status": status,
            "debtor_name": filing.get("debtor_name", filing.get("debtor", "Unknown")),
            "file_number": filing.get("file_number", None),
            "secured_party": filing.get("secured_party", None),
            "collateral": filing.get("collateral", None)
        })

    return normalized


def _extract_date_from_ucc_number(ucc_number: str) -> str:
    """
    Extract filing date from UCC number.

    Florida format: YYYYMMNNNNNN or YYMMNNNNNN
    Examples:
    - "980000085041" -> 1998-01-01 (2-digit year)
    - "200000012910" -> 2000-01-01 (4-digit year)
    - "201806358547" -> 2018-06-01 (with month)

    Returns date string in format "YYYY-MM-DD"
    """
    if not ucc_number or len(ucc_number) < 2:
        return "Unknown"

    try:
        # First, try 4-digit year format (positions 0-3)
        if len(ucc_number) >= 4:
            year_str = ucc_number[:4]
            year = int(year_str)

            # If it's a valid 4-digit year (1990-2099)
            if 1990 <= year <= 2099:
                # Try to extract month (positions 4-5)
                if len(ucc_number) >= 6:
                    month_str = ucc_number[4:6]
                    month = int(month_str)
                    # Validate month (1-12)
                    if 1 <= month <= 12:
                        return f"{year:04d}-{month:02d}-01"

                # Return with default month
                return f"{year:04d}-01-01"

        # If not valid 4-digit year, try 2-digit year (positions 0-1)
        if len(ucc_number) >= 2:
            year_str = ucc_number[:2]
            year = int(year_str)

            # Convert 2-digit year to 4-digit (90-99 -> 1990-1999, 00-89 -> 2000-2089)
            if year >= 90:
                full_year = 1900 + year
            else:
                full_year = 2000 + year

            # Try to extract month (positions 2-3 for 2-digit year format)
            if len(ucc_number) >= 4:
                month_str = ucc_number[2:4]
                # Check if it looks like a month (not part of sequence number)
                try:
                    month = int(month_str)
                    if 1 <= month <= 12:
                        return f"{full_year:04d}-{month:02d}-01"
                except ValueError:
                    pass

            # Return with default month
            return f"{full_year:04d}-01-01"

    except (ValueError, IndexError):
        pass

    return "Unknown"


def _normalize_date(date_str: str) -> str:
    """
    Normalize various date formats to ISO format (YYYY-MM-DD)

    Handles formats like:
    - "2025-04-04"
    - "04/04/2025"
    - "Apr 4, 2025"
    - "2025-04-04T14:17:00Z"
    """
    if not date_str or date_str == "Unknown":
        return "Unknown"

    # Try ISO format with time
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        pass

    # Try MM/DD/YYYY format
    try:
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        pass

    # Try YYYY-MM-DD format
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        pass

    # Return as-is if parsing failed
    return date_str


def _normalize_status(status: str) -> str:
    """
    Normalize status values to standard values: Active, Lapsed, Inactive, Terminated

    Handles variations like:
    - "active" -> "Active"
    - "LAPSED" -> "Lapsed"
    - "Expired" -> "Lapsed"
    - "Filed" -> "Active"
    """
    if not status:
        return "Unknown"

    status_lower = status.lower().strip()

    # Active status variations
    if status_lower in ["active", "filed", "current", "valid"]:
        return "Active"

    # Lapsed status variations
    if status_lower in ["lapsed", "expired", "inactive"]:
        return "Lapsed"

    # Terminated status variations
    if status_lower in ["terminated", "cancelled", "discharged", "released"]:
        return "Terminated"

    # Return capitalized version if no match
    return status.capitalize()


def normalize_all_states(visited_states: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize UCC filings from all visited states

    Args:
        visited_states: List of state results from UCC verification

    Returns:
        Dictionary mapping state name to list of normalized filings
    """
    all_normalized = {}

    for state_result in visited_states:
        state = state_result.get("state", "Unknown")
        flow_result = state_result.get("flow_result")

        if flow_result:
            normalized_filings = normalize_ucc_filings(flow_result, state)
            all_normalized[state] = normalized_filings

    return all_normalized
