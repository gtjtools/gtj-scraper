"""
California UCC Filing Flow
State-specific implementation for California's UCC filing system
URL: https://bizfileonline.sos.ca.gov/search/ucc
"""

from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class CaliforniaFlow(BaseUCCFlow):
    """California-specific UCC filing flow"""

    SEARCH_URL = "https://bizfileonline.sos.ca.gov/search/ucc"

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to California UCC search page"""
        try:
            print(f"📍 Navigating to California UCC search page...")
            print(f"   URL: {self.SEARCH_URL}")

            await page.goto(
                self.SEARCH_URL, wait_until="domcontentloaded", timeout=30000
            )
            await page.wait_for_timeout(3000)

            print("✓ Successfully navigated to California UCC search page")
            return True
        except Exception as e:
            print(f"❌ California navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill California UCC search form

        Steps:
        1. Find and fill the search input: //input[@placeholder="Search by name or file number"]
        2. Click the advanced search button: //button[contains(@class,"advanced-search-button")]
        3. Wait for results
        """
        try:
            print(f"📝 Filling California UCC search form for: {search_query}")

            # Step 1: Find and fill the search input
            print("   Step 1: Looking for search input field...")
            try:
                search_input = page.locator(
                    '//input[@placeholder="Search by name or file number"]'
                )
                await search_input.wait_for(state="visible", timeout=10000)
                print("   ✓ Found search input field")

                await search_input.fill(search_query)
                await page.wait_for_timeout(1000)
                print(f"   ✓ Entered search query: {search_query}")

            except Exception as e:
                print(f"   ❌ Could not find or fill search input: {str(e)}")
                await self.take_screenshot(page, f"california_input_error.png")
                return False

            # Step 2: Click the advanced search button
            print("   Step 2: Clicking advanced search button...")
            try:
                search_button = page.locator(
                    '//button[contains(@class,"search-button")]'
                )
                await search_button.wait_for(state="visible", timeout=10000)
                print("   ✓ Found advanced search button")

                await search_button.click()
                print("   ✓ Advanced search button clicked")

            except Exception as e:
                print(f"   ❌ Could not find or click search button: {str(e)}")
                await self.take_screenshot(page, f"california_button_error.png")
                return False

            # Step 3: Wait for results to load
            print("   Step 3: Waiting for results...")
            await page.wait_for_timeout(5000)
            print("   ✓ Results loaded")

            # Take screenshot of results
            await self.take_screenshot(page, f"california_search_results.png")

            print("✓ California search form completed successfully")
            return True

        except Exception as e:
            print(f"❌ California form fill error: {str(e)}")
            await self.take_screenshot(page, f"california_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from California's custom table structure

        Table structure:
        - UCC Type | Debtor Information | File Number | Secured Party Info | Status | Filing Date | Lapse Date
        """
        try:
            print("📊 Extracting California UCC search results...")

            # Get page title and URL for reference
            page_title = await page.title()
            page_url = page.url

            print(f"   Page Title: {page_title}")
            print(f"   Page URL: {page_url}")

            # Take screenshot of final results
            await self.take_screenshot(page, f"california_final_results.png")

            # Extract data from California's custom table
            filings = []

            try:
                # Find all rows in the table body using XPath
                print("   Looking for result table rows...")

                # Use XPath to find tbody rows in the div-table
                rows = page.locator('//tbody[@class="div-table-body"]/tr[@class="div-table-row  "]')
                row_count = await rows.count()
                print(f"   Found {row_count} filing rows")

                # Process each row
                for i in range(row_count):
                    try:
                        row = rows.nth(i)

                        # Extract all cell values (columns in order):
                        # 0: UCC Type
                        # 1: Debtor Information
                        # 2: File Number
                        # 3: Secured Party Info
                        # 4: Status
                        # 5: Filing Date
                        # 6: Lapse Date

                        # Get all td cells in the row
                        cells = row.locator('xpath=.//td[@class="div-table-cell  interactive"]')
                        cell_count = await cells.count()

                        if cell_count >= 7:
                            # Extract text from each cell (handles nested spans/divs)
                            filing_record = {
                                "ucc_type": (await cells.nth(0).inner_text()).strip(),
                                "debtor_name": (await cells.nth(1).inner_text()).strip(),
                                "file_number": (await cells.nth(2).inner_text()).strip(),
                                "secured_party": (await cells.nth(3).inner_text()).strip(),
                                "status": (await cells.nth(4).inner_text()).strip(),
                                "filing_date": (await cells.nth(5).inner_text()).strip(),
                                "lapse_date": (await cells.nth(6).inner_text()).strip(),
                            }

                            filings.append(filing_record)
                            print(f"   Row {i + 1}: {filing_record}")
                        else:
                            print(f"   ⚠️  Row {i + 1} has only {cell_count} cells, expected 7")

                    except Exception as row_error:
                        print(f"   ⚠️  Error processing row {i + 1}: {str(row_error)}")
                        continue

                print(f"\n✓ Extracted {len(filings)} filing records")

            except Exception as e:
                print(f"⚠️  Could not extract table data: {str(e)}")
                await self.take_screenshot(page, f"california_extraction_error.png")

            print("✓ California results extraction completed")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "functional",
                "notes": f"Extracted {len(filings)} UCC filing records from California BizFile",
            }
        except Exception as e:
            print(f"❌ California extraction error: {str(e)}")
            return {"filings": [], "total_count": 0, "error": str(e)}
