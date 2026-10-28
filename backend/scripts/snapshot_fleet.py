#!/usr/bin/env python3
"""
Capture a monthly fleet snapshot, so TrustScore v5.0's `Churn_Fleet` becomes
computable.

RUN THIS MONTHLY. Churn (§3) is a 12-month differential — TailsAdded and
TailsRemoved against a baseline fleet size — and cannot be derived from current
state. gtj.aircraft is updated in place and keeps no history, so a month that
is not captured is a month that cannot be reconstructed afterwards. Until two
or more months exist, `Churneffective` stays 0 and no operator is penalised for
shedding or rapidly onboarding aircraft.

USAGE
-----
    python scripts/snapshot_fleet.py                 # snapshot the current month
    python scripts/snapshot_fleet.py --dry-run       # counts only, no writes
    python scripts/snapshot_fleet.py --month 2026-09 # backfill a labelled month
    python scripts/snapshot_fleet.py --churn         # report churn from history

SUGGESTED CRON (first of the month, 03:00)
    0 3 1 * * cd /home/gtjadmin/gtj-scraper/backend && \\
              venv/bin/python3 scripts/snapshot_fleet.py >> ~/fleet-snapshot.log 2>&1

Idempotent: a unique constraint on (operator_id, tail_number, snapshot_month)
means re-running within the same month updates rather than duplicating.

A NOTE ON --month
-----------------
Backfilling only labels *today's* fleet with an earlier month. It does not
recover what the fleet actually was then — nothing knows that. Use it to seed a
baseline when starting out, and be aware the first churn figures computed
against a backfilled month will understate real movement.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402

SOURCE = "gtj.aircraft"


def _month_start(value: Optional[str]) -> date:
    """
    Normalise to the first of the month.

    Snapshots are labelled by month rather than by run date so two snapshots
    compare exactly, regardless of which day the job happened to fire.
    """
    if value:
        try:
            parsed = datetime.strptime(value, "%Y-%m")
        except ValueError:
            raise SystemExit(f"--month must look like 2026-09, got {value!r}")
        return parsed.date().replace(day=1)
    return datetime.now(timezone.utc).date().replace(day=1)


def fetch_current_fleet() -> List[Dict[str, Any]]:
    """Every tail currently attached to an operator."""
    session = SessionLocal()
    try:
        return [dict(r) for r in session.execute(text("""
            SELECT a.operator_id, o.name AS operator_name,
                   a.tail_number, a.make_model
            FROM gtj.aircraft a
            JOIN gtj.operators o ON o.operator_id = a.operator_id
            ORDER BY o.name, a.tail_number
        """)).mappings()]
    finally:
        session.close()


def write_snapshot(rows: List[Dict[str, Any]], month: date) -> int:
    """
    Upsert one row per tail for the given month.

    ON CONFLICT DO UPDATE rather than DO NOTHING: a re-run within the same month
    should refresh the denormalised name and model, not silently keep stale
    values from earlier in the month.
    """
    if not rows:
        return 0

    session = SessionLocal()
    written = 0
    try:
        for row in rows:
            session.execute(text("""
                INSERT INTO gtj.fleet_snapshots
                    (operator_id, operator_name, tail_number, make_model,
                     snapshot_month, source)
                VALUES
                    (:operator_id, :operator_name, :tail_number, :make_model,
                     :snapshot_month, :source)
                ON CONFLICT (operator_id, tail_number, snapshot_month)
                DO UPDATE SET
                    operator_name = EXCLUDED.operator_name,
                    make_model    = EXCLUDED.make_model,
                    captured_at   = now(),
                    source        = EXCLUDED.source
            """), {**row, "snapshot_month": month, "source": SOURCE})
            written += 1
        session.commit()
        return written
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def report_churn(months_back: int = 12) -> None:
    """
    Show churn per operator from whatever history exists.

    Mirrors §3: contraction weighted 1.0, expansion free to 25% then weighted
    0.50, capped at 0.65. Reported here for inspection — the calculator does its
    own arithmetic from the same rows.
    """
    session = SessionLocal()
    try:
        months = [r[0] for r in session.execute(text("""
            SELECT DISTINCT snapshot_month FROM gtj.fleet_snapshots
            ORDER BY snapshot_month DESC LIMIT :n
        """), {"n": months_back + 1})]

        if len(months) < 2:
            print(f"\n  Only {len(months)} snapshot month(s) recorded.")
            print("  Churn needs at least two to compute a differential, and")
            print("  twelve for the figure the specification describes.\n")
            return

        latest, baseline = months[0], months[-1]
        print(f"\n  Comparing {baseline} -> {latest} "
              f"({len(months)} month(s) of history)\n")

        rows = session.execute(text("""
            WITH now_f AS (
                SELECT operator_id, operator_name, tail_number
                FROM gtj.fleet_snapshots WHERE snapshot_month = :latest
            ),
            then_f AS (
                SELECT operator_id, tail_number
                FROM gtj.fleet_snapshots WHERE snapshot_month = :baseline
            )
            SELECT
                COALESCE(n.operator_name, 'unknown') AS name,
                COUNT(DISTINCT t.tail_number) AS baseline_size,
                COUNT(DISTINCT n.tail_number) FILTER (
                    WHERE n.tail_number NOT IN (
                        SELECT tail_number FROM then_f t2
                        WHERE t2.operator_id = n.operator_id)) AS added,
                COUNT(DISTINCT t.tail_number) FILTER (
                    WHERE t.tail_number NOT IN (
                        SELECT tail_number FROM now_f n2
                        WHERE n2.operator_id = t.operator_id)) AS removed
            FROM then_f t
            FULL OUTER JOIN now_f n
              ON n.operator_id = t.operator_id AND n.tail_number = t.tail_number
            GROUP BY 1
            HAVING COUNT(DISTINCT t.tail_number) > 0
            ORDER BY 4 DESC, 3 DESC
            LIMIT 25
        """), {"latest": latest, "baseline": baseline}).mappings()

        print(f"  {'operator':<40} {'base':>5} {'+':>4} {'-':>4} {'churn':>7}")
        print("  " + "-" * 64)
        for r in rows:
            base = r["baseline_size"] or 1
            contraction = (r["removed"] or 0) / base
            expansion = (r["added"] or 0) / base
            churn = min(0.65, contraction + 0.50 * max(0.0, expansion - 0.25))
            if churn > 0:
                print(f"  {r['name'][:38]:<40} {base:>5} {r['added']:>4} "
                      f"{r['removed']:>4} {churn:>7.3f}")
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a monthly fleet snapshot for Churn_Fleet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--month", help="label the snapshot YYYY-MM (default: this month)")
    parser.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    parser.add_argument("--churn", action="store_true",
                        help="report churn from existing history instead of snapshotting")
    args = parser.parse_args()

    if args.churn:
        report_churn()
        return 0

    month = _month_start(args.month)
    print(f"\n{'=' * 70}")
    print("  FLEET SNAPSHOT")
    print(f"  month : {month}")
    print(f"  mode  : {'DRY RUN (no writes)' if args.dry_run else 'LIVE'}")
    print(f"{'=' * 70}\n")

    rows = fetch_current_fleet()
    operators = len({r["operator_id"] for r in rows})
    print(f"  tails     : {len(rows):,}")
    print(f"  operators : {operators:,}")

    if args.dry_run:
        print("\n  Dry run — nothing written.\n")
        return 0

    written = write_snapshot(rows, month)
    print(f"  written   : {written:,} rows\n")

    session = SessionLocal()
    try:
        total_months = session.execute(text(
            "SELECT COUNT(DISTINCT snapshot_month) FROM gtj.fleet_snapshots"
        )).scalar()
    finally:
        session.close()

    print(f"  snapshot months on record: {total_months}")
    if total_months < 2:
        print("  Churn needs at least two months to compute anything; run again")
        print("  next month. Twelve gives the figure the specification describes.")
    elif total_months < 12:
        print(f"  Partial signal available. {12 - total_months} more month(s) for")
        print("  the full 12-month differential.")
    else:
        print("  Twelve months on record — Churn_Fleet is fully computable.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
