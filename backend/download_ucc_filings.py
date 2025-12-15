"""
UCC Filings Bulk Download Script
Downloads UCC filings for all operators in operators.dat across all implemented states
Outputs results to JSON file
"""
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'scoring', 'ucc-filings-flow'))

from playwright.async_api import async_playwright


# State configurations with their UCC search URLs
STATE_CONFIGS = {
    "Alabama": "https://www.alabamainteractive.org/ucc_filing/",
    "Alaska": "https://online.corp.delaware.gov/ucc/",  # Uses Delaware system
    "Arizona": "https://ecorp.azcc.gov/PublicSearch/UCCSearch",
    "Arkansas": "https://www.sos.arkansas.gov/corps/ucc/index.php",
    "California": "https://bizfileonline.sos.ca.gov/search/business",
    "Colorado": "https://www.sos.state.co.us/ucc/pages/search/standardSearch.xhtml",
    "Connecticut": "https://www.concord-sots.ct.gov/CONCORD/online?sn=InquiryServlet&ession=UCC",
    "Delaware": "https://icis.corp.delaware.gov/UCCInquiry/UCCSearch",
    "District of Columbia": "https://corp.dcra.dc.gov/Account.aspx/LogOn",
    "Florida": "https://services.sunbiz.org/Filings/UCCSearch/Search",
    "Georgia": "https://ecorp.sos.ga.gov/UCCSearch",
    "Hawaii": "https://hbe.ehawaii.gov/documents/search.html",
    "Idaho": "https://www.accessidaho.org/public/sos/ucc/search.html",
    "Illinois": "https://www.ilsos.gov/uccsearch/",
    "Indiana": "https://bsd.sos.in.gov/publicbusinesssearch",
    "Iowa": "https://sos.iowa.gov/uccsearch/",
    "Kansas": "https://www.kansas.gov/bess/flow/main?execution=e1s1",
    "Kentucky": "https://app.sos.ky.gov/ftucc/",
    "Louisiana": "https://coraweb.sos.la.gov/commercialsearch/commercialsearch.aspx",
    "Maine": "https://icrs.informe.org/nei-sos-icrs/ICRS?MainPage=x",
    "Maryland": "https://egov.maryland.gov/BusinessExpress/EntitySearch",
    "Massachusetts": "https://corp.sec.state.ma.us/corp/uccsearch/uccsearch.asp",
    "Michigan": "https://cofs.lara.state.mi.us/SearchApi/Search/Search",
    "Minnesota": "https://mblsportal.sos.state.mn.us/",
    "Mississippi": "https://www.sos.ms.gov/UCC-Search",
    "Missouri": "https://bsd.sos.mo.gov/BusinessEntity/UCCSearch.aspx",
    "Montana": "https://sosmt.gov/business/",
    "Nebraska": "https://www.nebraska.gov/sos/ucc/",
    "Nevada": "https://esos.nv.gov/EntitySearch/OnlineEntitySearch",
    "New Hampshire": "https://quickstart.sos.nh.gov/online/search",
    "New Jersey": "https://www.njportal.com/DOR/BusinessNameSearch/",
    "New Mexico": "https://portal.sos.state.nm.us/BFS/online/",
    "New York": "https://appext20.dos.ny.gov/pls/ucc_public/web_search.main_frame",
    "North Carolina": "https://www.sosnc.gov/online_services/search/ucc",
    "North Dakota": "https://apps.nd.gov/sc/busnsrch/busnSearch.htm",
    "Ohio": "https://www.sos.state.oh.us/businesses/information-on-a-business/",
    "Oklahoma": "https://www.sos.ok.gov/ucc/",
    "Oregon": "https://sos.oregon.gov/business/Pages/find.aspx",
    "Pennsylvania": "https://www.corporations.pa.gov/Search/SearchCorportions",
    "Rhode Island": "https://business.sos.ri.gov/CorpWeb/CorpSearch/CorpSearch.aspx",
    "South Carolina": "https://businessfilings.sc.gov/businessfiling/",
    "South Dakota": "https://sos.sd.gov/business/",
    "Tennessee": "https://tnbear.tn.gov/Ecommerce/UCCFilingSearch.aspx",
    "Texas": "https://direct.sos.state.tx.us/acct/acct-login.asp",
    "Utah": "https://secure.utah.gov/uccsearch/",
    "Vermont": "https://www.vtsosonline.com/online/UCCSearch/",
    "Virginia": "https://scc.virginia.gov/pages/ucc",
    "Washington": "https://www.sos.wa.gov/corps/search.aspx",
    "West Virginia": "https://apps.wv.gov/SOS/BusinessEntitySearch/",
    "Wisconsin": "https://www.wdfi.org/apps/ucc/",
    "Wyoming": "https://wyobiz.wyo.gov/Business/FilingSearch.aspx",
}


def load_operators(filepath: str) -> List[str]:
    """Load operator names from operators.dat file"""
    operators = []
    with open(filepath, 'r') as f:
        content = f.read()
        # Parse as Python-style quoted strings
        for line in content.strip().split('\n'):
            line = line.strip().strip(',')
            if line.startswith("'") and line.endswith("'"):
                operators.append(line[1:-1])
            elif line.startswith('"') and line.endswith('"'):
                operators.append(line[1:-1])
            elif line:
                operators.append(line)
    return operators


async def search_state_ucc(page, state_name: str, state_url: str, operator_name: str) -> Dict[str, Any]:
    """
    Search for UCC filings in a specific state for an operator

    This is a generic search implementation that attempts to work with most state sites.
    For best results, state-specific flows should be used.
    """
    result = {
        "state": state_name,
        "operator": operator_name,
        "url": state_url,
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "filings": [],
        "error": None
    }

    try:
        print(f"  📍 Searching {state_name} for: {operator_name}")

        # Navigate to state UCC search
        await page.goto(state_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Try to find and fill search form
        search_selectors = [
            'input[name*="name"]',
            'input[name*="debtor"]',
            'input[name*="organization"]',
            'input[name*="search"]',
            'input[name*="Name"]',
            'input[id*="name"]',
            'input[id*="debtor"]',
            'input[id*="search"]',
            'input[placeholder*="Name"]',
            'input[placeholder*="Search"]',
            'input[type="text"]:first-of-type',
        ]

        input_filled = False
        for selector in search_selectors:
            try:
                input_field = await page.query_selector(selector)
                if input_field and await input_field.is_visible():
                    await input_field.fill(operator_name)
                    input_filled = True
                    print(f"    ✓ Found input field: {selector}")
                    break
            except:
                continue

        if not input_filled:
            result["error"] = "Could not find search input field"
            return result

        # Try to submit the search
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Search")',
            'button:has-text("Submit")',
            'input[value*="Search"]',
            'a:has-text("Search")',
            'button:has-text("Find")',
        ]

        submitted = False
        for selector in submit_selectors:
            try:
                button = await page.query_selector(selector)
                if button and await button.is_visible():
                    await button.click()
                    submitted = True
                    print(f"    ✓ Clicked submit: {selector}")
                    await page.wait_for_load_state('networkidle', timeout=15000)
                    await page.wait_for_timeout(2000)
                    break
            except:
                continue

        if not submitted:
            # Try pressing Enter on the input
            try:
                await page.keyboard.press('Enter')
                await page.wait_for_load_state('networkidle', timeout=15000)
                await page.wait_for_timeout(2000)
                submitted = True
                print(f"    ✓ Submitted via Enter key")
            except:
                result["error"] = "Could not submit search form"
                return result

        # Extract results from the page
        filings = await page.evaluate("""() => {
            const results = [];

            // Try table extraction
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll('td');
                    if (cells.length >= 2) {
                        const text = rows[i].textContent.trim();
                        if (text && text.length > 5) {
                            results.push({
                                row_data: Array.from(cells).map(c => c.textContent.trim()),
                                raw_text: text
                            });
                        }
                    }
                }
            }

            // Try list extraction if no table results
            if (results.length === 0) {
                const listItems = document.querySelectorAll('li.result, div.result, div[class*="filing"], tr[class*="result"]');
                for (const item of listItems) {
                    results.push({
                        raw_text: item.textContent.trim()
                    });
                }
            }

            return results;
        }""")

        result["success"] = True
        result["filings"] = filings
        result["filing_count"] = len(filings)

        # Check for no results message
        no_results = await page.evaluate("""() => {
            const text = document.body.textContent.toLowerCase();
            return text.includes('no results') ||
                   text.includes('no records') ||
                   text.includes('no filings') ||
                   text.includes('not found') ||
                   text.includes('0 results');
        }""")

        if no_results and len(filings) == 0:
            result["no_results_found"] = True

        print(f"    ✓ Found {len(filings)} potential filings")

    except Exception as e:
        result["error"] = str(e)
        print(f"    ❌ Error: {str(e)[:100]}")

    return result


async def download_ucc_filings(operators: List[str], states: List[str] = None, output_file: str = None) -> Dict[str, Any]:
    """
    Download UCC filings for all operators across specified states

    Args:
        operators: List of operator names to search
        states: List of states to search (default: all)
        output_file: Path for JSON output file

    Returns:
        Dictionary with all results
    """
    if states is None:
        states = list(STATE_CONFIGS.keys())

    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"ucc_filings_{timestamp}.json"

    results = {
        "metadata": {
            "start_time": datetime.now().isoformat(),
            "total_operators": len(operators),
            "total_states": len(states),
            "output_file": output_file
        },
        "operators": {}
    }

    print(f"\n{'=' * 70}")
    print(f"UCC Filings Bulk Download")
    print(f"{'=' * 70}")
    print(f"Operators: {len(operators)}")
    print(f"States: {len(states)}")
    print(f"Output: {output_file}")
    print(f"{'=' * 70}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        for i, operator in enumerate(operators, 1):
            print(f"\n[{i}/{len(operators)}] Processing: {operator}")
            print("-" * 50)

            operator_results = {
                "operator_name": operator,
                "search_timestamp": datetime.now().isoformat(),
                "states_searched": [],
                "total_filings_found": 0
            }

            for state in states:
                if state not in STATE_CONFIGS:
                    print(f"  ⚠️  Skipping {state} - no URL configured")
                    continue

                page = await context.new_page()
                try:
                    state_result = await search_state_ucc(
                        page,
                        state,
                        STATE_CONFIGS[state],
                        operator
                    )
                    operator_results["states_searched"].append(state_result)
                    operator_results["total_filings_found"] += len(state_result.get("filings", []))
                except Exception as e:
                    operator_results["states_searched"].append({
                        "state": state,
                        "operator": operator,
                        "success": False,
                        "error": str(e)
                    })
                finally:
                    await page.close()

                # Small delay between states to be respectful
                await asyncio.sleep(1)

            results["operators"][operator] = operator_results

            # Save intermediate results
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"  💾 Saved intermediate results to {output_file}")

        await browser.close()

    results["metadata"]["end_time"] = datetime.now().isoformat()

    # Final save
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print(f"Download Complete!")
    print(f"{'=' * 70}")
    print(f"Results saved to: {output_file}")

    return results


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Download UCC filings for operators")
    parser.add_argument(
        "--operators-file",
        default="operators.dat",
        help="Path to operators file (default: operators.dat)"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output JSON file path (default: ucc_filings_TIMESTAMP.json)"
    )
    parser.add_argument(
        "--states",
        nargs="+",
        default=None,
        help="Specific states to search (default: all)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of operators to process (for testing)"
    )

    args = parser.parse_args()

    # Load operators
    operators_path = Path(args.operators_file)
    if not operators_path.exists():
        print(f"Error: Operators file not found: {args.operators_file}")
        sys.exit(1)

    operators = load_operators(str(operators_path))
    print(f"Loaded {len(operators)} operators from {args.operators_file}")

    if args.limit:
        operators = operators[:args.limit]
        print(f"Limited to first {args.limit} operators")

    # Run download
    await download_ucc_filings(
        operators=operators,
        states=args.states,
        output_file=args.output
    )


if __name__ == "__main__":
    asyncio.run(main())
