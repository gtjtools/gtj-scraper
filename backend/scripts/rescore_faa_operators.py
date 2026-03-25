"""
Rescore operators that have matching FAA enforcement records.

Queries gtj.faa_enforcement_actions for all distinct normalized operator names,
cross-references against gtj.operators to find matching UUIDs, and triggers
the batch-verify-by-states scoring workflow for each matched operator.

Usage:
    python scripts/rescore_faa_operators.py
    python scripts/rescore_faa_operators.py --base-url http://prod-server:8000
    python scripts/rescore_faa_operators.py --dry-run
    python -m scripts.rescore_faa_operators
"""

import argparse
import re
import sys
import time
from datetime import datetime

import httpx
from sqlalchemy import func, text

# NOTE: Appending parent dir so this script can run standalone or as a module.
# When run as `python scripts/rescore_faa_operators.py` from backend/,
# the backend/ directory is already on sys.path. When run as a module,
# Python handles it. This import path covers both cases.
sys.path.insert(0, ".")

from src.common.config import SessionLocal
from src.common.models import FAAEnforcementAction, Operator


# ─── Name normalization (mirrors faa_enforcement_service.py) ──────────────────

_STRIP_SUFFIXES = re.compile(
    r"\b(?:LLC|INC|CORP|LTD|CO|LP|LLP|PC|PLLC|"
    r"INCORPORATED|CORPORATION|COMPANY|LIMITED|DBA)\b",
    re.IGNORECASE,
)


def _normalize_operator_name(raw_name: str) -> str:
    """Normalize an operator name identically to FAAEnforcementService."""
    if not raw_name:
        return ""
    name = _STRIP_SUFFIXES.sub("", raw_name)
    name = re.sub(r"[.,]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.upper()


# ─── Database query ───────────────────────────────────────────────────────────

def find_matched_operators() -> list[dict]:
    """
    Find operators that have matching FAA enforcement records.

    Joins gtj.faa_enforcement_actions (by operator_name_normalized) against
    gtj.operators (normalizing the operator name at query time) and returns
    distinct matches with operator_id and name.

    Returns:
        List of dicts with keys: operator_id, operator_name, faa_names, action_count
    """
    db = SessionLocal()
    try:
        # Get all distinct normalized names from FAA enforcement table
        faa_names_rows = (
            db.query(FAAEnforcementAction.operator_name_normalized)
            .distinct()
            .all()
        )
        faa_normalized_names: set[str] = {row[0] for row in faa_names_rows}

        if not faa_normalized_names:
            print("No FAA enforcement records found in database.")
            return []

        print(f"Found {len(faa_normalized_names)} distinct operator names in FAA enforcement data.")

        # Get all operators and normalize their names for matching
        operators = db.query(Operator.operator_id, Operator.name).all()
        print(f"Found {len(operators)} total operators in gtj.operators.")

        # Build lookup: normalized_name -> list of (operator_id, original_name)
        matches: list[dict] = []
        for operator_id, operator_name in operators:
            normalized = _normalize_operator_name(operator_name)
            if normalized in faa_normalized_names:
                # Count how many FAA actions match this operator
                action_count = (
                    db.query(func.count(FAAEnforcementAction.id))
                    .filter(FAAEnforcementAction.operator_name_normalized == normalized)
                    .scalar()
                )
                matches.append({
                    "operator_id": str(operator_id),
                    "operator_name": operator_name,
                    "normalized_name": normalized,
                    "action_count": action_count,
                })

        return matches

    finally:
        db.close()


# ─── Rescoring ────────────────────────────────────────────────────────────────

def rescore_operators(
    matches: list[dict],
    base_url: str,
    delay_seconds: float,
    dry_run: bool = False,
) -> dict:
    """
    Trigger batch-verify-by-states for each matched operator.

    Args:
        matches: List of operator match dicts from find_matched_operators().
        base_url: Backend API base URL (e.g., http://localhost:8000).
        delay_seconds: Pause between API calls to avoid overwhelming Hatchet.
        dry_run: If True, log what would be done without making API calls.

    Returns:
        Summary dict with counts of success, failure, and skipped.
    """
    total = len(matches)
    succeeded = 0
    failed = 0
    failures: list[dict] = []

    endpoint = f"{base_url.rstrip('/')}/scoring/batch-verify-by-states"

    print(f"\n{'=' * 80}")
    if dry_run:
        print(f"DRY RUN: Would rescore {total} operators via {endpoint}")
    else:
        print(f"Rescoring {total} operators via {endpoint}")
    print(f"Delay between calls: {delay_seconds}s")
    print(f"{'=' * 80}\n")

    with httpx.Client(timeout=30.0) as client:
        for idx, match in enumerate(matches, start=1):
            operator_id = match["operator_id"]
            operator_name = match["operator_name"]
            action_count = match["action_count"]

            label = f"[{idx}/{total}] {operator_name} ({operator_id}) - {action_count} FAA action(s)"

            if dry_run:
                print(f"  DRY RUN {label}")
                succeeded += 1
                continue

            try:
                response = client.post(
                    endpoint,
                    params={"operator_id": operator_id},
                )
                response.raise_for_status()
                data = response.json()
                workflow_id = data.get("workflow_run_id", "unknown")
                print(f"  OK {label} -> workflow {workflow_id}")
                succeeded += 1

            except httpx.HTTPStatusError as exc:
                error_msg = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                print(f"  FAIL {label} -> {error_msg}")
                failed += 1
                failures.append({"operator_name": operator_name, "error": error_msg})

            except httpx.RequestError as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                print(f"  FAIL {label} -> {error_msg}")
                failed += 1
                failures.append({"operator_name": operator_name, "error": error_msg})

            # Throttle between calls (skip delay after the last one)
            if idx < total and not dry_run:
                time.sleep(delay_seconds)

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "failures": failures,
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rescore operators with matching FAA enforcement records.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between API calls (default: 2.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log matched operators without triggering rescoring",
    )
    args = parser.parse_args()

    start_time = datetime.now()
    print(f"\n{'=' * 80}")
    print(f"FAA ENFORCEMENT OPERATOR RESCORE")
    print(f"Started: {start_time.isoformat()}")
    print(f"{'=' * 80}\n")

    # Step 1: Find matched operators
    print("Step 1: Querying database for FAA enforcement <-> operator matches...")
    matches = find_matched_operators()

    if not matches:
        print("\nNo operator matches found. Nothing to rescore.")
        sys.exit(0)

    print(f"\nFound {len(matches)} operators with FAA enforcement records:")
    for m in matches:
        print(f"  - {m['operator_name']} ({m['action_count']} action(s))")

    # Step 2: Trigger rescoring
    print("\nStep 2: Triggering rescore workflows...")
    summary = rescore_operators(
        matches=matches,
        base_url=args.base_url,
        delay_seconds=args.delay,
        dry_run=args.dry_run,
    )

    # Step 3: Print summary
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'=' * 80}")
    print(f"RESCORE SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total operators matched:  {summary['total']}")
    print(f"  Successfully triggered:   {summary['succeeded']}")
    print(f"  Failed:                   {summary['failed']}")
    print(f"  Elapsed time:             {elapsed:.1f}s")

    if summary["failures"]:
        print(f"\nFailed operators:")
        for f in summary["failures"]:
            print(f"  - {f['operator_name']}: {f['error']}")

    print(f"{'=' * 80}\n")

    # Exit with non-zero if any failures occurred
    if summary["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
