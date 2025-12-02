"""
Florida UCC Filing Flow
State-specific implementation for Florida's UCC filing system using API
API URL: https://publicsearchapi.floridaucc.com/search
"""

from typing import Dict, Any, List
from playwright.async_api import Page
from base_flow import BaseUCCFlow
import httpx
import importlib


class FloridaFlow(BaseUCCFlow):
    """Florida-specific UCC filing flow using public search API"""

    API_BASE_URL = "https://publicsearchapi.floridaucc.com/search"

    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to Florida UCC search page
        Note: Using API, so navigation is minimal
        """
        try:
            print(f"📍 Florida UCC - Using API endpoint: {self.API_BASE_URL}")
            return True
        except Exception as e:
            print(f"❌ Florida navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Florida UCC search form
        Note: Using API instead of form filling
        """
        try:
            print(f"📝 Querying Florida UCC API for: {search_query}")

            # Store search query for use in extract_results
            self.search_query = search_query

            print("✓ Florida API query prepared")
            return True
        except Exception as e:
            print(f"❌ Florida form fill error: {str(e)}")
            return False

    def normalize_filings(self, flow_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Normalize Florida UCC filings to standard format

        Args:
            flow_result: The raw flow result containing API response

        Returns:
            List of normalized filing records with standard fields:
            - filing_date: Date extracted from UCC number (YYYY-MM-DD)
            - status: Lapsed, Active, Terminated, etc.
            - debtor_name: Name of the debtor
            - file_number: UCC filing number
            - address: Full address string (street, city, state, zip)
            - secured_party: null (not available in compact response)
            - collateral: null (not available in compact response)
        """
        try:
            # Import the normalizer using importlib to handle package name with hyphens
            normalizer = importlib.import_module('.ucc_normalizer', package='src.scoring.ucc-filings-flow')
            return normalizer.normalize_ucc_filings(flow_result, "Florida")
        except Exception as e:
            print(f"⚠️ Error normalizing Florida filings: {str(e)}")
            return []

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Florida API
        Uses GET request to public search API with pagination support
        """
        try:
            print("📊 Fetching Florida UCC search results from API...")

            all_debtors = []
            all_responses = []
            row_number = ""
            page_count = 0
            max_pages = 100  # Safety limit to prevent infinite loops

            async with httpx.AsyncClient(timeout=30.0) as client:
                while page_count < max_pages:
                    page_count += 1

                    # Build API URL with query parameters
                    params = {
                        "rowNumber": row_number,
                        "text": self.search_query,
                        "searchOptionType": "OrganizationDebtorName",
                        "searchOptionSubOption": "FiledAndLapsedCompactDebtorNameList",
                        "searchCategory": "Exact"
                    }

                    print(f"   Fetching page {page_count}..." + (f" (rowNumber: {row_number})" if row_number else ""))

                    # Make GET request to API
                    response = await client.get(self.API_BASE_URL, params=params)
                    response.raise_for_status()

                    # Get response data
                    data = response.json()

                    # Extract debtors from this page
                    payload = data.get("payload", {})
                    debtors = payload.get("debtors", [])
                    all_debtors.extend(debtors)

                    # Store page response without debtors (to avoid duplication)
                    page_response = {
                        "status": data.get("status"),
                        "notOk": data.get("notOk"),
                        "messages": data.get("messages"),
                        "payload": {
                            **payload,
                            "debtors": f"[Omitted - {len(debtors)} records included in combined debtors list above]"
                        },
                        "messageSummary": data.get("messageSummary"),
                        "friendlyMessageSummary": data.get("friendlyMessageSummary")
                    }
                    all_responses.append(page_response)

                    print(f"   ✓ Page {page_count}: Found {len(debtors)} filings")

                    # Check for next page
                    next_row_number = payload.get("nextRowNumber")
                    if next_row_number is None:
                        print(f"   ✓ Reached last page")
                        break

                    row_number = str(next_row_number)

            print(f"✓ Florida API pagination complete")
            print(f"   Total pages fetched: {page_count}")
            print(f"   Total filings found: {len(all_debtors)}")

            # Build combined response with all debtors
            combined_response = {
                "status": all_responses[0].get("status") if all_responses else "OK",
                "notOk": all_responses[0].get("notOk", False) if all_responses else False,
                "messages": all_responses[0].get("messages", []) if all_responses else [],
                "payload": {
                    "debtors": all_debtors,
                    "totalExactMatches": all_responses[0].get("payload", {}).get("totalExactMatches", len(all_debtors)) if all_responses else len(all_debtors),
                    "pages_fetched": page_count,
                    "all_page_responses": all_responses  # Keep all individual page responses
                },
                "messageSummary": all_responses[0].get("messageSummary", "") if all_responses else "",
                "friendlyMessageSummary": all_responses[0].get("friendlyMessageSummary", "") if all_responses else ""
            }

            # Build flow result
            flow_result = {
                "raw_response": combined_response,
                "api_url": self.API_BASE_URL,
                "status_code": 200,
                "implementation_status": "api_integration",
                "pages_fetched": page_count
            }

            # Normalize the filings
            normalized_filings = self.normalize_filings(flow_result)

            # Add normalized filings to result
            result = {
                **flow_result,
                "normalized_filings": normalized_filings,
                "filings_count": len(normalized_filings),
                "notes": f"Using Florida public search API with pagination ({page_count} pages)"
            }

            if normalized_filings:
                print(f"   Sample filing: {normalized_filings[0]}")

            return result

        except httpx.HTTPError as e:
            print(f"❌ Florida API HTTP error: {str(e)}")
            return {
                "error": f"HTTP error: {str(e)}",
                "api_url": self.API_BASE_URL,
                "implementation_status": "error"
            }
        except Exception as e:
            print(f"❌ Florida extraction error: {str(e)}")
            return {
                "error": str(e),
                "implementation_status": "error"
            }
