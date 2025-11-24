# UCC Filings Flow Management

State-specific scraping flows for UCC filing systems. Each state has its own Python file with customized logic for navigating and extracting UCC filing data.

## Overview

The UCC filings flow system provides:
- **State-specific flows**: Each state has a dedicated `.py` file (e.g., `montana.py`, `alaska.py`)
- **Base flow template**: All state flows inherit from `BaseUCCFlow`
- **Automatic integration**: The `verify_ucc_filings()` function automatically uses state flows when available
- **Fallback mechanism**: Falls back to basic scraping if no custom flow exists

## Directory Structure

```
ucc-filings-flow/
├── __init__.py                     # Package initialization
├── base_flow.py                    # Base class for all state flows
├── flow_manager.py                 # Manages flow loading and execution
├── generate_state_templates.py    # Script to generate new state templates
├── README.md                       # This file
├── alabama.py                      # Alabama-specific flow
├── alaska.py                       # Alaska-specific flow
├── montana.py                      # Montana-specific flow
└── ... (51 state files total)
```

## How It Works

### 1. Automatic Flow Detection

When `verify_ucc_filings()` runs, it:
1. Loads search results from `utsb_sample_response.json`
2. Extracts state names from each result
3. For each state:
   - Tries to load the state-specific flow (e.g., `montana.py` for Montana)
   - If flow exists: Runs the custom flow
   - If no flow: Falls back to basic page scraping

### 2. State Flow Structure

Each state file (e.g., `montana.py`) contains:

```python
class MontanaFlow(BaseUCCFlow):
    """Montana-specific UCC filing flow"""

    async def navigate_to_search(self, page: Page) -> bool:
        """Navigate to Montana UCC search page"""
        # Implementation here
        pass

    async def fill_search_form(self, page: Page, search_query: str) -> bool:
        """Fill Montana UCC search form"""
        # Implementation here
        pass

    async def extract_results(self, page: Page) -> Dict[str, Any]:
        """Extract UCC filing results from Montana's page"""
        # Implementation here
        pass
```

## Implementing a State Flow

### Step 1: Open the State File

Find the state file in `/src/scoring/ucc-filings-flow/` (e.g., `montana.py`)

### Step 2: Implement the Three Methods

#### `navigate_to_search()`

Navigate to the state's UCC search page:

```python
async def navigate_to_search(self, page: Page) -> bool:
    try:
        await page.goto(self.state_url, wait_until="domcontentloaded", timeout=30000)

        # Wait for search button to appear
        await page.wait_for_selector('button.search-btn', timeout=10000)

        return True
    except Exception as e:
        print(f"❌ Navigation error: {str(e)}")
        return False
```

#### `fill_search_form()`

Fill out the search form with the operator name:

```python
async def fill_search_form(self, page: Page, search_query: str) -> bool:
    try:
        # Fill the debtor name field
        await page.fill('input[name="debtor_name"]', search_query)

        # Click search button
        await page.click('button[type="submit"]')

        # Wait for results to load
        await page.wait_for_load_state('networkidle')

        return True
    except Exception as e:
        print(f"❌ Form fill error: {str(e)}")
        return False
```

#### `extract_results()`

Extract UCC filing data from the results page:

```python
async def extract_results(self, page: Page) -> Dict[str, Any]:
    try:
        # Extract filings using JavaScript
        filings = await page.evaluate("""() => {
            const rows = document.querySelectorAll('.results-table tr');
            return Array.from(rows).map(row => ({
                filing_number: row.querySelector('.filing-number')?.textContent,
                debtor_name: row.querySelector('.debtor-name')?.textContent,
                filing_date: row.querySelector('.filing-date')?.textContent,
                status: row.querySelector('.status')?.textContent
            }));
        }""")

        return {
            "filings": filings,
            "total_count": len(filings),
            "page_title": await page.title()
        }
    except Exception as e:
        print(f"❌ Extraction error: {str(e)}")
        return {
            "filings": [],
            "total_count": 0,
            "error": str(e)
        }
```

### Step 3: Test Your Flow

Run the UCC verification service with a state that uses your flow:

```python
service = UCCVerificationService()
result = await service.verify_ucc_filings("Company Name", state="Montana")
```

## Helper Methods

The `BaseUCCFlow` class provides helper methods:

### `take_screenshot()`

```python
screenshot_path = await self.take_screenshot(page, "montana_search_form.png")
print(f"Screenshot saved: {screenshot_path}")
```

## Tips for Implementation

1. **Inspect the Page First**: Use browser DevTools to identify:
   - Form input selectors
   - Button selectors
   - Result table structure

2. **Use Screenshots**: Take screenshots at each step to debug:
   ```python
   await self.take_screenshot(page, f"{state_name}_step1.png")
   ```

3. **Add Waits**: Wait for elements to load:
   ```python
   await page.wait_for_selector('.results', timeout=10000)
   ```

4. **Handle Errors**: Wrap operations in try-catch blocks

5. **Test Incrementally**: Implement and test one method at a time

## Flow Status

- ✅ **Template Created**: All 51 states have template files
- ⚠️ **Implementation Needed**: Each state flow needs customization
- 🔄 **In Progress**: Montana, Alaska (examples with TODO comments)

## Example: Montana Flow

See `montana.py` for a complete example with:
- Navigation to Montana's UCC page
- TODO comments for form filling
- TODO comments for result extraction
- Screenshot capture for debugging

## Generating New State Templates

If you need to regenerate state templates:

```bash
cd /src/scoring/ucc-filings-flow/
python3 generate_state_templates.py
```

This will create template files for any missing states.

## Integration with verify_ucc_filings()

The integration is automatic:

```python
# In ucc_service.py
flow = get_flow_for_state(state_name, ucc_url)

if flow:
    # Use custom flow
    flow_result = await flow.run_flow(page, operator_name)
else:
    # Fallback to basic scraping
    # ... basic scraping code ...
```

## Next Steps

1. **Choose a State**: Pick a state from the sample data (Montana, Alaska)
2. **Inspect the Page**: Visit the state's UCC page and inspect the HTML
3. **Implement the Flow**: Fill in the three methods in the state file
4. **Test**: Run `verify_ucc_filings()` and check the results
5. **Repeat**: Move to the next state

## Questions?

Each state's UCC filing system is different. Common patterns:
- **Search forms**: Usually have debtor name, secured party, or filing number fields
- **Results tables**: Often HTML tables or divs with class names like `.results`, `.filing-row`
- **Pagination**: Some states have paginated results that need handling

Good luck with implementation! 🎯
