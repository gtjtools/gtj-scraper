"""
Generate template state flow files for all states
Run this script to create template .py files for all states
"""
import json
import os


TEMPLATE = '''"""
{state_name} UCC Filing Flow
State-specific implementation for {state_name}'s UCC filing system
URL: {url}
"""
from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class {class_name}(BaseUCCFlow):
    """{state_name}-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to {state_name} UCC search page"""
        try:
            await page.goto(self.state_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            print(f"❌ {state_name} navigation error: {{{{str(e)}}}}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill {state_name} UCC search form

        TODO: Implement specific selectors for {state_name}'s UCC search form
        This is a template - needs to be customized based on {state_name}'s actual form
        """
        try:
            # Example selectors - NEEDS TO BE CUSTOMIZED
            # Uncomment and modify based on actual {state_name} page structure

            # await page.fill('input[name="debtor_name"]', search_query)
            # await page.click('button[type="submit"]')
            # await page.wait_for_load_state('networkidle')

            print("⚠️  {state_name} search form filling not yet implemented")
            print("   Please inspect the page and add proper selectors")

            # Take screenshot to help with implementation
            await self.take_screenshot(page, f"{file_name}_search_form.png")

            return True
        except Exception as e:
            print(f"❌ {state_name} form fill error: {{{{str(e)}}}}")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from {state_name}'s page

        TODO: Implement specific extraction logic for {state_name}
        This is a template - needs to be customized based on {state_name}'s actual results
        """
        try:
            # Example extraction - NEEDS TO BE CUSTOMIZED
            filings = []

            # Uncomment and modify based on actual {state_name} page structure
            # filings = await page.evaluate("""() => {{{{
            #     const rows = document.querySelectorAll('.results-table tr');
            #     return Array.from(rows).map(row => ({{{{
            #         filing_number: row.querySelector('.filing-number')?.textContent,
            #         debtor_name: row.querySelector('.debtor-name')?.textContent,
            #         filing_date: row.querySelector('.filing-date')?.textContent,
            #         status: row.querySelector('.status')?.textContent
            #     }}}}));
            # }}}}""")

            print("⚠️  {state_name} results extraction not yet implemented")
            print("   Please inspect the page and add proper extraction logic")

            # Take screenshot to help with implementation
            await self.take_screenshot(page, f"{file_name}_results.png")

            return {{{{
                "filings": filings,
                "total_count": len(filings),
                "page_title": await page.title(),
                "implementation_status": "template_only"
            }}}}
        except Exception as e:
            print(f"❌ {state_name} extraction error: {{{{str(e)}}}}")
            return {{{{
                "filings": [],
                "total_count": 0,
                "error": str(e)
            }}}}
'''


def generate_state_files():
    """Generate template files for all states"""
    # Load state options
    data_path = '../../../data/ucc_state_options.json'
    with open(data_path, 'r') as f:
        states = json.load(f)

    created = []
    skipped = []

    for state in states:
        state_name = state['text']
        state_url = state['value']

        if state_name == "Please select" or not state_url:
            continue

        # Create file name and class name
        file_name = state_name.lower().replace(' ', '_')
        class_name = f"{state_name.replace(' ', '')}Flow"
        file_path = f"{file_name}.py"

        # Skip if file already exists
        if os.path.exists(file_path):
            skipped.append(state_name)
            continue

        # Generate content from template
        content = TEMPLATE.format(
            state_name=state_name,
            url=state_url,
            class_name=class_name,
            file_name=file_name
        )

        # Write file
        with open(file_path, 'w') as f:
            f.write(content)

        created.append(state_name)
        print(f"✓ Created: {file_path}")

    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Created: {len(created)} state files")
    print(f"  Skipped (already exist): {len(skipped)} state files")
    print(f"{'=' * 60}")

    if skipped:
        print(f"\nSkipped states: {', '.join(skipped)}")


if __name__ == "__main__":
    generate_state_files()
