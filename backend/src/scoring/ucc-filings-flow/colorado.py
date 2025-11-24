"""
Colorado UCC Filing Flow
State-specific implementation for Colorado's UCC filing system

IMPORTANT NOTES:
- Colorado offers FREE debtor lien searches
- Three search options available:
  1. Debtor Name Search - search by debtor's name
  2. Advanced Search - by secured party and other criteria
  3. Master List Search - comprehensive search
- Online filing requires account login
- Public searches are FREE and do not require login
- Certified searches require a UCC Account

URL: http://www.sos.state.co.us/pubs/UCC/uccHome.html
Search Portal: https://www.sos.state.co.us/ucc/pages/search/standardSearch.xhtml
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class ColoradoFlow(BaseUCCFlow):
    """
    Colorado-specific UCC filing flow

    NOTE: This flow can perform free debtor name searches on Colorado's public database
    """

    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to Colorado UCC search portal

        Navigation flow:
        1. Navigate directly to standard search page
        2. This is the free public debtor name search
        3. No login required for basic searches
        """
        try:
            # Navigate directly to Colorado standard search
            search_url = "https://www.sos.state.co.us/ucc/pages/search/standardSearch.xhtml"
            print(f"📍 Navigating to Colorado UCC search portal: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Take screenshot of search page
            await self.take_screenshot(page, "colorado_search_page.png")

            print("✓ Reached Colorado UCC standard search portal")
            return True
        except Exception as e:
            print(f"❌ Colorado navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Colorado UCC search form

        Colorado standard search:
        - Search by Debtor Name (organization or individual)
        - Uses standard search logic
        - Free for public access

        Common field patterns in Colorado:
        - Organization name fields
        - Individual name fields (last, first, middle)
        """
        try:
            print(f"🔍 Searching for debtor: {search_query}")

            # Take screenshot before filling
            await self.take_screenshot(page, "colorado_form_before.png")

            # Colorado typically has separate fields for organization vs individual
            # Try to find organization name field first
            org_selectors = [
                'input[name*="organization"]',
                'input[name*="Organization"]',
                'input[id*="organization"]',
                'input[id*="orgName"]',
                'input[placeholder*="Organization"]',
            ]

            org_found = False
            for selector in org_selectors:
                try:
                    org_field = await page.query_selector(selector)
                    if org_field:
                        is_visible = await org_field.is_visible()
                        if is_visible:
                            print(f"✓ Found organization name input: {selector}")
                            await org_field.fill(search_query)
                            print(f"✓ Filled organization name: {search_query}")
                            org_found = True
                            await page.wait_for_timeout(1000)
                            break
                except:
                    continue

            # If organization field not found, try general name/debtor fields
            if not org_found:
                general_selectors = [
                    'input[name*="debtor"]',
                    'input[name*="name"]',
                    'input[id*="debtor"]',
                    'input[placeholder*="Name"]',
                    'input[type="text"]',
                ]

                for selector in general_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field:
                            is_visible = await field.is_visible()
                            if is_visible:
                                print(f"✓ Found name input: {selector}")
                                await field.fill(search_query)
                                print(f"✓ Filled search query: {search_query}")
                                org_found = True
                                await page.wait_for_timeout(1000)
                                break
                    except:
                        continue

            if not org_found:
                print("⚠️  Could not find name input field")

            # Take screenshot after filling
            await self.take_screenshot(page, "colorado_form_filled.png")

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
            await self.take_screenshot(page, "colorado_after_submit.png")

            return True
        except Exception as e:
            print(f"❌ Colorado form fill error: {str(e)}")
            await self.take_screenshot(page, "colorado_form_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Colorado's search results

        Expected Colorado result fields:
        - Filing Number: UCC-1 filing number
        - Debtor Name: Organization or individual name
        - Filing Date: Date of filing
        - Status: Active, Lapsed, etc.
        - Secured Party: Creditor name
        - Lapse Date: When filing expires
        """
        try:
            print("📊 Extracting results from Colorado search...")

            # Take screenshot of results page
            await self.take_screenshot(page, "colorado_results_page.png")

            page_title = await page.title()
            page_url = page.url

            print(f"   Current page: {page_title}")
            print(f"   Current URL: {page_url}")

            filings = []

            # Check for results table
            has_table = await page.query_selector('table')
            has_results_div = await page.query_selector('div.results, div[class*="result"]')

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
                       bodyText.includes('no filings found');
            }""")

            if no_results_text:
                print("ℹ️  No UCC filings found for this search")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "functional",
                "search_cost": "Free",
                "notes": "Free debtor lien searches available. Certified searches require UCC Account."
            }
        except Exception as e:
            print(f"❌ Colorado extraction error: {str(e)}")
            return {
                "filings": [],
                "total_count": 0,
                "error": str(e)
            }
