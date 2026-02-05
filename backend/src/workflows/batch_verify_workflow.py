import os
import json
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from decimal import Decimal

from src.hatchet_client import hatchet
from hatchet_sdk import Context

# Directory for storing verification results
VERIFICATION_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "../../data/temp")
os.makedirs(VERIFICATION_RESULTS_DIR, exist_ok=True)

# States with UCC scraper ready
UCC_READY_STATES = ["CA"]

# Test filter for batch verification
BATCH_TEST_OPERATORS = None


class BatchVerifyInput(BaseModel):
    session_id: Optional[str] = None
    null_trust_score_only: bool = False
    operator_id: Optional[str] = None


class BatchVerifyOutput(BaseModel):
    status: str
    message: str
    total_operators: int
    successful: int
    failed: int
    saved_to_supabase: int
    results: List[dict]


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
    """
    from src.common.config import SessionLocal
    from src.common.models import Operator, TrustScore

    db = SessionLocal()
    try:
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


batch_verify_workflow = hatchet.workflow(name="batch-verify-operators")


@batch_verify_workflow.task(
    name="verify-operators",
    execution_timeout=timedelta(hours=2),
    retries=1
)
async def verify_operators_task(workflow_input, ctx: Context) -> dict:
    """
    Main task that processes all operators for batch verification.
    """
    from src.operator.charter_service import get_charter_operators, get_charter_operator_by_id
    from src.scoring.service import NTSBService
    from src.scoring.ucc_service import UCCVerificationService
    from src.trustscore.calculator import (
        TrustScoreCalculator,
        FleetScoreData,
        TailScoreData,
    )
    from src.trustscore.llm_client import LLMClient, LLMProvider
    from src.common.models import Operator as OperatorModel
    from src.common.config import SessionLocal

    # Parse workflow input - handle both dict and Pydantic model cases
    if hasattr(workflow_input, 'model_dump'):
        # It's a Pydantic model, convert to dict
        raw_input = workflow_input.model_dump()
    elif isinstance(workflow_input, dict):
        raw_input = workflow_input
    else:
        # Fallback to empty dict for EmptyModel or other cases
        raw_input = {}

    input_data = BatchVerifyInput.model_validate(raw_input)
    session_id = input_data.session_id
    null_trust_score_only = input_data.null_trust_score_only
    operator_id = input_data.operator_id

    states = None

    print(f"\n{'='*80}")
    if operator_id:
        print(f"BATCH VERIFICATION FOR OPERATOR ID: {operator_id}")
    else:
        print(f"BATCH VERIFICATION FOR STATES: {states if states else 'ALL'}")
    print(f"{'='*80}\n")

    # Step 1: Get operators from database
    print("Step 1: Fetching operators from database...")

    if operator_id:
        print(f"📍 Fetching specific operator by ID: {operator_id}")
        operator = await get_charter_operator_by_id(operator_id)
        if operator:
            filtered_operators = [operator]
            print(f"✓ Found operator: {operator.company}")
        else:
            return {
                "status": "failed",
                "message": f"Operator with ID {operator_id} not found",
                "total_operators": 0,
                "successful": 0,
                "failed": 0,
                "saved_to_supabase": 0,
                "results": [],
            }
    elif BATCH_TEST_OPERATORS:
        print(f"📍 Test filter active - querying only: {BATCH_TEST_OPERATORS}")
        filtered_operators = []
        for operator_name in BATCH_TEST_OPERATORS:
            operators_response = await get_charter_operators(
                skip=0, limit=None, search=operator_name
            )
            for op in operators_response.data:
                if op.company == operator_name:
                    filtered_operators.append(op)
        print(f"✓ Found {len(filtered_operators)} operator(s) matching test filter")
    else:
        operators_response = await get_charter_operators(
            skip=0, limit=None, search=None
        )
        all_operators = operators_response.data
        print(f"✓ Found {len(all_operators)} total operators in database")

        if states:
            filtered_operators = [op for op in all_operators if op.faa_state in states]
            print(f"✓ Filtered to {len(filtered_operators)} operators with faa_state in {states}")
        else:
            filtered_operators = all_operators
            print(f"✓ Processing all {len(filtered_operators)} operators (no state filter)")

    # Filter to only operators with null trust_score if requested
    if null_trust_score_only:
        print("📍 Filtering to operators with NULL trust_score...")
        db = SessionLocal()
        try:
            null_trust_score_operators = db.query(OperatorModel.name).filter(
                OperatorModel.trust_score.is_(None)
            ).all()
            null_trust_score_names = {op.name for op in null_trust_score_operators}

            filtered_operators = [
                op for op in filtered_operators
                if op.company in null_trust_score_names
            ]
            print(f"✓ Filtered to {len(filtered_operators)} operators with NULL trust_score")
        finally:
            db.close()

    if not filtered_operators:
        return {
            "status": "completed",
            "message": f"No operators found with faa_state in {states}",
            "total_operators": 0,
            "successful": 0,
            "failed": 0,
            "saved_to_supabase": 0,
            "results": [],
        }

    # Step 3: Run verification for each operator
    results = []
    successful = 0
    failed = 0
    saved_to_supabase_count = 0

    for idx, operator in enumerate(filtered_operators, 1):
        print(f"\n{'='*60}")
        print(f"Processing operator {idx}/{len(filtered_operators)}: {operator.company}")
        print(f"FAA State: {operator.faa_state}")
        print(f"{'='*60}")

        try:
            # Run NTSB query
            print(f"  → Querying NTSB for {operator.company}...")
            ntsb_error = None
            try:
                ntsb_data = await NTSBService.query_ntsb_incidents(operator.company)
                incidents = NTSBService.parse_ntsb_response(ntsb_data)
                total_incidents = len(incidents)
                ntsb_score = max(0, 100 - (total_incidents * 5))
                print(f"  ✓ NTSB: {total_incidents} incidents, score: {ntsb_score}")
            except Exception as e:
                ntsb_error = str(e)
                print(f"  ⚠️  NTSB failed: {ntsb_error}")
                print("  → Continuing with default values")
                ntsb_data = {"Results": []}
                incidents = []
                total_incidents = 0
                ntsb_score = 100.0

            # Run UCC verification
            print(f"  → Verifying UCC filings...")
            ucc_error = None
            try:
                ucc_service = UCCVerificationService()
                ntsb_results = ntsb_data.get("Results", [])
                ucc_data = await ucc_service.verify_ucc_filings_with_session(
                    operator.company,
                    ntsb_results,
                    operator.faa_state,
                    None,
                    session_id,
                    UCC_READY_STATES,
                )
                print(f"  ✓ UCC: {ucc_data.get('status')}")
            except Exception as e:
                ucc_error = str(e)
                print(f"  ⚠️  UCC failed: {ucc_error}")
                print("  → Continuing with default values")
                ucc_data = {
                    "status": "failed",
                    "error": ucc_error,
                    "visited_states": [],
                    "states_processed": 0,
                }

            # Calculate TrustScore
            print(f"  → Calculating TrustScore...")
            trust_score_error = None

            try:
                ucc_filings = []
                visited_states = ucc_data.get("visited_states", [])
                for state_result in visited_states:
                    if state_result.get("flow_used") and state_result.get("flow_result"):
                        flow_result = state_result["flow_result"]
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
                                "state": state_result.get("state", "Unknown"),
                            })

                fleet_events = [incident.dict() for incident in incidents]

                operator_age_years = 10.0
                fleet_size = 1
                argus_rating = None
                wyvern_rating = None

                try:
                    db = SessionLocal()
                    db_operator = (
                        db.query(OperatorModel)
                        .filter(OperatorModel.name == operator.company)
                        .first()
                    )

                    if db_operator and db_operator.business_started_date:
                        years_diff = (
                            datetime.now() - db_operator.business_started_date
                        ).days / 365.25
                        operator_age_years = round(years_diff, 1)

                    if db_operator:
                        argus_rating = db_operator.argus_rating
                        wyvern_rating = db_operator.wyvern_rating

                    db.close()
                except Exception as e:
                    print(f"  ⚠️  Could not fetch operator data from gtj.operators: {e}")

                fleet_data = FleetScoreData(
                    operator_name=operator.company,
                    operator_age_years=operator_age_years,
                    fleet_size=fleet_size,
                    fleet_events=fleet_events,
                    ucc_filings=ucc_filings,
                    argus_rating=argus_rating,
                    wyvern_rating=wyvern_rating,
                    bankruptcy_history=None,
                )

                tail_data = TailScoreData(
                    aircraft_age_years=5.0,
                    operator_name=operator.company,
                    registered_owner=operator.company,
                    fractional_owner=False,
                    tail_events=fleet_events,
                )

                try:
                    llm_client = LLMClient(provider=LLMProvider.OPENROUTER)
                    calculator = TrustScoreCalculator(llm_client=llm_client)
                except Exception:
                    calculator = TrustScoreCalculator(llm_client=None)

                trust_score_result = await calculator.calculate_trust_score(
                    fleet_data, tail_data
                )
                print(f"  ✓ TrustScore: {trust_score_result['trust_score']}")

            except Exception as e:
                trust_score_error = str(e)
                print(f"  ⚠️  TrustScore calculation failed: {trust_score_error}")
                print(f"  → Using fallback calculation based on NTSB score: {ntsb_score}")
                fleet_events = (
                    [incident.dict() for incident in incidents] if incidents else []
                )
                argus_rating = None
                wyvern_rating = None
                fallback_score = ntsb_score if ntsb_score is not None else 50.0
                trust_score_result = {
                    "trust_score": fallback_score,
                    "fleet_score": fallback_score,
                    "tail_score": fallback_score,
                    "error": trust_score_error,
                    "fallback": True,
                }

            # Save result
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_operator_name = "".join(
                c if c.isalnum() else "_" for c in operator.company
            )
            date_only = datetime.now().strftime("%Y%m%d")
            folder_name = f"{date_only}/{safe_operator_name}"
            operator_folder = os.path.join(VERIFICATION_RESULTS_DIR, folder_name)
            os.makedirs(operator_folder, exist_ok=True)

            has_errors = any([ntsb_error, ucc_error, trust_score_error])
            operator_status = "completed_with_errors" if has_errors else "completed"

            result_data = {
                "operator_name": operator.company,
                "faa_state": operator.faa_state,
                "verification_date": datetime.now().isoformat(),
                "ntsb": {
                    "score": ntsb_score,
                    "total_incidents": total_incidents,
                    "incidents": fleet_events,
                    "raw_response": ntsb_data,
                    "error": ntsb_error,
                },
                "ucc": ucc_data,
                "trust_score": trust_score_result,
                "combined_score": trust_score_result["trust_score"],
                "argus_rating": argus_rating,
                "wyvern_rating": wyvern_rating,
                "status": operator_status,
                "errors": {
                    "ntsb": ntsb_error,
                    "ucc": ucc_error,
                    "trust_score": trust_score_error,
                },
            }

            filename = f"verification_result_{safe_operator_name}_{timestamp}.json"
            filepath = os.path.join(operator_folder, filename)

            with open(filepath, "w") as f:
                json.dump(result_data, f, indent=2, default=str)

            print(f"  ✓ Saved JSON: {filename}")

            # Save to Supabase database (gtj.operators and gtj.trust_scores)
            saved_to_db = save_trust_score_to_supabase(
                operator_name=operator.company,
                trust_score_result=trust_score_result,
                ntsb_result={
                    "score": ntsb_score,
                    "total_incidents": total_incidents,
                    "incidents": fleet_events
                },
                ucc_result=ucc_data,
                argus_rating=argus_rating,
                wyvern_rating=wyvern_rating
            )

            results.append({
                "operator_name": operator.company,
                "faa_state": operator.faa_state,
                "status": operator_status,
                "ntsb_score": ntsb_score,
                "trust_score": trust_score_result["trust_score"],
                "total_incidents": total_incidents,
                "ucc_states_processed": ucc_data.get("states_processed", 0),
                "saved_file": filename,
                "saved_to_supabase": saved_to_db,
                "live_view_url": ucc_data.get("live_view_url"),
                "session_id": ucc_data.get("session_id"),
                "errors": {
                    "ntsb": ntsb_error,
                    "ucc": ucc_error,
                    "trust_score": trust_score_error,
                },
            })

            successful += 1
            if saved_to_db:
                saved_to_supabase_count += 1
            if has_errors:
                print(f"  ✓ Verified {operator.company} (with errors in some steps)")
            else:
                print(f"  ✓ Successfully verified {operator.company}")

        except Exception as e:
            print(f"  ❌ Error verifying {operator.company}: {str(e)}")
            results.append({
                "operator_name": operator.company,
                "faa_state": operator.faa_state,
                "status": "failed",
                "error": str(e),
            })
            failed += 1

    # Summary
    print(f"\n{'='*80}")
    print(f"BATCH VERIFICATION COMPLETED")
    print(
        f"Total: {len(filtered_operators)}, Successful: {successful}, Failed: {failed}, Saved to Supabase: {saved_to_supabase_count}"
    )
    print(f"{'='*80}\n")

    return {
        "status": "completed",
        "message": f"Batch verification completed for {len(filtered_operators)} operators",
        "total_operators": len(filtered_operators),
        "successful": successful,
        "failed": failed,
        "saved_to_supabase": saved_to_supabase_count,
        "results": results,
    }
