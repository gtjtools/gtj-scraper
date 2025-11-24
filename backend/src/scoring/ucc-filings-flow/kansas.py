"""
Kansas UCC Filing Flow
State-specific implementation for Kansas's UCC filing system

IMPORTANT NOTES:
- Kansas UCC searches REQUIRE PAID SUBSCRIPTION
- Online UCCII searches: $10 per search + $1 per page for images
- Paper UCCII searches: $20 per search + $1 per page
- Subscription account required for online access
- NO FREE PUBLIC SEARCH available
- All electronic access requires account login

URL: https://sos.ks.gov/general-services/ucc-filing-information.html
Search Portal: https://mykansas.ks.gov/ucc/
Login Required: https://mykansas.ks.gov/ucc/secure/?p=user_login
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class KansasFlow(BaseUCCFlow):
    """
    Kansas-specific UCC filing flow

    NOTE: This flow CANNOT complete searches without paid subscription credentials.
    Kansas does not offer free public UCC searches.
    """

    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to Kansas UCC system

        Navigation flow:
        1. Navigate to main UCC portal
        2. Show login requirement
        3. Document that subscription is required
        """
        try:
            # Navigate to the main Kansas UCC portal
            search_url = "https://mykansas.ks.gov/ucc/"
            print(f"📍 Navigating to Kansas UCC portal: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Take screenshot of portal page
            await self.take_screenshot(page, "kansas_ucc_portal.png")

            print("✓ Reached Kansas UCC portal")
            print("⚠️  Kansas requires paid subscription for searches")

            # Try to navigate to search menu to show what's available
            try:
                search_menu_url = "https://mykansas.ks.gov/ucc/?p=fsrc_menu"
                await page.goto(search_menu_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                await self.take_screenshot(page, "kansas_search_menu.png")
                print("✓ Navigated to search menu (login required to proceed)")
            except Exception as menu_error:
                print(f"⚠️  Could not access search menu: {str(menu_error)}")

            return True
        except Exception as e:
            print(f"❌ Kansas navigation error: {str(e)}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill Kansas UCC search form

        LIMITATION: Cannot complete search without subscription credentials.

        Kansas requires:
        - Active subscription account
        - User login credentials
        - Payment ($10 per search + $1 per page)
        """
        try:
            print(f"🔍 Attempting to access search for: {search_query}")
            print("⚠️  SUBSCRIPTION REQUIRED: $10 per search + $1 per page")
            print("   Cannot proceed without login credentials")

            # Take screenshot of current page
            await self.take_screenshot(page, "kansas_subscription_required.png")

            # Check if login page is displayed
            login_indicators = await page.evaluate("""() => {
                const bodyText = document.body.textContent.toLowerCase();
                return {
                    hasLogin: bodyText.includes('login') || bodyText.includes('sign in'),
                    hasSubscription: bodyText.includes('subscription') || bodyText.includes('account'),
                    pageUrl: window.location.href
                };
            }""")

            if login_indicators.get('hasLogin'):
                print("ℹ️  Login page detected - subscription credentials required")

            print("📋 Kansas UCC Search Requirements:")
            print("   - Subscription account needed")
            print("   - Online: $10/search + $1/page")
            print("   - Paper: $20/search + $1/page")
            print("   - Contact: (785) 296-4564")

            return True
        except Exception as e:
            print(f"❌ Kansas form access error: {str(e)}")
            await self.take_screenshot(page, "kansas_access_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from Kansas's page

        LIMITATION: Cannot extract results without completing paid search.

        Expected Kansas result fields (if accessible):
        - Filing Number: UCC filing ID
        - Debtor Name: Organization or individual
        - Filing Date: Date of filing
        - Status: Active, Lapsed, etc.
        - Secured Party: Creditor information
        """
        try:
            print("📊 Documenting Kansas search page state...")

            # Take screenshot of current state
            await self.take_screenshot(page, "kansas_final_state.png")

            page_title = await page.title()
            page_url = page.url

            print(f"   Current page: {page_title}")
            print(f"   Current URL: {page_url}")

            return {
                "filings": [],
                "total_count": 0,
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "subscription_required",
                "payment_required": True,
                "search_cost": "$10 per search + $1 per page (online)",
                "subscription_info": {
                    "required": True,
                    "online_cost": "$10/search + $1/page",
                    "paper_cost": "$20/search + $1/page"
                },
                "notes": "Kansas requires paid subscription for all UCC searches. No free public access available."
            }
        except Exception as e:
            print(f"❌ Kansas page documentation error: {str(e)}")
            return {
                "filings": [],
                "total_count": 0,
                "error": str(e),
                "payment_required": True
            }
