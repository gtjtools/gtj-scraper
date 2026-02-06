# src/scoring/router.py
import os
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import UUID4
from datetime import datetime, timedelta
from decimal import Decimal
from src.scoring.schemas import NTSBQueryRequest, ScoreCalculationResponse
from src.scoring.service import ScoringService
from src.scoring.ucc_service import UCCVerificationService
from src.trustscore.calculator import (
    TrustScoreCalculator,
    FleetScoreData,
    TailScoreData,
)
from src.trustscore.llm_client import LLMClient, LLMProvider
from src.common.dependencies import get_db
from src.auth.service import authentication
from src.common.error import HTTPError
from src.common.models import Operator, TrustScore
from src.hatchet_client import hatchet
from src.workflows.batch_verify_workflow import batch_verify_workflow

# Directory for storing verification results
VERIFICATION_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "../../data/temp")
os.makedirs(VERIFICATION_RESULTS_DIR, exist_ok=True)

scoring_router = APIRouter()

# Special operator state mappings (for testing specific flows)
OPERATOR_STATE_OVERRIDES = {
    "Aero Air LLC": "Oregon",
}

# States with UCC scraper ready - UCC flow will only scrape these states
# Add more states here as scrapers become available (e.g., ["CA", "FL"])
UCC_READY_STATES = ["CA"]

# Test filter for batch verification - only process these operators
# Set to None or empty list to process all operators matching state filter
# Example: ["GO FLY LLC.", "Another Operator"]
# BATCH_TEST_OPERATORS = ["GO FLY LLC."]  # Set to None to disable filter
BATCH_TEST_OPERATORS = None


def save_trust_score_to_supabase(
    operator_name: str,
    trust_score_result: dict,
    ntsb_result: dict,
    ucc_result: dict,
    argus_rating: str = None,
    wyvern_rating: str = None
) -> bool:
    """
    Save trust score results to Supabase database.
    Updates gtj.operators and creates record in gtj.trust_scores.

    Args:
        operator_name: Name of the operator
        trust_score_result: TrustScore calculation result
        ntsb_result: NTSB query result
        ucc_result: UCC verification result
        argus_rating: ARGUS certification rating
        wyvern_rating: Wyvern certification rating

    Returns:
        True if saved successfully, False otherwise
    """
    from src.common.config import SessionLocal

    db = SessionLocal()
    try:
        # Find the operator
        operator = db.query(Operator).filter(Operator.name == operator_name).first()

        if not operator:
            print(f"  ⚠️  Operator '{operator_name}' not found in gtj.operators table")
            return False

        # Extract scores from trust_score_result
        overall_score = trust_score_result.get('trust_score', 0)
        fleet_score = trust_score_result.get('fleet_score', overall_score)
        tail_score = trust_score_result.get('tail_score', 100)
        operator_score = trust_score_result.get('operator_score', 100)
        confidence_score = trust_score_result.get('confidence_score', 0.8)

        # Extract financial score from fleet_breakdown final_score
        fleet_breakdown = trust_score_result.get('fleet_breakdown', {})
        financial_score = fleet_breakdown.get('final_score', 100)

        # Update operator's trust_score
        operator.trust_score = Decimal(str(overall_score))
        operator.trust_score_updated_at = datetime.utcnow()

        # Build comprehensive factors JSON
        factors = {
            "ntsb": {
                "score": ntsb_result.get('score', 100),
                "total_incidents": ntsb_result.get('total_incidents', 0),
                "incidents": ntsb_result.get('incidents', [])
            },
            "ucc": {
                "status": ucc_result.get('status', 'unknown'),
                "states_processed": ucc_result.get('states_processed', 0),
                "visited_states": ucc_result.get('visited_states', [])
            },
            "scores": {
                "fleet_score": fleet_score,
                "tail_score": tail_score,
                "operator_score": operator_score,
                "raw_combined_score": trust_score_result.get('raw_combined_score', 0),
                "score_tier": trust_score_result.get('score_tier', 'Unknown')
            },
            "fleet_breakdown": fleet_breakdown,
            "tail_breakdown": trust_score_result.get('tail_breakdown', {}),
            "certifications": {
                "argus_rating": argus_rating,
                "wyvern_rating": wyvern_rating
            },
            "ai_insights": trust_score_result.get('ai_insights', None)
        }

        # Create trust_scores record with enriched data
        trust_score_record = TrustScore(
            operator_id=operator.operator_id,
            overall_score=Decimal(str(overall_score)),
            safety_score=Decimal(str(fleet_score)),
            financial_score=Decimal(str(financial_score)),
            regulatory_score=Decimal(str(operator_score)),
            aog_score=Decimal(str(100)),  # Default, no AOG data yet
            factors=factors,
            version="3.0",  # Algorithm v3
            expires_at=datetime.utcnow() + timedelta(days=30),
            confidence_level=Decimal(str(confidence_score))
        )

        db.add(trust_score_record)
        db.commit()

        print(f"  ✓ Saved trust score {overall_score} for {operator_name} to gtj.operators and gtj.trust_scores")
        return True

    except Exception as e:
        print(f"  ❌ Error saving to Supabase for {operator_name}: {e}")
        db.rollback()
        return False
    finally:
        db.close()


@scoring_router.post(
    "/scoring/run-score/{operator_id}",
    response_model=ScoreCalculationResponse,
    summary="Run score calculation for an operator",
    description="Calculate operator score based on NTSB incident data and other factors.",
    response_description="Calculated score with incident details",
    tags=["scoring"],
)
async def run_score_calculation(
    operator_id: UUID4, db: Session = Depends(get_db), auth=Depends(authentication)
):
    """
    Run complete score calculation for an operator.

    This endpoint:
    1. Retrieves operator information from the database
    2. Queries NTSB database for incident history
    3. Calculates a score based on incident data
    4. Returns the score along with incident details

    Args:
        operator_id: UUID of the operator to score

    Returns:
        ScoreCalculationResponse: Calculated score and incident data

    Raises:
        HTTPException: If operator not found or NTSB API fails
    """
    try:
        scoring_service = ScoringService(db)
        result = await scoring_service.run_score_calculation(operator_id)
        return result
    except HTTPError as e:
        raise HTTPException(status_code=400, detail=str(e.detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@scoring_router.get(
    "/scoring/health",
    summary="Health check for scoring service",
    description="Check if the scoring service is operational",
    tags=["scoring"],
)
async def scoring_health_check():
    """
    Health check endpoint for scoring service.

    Returns:
        dict: Service status
    """
    return {
        "status": "healthy",
        "service": "scoring",
        "ntsb_api_url": "https://data.ntsb.gov/carol-main-public/api/Query/Main",
    }


@scoring_router.post(
    "/scoring/query-ntsb",
    summary="Query NTSB database by operator name",
    description="Directly query NTSB database for incidents by operator name without authentication",
    response_description="NTSB incidents and calculated score",
    tags=["scoring"],
)
async def query_ntsb_by_name(operator_name: str):
    """
    Query NTSB database directly by operator name.

    This is a simplified endpoint that doesn't require authentication
    or database operator creation. It directly queries the NTSB API.

    Args:
        operator_name: Name of the operator to search for

    Returns:
        ScoreCalculationResponse: Score and incident details

    Raises:
        HTTPException: If NTSB API query fails
    """
    try:
        from src.scoring.service import NTSBService

        # Query NTSB directly
        print(f"\n{'='*80}")
        print(f"QUERYING NTSB FOR OPERATOR: {operator_name}")
        print(f"{'='*80}")

        ntsb_data = await NTSBService.query_ntsb_incidents(operator_name)

        print(f"\nNTSB Response Type: {type(ntsb_data)}")
        print(
            f"NTSB Response Keys: {ntsb_data.keys() if isinstance(ntsb_data, dict) else 'Not a dict'}"
        )
        print(f"\n{'='*80}")
        print(f"FULL NTSB RESPONSE DATA:")
        print(f"{'='*80}")

        import json

        print(json.dumps(ntsb_data, indent=2, default=str))

        print(f"\n{'='*80}")

        # Parse incidents
        incidents = NTSBService.parse_ntsb_response(ntsb_data)
        print(f"\nParsed {len(incidents)} incidents")

        print(f"\n{'='*80}")
        print(f"PARSED INCIDENTS:")
        print(f"{'='*80}")
        import json

        for i, incident in enumerate(incidents, 1):
            print(f"\nIncident {i}:")
            print(json.dumps(incident.dict(), indent=2, default=str))

        # Calculate simple score based on incidents
        total_incidents = len(incidents)

        # Simple scoring: 100 - (incidents * 5), minimum 0
        ntsb_score = max(0, 100 - (total_incidents * 5))

        print(f"\n{'='*80}")
        print(f"FINAL CALCULATION:")
        print(f"{'='*80}")
        print(f"Total Incidents: {total_incidents}")
        print(f"NTSB Score: {ntsb_score}")
        print(f"{'='*80}\n")

        return ScoreCalculationResponse(
            operator_id=None,  # No operator in database
            operator_name=operator_name,
            ntsb_score=ntsb_score,
            total_incidents=total_incidents,
            incidents=incidents,
            calculated_at=datetime.now().isoformat(),
        )

    except HTTPError as e:
        print(f"HTTPError: {e.detail}")
        raise HTTPException(status_code=400, detail=str(e.detail))
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@scoring_router.post(
    "/scoring/start-session",
    summary="Start a Browserbase session for live viewing",
    description="Create a Browserbase session and return the live view URL immediately",
    tags=["scoring"],
)
async def start_browserbase_session(operator_name: str):
    """
    Start a Browserbase session for live viewing.
    Returns the session URL immediately so user can watch live.
    """
    try:
        from browserbase import Browserbase
        import os

        browserbase_api_key = os.getenv("BROWSERBASE_API_KEY")
        browserbase_project_id = os.getenv("BROWSERBASE_PROJECT_ID")

        if not browserbase_api_key or not browserbase_project_id:
            raise HTTPException(
                status_code=500, detail="Browserbase credentials not configured"
            )

        # Create session
        bb = Browserbase(api_key=browserbase_api_key)
        session = bb.sessions.create(project_id=browserbase_project_id, proxies=False)

        session_id = session.id

        # Get the debugger fullscreen URL for iframe embedding
        live_view_links = bb.sessions.debug(session_id)
        debugger_fullscreen_url = live_view_links.debugger_fullscreen_url

        print(f"✓ Browserbase session created: {session_id}")
        print(f"✓ Live view URL: {debugger_fullscreen_url}")

        return {
            "session_id": session_id,
            "live_view_url": debugger_fullscreen_url,
            "connect_url": session.connect_url,
            "operator_name": operator_name,
        }

    except Exception as e:
        print(f"❌ Error creating session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create session: {str(e)}"
        )


@scoring_router.post(
    "/scoring/full-scoring-flow",
    summary="Run full scoring flow (NTSB + UCC) for an operator",
    description="Execute complete scoring workflow: Query NTSB incident database and verify UCC filings",
    tags=["scoring"],
)
async def full_scoring_flow(
    operator_name: str, faa_state: str, state: str = None, session_id: str = None
):
    """
    Run full scoring flow including NTSB and UCC checks.

    This endpoint:
    1. Queries NTSB database for incident history
    2. Verifies UCC filings using Browserbase (with optional existing session)
    3. Uses faa_state as fallback if no filings found in NTSB-based states
    4. Returns combined scoring results

    Args:
        operator_name: Name of the operator to verify
        faa_state: FAA state code (2-letter abbreviation) from database - used as fallback
        state: Optional state code for UCC search override
        session_id: Optional existing Browserbase session ID

    Returns:
        Combined scoring results with NTSB and UCC data
    """
    try:
        from src.scoring.service import NTSBService

        # Check for operator-specific state overrides
        if state is None and operator_name in OPERATOR_STATE_OVERRIDES:
            state = OPERATOR_STATE_OVERRIDES[operator_name]
            print(f"📍 Using operator-specific state override: {state}")

        print(f"\n{'='*80}")
        print(f"FULL SCORING FLOW FOR: {operator_name}")
        if state:
            print(f"State: {state}")
        else:
            print("State: Will be determined from NTSB results")
        if session_id:
            print(f"Using existing session: {session_id}")
        print(f"{'='*80}\n")

        # Step 1: Query NTSB
        print("Step 1: Querying NTSB database...")
        ntsb_error = None
        try:
            ntsb_data = await NTSBService.query_ntsb_incidents(operator_name)
            incidents = NTSBService.parse_ntsb_response(ntsb_data)
            total_incidents = len(incidents)
            ntsb_score = max(0, 100 - (total_incidents * 5))
            print(
                f"✓ NTSB check complete: {total_incidents} incidents found, score: {ntsb_score}"
            )
        except Exception as e:
            ntsb_error = str(e)
            print(f"⚠️  NTSB check failed: {ntsb_error}")
            print("  → Continuing with default values (no incidents, score: 100)")
            ntsb_data = {"Results": []}
            incidents = []
            total_incidents = 0
            ntsb_score = 100.0

        # Step 2: Verify UCC filings
        print("\nStep 2: Verifying UCC filings with Browserbase...")
        ucc_error = None
        try:
            ucc_service = UCCVerificationService()
            # Pass raw NTSB results (Results array) to UCC service, not parsed incidents
            ntsb_results = ntsb_data.get("Results", [])
            ucc_data = await ucc_service.verify_ucc_filings_with_session(
                operator_name,
                ntsb_results,
                faa_state,
                state,
                session_id,
                UCC_READY_STATES,
            )
            print(f"✓ UCC check complete: {ucc_data.get('status')}")
        except Exception as e:
            ucc_error = str(e)
            print(f"⚠️  UCC check failed: {ucc_error}")
            print("  → Continuing with default values (no UCC data)")
            ucc_data = {
                "status": "failed",
                "error": ucc_error,
                "visited_states": [],
                "states_processed": 0,
            }

        # Step 3: Calculate TrustScore using gathered data
        print("\nStep 3: Calculating TrustScore...")
        trust_score_error = None

        try:
            # Extract UCC filings from the verification result
            ucc_filings = []
            visited_states = ucc_data.get("visited_states", [])
            for state_result in visited_states:
                if state_result.get("flow_used") and state_result.get("flow_result"):
                    flow_result = state_result["flow_result"]
                    # Use normalized_filings instead of raw filings
                    normalized_filings = flow_result.get("normalized_filings", [])
                    for filing in normalized_filings:
                        ucc_filings.append(
                            {
                                "file_number": filing.get("file_number", "Unknown"),
                                "status": filing.get("status", "Unknown"),
                                "filing_date": filing.get("filing_date", "Unknown"),
                                "lapse_date": filing.get("lapse_date", "Unknown"),
                                "lien_type": filing.get("lien_type", "Unknown"),
                                "debtor": filing.get("debtor", "Unknown"),
                                "secured_party": filing.get("secured_party", None),
                                "collateral": filing.get("collateral", None),
                                "state": state_result.get("state", "Unknown"),
                            }
                        )

            # Convert NTSB incidents to dict format for TrustScore calculator (Algorithm v3)
            fleet_events = [incident.dict() for incident in incidents]
            ntsb_incidents_dict = fleet_events  # Keep reference for result output

            # Fetch operator data from database to get business_started_date
            from src.common.models import Operator
            from src.common.config import SessionLocal

            operator_age_years = 10.0  # Default fallback
            fleet_size = 1  # Default fallback
            argus_rating = None  # Default fallback
            wyvern_rating = None  # Default fallback

            try:
                db = SessionLocal()
                operator = (
                    db.query(Operator).filter(Operator.name == operator_name).first()
                )

                if operator:
                    # Calculate operator age in years from business_started_date
                    if operator.business_started_date:
                        years_diff = (
                            datetime.now() - operator.business_started_date
                        ).days / 365.25
                        operator_age_years = round(years_diff, 1)
                        print(
                            f"✓ Operator age calculated: {operator_age_years} years (started: {operator.business_started_date})"
                        )
                    else:
                        print(
                            f"⚠️  No business_started_date found for operator, using default: {operator_age_years} years"
                        )

                    # Fetch ARGUS and Wyvern ratings
                    argus_rating = operator.argus_rating
                    wyvern_rating = operator.wyvern_rating
                    print(
                        f"✓ ARGUS rating: {argus_rating or 'None'}, Wyvern rating: {wyvern_rating or 'None'}"
                    )
                else:
                    print(f"⚠️  Operator not found in database, using default values")

                db.close()
            except Exception as e:
                print(f"⚠️  Error fetching operator data: {e}, using default values")

            # Create FleetScoreData (Algorithm v3)
            fleet_data = FleetScoreData(
                operator_name=operator_name,
                operator_age_years=operator_age_years,
                fleet_size=fleet_size,  # Default - would need to be fetched from operator data
                fleet_events=fleet_events,  # All fleet-wide events (NTSB + FAA)
                ucc_filings=ucc_filings,
                argus_rating=argus_rating,
                wyvern_rating=wyvern_rating,
                bankruptcy_history=None,
            )

            # Create TailScoreData (placeholder - would need aircraft-specific data)
            tail_data = TailScoreData(
                aircraft_age_years=5.0,  # Default placeholder
                operator_name=operator_name,
                registered_owner=operator_name,  # Assume same as operator
                fractional_owner=False,
                tail_events=fleet_events,  # Tail-specific events
            )

            # Initialize calculator with LLM for AI insights
            try:
                llm_client = LLMClient(provider=LLMProvider.OPENROUTER)
                calculator = TrustScoreCalculator(llm_client=llm_client)
                print("✓ Using LLM for AI insights")
            except Exception as e:
                print(f"⚠️  LLM unavailable, using calculator without AI insights: {e}")
                calculator = TrustScoreCalculator(llm_client=None)

            # Calculate TrustScore
            trust_score_result = await calculator.calculate_trust_score(
                fleet_data, tail_data
            )
            print(f"✓ TrustScore calculated: {trust_score_result['trust_score']}")

        except Exception as e:
            trust_score_error = str(e)
            print(f"⚠️  TrustScore calculation failed: {trust_score_error}")
            print(f"  → Using fallback calculation based on NTSB score: {ntsb_score}")
            # Set default values
            ntsb_incidents_dict = (
                [incident.dict() for incident in incidents] if incidents else []
            )
            argus_rating = None
            wyvern_rating = None
            # Use NTSB score as fallback trust score if available
            fallback_score = ntsb_score if ntsb_score is not None else 50.0
            trust_score_result = {
                "trust_score": fallback_score,
                "fleet_score": fallback_score,
                "tail_score": fallback_score,
                "error": trust_score_error,
                "fallback": True,
            }

        # Determine overall status
        has_errors = any([ntsb_error, ucc_error, trust_score_error])
        overall_status = "completed_with_errors" if has_errors else "completed"

        # Combine results
        result = {
            "operator_name": operator_name,
            "verification_date": datetime.now().isoformat(),
            # NTSB Results
            "ntsb": {
                "score": ntsb_score,
                "total_incidents": total_incidents,
                "incidents": ntsb_incidents_dict,
                "raw_response": ntsb_data,
                "error": ntsb_error,  # Will be None if successful
            },
            # UCC Results
            "ucc": ucc_data,
            # TrustScore Results
            "trust_score": trust_score_result,
            # Combined score (now using TrustScore)
            "combined_score": trust_score_result["trust_score"],
            # Certification ratings
            "argus_rating": argus_rating,
            "wyvern_rating": wyvern_rating,
            # Status and errors
            "status": overall_status,
            "errors": {
                "ntsb": ntsb_error,
                "ucc": ucc_error,
                "trust_score": trust_score_error,
            },
        }

        # Save combined verification result to single JSON file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_operator_name = "".join(c if c.isalnum() else "_" for c in operator_name)

        # Create operator-specific folder: YYYYMMDD/operator_name
        date_only = datetime.now().strftime("%Y%m%d")
        folder_name = f"{date_only}/{safe_operator_name}"
        operator_folder = os.path.join(VERIFICATION_RESULTS_DIR, folder_name)
        os.makedirs(operator_folder, exist_ok=True)

        # Save verification result in the operator folder
        filename = f"verification_result_{safe_operator_name}_{timestamp}.json"
        filepath = os.path.join(operator_folder, filename)

        with open(filepath, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"✓ Verification result saved to: {filepath}")

        # Add filename to result
        result["saved_file"] = filename

        # Save to Supabase database (gtj.operators and gtj.trust_scores)
        saved_to_db = save_trust_score_to_supabase(
            operator_name=operator_name,
            trust_score_result=trust_score_result,
            ntsb_result={
                "score": ntsb_score,
                "total_incidents": total_incidents,
                "incidents": ntsb_incidents_dict
            },
            ucc_result=ucc_data,
            argus_rating=argus_rating,
            wyvern_rating=wyvern_rating
        )
        result["saved_to_supabase"] = saved_to_db

        print(f"\n{'='*80}")
        print(f"FULL SCORING FLOW COMPLETED - Status: {overall_status.upper()}")
        if has_errors:
            print(f"⚠️  Some steps encountered errors but flow completed:")
            if ntsb_error:
                print(f"  - NTSB: {ntsb_error}")
            if ucc_error:
                print(f"  - UCC: {ucc_error}")
            if trust_score_error:
                print(f"  - TrustScore: {trust_score_error}")
        print(f"NTSB Score: {ntsb_score}, UCC Status: {ucc_data.get('status')}")
        print(
            f"TrustScore: {trust_score_result['trust_score']} (Fleet: {trust_score_result['fleet_score']}, Tail: {trust_score_result['tail_score']})"
        )
        print(f"Saved to: {filename}")
        print(f"{'='*80}\n")

        return result

    except Exception as e:
        print(f"❌ Full scoring flow error: {type(e).__name__}: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Scoring flow failed: {str(e)}")


@scoring_router.post(
    "/scoring/batch-verify-by-states",
    summary="Batch verify operators by FAA states (NTSB + UCC)",
    description="Trigger batch verification workflow for all operators from database. Returns immediately with workflow run ID.",
    tags=["scoring"],
)
async def batch_verify_by_states(
    session_id: str = None,
    null_trust_score_only: bool = False,
    operator_id: str = None
):
    """
    Trigger batch verification workflow for all operators.

    This endpoint:
    1. Triggers a Hatchet workflow for batch verification
    2. Returns immediately with a workflow_run_id
    3. The workflow processes operators asynchronously in the background

    Args:
        session_id: Optional existing Browserbase session ID
        null_trust_score_only: If True, only process operators with NULL trust_score
        operator_id: Optional specific operator ID (UUID) to process only that operator

    Returns:
        Workflow run ID for tracking progress
    """
    try:
        # Trigger the Hatchet workflow (fire and forget - returns immediately)
        workflow_ref = batch_verify_workflow.run_no_wait(
            input={
                "session_id": session_id,
                "null_trust_score_only": null_trust_score_only,
                "operator_id": operator_id
            }
        )

        # Save Hatchet workflow run ID for tracking/cancellation via ./run_production.sh cancel-all logs/workflows.txt
        workflow_file = os.path.join(os.path.dirname(__file__), "../../logs/workflows.txt")
        os.makedirs(os.path.dirname(workflow_file), exist_ok=True)
        with open(workflow_file, "a") as f:
            f.write(f"{workflow_ref.workflow_run_id}\n")

        return {
            "status": "queued",
            "message": "Batch verification workflow started",
            "workflow_run_id": workflow_ref.workflow_run_id
        }

    except Exception as e:
        print(f"❌ Failed to start batch verification workflow: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Failed to start batch verification workflow: {str(e)}"
        )


@scoring_router.delete(
    "/scoring/batch-verify-cancel/{workflow_run_id}",
    summary="Cancel a batch verification workflow",
    description="Cancel a running or queued batch verification workflow",
    tags=["scoring"],
)
async def cancel_batch_verify(workflow_run_id: str):
    """
    Cancel a batch verification workflow run.

    Args:
        workflow_run_id: The workflow run ID to cancel

    Returns:
        Cancellation confirmation
    """
    try:
        await hatchet.runs.aio_cancel(workflow_run_id)
        return {
            "workflow_run_id": workflow_run_id,
            "status": "cancelled",
            "message": "Workflow run cancelled successfully"
        }
    except Exception as e:
        print(f"❌ Failed to cancel workflow: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel workflow: {str(e)}"
        )


@scoring_router.get(
    "/scoring/batch-verify-status/{workflow_run_id}",
    summary="Get batch verification workflow status",
    description="Check the status of a batch verification workflow run",
    tags=["scoring"],
)
async def get_batch_verify_status(workflow_run_id: str):
    """
    Get the status of a batch verification workflow run.

    Args:
        workflow_run_id: The workflow run ID returned from batch-verify-by-states

    Returns:
        Workflow status and result if completed
    """
    try:
        # Get workflow run status
        status = await hatchet.runs.aio_get_status(workflow_run_id)

        # Try to get result if completed
        result = None
        if status in ["SUCCEEDED", "COMPLETED"]:
            try:
                result = await hatchet.runs.aio_get_result(workflow_run_id)
            except Exception:
                pass

        return {
            "workflow_run_id": workflow_run_id,
            "status": status,
            "result": result
        }
    except Exception as e:
        print(f"❌ Failed to get workflow status: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get workflow status: {str(e)}"
        )
