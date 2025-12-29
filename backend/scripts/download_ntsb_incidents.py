"""
Download NTSB Incidents Script
Downloads NTSB incidents for all operators from the database
Outputs results to ntsb_incidents_<timestamp>.json
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from tqdm import tqdm

# Robust path resolution: Find 'backend' directory relative to this script
script_path = Path(__file__).resolve()
backend_dir = script_path.parent.parent
sys.path.insert(0, str(backend_dir))

# Load environment variables from .env file in backend directory
from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from sqlalchemy import func

from src.scoring.service import NTSBService
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


def get_operators_from_db(
    limit: int = None,
    cert_start: str = None,
    cert_end: str = None,
    only_null_ntsb: bool = False
) -> List[Dict[str, Any]]:
    """Load operators from the database

    Args:
        limit: Maximum number of operators to return
        cert_start: Filter operators where first char of certificate_number >= this value
        cert_end: Filter operators where first char of certificate_number <= this value
        only_null_ntsb: Filter operators that have no NTSB data yet
    """
    db = SessionLocal()
    try:
        query = db.query(Operator).order_by(Operator.name)

        if only_null_ntsb:
            query = query.filter(Operator.ntsb_incidents.is_(None))

        # Apply certificate_number filter if specified
        if cert_start or cert_end:
            first_char = func.substring(Operator.certificate_number, 1, 1)
            if cert_start and cert_end:
                query = query.filter(first_char.between(cert_start.upper(), cert_end.upper()))
            elif cert_start:
                query = query.filter(first_char >= cert_start.upper())
            elif cert_end:
                query = query.filter(first_char <= cert_end.upper())

        if limit:
            query = query.limit(limit)
        operators = query.all()
        return [
            {
                "operator_id": str(op.operator_id),
                "name": op.name,
                "dba_name": op.dba_name,
                "base_airport": op.base_airport,
                "regulatory_status": op.regulatory_status,
                "certificate_number": op.certificate_number
            }
            for op in operators
        ]
    finally:
        db.close()


async def download_ntsb_incidents(
    operator_id: str,
    operator_name: str
) -> Dict[str, Any]:
    """
    Download NTSB incidents for a single operator.

    Args:
        operator_id: UUID of the operator
        operator_name: Name of the operator to search for

    Returns:
        Dict with operator info and NTSB incidents
    """
    logger.info(f"Querying NTSB for: {operator_name}")

    result = {
        "operator_id": operator_id,
        "operator_name": operator_name,
        "query_date": datetime.now().isoformat(),
        "status": "pending"
    }

    try:
        # Query NTSB
        ntsb_data = await NTSBService.query_ntsb_incidents(operator_name)
        incidents = NTSBService.parse_ntsb_response(ntsb_data)
        total_incidents = len(incidents)
        ntsb_score = max(0, 100 - (total_incidents * 5))

        # Convert incidents to dict format
        ntsb_incidents_dict = [incident.dict() for incident in incidents]

        result["score"] = ntsb_score
        result["total_incidents"] = total_incidents
        result["incidents"] = ntsb_incidents_dict
        result["status"] = "completed"

        logger.info(f"[{operator_name}] Found {total_incidents} incidents, score: {ntsb_score}")

    except Exception as e:
        logger.error(f"[{operator_name}] Error querying NTSB: {type(e).__name__}: {str(e)}")
        result["status"] = "error"
        result["error"] = str(e)

    return result


def save_results(results: Dict, output_dir: str, datetime_suffix: str):
    """Save results to JSON file"""
    output_path = Path(output_dir)
    results_file = output_path / f"ntsb_incidents_{datetime_suffix}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Saved NTSB incidents to {results_file}")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Download NTSB incidents for operators from database")
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
        "--concurrency", "-c",
        type=int,
        default=5,
        help="Number of concurrent operators to process (default: 5)"
    )
    parser.add_argument(
        "--operator-id",
        type=str,
        default=None,
        help="Run for a single operator by ID (overrides database query)"
    )
    parser.add_argument(
        "--operator-name",
        type=str,
        default=None,
        help="Run for a single operator by name (no database required)"
    )
    parser.add_argument(
        "--cert-start",
        type=str,
        default=None,
        help="Filter operators where first char of certificate_number >= this value (e.g., 'A')"
    )
    parser.add_argument(
        "--cert-end",
        type=str,
        default=None,
        help="Filter operators where first char of certificate_number <= this value (e.g., 'M')"
    )
    parser.add_argument(
        "--only-null-ntsb",
        action="store_true",
        help="Run only for operators that have no NTSB data yet"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)"
    )

    args = parser.parse_args()

    # Generate datetime suffix for output files
    datetime_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Ensure output directory exists and add file handler for logging
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    log_file = output_path / f"ntsb_download_{datetime_suffix}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(file_handler)
    logger.info(f"Logging to: {log_file}")

    # Determine operators to process
    if args.operator_name:
        # Single operator by name (no database needed)
        operators = [{
            "operator_id": "manual",
            "name": args.operator_name
        }]
        logger.info(f"Running for single operator by name: {args.operator_name}")
    elif args.operator_id:
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
        operators = get_operators_from_db(
            limit=args.limit,
            cert_start=args.cert_start,
            cert_end=args.cert_end,
            only_null_ntsb=args.only_null_ntsb
        )
        filter_desc = ""
        if args.only_null_ntsb:
            filter_desc += " (only null NTSB data)"
        if args.cert_start or args.cert_end:
            filter_desc += f" (certificate filter: {args.cert_start or '*'} to {args.cert_end or '*'})"
        logger.info(f"Loaded {len(operators)} operators from database{filter_desc}")

    if not operators:
        logger.error("No operators found")
        sys.exit(1)

    # Build filter metadata
    filter_metadata = {}
    if args.cert_start or args.cert_end:
        filter_metadata["cert_filter"] = {
            "start": args.cert_start,
            "end": args.cert_end
        }
    if args.only_null_ntsb:
        filter_metadata["only_null_ntsb"] = True

    # Initialize result container
    results = {
        "metadata": {
            "start_time": datetime.now().isoformat(),
            "total_operators": len(operators),
            "source": "database" if not args.operator_name else "manual",
            "concurrency": args.concurrency,
            **filter_metadata
        },
        "operators": []
    }

    # Track statistics
    successful = 0
    failed = 0
    total_incidents = 0

    logger.info("=" * 70)
    logger.info("NTSB Incidents Download - Batch Processing")
    logger.info("=" * 70)
    logger.info(f"Operators: {len(operators)}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Concurrency: {args.concurrency}")
    logger.info(f"Delay between requests: {args.delay}s")
    if args.cert_start or args.cert_end:
        logger.info(f"Certificate filter: {args.cert_start or '*'} to {args.cert_end or '*'}")
    logger.info("=" * 70)

    # Semaphore for concurrency control
    semaphore = asyncio.Semaphore(args.concurrency)

    # Progress bar
    pbar = tqdm(total=len(operators), desc="Downloading NTSB Incidents", unit="op")

    async def process_operator(operator, delay: float):
        async with semaphore:
            try:
                # Update progress bar description
                pbar.set_postfix_str(f"Current: {operator['name'][:25]}...")

                result = await download_ntsb_incidents(
                    operator_id=operator["operator_id"],
                    operator_name=operator["name"]
                )

                # Add small delay to be respectful to NTSB API
                if delay > 0:
                    await asyncio.sleep(delay)

                pbar.update(1)
                return result
            except Exception as e:
                logger.error(f"Error processing {operator['name']}: {e}")
                pbar.update(1)
                return {
                    "operator_id": operator["operator_id"],
                    "operator_name": operator["name"],
                    "status": "error",
                    "error": str(e)
                }

    # Create tasks
    tasks = [process_operator(op, args.delay) for op in operators]

    # Run tasks
    try:
        operator_results = await asyncio.gather(*tasks)
    finally:
        pbar.close()

    # Process results
    for operator_result in operator_results:
        results["operators"].append(operator_result)

        if operator_result.get("status") == "completed":
            successful += 1
            total_incidents += operator_result.get("total_incidents", 0)
        else:
            failed += 1

    # Final metadata
    end_time = datetime.now().isoformat()
    results["metadata"]["end_time"] = end_time
    results["metadata"]["successful"] = successful
    results["metadata"]["failed"] = failed
    results["metadata"]["total_incidents_found"] = total_incidents

    # Save results
    save_results(results, args.output_dir, datetime_suffix)

    # Save summary
    summary = {
        "metadata": {
            "start_time": results["metadata"]["start_time"],
            "end_time": end_time,
            "total_operators": len(operators),
            "successful": successful,
            "failed": failed,
            "total_incidents_found": total_incidents,
            **filter_metadata
        },
        "operators_summary": [
            {
                "operator_id": r["operator_id"],
                "operator_name": r["operator_name"],
                "status": r["status"],
                "total_incidents": r.get("total_incidents", 0),
                "score": r.get("score")
            }
            for r in operator_results
        ]
    }
    summary_file = output_path / f"ntsb_summary_{datetime_suffix}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Saved summary to {summary_file}")

    logger.info("=" * 70)
    logger.info("Download Complete!")
    logger.info("=" * 70)
    logger.info(f"Results saved to:")
    logger.info(f"  - ntsb_incidents_{datetime_suffix}.json")
    logger.info(f"  - ntsb_summary_{datetime_suffix}.json")
    logger.info(f"  - ntsb_download_{datetime_suffix}.log")
    logger.info(f"Successful: {successful}/{len(operators)}")
    if failed > 0:
        logger.info(f"Failed: {failed}/{len(operators)}")
    logger.info(f"Total incidents found: {total_incidents}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
