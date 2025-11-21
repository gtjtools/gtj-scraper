"""
Oregon UCC Filing Flow
State-specific implementation for Oregon's UCC filing system
URL: https://sos.oregon.gov/business/Pages/ucc.aspx
"""

from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class OregonFlow(BaseUCCFlow):
    """Oregon-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to Oregon UCC search page"""
        try:
            # First go to the home page
            print(f"📍 Navigating to Oregon UCC home page: {self.state_url}")
            await page.goto(
                self.state_url, wait_until="domcontentloaded", timeout=30000
            )
            await page.wait_for_timeout(2000)

            # Then navigate to the actual search page
            search_url = "https://secure.sos.state.or.us/ucc/searchHome.action"
            print(f"📍 Navigating to Oregon UCC search page: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            print("✓ Successfully navigated to Oregon UCC search page")
            return True
        except Exception as e:
            print(f"❌ Oregon navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Oregon UCC search form

        Steps:
        1. Click the Organization debtor type label
        2. Fill in the organization name field
        3. Click the search button
        4. Wait for results
        """
        try:
            print(f"📝 Filling Oregon UCC search form for: {search_query}")

            # Step 1: Click the Organization label
            print("   Step 1: Selecting Organization debtor type...")
            organization_label = page.locator(
                '//input[@id="nonStandardSearchFormID_nonStandardEntityTypeOrganization"]'
            )
            await organization_label.click()
            await page.wait_for_timeout(1000)
            print("   ✓ Organization type selected")

            # Step 2: Fill in the organization name
            print(f"   Step 2: Entering organization name: {search_query}")
            org_name_input = page.locator('//input[@id="orgNameNS"]')
            await org_name_input.fill(search_query)
            await page.wait_for_timeout(1000)
            print("   ✓ Organization name entered")

            # Step 3: Click the search button
            print("   Step 3: Clicking search button...")
            search_button = page.locator('//input[@id="nonStandardSearchFormID_0"]')
            await search_button.click()
            print("   ✓ Search button clicked")

            # Step 4: Wait for results to load
            print("   Step 4: Waiting for results...")
            await page.wait_for_timeout(3000)
            print("   ✓ Results loaded")

            # Take screenshot of results
            await self.take_screenshot(page, f"oregon_search_results.png")

            print("✓ Oregon search form completed successfully")
            return True
        except Exception as e:
            print(f"❌ Oregon form fill error: {str(e)}")
            await self.take_screenshot(page, f"oregon_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Oregon's page
        """
        try:
            print("📊 Extracting Oregon UCC search results...")

            # Get page title and URL for reference
            page_title = await page.title()
            page_url = page.url

            print(f"   Page Title: {page_title}")
            print(f"   Page URL: {page_url}")

            # Take screenshot of final results
            await self.take_screenshot(page, f"oregon_final_results.png")

            # Extract data from the securedTable
            filings = []

            try:
                # Find all rows in the securedTable
                print("   Looking for rows with empty column 6...")
                rows = page.locator('//table[@id="securedTable"]//tr')

                # Get count of rows
                row_count = await rows.count()
                print(f"   Found {row_count} rows in securedTable")

                # Check each row
                for i in range(row_count):
                    row = rows.nth(i)

                    try:
                        # Get the 6th column cell for this row
                        col6_cell = row.locator('xpath=.//td[6]')
                        col6_count = await col6_cell.count()

                        if col6_count > 0:
                            col6_text = await col6_cell.inner_text()
                            col6_text = col6_text.strip()

                            print(f"   Row {i + 1}, Column 6: '{col6_text}'")

                            # Only process rows where column 6 is empty
                            if not col6_text:
                                print(f"   ✓ Found empty row at index {i + 1}, clicking link to get details...")

                                # First, click the link in td[1] to navigate to detail page
                                col1_link = row.locator('xpath=.//td[1]//a')

                                if await col1_link.count() > 0:
                                    # Get link href before clicking
                                    file_url = await col1_link.first.get_attribute('href')
                                    link_text = await col1_link.first.inner_text()

                                    print(f"      Clicking link: {link_text}")
                                    await col1_link.first.click()
                                    await page.wait_for_timeout(2000)  # Wait for detail page to load

                                    print(f"      ✓ Navigated to detail page")
                                    print(f"      Current URL: {page.url}")

                                    # Take screenshot of detail page
                                    await self.take_screenshot(page, f"oregon_filing_detail_{i}.png")

                                    # Now extract data from the detail page's table
                                    print(f"      Extracting data from detail page table...")

                                    # Extract from the table on the detail page
                                    detail_rows = page.locator('//table[@id="securedTable"]/tbody/tr')
                                    detail_row_count = await detail_rows.count()

                                    print(f"      Found {detail_row_count} rows in detail table")

                                    # Extract data from each row in the detail table
                                    for j in range(detail_row_count):
                                        detail_row = detail_rows.nth(j)

                                        # td[1]: file_url (href)
                                        detail_col1 = detail_row.locator('xpath=.//td[1]//a')
                                        detail_file_url = None
                                        if await detail_col1.count() > 0:
                                            detail_file_url = await detail_col1.first.get_attribute('href')

                                        # td[2]: file_number
                                        detail_col2 = detail_row.locator('xpath=.//td[2]')
                                        detail_file_number = await detail_col2.inner_text() if await detail_col2.count() > 0 else ""

                                        # td[3]: filing_date
                                        detail_col3 = detail_row.locator('xpath=.//td[3]')
                                        detail_filing_date = await detail_col3.inner_text() if await detail_col3.count() > 0 else ""

                                        # td[4]: documents
                                        detail_col4 = detail_row.locator('xpath=.//td[4]')
                                        detail_documents = await detail_col4.inner_text() if await detail_col4.count() > 0 else ""

                                        # td[5]: lapse_date
                                        detail_col5 = detail_row.locator('xpath=.//td[5]')
                                        detail_lapse_date = await detail_col5.inner_text() if await detail_col5.count() > 0 else ""

                                        filing_record = {
                                            "file_url": detail_file_url or file_url,
                                            "file_number": detail_file_number.strip(),
                                            "filing_date": detail_filing_date.strip(),
                                            "documents": detail_documents.strip(),
                                            "lapse_date": detail_lapse_date.strip(),
                                            "detail_page_url": page.url
                                        }

                                        filings.append(filing_record)

                                        print(f"      Row {j + 1}: {filing_record}")

                                    # Navigate back to the search results page
                                    await page.go_back()
                                    await page.wait_for_timeout(1000)
                                    print(f"      ✓ Navigated back to search results")

                                else:
                                    print(f"      ⚠️  No link found in td[1]")

                    except Exception as row_error:
                        print(f"   ⚠️  Error processing row {i + 1}: {str(row_error)}")
                        continue

                print(f"\n✓ Extracted {len(filings)} filing records from empty rows")

            except Exception as e:
                print(f"⚠️  Could not extract table data: {str(e)}")

            print("✓ Oregon results extraction completed")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "data_extracted",
                "notes": f"Extracted {len(filings)} UCC filing records from securedTable",
            }
        except Exception as e:
            print(f"❌ Oregon extraction error: {str(e)}")
            return {"filings": [], "total_count": 0, "error": str(e)}
