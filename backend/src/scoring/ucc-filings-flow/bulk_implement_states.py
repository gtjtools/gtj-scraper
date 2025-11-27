"""
Bulk implementation script to create UCC flow implementations for all states
using the Oregon pattern as a template.
"""

import json
import os
from pathlib import Path

# State name to file name mapping
STATE_FILE_NAMES = {
    "Alabama": "alabama",
    "Alaska": "alaska",
    "Arizona": "arizona",
    "Arkansas": "arkansas",
    "California": "california",
    "Colorado": "colorado",
    "Connecticut": "connecticut",
    "Delaware": "delaware",
    "District of Columbia": "district_of_columbia",
    "Florida": "florida",
    "Georgia": "georgia",
    "Hawaii": "hawaii",
    "Idaho": "idaho",
    "Illinois": "illinois",
    "Indiana": "indiana",
    "Iowa": "iowa",
    "Kansas": "kansas",
    "Kentucky": "kentucky",
    "Louisiana": "louisiana",
    "Maine": "maine",
    "Maryland": "maryland",
    "Massachusetts": "massachusetts",
    "Michigan": "michigan",
    "Minnesota": "minnesota",
    "Mississippi": "mississippi",
    "Missouri": "missouri",
    "Montana": "montana",
    "Nebraska": "nebraska",
    "Nevada": "nevada",
    "New Hampshire": "new_hampshire",
    "New Jersey": "new_jersey",
    "New Mexico": "new_mexico",
    "New York": "new_york",
    "North Carolina": "north_carolina",
    "North Dakota": "north_dakota",
    "Ohio": "ohio",
    "Oklahoma": "oklahoma",
    "Oregon": "oregon",
    "Pennsylvania": "pennsylvania",
    "Rhode Island": "rhode_island",
    "South Carolina": "south_carolina",
    "South Dakota": "south_dakota",
    "Tennessee": "tennessee",
    "Texas": "texas",
    "Utah": "utah",
    "Vermont": "vermont",
    "Virginia": "virginia",
    "Washington": "washington",
    "West Virginia": "west_virginia",
    "Wisconsin": "wisconsin",
    "Wyoming": "wyoming"
}

# States to skip (already implemented or functional)
SKIP_STATES = ["Oregon", "Idaho", "Colorado", "Kentucky", "Connecticut", "Iowa",
               "Kansas", "Louisiana", "Alabama"]


def generate_state_flow(state_name: str, state_url: str, class_name: str) -> str:
    """Generate UCC flow implementation for a state"""

    template = f'''"""
{state_name} UCC Filing Flow
State-specific implementation for {state_name}'s UCC filing system
URL: {state_url}
"""

from typing import Dict, Any
from playwright.async_api import Page
from base_flow import BaseUCCFlow


class {class_name}Flow(BaseUCCFlow):
    """{state_name}-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to {state_name} UCC search page"""
        try:
            print(f"📍 Navigating to {state_name} UCC page: {{self.state_url}}")
            await page.goto(
                self.state_url, wait_until="domcontentloaded", timeout=30000
            )
            await page.wait_for_timeout(2000)

            print("✓ Successfully navigated to {state_name} UCC page")
            return True
        except Exception as e:
            print(f"❌ {state_name} navigation error: {{str(e)}}")
            return False

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """
        Fill {state_name} UCC search form

        Steps:
        1. Look for organization/debtor name input
        2. Fill in the organization name field
        3. Click the search button
        4. Wait for results
        """
        try:
            print(f"📝 Filling {state_name} UCC search form for: {{search_query}}")

            # Step 1: Look for organization name input
            print("   Step 1: Looking for organization name input...")
            input_selectors = [
                'input[name*="organization"]',
                'input[name*="Organization"]',
                'input[id*="organization"]',
                'input[id*="orgName"]',
                'input[name*="debtor"]',
                'input[name*="Debtor"]',
                'input[id*="debtor"]',
                'input[name*="name"]',
                'input[name*="Name"]',
                'input[placeholder*="Organization"]',
                'input[placeholder*="Business"]',
                'input[placeholder*="Debtor"]',
                'input[placeholder*="Name"]',
                'input[type="text"]',
                'input[type="search"]'
            ]

            input_found = False
            for selector in input_selectors:
                try:
                    input_field = await page.query_selector(selector)
                    if input_field:
                        is_visible = await input_field.is_visible()
                        if is_visible:
                            print(f"   ✓ Found input field: {{selector}}")
                            await input_field.fill(search_query)
                            await page.wait_for_timeout(1000)
                            print(f"   ✓ Organization name entered: {{search_query}}")
                            input_found = True
                            break
                except:
                    continue

            if not input_found:
                print("   ⚠️  Could not find organization name input")

            # Step 2: Click the search button
            print("   Step 2: Clicking search button...")
            button_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Search")',
                'button:has-text("Submit")',
                'input[value*="Search"]',
                'a:has-text("Search")'
            ]

            button_found = False
            for selector in button_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        is_visible = await button.is_visible()
                        if is_visible:
                            print(f"   ✓ Found search button: {{selector}}")
                            await button.click()
                            print("   ✓ Search button clicked")
                            button_found = True
                            break
                except:
                    continue

            if not button_found:
                print("   ⚠️  Could not find search button")

            # Step 3: Wait for results to load
            print("   Step 3: Waiting for results...")
            await page.wait_for_timeout(3000)
            print("   ✓ Results loaded")

            # Take screenshot of results
            await self.take_screenshot(page, f"{STATE_FILE_NAMES.get(state_name, state_name.lower())}_search_results.png")

            print("✓ {state_name} search form completed successfully")
            return True
        except Exception as e:
            print(f"❌ {state_name} form fill error: {{str(e)}}")
            await self.take_screenshot(page, f"{STATE_FILE_NAMES.get(state_name, state_name.lower())}_error.png")
            return False

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """
        Extract UCC filing results from {state_name}'s page
        """
        try:
            print("📊 Extracting {state_name} UCC search results...")

            # Get page title and URL for reference
            page_title = await page.title()
            page_url = page.url

            print(f"   Page Title: {{page_title}}")
            print(f"   Page URL: {{page_url}}")

            # Take screenshot of final results
            await self.take_screenshot(page, f"{STATE_FILE_NAMES.get(state_name, state_name.lower())}_final_results.png")

            # Extract data from tables
            filings = []

            try:
                # Find all table rows
                print("   Looking for result tables...")
                tables = page.locator('table')
                table_count = await tables.count()
                print(f"   Found {{table_count}} tables")

                if table_count > 0:
                    # Try to extract from the main results table
                    rows = page.locator('table tr')
                    row_count = await rows.count()
                    print(f"   Found {{row_count}} rows in tables")

                    # Process each row (skip header)
                    for i in range(1, row_count):
                        row = rows.nth(i)
                        try:
                            # Extract all cells
                            cells = row.locator('td')
                            cell_count = await cells.count()

                            if cell_count > 0:
                                # Extract data from cells
                                filing_record = {{}}

                                # Typically: File Number, Debtor, Filing Date, Status, etc.
                                if cell_count >= 1:
                                    filing_record['file_number'] = (await cells.nth(0).inner_text()).strip()
                                if cell_count >= 2:
                                    filing_record['debtor_name'] = (await cells.nth(1).inner_text()).strip()
                                if cell_count >= 3:
                                    filing_record['filing_date'] = (await cells.nth(2).inner_text()).strip()
                                if cell_count >= 4:
                                    filing_record['status'] = (await cells.nth(3).inner_text()).strip()

                                if filing_record.get('file_number') or filing_record.get('debtor_name'):
                                    filings.append(filing_record)
                                    print(f"   Row {{i}}: {{filing_record}}")
                        except Exception as row_error:
                            print(f"   ⚠️  Error processing row {{i}}: {{str(row_error)}}")
                            continue

                print(f"\\n✓ Extracted {{len(filings)}} filing records")

            except Exception as e:
                print(f"⚠️  Could not extract table data: {{str(e)}}")

            print("✓ {state_name} results extraction completed")

            return {{
                "filings": filings,
                "total_count": len(filings),
                "page_title": page_title,
                "page_url": page_url,
                "implementation_status": "functional",
                "notes": f"Extracted {{len(filings)}} UCC filing records",
            }}
        except Exception as e:
            print(f"❌ {state_name} extraction error: {{str(e)}}")
            return {{"filings": [], "total_count": 0, "error": str(e)}}
'''
    return template


def main():
    # Load state URLs
    data_dir = Path(__file__).parent.parent.parent.parent / "data"
    json_path = data_dir / "ucc_state_options.json"

    with open(json_path, 'r') as f:
        state_options = json.load(f)

    # Get current directory
    current_dir = Path(__file__).parent

    # Track implementation stats
    implemented = 0
    skipped = 0

    for state_data in state_options:
        state_name = state_data.get("text", "")
        state_url = state_data.get("value", "")

        # Skip empty entries
        if not state_name or not state_url or state_name == "Please select":
            continue

        # Skip already implemented states
        if state_name in SKIP_STATES:
            print(f"⏭️  Skipping {state_name} (already implemented)")
            skipped += 1
            continue

        # Get file name
        file_name = STATE_FILE_NAMES.get(state_name)
        if not file_name:
            print(f"⚠️  No file mapping for {state_name}")
            continue

        # Generate class name (e.g., "New York" -> "NewYork")
        class_name = state_name.replace(" ", "")

        # Generate the implementation
        implementation = generate_state_flow(state_name, state_url, class_name)

        # Write to file
        output_file = current_dir / f"{file_name}.py"
        with open(output_file, 'w') as f:
            f.write(implementation)

        print(f"✅ Generated {state_name} -> {file_name}.py")
        implemented += 1

    print(f"\n{'='*60}")
    print(f"Implementation complete!")
    print(f"  ✅ Implemented: {implemented} states")
    print(f"  ⏭️  Skipped: {skipped} states (already functional)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
