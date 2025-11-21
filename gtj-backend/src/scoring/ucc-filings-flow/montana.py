"""
Montana UCC Filing Flow
State-specific implementation for Montana's UCC filing system
URL: https://sosmt.gov/business/ucc/
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class MontanaFlow(BaseUCCFlow):
    """Montana-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to Montana UCC search page"""
        try:
            await page.goto(self.state_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            print(f"❌ Montana navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Montana UCC search form

        TODO: Implement specific selectors for Montana's UCC search form
        This is a template - needs to be customized based on Montana's actual form
        """
        try:
            # Example selectors - NEEDS TO BE CUSTOMIZED
            # Uncomment and modify based on actual Montana page structure

            # await page.fill('input[name="debtor_name"]', search_query)
            # await page.click('button[type="submit"]')
            # await page.wait_for_load_state('networkidle')

            print("⚠️  Montana search form filling not yet implemented")
            print("   Please inspect the page and add proper selectors")

            # Take screenshot to help with implementation
            await self.take_screenshot(page, f"montana_search_form.png")

            return True
        except Exception as e:
            print(f"❌ Montana form fill error: {str(e)}")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Montana's page

        TODO: Implement specific extraction logic for Montana
        This is a template - needs to be customized based on Montana's actual results
        """
        try:
            # Example extraction - NEEDS TO BE CUSTOMIZED
            filings = []

            # Uncomment and modify based on actual Montana page structure
            # filings = await page.evaluate("""() => {
            #     const rows = document.querySelectorAll('.results-table tr');
            #     return Array.from(rows).map(row => ({
            #         filing_number: row.querySelector('.filing-number')?.textContent,
            #         debtor_name: row.querySelector('.debtor-name')?.textContent,
            #         filing_date: row.querySelector('.filing-date')?.textContent,
            #         status: row.querySelector('.status')?.textContent
            #     }));
            # }""")

            print("⚠️  Montana results extraction not yet implemented")
            print("   Please inspect the page and add proper extraction logic")

            # Take screenshot to help with implementation
            await self.take_screenshot(page, f"montana_results.png")

            return {
                "filings": filings,
                "total_count": len(filings),
                "page_title": await page.title(),
                "implementation_status": "template_only"
            }
        except Exception as e:
            print(f"❌ Montana extraction error: {str(e)}")
            return {
                "filings": [],
                "total_count": 0,
                "error": str(e)
            }
