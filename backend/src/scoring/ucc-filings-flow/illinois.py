"""
Illinois UCC Filing Flow
State-specific implementation for Illinois's UCC filing system
URL: https://apps.ilsos.gov/uccsearch/
"""

from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class IllinoisFlow(BaseUCCFlow):
    """Illinois-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to Illinois UCC search page"""
        try:
            url = "https://apps.ilsos.gov/uccsearch/"
            print(f"📍 Navigating to Illinois UCC page: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            print("✓ Successfully navigated to Illinois UCC page")
            return True
        except Exception as e:
            print(f"❌ Illinois navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Illinois UCC search form

        Steps:
        1. Click searchType radio button with value="U"
        2. Click uccSearch radio button with value="B" (appears after step 1)
        3. Click raType radio button with value="R" (appears after step 2)
        4. Fill organization name in orgName input
        5. Click submit button
        6. Wait for results to discover
        """
        try:
            print(f"📝 Filling Illinois UCC search form for: {search_query}")

            # Step 1: Click searchType radio button with value="U"
            print("   Step 1: Clicking searchType radio button (U)...")
            search_type_xpath = '//input[@id="searchType" and @value="U"]'
            await page.wait_for_selector(f'xpath={search_type_xpath}', timeout=10000)
            await page.click(f'xpath={search_type_xpath}')
            await page.wait_for_timeout(1000)
            print("   ✓ SearchType (U) clicked")

            # Step 2: Click uccSearch radio button with value="B"
            print("   Step 2: Clicking uccSearch radio button (B)...")
            ucc_search_xpath = '//input[@id="uccSearch" and @value="B"]'
            await page.wait_for_selector(f'xpath={ucc_search_xpath}', timeout=10000)
            await page.click(f'xpath={ucc_search_xpath}')
            await page.wait_for_timeout(1000)
            print("   ✓ UccSearch (B) clicked")

            # Step 3: Click raType radio button with value="R"
            print("   Step 3: Clicking raType radio button (R)...")
            ra_type_xpath = '//input[@id="raType" and @value="R"]'
            await page.wait_for_selector(f'xpath={ra_type_xpath}', timeout=10000)
            await page.click(f'xpath={ra_type_xpath}')
            await page.wait_for_timeout(1000)
            print("   ✓ RaType (R) clicked")

            # Step 4: Fill organization name in orgName input
            print("   Step 4: Filling organization name...")
            org_name_xpath = '//input[@id="orgName"]'
            await page.wait_for_selector(f'xpath={org_name_xpath}', timeout=10000)
            await page.fill(f'xpath={org_name_xpath}', search_query)
            await page.wait_for_timeout(1000)
            print(f"   ✓ Organization name entered: {search_query}")

            # Step 5: Click submit button
            print("   Step 5: Clicking submit button...")
            submit_button_xpath = '//input[@name="submitIt"]'
            await page.wait_for_selector(f'xpath={submit_button_xpath}', timeout=10000)
            await page.click(f'xpath={submit_button_xpath}')
            print("   ✓ Submit button clicked")

            # Step 6: Wait for results to discover
            print("   Step 6: Waiting for results to discover...")
            try:
                # Wait for any element containing "discover" or wait for page to load
                await page.wait_for_timeout(3000)
                print("   ✓ Results loaded")
            except Exception as e:
                print(f"   ⚠️  Timeout waiting for discover, but continuing: {str(e)}")

            # Take screenshot of results
            await self.take_screenshot(page, f"illinois_search_results.png")

            print("✓ Illinois search form completed successfully")
            return True
        except Exception as e:
            print(f"❌ Illinois form fill error: {str(e)}")
            await self.take_screenshot(page, f"illinois_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Illinois's page
        """
        try:
            print("📊 Extracting Illinois UCC search results...")

            # Get page title and URL for reference
            page_title = await page.title()
            page_url = page.url

            print(f"   Page Title: {page_title}")
            print(f"   Page URL: {page_url}")

            # Take screenshot of final results
            await self.take_screenshot(page, f"illinois_final_results.png")

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

            print("✓ Illinois results extraction completed")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "functional",
                "notes": f"Extracted {len(filings)} UCC filing records",
            }
        except Exception as e:
            print(f"❌ Illinois extraction error: {str(e)}")
            return {"filings": [], "total_count": 0, "error": str(e)}
