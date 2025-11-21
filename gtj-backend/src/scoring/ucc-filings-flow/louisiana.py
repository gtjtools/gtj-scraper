"""
Louisiana UCC Filing Flow
State-specific implementation for Louisiana's UCC filing system

IMPORTANT NOTES:
- Louisiana UCC searches REQUIRE PAYMENT
- Per-search fee: $30 per debtor name
- Annual subscription: $400 for unlimited searches
- Requires registration and login
- Louisiana was the last state to adopt UCC (1990)
- Can file with any of 64 parish filing offices
- Contact: 225-925-4701 for more information

URL: http://www.sos.la.gov/BusinessServices/UniformCommercialCode/Pages/default.aspx
Search Info: https://www.sos.la.gov/businessservices/uniformcommercialcode/HowToSearchForFinancingStatements/Pages/default.aspx
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class LouisianaFlow(BaseUCCFlow):
    """
    Louisiana-specific UCC filing flow

    NOTE: This flow CANNOT complete searches without payment credentials.
    Louisiana charges $30 per search or offers $400 annual subscriptions.
    """

    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to Louisiana UCC information page

        Navigation flow:
        1. Navigate to main UCC page
        2. Look for search information
        3. Document payment requirements
        """
        try:
            # Navigate to Louisiana UCC main page
            search_url = "https://www.sos.la.gov/businessservices/uniformcommercialcode/HowToSearchForFinancingStatements/Pages/default.aspx"
            print(f"📍 Navigating to Louisiana UCC search info: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Take screenshot of info page
            await self.take_screenshot(page, "louisiana_search_info.png")

            print("✓ Reached Louisiana UCC search information page")
            print("⚠️  Louisiana requires payment for searches")
            print("   $30 per search OR $400 annual subscription")

            return True
        except Exception as e:
            print(f"❌ Louisiana navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Louisiana UCC search form

        LIMITATION: Cannot complete search without payment credentials.

        Louisiana requires:
        - Registration for search access
        - Payment: $30 per search OR $400 annual subscription
        - User ID and password for login
        """
        try:
            print(f"🔍 Attempting to access search for: {search_query}")
            print("⚠️  PAYMENT REQUIRED:")
            print("   Option 1: $30 per debtor name search")
            print("   Option 2: $400 annual subscription (unlimited)")
            print("   Cannot proceed without payment credentials and login")

            # Take screenshot of current page
            await self.take_screenshot(page, "louisiana_payment_required.png")

            # Check if we can find search or login links
            search_links = await page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a'));
                return links
                    .filter(link => {
                        const text = link.textContent.toLowerCase();
                        return text.includes('search') ||
                               text.includes('login') ||
                               text.includes('register');
                    })
                    .map(link => ({
                        text: link.textContent.trim(),
                        href: link.href
                    }));
            }""")

            if search_links:
                print("ℹ️  Found related links on page:")
                for link in search_links[:5]:  # Show first 5 links
                    print(f"   - {link.get('text')}: {link.get('href')}")

            print("\n📋 Louisiana UCC Search Requirements:")
            print("   - Registration required")
            print("   - Payment: $30/search or $400/year")
            print("   - Contact: 225-925-4701")
            print("   - 64 parish filing offices available")

            return True
        except Exception as e:
            print(f"❌ Louisiana form access error: {str(e)}")
            await self.take_screenshot(page, "louisiana_access_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Louisiana's page

        LIMITATION: Cannot extract results without completing paid search.

        Expected Louisiana result fields (if accessible):
        - Filing Number: UCC filing ID
        - Debtor Name: Organization or individual
        - Filing Date: Date filed
        - Status: Active, Lapsed, Terminated
        - Secured Party: Creditor information
        - Parish: Filing location (Louisiana uses parishes instead of counties)
        """
        try:
            print("📊 Documenting Louisiana search page state...")

            # Take screenshot of current state
            await self.take_screenshot(page, "louisiana_final_state.png")

            page_title = await page.title()
            page_url = page.url

            print(f"   Current page: {page_title}")
            print(f"   Current URL: {page_url}")

            return {
                "filings": [],
                "total_count": 0,
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "payment_required",
                "payment_required": True,
                "search_cost": "$30 per search or $400 annual subscription",
                "subscription_info": {
                    "required": True,
                    "per_search_cost": "$30 per debtor name",
                    "annual_subscription": "$400 (unlimited searches)",
                    "contact": "225-925-4701"
                },
                "notes": "Louisiana requires payment for UCC searches. Choose per-search fee ($30) or annual subscription ($400). Louisiana was the last state to adopt UCC in 1990."
            }
        except Exception as e:
            print(f"❌ Louisiana page documentation error: {str(e)}")
            return {
                "filings": [],
                "total_count": 0,
                "error": str(e),
                "payment_required": True
            }
