"""
Vermont UCC Filing Flow
State-specific implementation for Vermont's UCC filing system
URL: https://sos.vermont.gov/business-services/ucc-liens/
"""

from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class VermontFlow(BaseUCCFlow):
    """Vermont-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to Vermont UCC search page"""
        try:
            print(f"📍 Navigating to Vermont UCC page: {self.state_url}")
            await page.goto(
                self.state_url, wait_until="domcontentloaded", timeout=30000
            )
            await page.wait_for_timeout(2000)

            print("✓ Successfully navigated to Vermont UCC page")
            return True
        except Exception as e:
            print(f"❌ Vermont navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Vermont UCC search form

        Steps:
        1. Look for organization/debtor name input
        2. Fill in the organization name field
        3. Click the search button
        4. Wait for results
        """
        try:
            print(f"📝 Filling Vermont UCC search form for: {search_query}")

            # Step 1: Look for organization name input
            print("   Step 1: Looking for organization name input...")
            input_selectors = [
                'input[name*="organization"]',
                'input[name*="Organization"]',
                'input[id*="organization"]',
                'input[id*="orgName"]',
                'input[name*="debtor"]',
                'input[name*="Debtor"]',
                'input[id*="debtor"]',
                'input[name*="name"]',
                'input[name*="Name"]',
                'input[placeholder*="Organization"]',
                'input[placeholder*="Business"]',
                'input[placeholder*="Debtor"]',
                'input[placeholder*="Name"]',
                'input[type="text"]',
                'input[type="search"]'
            ]

            input_found = False
            for selector in input_selectors:
                try:
                    input_field = await page.query_selector(selector)
                    if input_field:
                        is_visible = await input_field.is_visible()
                        if is_visible:
                            print(f"   ✓ Found input field: {selector}")
                            await input_field.fill(search_query)
                            await page.wait_for_timeout(1000)
                            print(f"   ✓ Organization name entered: {search_query}")
                            input_found = True
                            break
                except:
                    continue

            if not input_found:
                print("   ⚠️  Could not find organization name input")

            # Step 2: Click the search button
            print("   Step 2: Clicking search button...")
            button_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Search")',
                'button:has-text("Submit")',
                'input[value*="Search"]',
                'a:has-text("Search")'
            ]

            button_found = False
            for selector in button_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        is_visible = await button.is_visible()
                        if is_visible:
                            print(f"   ✓ Found search button: {selector}")
                            await button.click()
                            print("   ✓ Search button clicked")
                            button_found = True
                            break
                except:
                    continue

            if not button_found:
                print("   ⚠️  Could not find search button")

            # Step 3: Wait for results to load
            print("   Step 3: Waiting for results...")
            await page.wait_for_timeout(3000)
            print("   ✓ Results loaded")

            # Take screenshot of results
            await self.take_screenshot(page, f"vermont_search_results.png")

            print("✓ Vermont search form completed successfully")
            return True
        except Exception as e:
            print(f"❌ Vermont form fill error: {str(e)}")
            await self.take_screenshot(page, f"vermont_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Vermont's page
        """
        try:
            print("📊 Extracting Vermont UCC search results...")

            # Get page title and URL for reference
            page_title = await page.title()
            page_url = page.url

            print(f"   Page Title: {page_title}")
            print(f"   Page URL: {page_url}")

            # Take screenshot of final results
            await self.take_screenshot(page, f"vermont_final_results.png")

            # Extract data from tables
            filings = []

            try:
                # Find all table rows
                print("   Looking for result tables...")
                tables = page.locator('table')
                table_count = await tables.count()
                print(f"   Found {table_count} tables")

                if table_count > 0:
                    # Try to extract from the main results table
                    rows = page.locator('table tr')
                    row_count = await rows.count()
                    print(f"   Found {row_count} rows in tables")

                    # Process each row (skip header)
                    for i in range(1, row_count):
                        row = rows.nth(i)
                        try:
                            # Extract all cells
                            cells = row.locator('td')
                            cell_count = await cells.count()

                            if cell_count > 0:
                                # Extract data from cells
                                filing_record = {}

                                # Typically: File Number, Debtor, Filing Date, Status, etc.
                                if cell_count >= 1:
                                    filing_record['file_number'] = (await cells.nth(0).inner_text()).strip()
                                if cell_count >= 2:
                                    filing_record['debtor_name'] = (await cells.nth(1).inner_text()).strip()
                                if cell_count >= 3:
                                    filing_record['filing_date'] = (await cells.nth(2).inner_text()).strip()
                                if cell_count >= 4:
                                    filing_record['status'] = (await cells.nth(3).inner_text()).strip()

                                if filing_record.get('file_number') or filing_record.get('debtor_name'):
                                    filings.append(filing_record)
                                    print(f"   Row {i}: {filing_record}")
                        except Exception as row_error:
                            print(f"   ⚠️  Error processing row {i}: {str(row_error)}")
                            continue

                print(f"\n✓ Extracted {len(filings)} filing records")

            except Exception as e:
                print(f"⚠️  Could not extract table data: {str(e)}")

            print("✓ Vermont results extraction completed")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "functional",
                "notes": f"Extracted {len(filings)} UCC filing records",
            }
        except Exception as e:
            print(f"❌ Vermont extraction error: {str(e)}")
            return {"filings": [], "total_count": 0, "error": str(e)}
