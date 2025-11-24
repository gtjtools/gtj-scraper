"""
Kentucky UCC Filing Flow
State-specific implementation for Kentucky's UCC filing system

IMPORTANT NOTES:
- Kentucky offers online UCC search capability
- Search cost information not publicly disclosed
- Fast Track UCC search system available
- Prepaid accounts available for frequent users
- Bulk data subscription service available
- Contact: (502) 564-3490 for pricing information

URL: http://www.sos.ky.gov/bus/UCC/Pages/default.aspx
Search Portal: https://web.sos.ky.gov/ftucc/search.aspx
Office Hours: Monday-Friday, 8:00 AM - 4:30 PM ET
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class KentuckyFlow(BaseUCCFlow):
    """
    Kentucky-specific UCC filing flow

    NOTE: Pricing not publicly disclosed. This flow attempts to access
    the search portal to determine requirements.
    """

    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to Kentucky Fast Track UCC search portal

        Navigation flow:
        1. Navigate directly to Fast Track search page
        2. Assess if login/payment is required
        3. Attempt to access search form
        """
        try:
            # Navigate directly to Kentucky Fast Track UCC search
            search_url = "https://web.sos.ky.gov/ftucc/search.aspx"
            print(f"📍 Navigating to Kentucky UCC search portal: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Take screenshot of search page
            await self.take_screenshot(page, "kentucky_search_page.png")

            print("✓ Reached Kentucky Fast Track UCC search portal")
            print("ℹ️  Search cost not publicly disclosed - contact (502) 564-3490")

            return True
        except Exception as e:
            print(f"❌ Kentucky navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Kentucky UCC search form

        Kentucky Fast Track search:
        - Search by debtor name
        - Pricing not publicly disclosed
        - May require prepaid account

        This implementation attempts to find and fill search fields
        """
        try:
            print(f"🔍 Searching for debtor: {search_query}")

            # Take screenshot before filling
            await self.take_screenshot(page, "kentucky_form_before.png")

            # Look for debtor name search input field
            input_selectors = [
                'input[name*="debtor"]',
                'input[name*="Debtor"]',
                'input[name*="name"]',
                'input[name*="Name"]',
                'input[id*="debtor"]',
                'input[id*="name"]',
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
                        is_visible = await input_field.is_visible()
                        if is_visible:
                            print(f"✓ Found name input: {selector}")
                            await input_field.fill(search_query)
                            print(f"✓ Filled search query: {search_query}")
                            input_found = True
                            await page.wait_for_timeout(1000)
                            break
                except:
                    continue

            if not input_found:
                print("⚠️  Could not find debtor name input field")

            # Take screenshot after filling
            await self.take_screenshot(page, "kentucky_form_filled.png")

            # Look for search/submit button
            button_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Search")',
                'button:has-text("Submit")',
                'input[value="Search"]',
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
            await self.take_screenshot(page, "kentucky_after_submit.png")

            # Check if payment or login is required
            payment_indicators = await page.evaluate("""() => {
                const bodyText = document.body.textContent.toLowerCase();
                return {
                    hasPayment: bodyText.includes('payment') || bodyText.includes('fee') || bodyText.includes('cost'),
                    hasLogin: bodyText.includes('login') || bodyText.includes('sign in'),
                    hasAccount: bodyText.includes('prepaid account') || bodyText.includes('subscription')
                };
            }""")

            if payment_indicators.get('hasPayment') or payment_indicators.get('hasAccount'):
                print("ℹ️  Payment or account may be required")

            return True
        except Exception as e:
            print(f"❌ Kentucky form fill error: {str(e)}")
            await self.take_screenshot(page, "kentucky_form_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Kentucky's search results

        Expected Kentucky result fields:
        - Filing Number: UCC filing ID
        - Debtor Name: Organization or individual
        - Filing Date: Date of filing
        - Status: Active, Lapsed, etc.
        - Secured Party: Creditor information
        """
        try:
            print("📊 Extracting results from Kentucky search...")

            # Take screenshot of results page
            await self.take_screenshot(page, "kentucky_results_page.png")

            page_title = await page.title()
            page_url = page.url

            print(f"   Current page: {page_title}")
            print(f"   Current URL: {page_url}")

            filings = []

            # Check for results table or grid
            has_table = await page.query_selector('table')
            has_grid = await page.query_selector('div.grid, div[class*="result"]')

            if has_table or has_grid:
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

                                    // Only add if it has content
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
                "search_cost": "Contact (502) 564-3490 for pricing",
                "notes": "Fast Track UCC search system. Pricing not publicly disclosed. Prepaid accounts available."
            }
        except Exception as e:
            print(f"❌ Kentucky extraction error: {str(e)}")
            return {
                "filings": [],
                "total_count": 0,
                "error": str(e)
            }
