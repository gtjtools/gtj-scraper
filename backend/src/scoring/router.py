# src/scoring/router.py
import os
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import UUID4
from datetime import datetime
from src.scoring.schemas import NTSBQueryRequest, ScoreCalculationResponse
from src.scoring.service import ScoringService
from src.scoring.ucc_service import UCCVerificationService
from src.trustscore.calculator import TrustScoreCalculator, FleetScoreData, TailScoreData
from src.trustscore.llm_client import LLMClient, LLMProvider
from src.common.dependencies import get_db
from src.auth.service import authentication
from src.common.error import HTTPError

# Directory for storing verification results
VERIFICATION_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "../../data/temp")
os.makedirs(VERIFICATION_RESULTS_DIR, exist_ok=True)

scoring_router = APIRouter()

# Special operator state mappings (for testing specific flows)
OPERATOR_STATE_OVERRIDES = {
    "Aero Air LLC": "Oregon",
}


@scoring_router.post(
    "/scoring/run-score/{operator_id}",
    response_model=ScoreCalculationResponse,
    summary="Run score calculation for an operator",
    description="Calculate operator score based on NTSB incident data and other factors.",
    response_description="Calculated score with incident details",
    tags=["scoring"]
)
async def run_score_calculation(
    operator_id: UUID4,
    db: Session = Depends(get_db),
    auth=Depends(authentication)
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
    tags=["scoring"]
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
        "ntsb_api_url": "https://data.ntsb.gov/carol-main-public/api/Query/Main"
    }


@scoring_router.post(
    "/scoring/query-ntsb",
    summary="Query NTSB database by operator name",
    description="Directly query NTSB database for incidents by operator name without authentication",
    response_description="NTSB incidents and calculated score",
    tags=["scoring"]
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
        print(f"NTSB Response Keys: {ntsb_data.keys() if isinstance(ntsb_data, dict) else 'Not a dict'}")
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
            calculated_at=datetime.now().isoformat()
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
    tags=["scoring"]
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
            raise HTTPException(status_code=500, detail="Browserbase credentials not configured")

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
            "operator_name": operator_name
        }

    except Exception as e:
        print(f"❌ Error creating session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@scoring_router.post(
    "/scoring/full-scoring-flow",
    summary="Run full scoring flow (NTSB + UCC) for an operator",
    description="Execute complete scoring workflow: Query NTSB incident database and verify UCC filings",
    tags=["scoring"]
)
async def full_scoring_flow(operator_name: str, faa_state: str, state: str = None, session_id: str = None):
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
        ntsb_data = await NTSBService.query_ntsb_incidents(operator_name)
        incidents = NTSBService.parse_ntsb_response(ntsb_data)
        total_incidents = len(incidents)
        ntsb_score = max(0, 100 - (total_incidents * 5))

        print(f"✓ NTSB check complete: {total_incidents} incidents found, score: {ntsb_score}")

        # Step 2: Verify UCC filings
        print("\nStep 2: Verifying UCC filings with Browserbase...")
        ucc_service = UCCVerificationService()
        # Pass raw NTSB results (Results array) to UCC service, not parsed incidents
        ntsb_results = ntsb_data.get("Results", [])
        ucc_data = await ucc_service.verify_ucc_filings_with_session(operator_name, ntsb_results, faa_state, state, session_id)

        print(f"✓ UCC check complete: {ucc_data.get('status')}")

        # Step 3: Calculate TrustScore using gathered data
        print("\nStep 3: Calculating TrustScore...")

        # Extract UCC filings from the verification result
        ucc_filings = []
        visited_states = ucc_data.get("visited_states", [])
        for state_result in visited_states:
            if state_result.get("flow_used") and state_result.get("flow_result"):
                flow_result = state_result["flow_result"]
                # Use normalized_filings instead of raw filings
                normalized_filings = flow_result.get("normalized_filings", [])
                for filing in normalized_filings:
                    ucc_filings.append({
                        "file_number": filing.get("file_number", "Unknown"),
                        "status": filing.get("status", "Unknown"),
                        "filing_date": filing.get("filing_date", "Unknown"),
                        "lapse_date": filing.get("lapse_date", "Unknown"),
                        "lien_type": filing.get("lien_type", "Unknown"),
                        "debtor": filing.get("debtor", "Unknown"),
                        "secured_party": filing.get("secured_party", None),
                        "collateral": filing.get("collateral", None),
                        "state": state_result.get("state", "Unknown")
                    })

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
            operator = db.query(Operator).filter(Operator.name == operator_name).first()

            if operator:
                # Calculate operator age in years from business_started_date
                if operator.business_started_date:
                    years_diff = (datetime.now() - operator.business_started_date).days / 365.25
                    operator_age_years = round(years_diff, 1)
                    print(f"✓ Operator age calculated: {operator_age_years} years (started: {operator.business_started_date})")
                else:
                    print(f"⚠️  No business_started_date found for operator, using default: {operator_age_years} years")

                # Fetch ARGUS and Wyvern ratings
                argus_rating = operator.argus_rating
                wyvern_rating = operator.wyvern_rating
                print(f"✓ ARGUS rating: {argus_rating or 'None'}, Wyvern rating: {wyvern_rating or 'None'}")
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
            bankruptcy_history=None
        )

        # Create TailScoreData (placeholder - would need aircraft-specific data)
        tail_data = TailScoreData(
            aircraft_age_years=5.0,  # Default placeholder
            operator_name=operator_name,
            registered_owner=operator_name,  # Assume same as operator
            fractional_owner=False,
            tail_events=fleet_events  # Tail-specific events
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
        trust_score_result = await calculator.calculate_trust_score(fleet_data, tail_data)
        print(f"✓ TrustScore calculated: {trust_score_result['trust_score']}")

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
            },

            # UCC Results
            "ucc": ucc_data,

            # TrustScore Results
            "trust_score": trust_score_result,

            # Combined score (now using TrustScore)
            "combined_score": trust_score_result["trust_score"],

            "status": "completed"
        }

        # Save combined verification result to single JSON file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_operator_name = "".join(c if c.isalnum() else "_" for c in operator_name)

        # Create operator-specific folder: operator_name_YYYYMMDD
        date_only = datetime.now().strftime("%Y%m%d")
        folder_name = f"{safe_operator_name}_{date_only}"
        operator_folder = os.path.join(VERIFICATION_RESULTS_DIR, folder_name)
        os.makedirs(operator_folder, exist_ok=True)

        # Save verification result in the operator folder
        filename = f"verification_result_{safe_operator_name}_{timestamp}.json"
        filepath = os.path.join(operator_folder, filename)

        with open(filepath, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"✓ Verification result saved to: {filepath}")

        # Add filename to result
        result["saved_file"] = filename

        print(f"\n{'='*80}")
        print(f"FULL SCORING FLOW COMPLETED")
        print(f"NTSB Score: {ntsb_score}, UCC Status: {ucc_data.get('status')}")
        print(f"TrustScore: {trust_score_result['trust_score']} (Fleet: {trust_score_result['fleet_score']}, Tail: {trust_score_result['tail_score']})")
        print(f"Saved to: {filename}")
        print(f"{'='*80}\n")

        return result

    except Exception as e:
        print(f"❌ Full scoring flow error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Scoring flow failed: {str(e)}")
