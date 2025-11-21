"""
Alabama UCC Filing Flow
State-specific implementation for Alabama's UCC filing system

IMPORTANT NOTES:
- Alabama UCC searches require payment: $15.00 per name search + $1.00 per page
- Two search types available:
  1. Simple Search (No Images) - by Debtor Name or Filing Number
  2. Advanced Search (with Images) - includes document images
- Search system: https://www.alabamainteractive.org/ucc_filing/
- Public access requires credit card payment
- Subscriber access requires login (lower fees, ACH billing)

URL: https://www.sos.alabama.gov/business-services/ucc-home
Search Portal: https://www.alabamainteractive.org/ucc_filing/
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class AlabamaFlow(BaseUCCFlow):
    """
    Alabama-specific UCC filing flow

    NOTE: This flow navigates to the search system but cannot complete
    paid searches automatically without payment credentials.
    """

    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to Alabama UCC search system

        Navigation flow:
        1. Start at main UCC page or go directly to alabamainteractive.org
        2. Click "Continue to Filing & Search System" for public access
        3. Navigate to search by name option
        """
        try:
            # Navigate directly to the Alabama Interactive UCC system
            search_url = "https://www.alabamainteractive.org/ucc_filing/"
            print(f"📍 Navigating to Alabama UCC search portal: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Take screenshot of landing page
            await self.take_screenshot(page, "alabama_landing_page.png")

            # Look for the "Continue to Filing & Search System" link
            # This is for public (non-subscriber) access
            try:
                # Try to find and click the continue link
                continue_link = await page.query_selector('a:has-text("Continue to Filing & Search System")')
                if continue_link:
                    print("✓ Found 'Continue to Filing & Search System' link")
                    await continue_link.click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    await page.wait_for_timeout(2000)
                    await self.take_screenshot(page, "alabama_search_system.png")
                else:
                    print("⚠️  Could not find continue link, may already be on search page")
            except Exception as nav_error:
                print(f"⚠️  Navigation click error (may already be on correct page): {str(nav_error)}")

            return True
        except Exception as e:
            print(f"❌ Alabama navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Alabama UCC search form

        LIMITATION: This method can navigate to the search form but cannot
        complete the actual search without payment credentials.

        Steps:
        1. Look for "Search by Name" or similar option
        2. Click to navigate to search form
        3. Identify debtor name input field
        4. Note: Payment required ($15 per search) - cannot proceed without credentials
        """
        try:
            print(f"🔍 Attempting to locate search by name option for: {search_query}")

            # Take screenshot of current page to analyze options
            await self.take_screenshot(page, "alabama_search_options.png")

            # Look for search by name link or button
            search_options = [
                'a:has-text("Search by Name")',
                'a:has-text("Name Search")',
                'button:has-text("Search by Name")',
                'a:has-text("UCC Search")',
                'a:has-text("By Name")',
            ]

            search_link_found = False
            for selector in search_options:
                try:
                    link = await page.query_selector(selector)
                    if link:
                        print(f"✓ Found search option with selector: {selector}")
                        await link.click()
                        await page.wait_for_timeout(2000)
                        await self.take_screenshot(page, "alabama_search_form.png")
                        search_link_found = True
                        break
                except:
                    continue

            if not search_link_found:
                print("⚠️  Could not find 'Search by Name' link")
                print("   Taking screenshot of current page for manual inspection")
                await self.take_screenshot(page, "alabama_no_search_link.png")

            # Try to find debtor name input field (if available)
            input_selectors = [
                'input[name*="debtor"]',
                'input[name*="name"]',
                'input[id*="debtor"]',
                'input[id*="name"]',
                'input[type="text"]',
            ]

            input_found = False
            for selector in input_selectors:
                try:
                    input_field = await page.query_selector(selector)
                    if input_field:
                        print(f"✓ Found input field with selector: {selector}")
                        # Fill the field but don't submit (payment required)
                        await input_field.fill(search_query)
                        print(f"✓ Filled search query: {search_query}")
                        input_found = True
                        await self.take_screenshot(page, "alabama_form_filled.png")
                        break
                except:
                    continue

            if not input_found:
                print("⚠️  Could not find debtor name input field")

            # NOTE: Cannot proceed further without payment credentials
            print("⚠️  PAYMENT REQUIRED: $15.00 per search + $1.00 per page")
            print("   Cannot complete search without payment credentials")
            print("   Form navigation completed to demonstrate flow")

            return True
        except Exception as e:
            print(f"❌ Alabama form fill error: {str(e)}")
            await self.take_screenshot(page, "alabama_form_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Alabama's page

        LIMITATION: Cannot extract actual results without completing paid search.
        This method documents the current page state and expected result structure.

        Expected result fields (based on Alabama UCC system):
        - Filing Number: UCC filing identification number
        - Debtor Name: Name of the debtor/company
        - Filing Date: Date when UCC was filed
        - Status: Active, Lapsed, Terminated, etc.
        - Secured Party: Name of the secured party
        - Expiration Date: When the filing expires (if applicable)
        """
        try:
            print("📊 Attempting to extract results from current page...")

            # Take screenshot of current page state
            await self.take_screenshot(page, "alabama_final_state.png")

            page_title = await page.title()
            page_url = page.url

            print(f"   Current page: {page_title}")
            print(f"   Current URL: {page_url}")

            # Since we can't complete paid search, document what we see
            filings = []

            # Try to detect if we're on a results page (unlikely without payment)
            # Check for common result indicators
            has_results_table = await page.query_selector('table')
            has_results_list = await page.query_selector('ul.results, div.results')

            if has_results_table or has_results_list:
                print("✓ Detected possible results container on page")

                # Attempt to extract using generic selectors
                # This would need to be customized based on actual results page structure
                try:
                    filings = await page.evaluate("""() => {
                        const results = [];
                        // Look for table rows
                        const rows = document.querySelectorAll('table tr');
                        for (let i = 1; i < rows.length; i++) {
                            const cells = rows[i].querySelectorAll('td');
                            if (cells.length > 0) {
                                results.push({
                                    raw_text: rows[i].textContent.trim()
                                });
                            }
                        }
                        return results;
                    }""")
                    print(f"✓ Extracted {len(filings)} potential result rows")
                except Exception as extract_error:
                    print(f"⚠️  Could not extract table data: {str(extract_error)}")
            else:
                print("⚠️  No results container detected (expected - payment required)")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "navigation_only",
                "payment_required": True,
                "search_cost": "$15.00 per search + $1.00 per page",
                "notes": "Cannot complete search without payment credentials. Flow demonstrates navigation to search interface."
            }
        except Exception as e:
            print(f"❌ Alabama extraction error: {str(e)}")
            return {
                "filings": [],
                "total_count": 0,
                "error": str(e),
                "payment_required": True
            }
