"""
Iowa UCC Filing Flow
State-specific implementation for Iowa's UCC filing system

IMPORTANT NOTES:
- Iowa offers FREE certified lien searches
- No payment required
- Search by Person, Business, or Filing Number
- Can print certified lien search reports for free
- Option to include lapsed liens (within past year)
- Publicly accessible

URL: http://sos.iowa.gov/business/UCCInfo.html
Search Portal: https://filings.sos.iowa.gov/UCCSearch/UCC
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class IowaFlow(BaseUCCFlow):
    """Iowa-specific UCC filing flow - FREE certified searches"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to Iowa UCC search portal"""
        try:
            # Navigate directly to the search portal
            search_url = "https://filings.sos.iowa.gov/UCCSearch/UCC"
            print(f"📍 Navigating to Iowa UCC search portal: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await self.take_screenshot(page, "iowa_search_page.png")
            print("✓ Reached Iowa UCC search portal")
            return True
        except Exception as e:
            print(f"❌ Iowa navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Iowa UCC search form

        TODO: Implement specific selectors for Iowa's UCC search form
        This is a template - needs to be customized based on Iowa's actual form
        """
        try:
            # Example selectors - NEEDS TO BE CUSTOMIZED
            # Uncomment and modify based on actual Iowa page structure

            # await page.fill('input[name="debtor_name"]', search_query)
            # await page.click('button[type="submit"]')
            # await page.wait_for_load_state('networkidle')

            print("⚠️  Iowa search form filling not yet implemented")
            print("   Please inspect the page and add proper selectors")

            # Take screenshot to help with implementation
            await self.take_screenshot(page, f"iowa_search_form.png")

            return True
        except Exception as e:
            print(f"❌ Iowa form fill error: {{str(e)}}")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Iowa's page

        TODO: Implement specific extraction logic for Iowa
        This is a template - needs to be customized based on Iowa's actual results
        """
        try:
            # Example extraction - NEEDS TO BE CUSTOMIZED
            filings = []

            # Uncomment and modify based on actual Iowa page structure
            # filings = await page.evaluate("""() => {{
            #     const rows = document.querySelectorAll('.results-table tr');
            #     return Array.from(rows).map(row => ({{
            #         filing_number: row.querySelector('.filing-number')?.textContent,
            #         debtor_name: row.querySelector('.debtor-name')?.textContent,
            #         filing_date: row.querySelector('.filing-date')?.textContent,
            #         status: row.querySelector('.status')?.textContent
            #     }}));
            # }}""")

            print("⚠️  Iowa results extraction not yet implemented")
            print("   Please inspect the page and add proper extraction logic")

            # Take screenshot to help with implementation
            await self.take_screenshot(page, f"iowa_results.png")

            return {{
                "filings": filings,
                "total_count": len(filings),
                "page_title": await page.title(),
                "implementation_status": "template_only"
            }}
        except Exception as e:
            print(f"❌ Iowa extraction error: {{str(e)}}")
            return {{
                "filings": [],
                "total_count": 0,
                "error": str(e)
            }}
