"""
Full Scoring Flow Script (Database Version)
Runs NTSB + UCC + TrustScore calculation for all operators from the database
Outputs results to separate files: ntsb_results.json, ucc_results.json, aircraft_ratings.json
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

# Load environment variables from .env file in parent directory (backend/)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Add parent directory (backend) to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.scoring.service import NTSBService
from src.scoring.ucc_service import UCCVerificationService
from src.trustscore.calculator import TrustScoreCalculator, FleetScoreData, TailScoreData
from src.trustscore.llm_client import LLMClient, LLMProvider
from src.common.config import SessionLocal
from src.common.models import Operator

# Configure logging (file handler added later with output directory)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_operators_from_db(limit: int = None) -> List[Dict[str, Any]]:
    """Load operators from the database"""
    db = SessionLocal()
    try:
        query = db.query(Operator).order_by(Operator.name)
        if limit:
            query = query.limit(limit)
        operators = query.all()
        return [
            {
                "operator_id": str(op.operator_id),
                "name": op.name,
                "dba_name": op.dba_name,
                "base_airport": op.base_airport,
                "regulatory_status": op.regulatory_status
            }
            for op in operators
        ]
    finally:
        db.close()


async def run_full_scoring_flow(
    operator_id: str,
    operator_name: str,
    faa_state: str = "FL",
    state: str = None,
    use_browserbase: bool = True
) -> Dict[str, Any]:
    """
    Run full scoring flow for a single operator.

    Args:
        operator_id: UUID of the operator
        operator_name: Name of the operator to verify
        faa_state: FAA state code (2-letter abbreviation) - used as fallback
        state: Optional state code for UCC search override
        use_browserbase: Whether to run UCC verification (requires Browserbase)

    Returns:
        Combined scoring results with NTSB, UCC, and TrustScore data
    """
    logger.info("=" * 80)
    logger.info(f"FULL SCORING FLOW FOR: {operator_name} (ID: {operator_id})")
    logger.info("=" * 80)

    result = {
        "operator_id": operator_id,
        "operator_name": operator_name,
        "verification_date": datetime.now().isoformat(),
        "status": "pending"
    }

    try:
        # Step 1: Query NTSB
        logger.info(f"[{operator_name}] Step 1: Querying NTSB database...")
        ntsb_data = await NTSBService.query_ntsb_incidents(operator_name)
        incidents = NTSBService.parse_ntsb_response(ntsb_data)
        total_incidents = len(incidents)
        ntsb_score = max(0, 100 - (total_incidents * 5))

        logger.info(f"[{operator_name}] NTSB check complete: {total_incidents} incidents found, score: {ntsb_score}")

        # Convert incidents to dict format
        ntsb_incidents_dict = [incident.dict() for incident in incidents]

        result["ntsb"] = {
            "operator_id": operator_id,
            "operator_name": operator_name,
            "score": ntsb_score,
            "total_incidents": total_incidents,
            "incidents": ntsb_incidents_dict,
        }

        # Step 2: Verify UCC filings (optional)
        ucc_filings = []
        if use_browserbase:
            logger.info(f"[{operator_name}] Step 2: Verifying UCC filings with Browserbase...")
            ucc_service = UCCVerificationService()
            ntsb_results = ntsb_data.get("Results", [])

            try:
                ucc_data = await ucc_service.verify_ucc_filings(
                    operator_name, ntsb_results, faa_state, state
                )
                logger.info(f"[{operator_name}] UCC check complete: {ucc_data.get('status')}")

                # Extract UCC filings from the verification result
                visited_states = ucc_data.get("visited_states", [])
                for state_result in visited_states:
                    if state_result.get("flow_used") and state_result.get("flow_result"):
                        flow_result = state_result["flow_result"]
                        filings = flow_result.get("filings", [])
                        for filing in filings:
                            ucc_filings.append({
                                "status": filing.get("status", "Unknown"),
                                "filing_date": filing.get("filing_date", "Unknown"),
                                "debtor": filing.get("debtor_name", filing.get("debtor", "Unknown")),
                                "secured_party": filing.get("secured_party", "Unknown"),
                                "collateral": filing.get("collateral", "Unknown"),
                                "state": state_result.get("state", "Unknown")
                            })

                ucc_data["operator_id"] = operator_id
                ucc_data["operator_name"] = operator_name
                result["ucc"] = ucc_data
            except Exception as e:
                logger.warning(f"[{operator_name}] UCC verification failed: {str(e)}")
                result["ucc"] = {"operator_id": operator_id, "operator_name": operator_name, "status": "error", "error": str(e)}
        else:
            logger.info(f"[{operator_name}] Step 2: Skipping UCC verification (Browserbase disabled)")
            result["ucc"] = {"operator_id": operator_id, "operator_name": operator_name, "status": "skipped", "message": "Browserbase disabled"}

        # Step 3: Calculate TrustScore
        logger.info(f"[{operator_name}] Step 3: Calculating TrustScore...")

        fleet_data = FleetScoreData(
            operator_name=operator_name,
            operator_age_years=10.0,  # Default
            ntsb_incidents=ntsb_incidents_dict,
            ucc_filings=ucc_filings,
            argus_rating=None,
            wyvern_rating=None,
            bankruptcy_history=None,
            faa_violations=None
        )

        tail_data = TailScoreData(
            aircraft_age_years=5.0,  # Default
            operator_name=operator_name,
            registered_owner=operator_name,
            fractional_owner=False,
            ntsb_incidents=ntsb_incidents_dict
        )

        # Try with LLM, fallback to basic calculation
        try:
            llm_client = LLMClient(provider=LLMProvider.OPENROUTER)
            calculator = TrustScoreCalculator(llm_client=llm_client)
            trust_score_result = await calculator.calculate_trust_score(fleet_data, tail_data)
            logger.info(f"[{operator_name}] TrustScore calculated: {trust_score_result['trust_score']}")
        except Exception as e:
            logger.warning(f"[{operator_name}] Error calculating TrustScore with LLM: {str(e)}")
            calculator = TrustScoreCalculator(llm_client=None)
            trust_score_result = await calculator.calculate_trust_score(fleet_data, tail_data)
            trust_score_result["llm_error"] = str(e)
            logger.info(f"[{operator_name}] TrustScore calculated (without LLM): {trust_score_result['trust_score']}")

        trust_score_result["operator_id"] = operator_id
        trust_score_result["operator_name"] = operator_name
        result["trust_score"] = trust_score_result
        result["combined_score"] = trust_score_result["trust_score"]
        result["status"] = "completed"

        logger.info("=" * 80)
        logger.info(f"[{operator_name}] FULL SCORING FLOW COMPLETED")
        logger.info(f"[{operator_name}] NTSB Score: {ntsb_score}, TrustScore: {trust_score_result['trust_score']}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"[{operator_name}] Full scoring flow error: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        result["status"] = "error"
        result["error"] = str(e)

    return result


def save_separate_results(ntsb_results: Dict, ucc_results: Dict, aircraft_ratings: Dict, output_dir: str = ".", datetime_suffix: str = ""):
    """Save results to separate JSON files"""
    output_path = Path(output_dir)

    # Save NTSB results
    ntsb_file = output_path / f"ntsb_results_{datetime_suffix}.json"
    with open(ntsb_file, 'w') as f:
        json.dump(ntsb_results, f, indent=2, default=str)
    logger.info(f"Saved NTSB results to {ntsb_file}")

    # Save UCC results
    ucc_file = output_path / f"ucc_results_{datetime_suffix}.json"
    with open(ucc_file, 'w') as f:
        json.dump(ucc_results, f, indent=2, default=str)
    logger.info(f"Saved UCC results to {ucc_file}")

    # Save Aircraft ratings (TrustScore)
    ratings_file = output_path / f"aircraft_ratings_{datetime_suffix}.json"
    with open(ratings_file, 'w') as f:
        json.dump(aircraft_ratings, f, indent=2, default=str)
    logger.info(f"Saved aircraft ratings to {ratings_file}")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Run full scoring flow for operators from database")
    parser.add_argument(
        "--output-dir", "-o",
        default=".",
        help="Output directory for JSON files (default: current directory)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of operators to process (for testing)"
    )
    parser.add_argument(
        "--faa-state",
        default="FL",
        help="Default FAA state code for UCC fallback (default: FL)"
    )
    parser.add_argument(
        "--no-browserbase",
        action="store_true",
        help="Skip UCC verification (don't use Browserbase)"
    )
    parser.add_argument(
        "--operator-id",
        type=str,
        default=None,
        help="Run for a single operator by ID (overrides database query)"
    )

    args = parser.parse_args()

    # Generate datetime suffix for output files
    datetime_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Ensure output directory exists and add file handler for logging
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    log_file = output_path / f"scoring_flow_{datetime_suffix}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(file_handler)
    logger.info(f"Logging to: {log_file}")

    # Determine operators to process
    if args.operator_id:
        # Fetch single operator from database
        db = SessionLocal()
        try:
            from uuid import UUID
            op = db.query(Operator).filter(Operator.operator_id == UUID(args.operator_id)).first()
            if not op:
                logger.error(f"Operator not found with ID: {args.operator_id}")
                sys.exit(1)
            operators = [{
                "operator_id": str(op.operator_id),
                "name": op.name,
                "dba_name": op.dba_name,
                "base_airport": op.base_airport,
                "regulatory_status": op.regulatory_status
            }]
            logger.info(f"Running for single operator: {op.name} (ID: {args.operator_id})")
        finally:
            db.close()
    else:
        operators = get_operators_from_db(limit=args.limit)
        logger.info(f"Loaded {len(operators)} operators from database")

    if not operators:
        logger.error("No operators found in database")
        sys.exit(1)

    # Initialize separate result containers
    ntsb_results = {
        "metadata": {
            "start_time": datetime.now().isoformat(),
            "total_operators": len(operators),
            "source": "database"
        },
        "operators": []
    }

    ucc_results = {
        "metadata": {
            "start_time": datetime.now().isoformat(),
            "total_operators": len(operators),
            "browserbase_enabled": not args.no_browserbase,
            "source": "database"
        },
        "operators": []
    }

    aircraft_ratings = {
        "metadata": {
            "start_time": datetime.now().isoformat(),
            "total_operators": len(operators),
            "source": "database"
        },
        "operators": []
    }

    # Track processed operators and errors
    processed_operators = []
    failed_operators = []

    logger.info("=" * 70)
    logger.info("Full Scoring Flow - Batch Processing (Database Source)")
    logger.info("=" * 70)
    logger.info(f"Operators: {len(operators)}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Browserbase: {'Enabled' if not args.no_browserbase else 'Disabled'}")
    logger.info("=" * 70)

    # Process each operator
    for i, operator in enumerate(operators, 1):
        logger.info(f"[{i}/{len(operators)}] Processing: {operator['name']} (ID: {operator['operator_id']})")
        logger.info("-" * 50)

        operator_result = await run_full_scoring_flow(
            operator_id=operator["operator_id"],
            operator_name=operator["name"],
            faa_state=args.faa_state,
            use_browserbase=not args.no_browserbase
        )

        # Track success/failure
        if operator_result.get("status") == "completed":
            processed_operators.append({
                "operator_id": operator["operator_id"],
                "operator_name": operator["name"],
                "combined_score": operator_result.get("combined_score"),
                "ntsb_score": operator_result.get("ntsb", {}).get("score"),
                "ntsb_incidents": operator_result.get("ntsb", {}).get("total_incidents", 0)
            })
        else:
            failed_operators.append({
                "operator_id": operator["operator_id"],
                "operator_name": operator["name"],
                "status": operator_result.get("status"),
                "error": operator_result.get("error", "Unknown error")
            })

        # Separate results into different categories
        if "ntsb" in operator_result:
            ntsb_results["operators"].append(operator_result["ntsb"])

        if "ucc" in operator_result:
            ucc_results["operators"].append(operator_result["ucc"])

        if "trust_score" in operator_result:
            aircraft_ratings["operators"].append(operator_result["trust_score"])

        # Save intermediate results to separate files
        save_separate_results(ntsb_results, ucc_results, aircraft_ratings, args.output_dir, datetime_suffix)

        # Small delay between operators to be respectful
        if i < len(operators):
            logger.info("Waiting 2 seconds before next operator...")
            await asyncio.sleep(2)

    # Final save with end time
    end_time = datetime.now().isoformat()
    ntsb_results["metadata"]["end_time"] = end_time
    ucc_results["metadata"]["end_time"] = end_time
    aircraft_ratings["metadata"]["end_time"] = end_time

    save_separate_results(ntsb_results, ucc_results, aircraft_ratings, args.output_dir, datetime_suffix)

    # Save summary file
    summary_data = {
        "metadata": {
            "start_time": ntsb_results["metadata"]["start_time"],
            "end_time": end_time,
            "total_operators": len(operators),
            "successful": len(processed_operators),
            "failed": len(failed_operators),
            "browserbase_enabled": not args.no_browserbase,
            "source": "database"
        },
        "processed_operators": processed_operators
    }
    summary_file = output_path / f"summary_{datetime_suffix}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary_data, f, indent=2, default=str)
    logger.info(f"Saved summary to {summary_file}")

    # Save errors file (only if there are errors)
    if failed_operators:
        errors_data = {
            "metadata": {
                "start_time": ntsb_results["metadata"]["start_time"],
                "end_time": end_time,
                "total_failed": len(failed_operators)
            },
            "failed_operators": failed_operators
        }
        errors_file = output_path / f"errors_{datetime_suffix}.json"
        with open(errors_file, 'w') as f:
            json.dump(errors_data, f, indent=2, default=str)
        logger.info(f"Saved errors to {errors_file}")

    logger.info("=" * 70)
    logger.info("Processing Complete!")
    logger.info("=" * 70)
    logger.info(f"Results saved to:")
    logger.info(f"  - ntsb_results_{datetime_suffix}.json")
    logger.info(f"  - ucc_results_{datetime_suffix}.json")
    logger.info(f"  - aircraft_ratings_{datetime_suffix}.json")
    logger.info(f"  - summary_{datetime_suffix}.json")
    if failed_operators:
        logger.info(f"  - errors_{datetime_suffix}.json")
    logger.info(f"  - scoring_flow_{datetime_suffix}.log")

    # Summary
    logger.info(f"Successful: {len(processed_operators)}/{len(operators)}")
    if failed_operators:
        logger.info(f"Failed: {len(failed_operators)}/{len(operators)}")

    return {
        "ntsb": ntsb_results,
        "ucc": ucc_results,
        "aircraft_ratings": aircraft_ratings
    }


if __name__ == "__main__":
    asyncio.run(main())
