"""
Idaho UCC Filing Flow
State-specific implementation for Idaho's UCC filing system

IMPORTANT NOTES:
- Idaho offers FREE basic UCC searches (non-certified)
- $3 fee for non-certified searches if not logged in to exempt account
- Certified searches require additional fees
- Search types available:
  1. Basic Search (free) - provides filing number, debtor, and status
  2. Premium Search - more detailed information
- Publicly accessible without login for basic searches

URL: https://sos.idaho.gov/uniform-commercial-code/
Search Portal: https://sosbiz.idaho.gov/search/ucc
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class IdahoFlow(BaseUCCFlow):
    """
    Idaho-specific UCC filing flow

    NOTE: This flow can perform free basic searches on Idaho's public database
    """

    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to Idaho UCC search portal

        Navigation flow:
        1. Navigate directly to sosbiz.idaho.gov/search/ucc
        2. This is the public search interface
        3. No login required for basic searches
        """
        try:
            # Navigate directly to the Idaho UCC search portal
            search_url = "https://sosbiz.idaho.gov/search/ucc"
            print(f"📍 Navigating to Idaho UCC search portal: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Take screenshot of search page
            await self.take_screenshot(page, "idaho_search_page.png")

            print("✓ Reached Idaho UCC search portal")
            return True
        except Exception as e:
            print(f"❌ Idaho navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Idaho UCC search form

        Idaho search options:
        - Search by Debtor Name (individual or organization)
        - Search by Filing Number
        - Search by Secured Party Name

        This implementation focuses on debtor name search
        """
        try:
            print(f"🔍 Searching for debtor: {search_query}")

            # Take screenshot of form before filling
            await self.take_screenshot(page, "idaho_form_before.png")

            # Look for debtor name search input field
            # Common selectors for Idaho's search interface
            input_selectors = [
                'input[name*="debtor"]',
                'input[name*="DebtorName"]',
                'input[id*="debtor"]',
                'input[placeholder*="Debtor"]',
                'input[placeholder*="Name"]',
                'input[type="text"]',
                'input[type="search"]',
            ]

            input_found = False
            for selector in input_selectors:
                try:
                    input_field = await page.query_selector(selector)
                    if input_field:
                        # Check if field is visible
                        is_visible = await input_field.is_visible()
                        if is_visible:
                            print(f"✓ Found debtor name input: {selector}")
                            await input_field.fill(search_query)
                            print(f"✓ Filled search query: {search_query}")
                            input_found = True
                            await page.wait_for_timeout(1000)
                            break
                except:
                    continue

            if not input_found:
                print("⚠️  Could not find debtor name input field")
                print("   Trying to locate search elements on page...")

            # Take screenshot after filling
            await self.take_screenshot(page, "idaho_form_filled.png")

            # Look for search/submit button
            button_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Search")',
                'button:has-text("Submit")',
                'a:has-text("Search")',
            ]

            button_found = False
            for selector in button_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        is_visible = await button.is_visible()
                        if is_visible:
                            print(f"✓ Found search button: {selector}")
                            await button.click()
                            print("✓ Clicked search button")
                            button_found = True
                            await page.wait_for_load_state('networkidle', timeout=15000)
                            await page.wait_for_timeout(2000)
                            break
                except:
                    continue

            if not button_found:
                print("⚠️  Could not find search button")

            # Take screenshot after submission
            await self.take_screenshot(page, "idaho_after_submit.png")

            return True
        except Exception as e:
            print(f"❌ Idaho form fill error: {str(e)}")
            await self.take_screenshot(page, "idaho_form_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Idaho's search results page

        Expected Idaho result fields:
        - Filing Number: UCC filing ID
        - Debtor Name: Individual or organization name
        - Filing Date: When the UCC was filed
        - Status: Active, Lapsed, Terminated
        - Secured Party: Creditor information
        - Expiration Date: When filing expires
        """
        try:
            print("📊 Extracting results from Idaho search...")

            # Take screenshot of results page
            await self.take_screenshot(page, "idaho_results_page.png")

            page_title = await page.title()
            page_url = page.url

            print(f"   Current page: {page_title}")
            print(f"   Current URL: {page_url}")

            filings = []

            # Try to detect results table or list
            has_table = await page.query_selector('table')
            has_results_div = await page.query_selector('div.results, div.search-results, div[class*="result"]')

            if has_table or has_results_div:
                print("✓ Detected results container")

                try:
                    # Extract table data
                    filings = await page.evaluate("""() => {
                        const results = [];
                        const tables = document.querySelectorAll('table');

                        for (const table of tables) {
                            const rows = table.querySelectorAll('tr');

                            // Skip header row
                            for (let i = 1; i < rows.length; i++) {
                                const cells = rows[i].querySelectorAll('td, th');
                                if (cells.length > 0) {
                                    const rowData = {
                                        filing_number: cells[0]?.textContent?.trim() || '',
                                        debtor_name: cells[1]?.textContent?.trim() || '',
                                        filing_date: cells[2]?.textContent?.trim() || '',
                                        status: cells[3]?.textContent?.trim() || '',
                                        raw_text: rows[i].textContent.trim()
                                    };

                                    // Only add if it has some content
                                    if (rowData.filing_number || rowData.debtor_name) {
                                        results.push(rowData);
                                    }
                                }
                            }
                        }

                        return results;
                    }""")

                    print(f"✓ Extracted {len(filings)} filing records")

                except Exception as extract_error:
                    print(f"⚠️  Table extraction error: {str(extract_error)}")
            else:
                print("⚠️  No results table detected")

            # Check for "no results" message
            no_results_text = await page.evaluate("""() => {
                const bodyText = document.body.textContent.toLowerCase();
                return bodyText.includes('no results') ||
                       bodyText.includes('no records') ||
                       bodyText.includes('0 results');
            }""")

            if no_results_text:
                print("ℹ️  No UCC filings found for this search")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "functional",
                "search_cost": "Free (basic search)",
                "notes": "Free basic search available. $3 fee for non-certified searches if not logged in."
            }
        except Exception as e:
            print(f"❌ Idaho extraction error: {str(e)}")
            return {
                "filings": [],
                "total_count": 0,
                "error": str(e)
            }
