"""
Michigan UCC Filing Flow
State-specific implementation for Michigan's UCC filing system
URL: https://ucc.michigan.gov/ucc-search
"""

from typing import Dict, Any, List
from playwright.async_api import Page
from base_flow import BaseUCCFlow
import importlib


class MichiganFlow(BaseUCCFlow):
    """Michigan-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to Michigan UCC search page"""
        try:
            michigan_url = "https://ucc.michigan.gov/ucc-search"
            print(f"📍 Navigating to Michigan UCC page: {michigan_url}")
            await page.goto(
                michigan_url, wait_until="domcontentloaded", timeout=30000
            )
            await page.wait_for_timeout(2000)

            print("✓ Successfully navigated to Michigan UCC page")
            return True
        except Exception as e:
            print(f"❌ Michigan navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Michigan UCC search form

        Steps:
        1. Find and fill organization name input (XPath: //input[@id="organizationName"])
        2. Click the search button (XPath: //span[text()="Search"])
        3. Wait for results
        """
        try:
            print(f"📝 Filling Michigan UCC search form for: {search_query}")

            # Store search query for use in extract_results
            self.search_query = search_query

            # Step 1: Fill organization name input
            print("   Step 1: Looking for organization name input...")
            try:
                input_field = page.locator('xpath=//input[@id="organizationName"]')
                await input_field.wait_for(state="visible", timeout=10000)
                await input_field.fill(search_query)
                await page.wait_for_timeout(1000)
                print(f"   ✓ Organization name entered: {search_query}")
            except Exception as e:
                print(f"   ❌ Could not find or fill organization name input: {str(e)}")
                await self.take_screenshot(page, f"michigan_input_error.png")
                return False

            # Step 2: Click the search button
            print("   Step 2: Clicking search button...")
            try:
                search_button = page.locator('xpath=//span[text()="Search"]')
                await search_button.wait_for(state="visible", timeout=10000)
                await search_button.click()
                print("   ✓ Search button clicked")
            except Exception as e:
                print(f"   ❌ Could not find or click search button: {str(e)}")
                await self.take_screenshot(page, f"michigan_button_error.png")
                return False

            # Step 3: Wait for results to load
            print("   Step 3: Waiting for results...")
            await page.wait_for_timeout(3000)
            print("   ✓ Results loaded")

            # Take screenshot of results
            await self.take_screenshot(page, f"michigan_search_results.png")

            print("✓ Michigan search form completed successfully")
            return True
        except Exception as e:
            print(f"❌ Michigan form fill error: {str(e)}")
            await self.take_screenshot(page, f"michigan_error.png")
            return False

    def normalize_filings(self, flow_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Normalize Michigan UCC filings to standard format

        Args:
            flow_result: The raw flow result containing filings data

        Returns:
            List of normalized filing records with standard fields:
            - filing_date: Registered date (YYYY-MM-DD)
            - status: Active, Lapsed, Terminated, etc.
            - debtor: Name of the debtor (operator name)
            - file_number: Financing statement number
            - lapse_date: Date when the lien lapses
            - lien_type: Type of lien (e.g., "UCC Lien")
        """
        try:
            # Import the normalizer using importlib to handle package name with hyphens
            normalizer = importlib.import_module('.ucc_normalizer', package='src.scoring.ucc-filings-flow')
            return normalizer.normalize_ucc_filings(flow_result, "Michigan")
        except Exception as e:
            print(f"⚠️ Error normalizing Michigan filings: {str(e)}")
            return []

    def _parse_mat_row_text(self, row_text: str) -> Dict[str, Any]:
        """
        Parse mat-row text into structured data

        Example row text:
        "Financing statement number
        2016105551-8
        Lien type
        UCC Lien
        Registered date
        07/29/2016
        Lapse date
        07/29/2026
        Status
        Active"

        Returns dict with extracted fields
        """
        try:
            # Split by newlines and clean up
            lines = [line.strip() for line in row_text.split('\n') if line.strip()]

            # Create a dict by pairing labels with values
            data = {}
            i = 0
            while i < len(lines) - 1:
                label = lines[i].lower().replace(' ', '_')
                value = lines[i + 1]
                data[label] = value
                i += 2

            # Map to standard fields
            filing = {
                "file_number": data.get("financing_statement_number", "Unknown"),
                "filing_date": data.get("registered_date", "Unknown"),
                "lapse_date": data.get("lapse_date", "Unknown"),
                "status": data.get("status", "Unknown"),
                "lien_type": data.get("lien_type", "Unknown"),
                "debtor": getattr(self, 'search_query', 'Unknown')  # Use the operator name we searched for
            }

            return filing

        except Exception as e:
            print(f"   ⚠️ Error parsing row text: {str(e)}")
            return {}

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Michigan's page
        Uses mat-table structure (XPath: //mat-table//mat-row)
        """
        try:
            print("📊 Extracting Michigan UCC search results...")

            # Get page title and URL for reference
            page_title = await page.title()
            page_url = page.url

            print(f"   Page Title: {page_title}")
            print(f"   Page URL: {page_url}")

            # Take screenshot of final results
            await self.take_screenshot(page, f"michigan_final_results.png")

            # Extract data from mat-table
            filings = []

            try:
                # Find all mat-table rows using XPath
                print("   Looking for mat-table rows...")
                mat_rows = page.locator('xpath=//mat-table//mat-row')

                try:
                    # Wait for results to appear (with timeout)
                    await mat_rows.first.wait_for(state="visible", timeout=5000)
                    row_count = await mat_rows.count()
                    print(f"   ✓ Found {row_count} mat-rows")

                    # Process each row
                    for i in range(row_count):
                        row = mat_rows.nth(i)
                        try:
                            # Get the full text content of the row
                            row_text = await row.inner_text()
                            print(f"   Row {i + 1} raw text: {row_text[:100]}...")  # Print first 100 chars

                            # Parse the row text into structured data
                            parsed_filing = self._parse_mat_row_text(row_text)

                            if parsed_filing.get("file_number") != "Unknown":
                                filings.append(parsed_filing)
                                print(f"   ✓ Row {i + 1} parsed: {parsed_filing.get('file_number')} - {parsed_filing.get('status')}")
                            else:
                                print(f"   ⚠️  Row {i + 1} could not be parsed properly")

                        except Exception as row_error:
                            print(f"   ⚠️  Error processing row {i + 1}: {str(row_error)}")
                            continue

                    print(f"\n✓ Extracted {len(filings)} filing records")

                except Exception as wait_error:
                    print(f"   ℹ️  No results found or results took too long to load: {str(wait_error)}")
                    print("   This may indicate no UCC filings were found for this operator")

            except Exception as e:
                print(f"⚠️  Could not extract mat-table data: {str(e)}")

            print("✓ Michigan results extraction completed")

            # Build raw response structure (similar to Florida)
            raw_response = {
                "page_title": page_title,
                "page_url": page_url,
                "filings": filings,
                "total_count": len(filings)
            }

            # Build flow result (matching Florida's structure)
            flow_result = {
                "raw_response": raw_response,
                "filings": filings,  # Keep at top level for normalizer
                "implementation_status": "functional",
                "notes": f"Extracted {len(filings)} UCC filing records from mat-table",
            }

            # Normalize the filings
            normalized_filings = self.normalize_filings(flow_result)

            # Add normalized filings to result (matching Florida's structure)
            result = {
                **flow_result,
                "normalized_filings": normalized_filings,
                "filings_count": len(normalized_filings),
            }

            if normalized_filings:
                print(f"   Sample normalized filing: {normalized_filings[0]}")

            return result

        except Exception as e:
            print(f"❌ Michigan extraction error: {str(e)}")
            await self.take_screenshot(page, f"michigan_extraction_error.png")
            return {"filings": [], "total_count": 0, "error": str(e)}
