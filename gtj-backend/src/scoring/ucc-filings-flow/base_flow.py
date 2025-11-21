"""
Base UCC Flow Class
All state-specific UCC flows should inherit from this class
"""
from typing import Dict, Any, Optional
from playwright.async_api import Page
from abc import ABC, abstractmethod


class BaseUCCFlow(ABC):
    """Base class for state-specific UCC filing flows"""

    def __init__(self, state_name: str, state_url: str):
        self.state_name = state_name
        self.state_url = state_url

    @abstractmethod
    async def navigate_to_search(self, page: Page) -> bool:
        """
        Navigate to the UCC search page

        Args:
            page: Playwright page object

        Returns:
            bool: True if navigation successful, False otherwise
        """
        pass

    @abstractmethod
    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill out the search form with the query

        Args:
            page: Playwright page object
            search_query: The search term (e.g., company name)

        Returns:
            bool: True if form filled successfully, False otherwise
        """
        pass

    @abstractmethod
    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from the page

        Args:
            page: Playwright page object

        Returns:
            Dict containing extracted UCC filing data
        """
        pass

    async def run_flow(self, page: Page, operator_name: str) -> Dict[str, Any]:
        """
        Run the complete UCC filing flow for this state

        Args:
            page: Playwright page object
            operator_name: Name of the operator to search for

        Returns:
            Dict containing flow results
        """
        try:
            print(f"\n{'=' * 60}")
            print(f"Running UCC Flow for {self.state_name}")
            print(f"{'=' * 60}")

            # Step 1: Navigate to search page
            print(f"📍 Navigating to {self.state_name} UCC search...")
            nav_success = await self.navigate_to_search(page)

            if not nav_success:
                return self._create_error_result("Failed to navigate to search page")

            print(f"✓ Navigation successful")

            # Step 2: Fill search form
            print(f"📝 Filling search form with operator: {operator_name}")
            form_success = await self.fill_search_form(page, operator_name)

            if not form_success:
                return self._create_error_result("Failed to fill search form")

            print(f"✓ Search form submitted")

            # Step 3: Extract results
            print(f"📊 Extracting UCC filing results...")
            results = await self.extract_results(page)

            print(f"✓ Extracted {len(results.get('filings', []))} filings")

            return {
                "state": self.state_name,
                "success": True,
                "operator_name": operator_name,
                "url": self.state_url,
                **results
            }

        except Exception as e:
            print(f"❌ Error in {self.state_name} flow: {str(e)}")
            return self._create_error_result(str(e))

    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """Create an error result dictionary"""
        return {
            "state": self.state_name,
            "success": False,
            "error": error_message,
            "url": self.state_url,
            "filings": []
        }

    async def take_screenshot(self, page: Page, filename: str) -> str:
        """
        Take a screenshot of the current page

        Args:
            page: Playwright page object
            filename: Name for the screenshot file

        Returns:
            str: Path to the saved screenshot
        """
        screenshot_path = f"/tmp/{filename}"
        await page.screenshot(path=screenshot_path, full_page=True)
        return screenshot_path
