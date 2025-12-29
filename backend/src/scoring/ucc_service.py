"""
UCC Filing Verification Service using Browserbase
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional, List
from browserbase import Browserbase
from playwright.async_api import async_playwright


class UCCVerificationService:
    """Service for verifying UCC filings using Browserbase"""

    # NTSB API Configuration
    NTSB_API_URL = "https://data.ntsb.gov/carol-main-public/api/Query/Main"
    NTSB_TIMEOUT = 30.0  # seconds

    def __init__(self):
        self.browserbase_api_key = os.getenv("BROWSERBASE_API_KEY")
        self.browserbase_project_id = os.getenv("BROWSERBASE_PROJECT_ID")

        if not self.browserbase_api_key:
            print("⚠️  WARNING: BROWSERBASE_API_KEY not set in environment")
        if not self.browserbase_project_id:
            print("⚠️  WARNING: BROWSERBASE_PROJECT_ID not set in environment")

    async def _retry_with_backoff(
        self,
        func,
        max_retries: int = 5,
        initial_delay: float = 1.0,
        context: str = "Operation",
    ):
        """
        Retry an async function with exponential backoff.

        Args:
            func: Async function to retry (should be a callable that returns a coroutine)
            max_retries: Maximum number of retry attempts (default: 5)
            initial_delay: Initial delay in seconds before first retry (default: 1.0)
            context: Description of the operation for logging

        Returns:
            Result of the function or None if all retries exhausted

        Raises:
            Exception: Re-raises the last exception if all retries fail
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = await func()
                if attempt > 0:
                    print(f"✓ {context} succeeded on attempt {attempt + 1}")
                return result
            except Exception as error:
                last_error = error

                if attempt == max_retries:
                    print(
                        f"❌ {context} failed after {max_retries + 1} attempts: {str(error)}"
                    )
                    raise error

                # Calculate exponential backoff delay: initial_delay * 2^attempt
                delay = initial_delay * (2**attempt)
                print(
                    f"⚠️  {context} failed (attempt {attempt + 1}/{max_retries + 1}): {str(error)}"
                )
                print(
                    f"   Retrying in {delay:.1f}s... ({max_retries - attempt} attempts remaining)"
                )

                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        if last_error:
            raise last_error

    async def _query_ntsb_incidents(self, operator_name: str) -> List[Dict[str, Any]]:
        """
        Query NTSB database for incidents related to an operator.

        Args:
            operator_name: The name of the operator to search for

        Returns:
            List of results from NTSB API
        """
        payload = {
            "ResultSetSize": 50,
            "ResultSetOffset": 0,
            "QueryGroups": [
                {
                    "QueryRules": [
                        {
                            "RuleType": "Simple",
                            "Values": [operator_name],
                            "Columns": ["AviationOperation.OperatorName"],
                            "Operator": "ResultSetSize",
                            "overrideColumn": "",
                            "selectedOption": {
                                "FieldName": "OperatorName",
                                "DisplayText": "Operator name",
                                "Columns": ["AviationOperation.OperatorName"],
                                "Selectable": True,
                                "InputType": "Text",
                                "RuleType": 0,
                                "Options": None,
                                "TargetCollection": "cases",
                                "UnderDevelopment": False,
                            },
                        }
                    ],
                    "AndOr": "and",
                    "inLastSearch": False,
                    "editedSinceLastSearch": False,
                }
            ],
            "AndOr": "and",
            "SortColumn": None,
            "SortDescending": True,
            "TargetCollection": "cases",
            "SessionId": 146165,
        }

        try:
            print(f"🔍 Querying NTSB API for operator: {operator_name}")
            async with httpx.AsyncClient(timeout=self.NTSB_TIMEOUT) as client:
                response = await client.post(self.NTSB_API_URL, json=payload)
                response.raise_for_status()
                data = response.json()
                results = data.get("Results", [])
                print(f"✓ Found {len(results)} NTSB incidents for {operator_name}")
                return results
        except httpx.TimeoutException:
            print(f"⚠️  NTSB API request timed out after {self.NTSB_TIMEOUT} seconds")
            return []
        except httpx.HTTPStatusError as e:
            print(f"⚠️  NTSB API returned error: {e.response.status_code}")
            return []
        except Exception as e:
            print(f"⚠️  Error querying NTSB API: {str(e)}")
            return []

    def _load_ucc_state_options(self) -> List[Dict[str, str]]:
        """Load UCC state options from JSON file"""
        data_path = os.path.join(
            os.path.dirname(__file__), "../../data/ucc_state_options.json"
        )
        try:
            with open(data_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Warning: Could not load UCC state options: {e}")
            return []

    def _extract_state_from_result(self, result: Dict[str, Any]) -> Optional[str]:
        """Extract state name from a search result"""
        fields = result.get("Fields", [])
        for field in fields:
            if field.get("FieldName") == "State":
                values = field.get("Values", [])
                if values:
                    return values[0]
        return None

    def _get_state_info(
        self, state_name: str, state_options: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """
        Get state info (full name, abbreviation, URL) for a given state identifier.
        Matches by abbreviation first, then by full state name.

        Returns:
            Dict with 'name', 'abbreviation', and 'url' keys, or None if not found
        """
        # Try matching by abbreviation first (for database faa_state column)
        for option in state_options:
            if option.get("abbreviation") == state_name:
                return {
                    "name": option.get("text"),
                    "abbreviation": option.get("abbreviation"),
                    "url": option.get("value", "").strip()
                }

        # Fallback: try matching by full state name (for NTSB results)
        for option in state_options:
            if option.get("text") == state_name:
                return {
                    "name": option.get("text"),
                    "abbreviation": option.get("abbreviation"),
                    "url": option.get("value", "").strip()
                }

        return None

    def _get_ucc_url_for_state(
        self, state_name: str, state_options: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Get UCC URL for a given state.
        Matches by abbreviation first (e.g., "FL", "CA", "TX") for database queries,
        then falls back to full state name (e.g., "Florida", "California") for NTSB results.
        """
        state_info = self._get_state_info(state_name, state_options)
        return state_info["url"] if state_info and state_info.get("url") else None

    async def _process_single_state(
        self, page, state_name: str, ucc_url: str, operator_name: str, session_id: str
    ) -> Dict[str, Any]:
        """
        Process a single state's UCC verification with retry logic.

        Args:
            page: Playwright page object
            state_name: Name of the state to process
            ucc_url: URL for the state's UCC filing page
            operator_name: Name of the operator to search for
            session_id: Browserbase session ID for screenshots

        Returns:
            Dictionary containing state verification result
        """
        print(f"📍 Processing {state_name}...")
        print(f"   URL: {ucc_url}")

        # Try to get state-specific flow
        flow = self._get_flow_for_state(state_name, ucc_url)

        if flow:
            print(f"✓ Using custom flow for {state_name}")
            # Run the state-specific flow
            flow_result = await flow.run_flow(page, operator_name)

            return {
                "state": state_name,
                "url": ucc_url,
                "flow_used": True,
                "flow_result": flow_result,
                "page_info": {
                    "state": state_name,
                    "flow_success": flow_result.get("success", False),
                    "filings_count": len(flow_result.get("filings", [])),
                },
            }

        else:
            print(f"⚠️  No custom flow found for {state_name}, using basic scraping")
            # Fallback to basic page scraping
            await page.goto(ucc_url, wait_until="domcontentloaded", timeout=30000)
            print(f"✓ Navigated to {state_name} UCC page")

            # Wait a bit for visibility
            await page.wait_for_timeout(2000)

            # Extract page information
            page_info = await page.evaluate(
                """() => {
                return {
                    title: document.title,
                    heading: document.querySelector('h1')?.textContent || 'N/A',
                    description: document.querySelector('meta[name="description"]')?.content || 'N/A',
                    hasSearchForm: !!document.querySelector('form, input[type="search"]')
                };
            }"""
            )

            print(f"✓ Page title: {page_info['title']}")
            print(f"✓ Page heading: {page_info['heading']}")

            # Scroll down to show content
            print("📜 Scrolling page to show content...")
            await page.evaluate("window.scrollTo(0, 300)")
            await page.wait_for_timeout(1000)

            await page.evaluate("window.scrollTo(0, 600)")
            await page.wait_for_timeout(1000)

            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            # Take a screenshot for debugging
            screenshot_bytes = await page.screenshot(full_page=True)
            screenshot_path = f"/tmp/ucc_search_{state_name}_{session_id}.png"
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            print(f"✓ Screenshot saved: {screenshot_path}")

            return {
                "state": state_name,
                "url": ucc_url,
                "flow_used": False,
                "page_info": page_info,
                "screenshot_path": screenshot_path,
            }

    def _get_flow_for_state(self, state_name: str, state_url: str):
        """
        Dynamically import and get the flow class for a specific state

        Args:
            state_name: Name of the state (e.g., "Montana", "Alaska")
            state_url: URL for the state's UCC filing page

        Returns:
            Instance of the state's UCC flow class, or None if not implemented
        """
        # Convert state name to module name (e.g., "Montana" -> "montana")
        module_name = state_name.lower().replace(" ", "_")

        try:
            # Dynamically import the state's flow module
            import importlib.util
            import sys

            flow_dir = os.path.join(os.path.dirname(__file__), "ucc-filings-flow")

            # First, load base_flow module if not already loaded
            if "base_flow" not in sys.modules:
                base_flow_path = os.path.join(flow_dir, "base_flow.py")
                base_spec = importlib.util.spec_from_file_location(
                    "base_flow", base_flow_path
                )
                if base_spec and base_spec.loader:
                    base_module = importlib.util.module_from_spec(base_spec)
                    sys.modules["base_flow"] = base_module
                    base_spec.loader.exec_module(base_module)

            # Build path to the state module
            module_path = os.path.join(flow_dir, f"{module_name}.py")

            # Check if file exists
            if not os.path.exists(module_path):
                return None

            # Load the module dynamically
            spec = importlib.util.spec_from_file_location(
                f"ucc_flow_{module_name}", module_path
            )
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)

            # Make base_flow available for relative imports
            module.__package__ = "ucc_filings_flow"

            sys.modules[f"ucc_flow_{module_name}"] = module
            spec.loader.exec_module(module)

            # Get the flow class (should be named like MontanaFlow, AlaskaFlow, etc.)
            class_name = f"{state_name.replace(' ', '')}Flow"
            flow_class = getattr(module, class_name, None)

            if flow_class is None:
                return None

            # Return an instance of the flow
            return flow_class(state_name, state_url)

        except Exception as e:
            print(f"⚠️  Could not load flow for {state_name}: {str(e)}")
            return None

    async def verify_ucc_filings(
        self,
        operator_name: str,
        ntsb_results: List[Dict[str, Any]],
        faa_state: str,
        state: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify UCC filings for an operator using Browserbase

        Args:
            operator_name: Name of the operator to verify
            ntsb_results: NTSB results from previous NTSB check (required)
            faa_state: FAA state code (2-letter abbreviation) - used as fallback if no filings found in NTSB states
            state: Optional state code for targeted search

        Returns:
            Dictionary containing UCC verification results
        """
        print(f"\n{'=' * 80}")
        print(f"VERIFYING UCC FILINGS FOR: {operator_name}")
        if state:
            print(f"State: {state}")
        else:
            print("State: Will be determined from NTSB results")
        print(f"{'=' * 80}\n")

        if not self.browserbase_api_key or not self.browserbase_project_id:
            return self._create_error_response(
                operator_name, "Browserbase credentials not configured"
            )

        try:
            # Initialize Browserbase client
            bb = Browserbase(api_key=self.browserbase_api_key)

            # Create a new session with live view enabled and US proxy
            session = bb.sessions.create(
                project_id=self.browserbase_project_id,
                proxies=True,  # Enable proxies with US location
            )
            session_id = session.id
            connect_url = session.connect_url

            # Debug URL (this one works without auth)
            debug_url = f"https://www.browserbase.com/sessions/{session_id}"

            # For live view, we'll use the debug URL since /live requires auth
            live_view_url = debug_url

            print(f"✓ Browserbase session created: {session_id}")
            print(f"✓ Connect URL: {connect_url}")
            print(f"✓ Debug URL: {debug_url}")
            print(f"\n🎥 Open this URL to watch: {debug_url}\n")

            # Use NTSB results from previous step and load state options
            print(f"✓ Using NTSB results from previous step ({len(ntsb_results)} incidents)")
            search_results = ntsb_results
            state_options = self._load_ucc_state_options()

            if not search_results:
                print("⚠️  No NTSB incidents found for this operator - will use FAA state only")

            if not state_options:
                print("⚠️  No state options found")
                return self._create_error_response(
                    operator_name, "No state options found"
                )

            if search_results:
                print(f"✓ Found {len(search_results)} NTSB incidents from API")
            print(f"✓ Loaded {len(state_options)} state options")

            # Use Playwright to connect to the Browserbase session
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(connect_url)
                context = browser.contexts[0]
                page = context.pages[0]

                # Set viewport to a larger size for better preview visibility
                await page.set_viewport_size({"width": 1920, "height": 1080})
                print("✓ Connected to Browserbase browser (viewport: 1920x1080)")

                # Process each search result
                visited_states = []
                all_page_info = []

                # Determine states to process
                if state:
                    states_to_process = [state]
                    print(f"📍 Processing specified state: {state}")
                else:
                    # Extract states from NTSB results
                    states_to_process = [
                        self._extract_state_from_result(r) for r in search_results
                    ]
                    states_to_process = [
                        s for s in states_to_process if s
                    ]  # Remove None values
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_states = []
                    for s in states_to_process:
                        if s not in seen:
                            seen.add(s)
                            unique_states.append(s)
                    states_to_process = unique_states

                    # Always add faa_state to the processing queue if provided
                    if faa_state:
                        # Get full state name from abbreviation
                        state_info = self._get_state_info(faa_state, state_options)
                        if state_info:
                            faa_state_full_name = state_info["name"]
                            # Only add if not already in the list
                            if faa_state_full_name not in states_to_process:
                                states_to_process.append(faa_state_full_name)
                                print(f"📍 Adding FAA state to queue: {faa_state_full_name} ({faa_state})")

                    print(
                        f"📍 Processing states: {states_to_process}"
                    )

                for idx, state_name in enumerate(states_to_process):
                    if not state_name:
                        print(f"⚠️  Invalid state in list")
                        continue

                    print(f"\n{'=' * 60}")
                    print(
                        f"Processing state {idx + 1}/{len(states_to_process)}: {state_name}"
                    )
                    print(f"{'=' * 60}")

                    # Get UCC URL for this state
                    ucc_url = self._get_ucc_url_for_state(state_name, state_options)

                    if not ucc_url:
                        print(f"⚠️  No UCC URL found for state: {state_name}")
                        continue

                    try:
                        # Process state with retry logic (default 5 retries)
                        state_result = await self._retry_with_backoff(
                            lambda: self._process_single_state(
                                page, state_name, ucc_url, operator_name, session_id
                            ),
                            max_retries=5,
                            initial_delay=1.0,
                            context=f"State verification for {state_name}",
                        )

                        # Add to visited states
                        visited_states.append(state_result)

                        # Extract page info for summary
                        if state_result.get("flow_used"):
                            all_page_info.append(state_result["page_info"])
                        else:
                            all_page_info.append(
                                {
                                    "state": state_name,
                                    **state_result.get("page_info", {}),
                                }
                            )

                        # Wait a bit before moving to next state
                        print("⏱️  Waiting 3 seconds before next state...")
                        await page.wait_for_timeout(3000)

                    except Exception as e:
                        print(
                            f"❌ Error processing {state_name} after all retries: {str(e)}"
                        )
                        # Add failed state to results
                        visited_states.append(
                            {
                                "state": state_name,
                                "url": ucc_url,
                                "error": str(e),
                                "status": "failed_after_retries",
                            }
                        )
                        continue

                print(f"\n{'=' * 60}")
                print(f"✓ Processed {len(visited_states)} states successfully")
                print(f"{'=' * 60}\n")

                await browser.close()
                print("✓ Browser session closed")

                # Create result
                result = {
                    "operator_name": operator_name,
                    "ucc_verified": False,
                    "verification_date": datetime.now().isoformat(),
                    "source": "State-specific UCC filing pages",
                    "status": "manual_verification_required",
                    "message": f"Navigated to {len(visited_states)} state-specific UCC pages based on NTSB incident locations for {operator_name}.",
                    "states_processed": len(visited_states),
                    "visited_states": visited_states,
                    "all_page_info": all_page_info,
                    "browserbase_session_id": session_id,
                    "browserbase_debug_url": debug_url,
                    "browserbase_live_view_url": live_view_url,
                }

                print(f"\n✓ UCC verification completed")
                print(f"Session debug URL: {debug_url}")
                print(f"{'=' * 80}\n")

                return result

        except Exception as error:
            print(f"❌ UCC verification error: {str(error)}")
            return self._create_error_response(operator_name, str(error))

    async def verify_ucc_filings_with_session(
        self,
        operator_name: str,
        ntsb_results: List[Dict[str, Any]],
        faa_state: str,
        state: Optional[str] = None,
        existing_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify UCC filings using an existing Browserbase session.
        This allows the user to watch the automation live.

        Args:
            operator_name: Name of the operator to verify
            ntsb_results: NTSB results from previous NTSB check (required)
            faa_state: FAA state code (2-letter abbreviation) - used as fallback if no filings found
            state: Optional state code for targeted search
            existing_session_id: Optional existing Browserbase session ID
        """
        if existing_session_id:
            print(f"Using existing Browserbase session: {existing_session_id}")
            return await self._run_ucc_automation(
                operator_name, ntsb_results, faa_state, state, existing_session_id
            )
        else:
            # Fallback to creating new session
            return await self.verify_ucc_filings(operator_name, ntsb_results, faa_state, state)

    async def _run_ucc_automation(
        self, operator_name: str, ntsb_results: List[Dict[str, Any]], faa_state: str, state: Optional[str], session_id: str
    ) -> Dict[str, Any]:
        """
        Run the UCC automation using an existing session

        Args:
            operator_name: Name of the operator to verify
            ntsb_results: NTSB results from previous NTSB check (required)
            faa_state: FAA state code (2-letter abbreviation) - used as fallback if no filings found
            state: Optional state code for targeted search
            session_id: Browserbase session ID
        """
        try:
            # Get session info
            bb = Browserbase(api_key=self.browserbase_api_key)
            session = bb.sessions.retrieve(session_id)
            connect_url = session.connect_url

            debug_url = f"https://www.browserbase.com/sessions/{session_id}"
            live_view_url = debug_url

            print(f"✓ Connected to existing session: {session_id}")
            if state:
                print(f"State: {state}")
            else:
                print("State: Will be determined from NTSB results")

            # Use NTSB results from previous step and load state options
            print(f"✓ Using NTSB results from previous step ({len(ntsb_results)} incidents)")
            search_results = ntsb_results
            state_options = self._load_ucc_state_options()

            if not search_results:
                print("⚠️  No NTSB incidents found for this operator - will use FAA state only")

            if not state_options:
                print("⚠️  No state options found")
                return self._create_error_response(
                    operator_name, "No state options found"
                )

            if search_results:
                print(f"✓ Found {len(search_results)} NTSB incidents from API")
            print(f"✓ Loaded {len(state_options)} state options")

            # Use Playwright to connect to the Browserbase session
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(connect_url)
                context = browser.contexts[0]
                page = context.pages[0]

                # Set viewport to a larger size for better preview visibility
                await page.set_viewport_size({"width": 1920, "height": 1080})
                print("✓ Connected to Browserbase browser (viewport: 1920x1080)")

                # Process each search result
                visited_states = []
                all_page_info = []

                # Determine states to process
                if state:
                    states_to_process = [state]
                    print(f"📍 Processing specified state: {state}")
                else:
                    # Extract states from NTSB results
                    states_to_process = [
                        self._extract_state_from_result(r) for r in search_results
                    ]
                    states_to_process = [
                        s for s in states_to_process if s
                    ]  # Remove None values
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_states = []
                    for s in states_to_process:
                        if s not in seen:
                            seen.add(s)
                            unique_states.append(s)
                    states_to_process = unique_states

                    # Always add faa_state to the processing queue if provided
                    if faa_state:
                        # Get full state name from abbreviation
                        state_info = self._get_state_info(faa_state, state_options)
                        if state_info:
                            faa_state_full_name = state_info["name"]
                            # Only add if not already in the list
                            if faa_state_full_name not in states_to_process:
                                states_to_process.append(faa_state_full_name)
                                print(f"📍 Adding FAA state to queue: {faa_state_full_name} ({faa_state})")

                    print(
                        f"📍 Processing states: {states_to_process}"
                    )

                for idx, state_name in enumerate(states_to_process):
                    if not state_name:
                        print(f"⚠️  Invalid state in list")
                        continue

                    print(f"\n{'=' * 60}")
                    print(
                        f"Processing state {idx + 1}/{len(states_to_process)}: {state_name}"
                    )
                    print(f"{'=' * 60}")

                    # Get UCC URL for this state
                    ucc_url = self._get_ucc_url_for_state(state_name, state_options)

                    if not ucc_url:
                        print(f"⚠️  No UCC URL found for state: {state_name}")
                        continue

                    try:
                        # Process state with retry logic (default 5 retries)
                        state_result = await self._retry_with_backoff(
                            lambda: self._process_single_state(
                                page, state_name, ucc_url, operator_name, session_id
                            ),
                            max_retries=5,
                            initial_delay=1.0,
                            context=f"State verification for {state_name}",
                        )

                        # Add to visited states
                        visited_states.append(state_result)

                        # Extract page info for summary
                        if state_result.get("flow_used"):
                            all_page_info.append(state_result["page_info"])
                        else:
                            all_page_info.append(
                                {
                                    "state": state_name,
                                    **state_result.get("page_info", {}),
                                }
                            )

                        # Wait a bit before moving to next state
                        print("⏱️  Waiting 3 seconds before next state...")
                        await page.wait_for_timeout(3000)

                    except Exception as e:
                        print(
                            f"❌ Error processing {state_name} after all retries: {str(e)}"
                        )
                        # Add failed state to results
                        visited_states.append(
                            {
                                "state": state_name,
                                "url": ucc_url,
                                "error": str(e),
                                "status": "failed_after_retries",
                            }
                        )
                        continue

                print(f"\n{'=' * 60}")
                print(f"✓ Processed {len(visited_states)} states successfully")
                print(f"{'=' * 60}\n")

                await browser.close()
                print("✓ Browser session closed")

                # Create result
                result = {
                    "operator_name": operator_name,
                    "ucc_verified": False,
                    "verification_date": datetime.now().isoformat(),
                    "source": "State-specific UCC filing pages",
                    "status": "manual_verification_required",
                    "message": f"Navigated to {len(visited_states)} state-specific UCC pages based on NTSB incident locations for {operator_name}.",
                    "states_processed": len(visited_states),
                    "visited_states": visited_states,
                    "all_page_info": all_page_info,
                    "browserbase_session_id": session_id,
                    "browserbase_debug_url": debug_url,
                    "browserbase_live_view_url": live_view_url,
                }

                print(f"\n✓ UCC verification completed")
                print(f"Session debug URL: {debug_url}")
                print(f"{'=' * 80}\n")

                return result

        except Exception as error:
            print(f"❌ UCC verification error: {str(error)}")
            return self._create_error_response(operator_name, str(error))

    def _create_error_response(
        self, operator_name: str, error_message: str
    ) -> Dict[str, Any]:
        """Create an error response"""
        return {
            "operator_name": operator_name,
            "ucc_verified": False,
            "verification_date": datetime.now().isoformat(),
            "status": "error",
            "error": error_message,
            "browserbase_session_id": None,
        }


# Synchronous wrapper for FastAPI
def verify_ucc_filings_sync(
    operator_name: str, ntsb_results: List[Dict[str, Any]], faa_state: str, state: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for UCC verification

    Args:
        operator_name: Name of the operator to verify
        ntsb_results: NTSB results from previous NTSB check (required)
        faa_state: FAA state code (2-letter abbreviation) - used as fallback if no filings found
        state: Optional state code for targeted search
    """
    service = UCCVerificationService()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            service.verify_ucc_filings(operator_name, ntsb_results, faa_state, state)
        )
        return result
    finally:
        loop.close()
