#!/usr/bin/env python3
"""
Ingest the FAA Part 135 D085 aircraft authorization table into fleet_snapshots.

RUN THIS WEEKLY. The FAA publishes the nationwide D085 table as a public
spreadsheet and overwrites it in place, so a week not captured is a week of
fleet movement that cannot be reconstructed from the FAA (only, partially, from
web.archive.org — see --backfill).

WHAT THIS IS, AND WHY IT IS NOT gtj.aircraft
--------------------------------------------
D085 is the operations specification page listing the aircraft an operator is
*legally authorized* to fly for hire. The signed document lives in the FAA's
internal WebOPSS portal, but the fleet table inside it is published weekly for
exactly this purpose: letting brokers verify legal charter tails.

That makes it the authoritative Vf for TrustScore v5.0 §3, and a different
thing from gtj.aircraft, which is JETNET's commercial view of what an operator
*has*. Both are written to gtj.fleet_snapshots, discriminated by `source`:

    source = 'gtj.aircraft'   JETNET  — what the operator holds
    source = 'opspecs_d085'   FAA     — what it may fly for hire

Keeping both is deliberate. A tail in JETNET but absent from D085 is flying
without charter authorization, which is a finding in itself; collapsing the two
would hide it. Migration 080 widened the unique constraint to include `source`
so the two can coexist per tail per month.

WHAT IT MAKES COMPUTABLE
------------------------
Churn_Fleet (§3): TailsAdded and TailsRemoved over a trailing 12 months, as a
set difference of N-numbers per certificate designator between two snapshots.
Until this runs for two or more months, Churneffective stays 0 and no operator
is penalised for shedding or rapidly onboarding aircraft.

USAGE
-----
    python scripts/ingest_d085.py --dry-run      # report, write nothing
    python scripts/ingest_d085.py                # ingest this week's roster
    python scripts/ingest_d085.py --backfill     # walk web.archive.org first
    python scripts/ingest_d085.py --churn        # report churn from what exists

SUGGESTED CRON (Mondays, 03:00 — the FAA refreshes over the weekend)
    0 3 * * 1 cd /home/gtjadmin/gtj-scraper/backend && \\
              venv/bin/python3 scripts/ingest_d085.py >> ~/d085.log 2>&1

ON SNAPSHOT GRANULARITY
-----------------------
Rows are stamped with the first of the month, matching fleet_snapshots'
existing convention, so a weekly run overwrites that month's rows rather than
accumulating four near-identical copies. Weekly cadence still matters: it means
the month is captured even if one run fails, and the last run of the month is
the one that sticks.

ON --backfill
-------------
The FAA keeps no history of this file. web.archive.org holds snapshots back to
roughly 2023, which is the only way to obtain a trailing-12-month baseline
without waiting a year. Archived captures are sparse and unevenly spaced, so
backfilled months are whatever the Wayback Machine actually holds — recorded
honestly rather than interpolated.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import openpyxl  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402

PART135_URL = (
    "https://www.faa.gov/about/officeorg/headquartersoffices/avs/"
    "faa-certificated-aircraft-operators-legal-part-135-holders.xlsx"
)

CDX_URL = "http://web.archive.org/cdx/search/cdx"
#: `id_` asks for the original bytes rather than the archive's rewritten page.
WAYBACK = "http://web.archive.org/web/{ts}id_/{url}"

SOURCE = "opspecs_d085"

#: Verified against the live file on 2026-11-08:
#: CFR | CHDO | DSGN | Name | Aircraft M/M/S | Registration No. | Serial No.
COL_DSGN, COL_NAME, COL_MMS, COL_TAIL, COL_SERIAL = 2, 3, 4, 5, 6

_HTTP_TIMEOUT = 120.0
#: archive.org returns 429 readily; this is deliberately unhurried.
_ARCHIVE_DELAY = 3.0

#: Rows below this are treated as a truncated or changed download rather than a
#: real shrinkage. The live file carries ~11,500 rows; a genuine FAA change
#: would not halve it in a week, and overwriting a good month with a partial
#: file loses data that cannot be recovered.
_MIN_PLAUSIBLE_ROWS = 6000


def fetch_roster(url: str) -> Optional[bytes]:
    """Download a roster workbook. Returns None rather than raising."""
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as exc:
        print(f"  ⚠️  download failed: {type(exc).__name__}: {str(exc)[:120]}")
        return None


#: Longest value gtj.fleet_snapshots.tail_number accepts.
_TAIL_MAX = 10


def clean_tail(raw: str) -> Optional[str]:
    """
    Normalise a roster registration value, or None if it is not a US N-number.

    The roster is hand-maintained and carries a few values that are not plain
    tails (observed 2026-11-08, 4 of 11,482):

        'N325CT EXCLUSIVE USE'   annotation appended to a real tail
        'NFA3HTYPAP3/USA'        foreign registration placeholder

    Taking the first whitespace-delimited token recovers the real tail from the
    first. The second has no N-number to recover and is dropped — writing it
    would either overflow the column or invent a tail that does not exist.
    """
    token = str(raw or "").strip().upper().split()[0] if str(raw or "").strip() else ""
    if not token:
        return None

    # Foreign/placeholder forms carry a country suffix; there is no US tail here.
    if "/" in token:
        return None

    if not token.startswith("N"):
        token = f"N{token}"

    # A real N-number is N + 1-5 alphanumerics. Anything longer is malformed
    # rather than merely unusual, and must not be silently truncated into a
    # different aircraft's tail.
    if len(token) > _TAIL_MAX or len(token) < 2 or not token[1:].isalnum():
        return None

    return token


def parse_roster(blob: bytes) -> List[Tuple[str, str, str, str, str]]:
    """
    (designator, operator_name, tail, make_model, serial) per authorized aircraft.

    Rows without a designator or a usable tail are skipped: the roster carries a
    few certificate-level rows with no aircraft, plus a handful of malformed
    registration values — see clean_tail.
    """
    workbook = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]

    out: List[Tuple[str, str, str, str, str]] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row or len(row) <= COL_SERIAL:
            continue
        dsgn = str(row[COL_DSGN] or "").strip().upper()
        tail = clean_tail(row[COL_TAIL])
        if not dsgn or not tail:
            continue
        out.append((
            dsgn,
            str(row[COL_NAME] or "").strip(),
            tail,
            str(row[COL_MMS] or "").strip(),
            str(row[COL_SERIAL] or "").strip(),
        ))

    workbook.close()
    return out


def operators_by_designator(db) -> Dict[str, Tuple[str, str]]:
    """designator -> (operator_id, name), for attaching roster rows to our rows."""
    return {
        r[0].strip().upper(): (str(r[1]), r[2])
        for r in db.execute(text("""
            SELECT faa_dsgn_code, operator_id, name
            FROM gtj.operators
            WHERE faa_dsgn_code IS NOT NULL AND faa_dsgn_code <> ''
        """))
        if r[0]
    }


def write_snapshot(db, rows, snapshot_month: date, dry_run: bool) -> Dict[str, int]:
    """
    Upsert one month of D085 rows.

    Only operators we already know are written: a snapshot row needs an
    operator_id (the column is NOT NULL and a foreign key), and inventing
    operators from the roster is a different job from recording fleet state.
    Unmatched certificates are counted and reported rather than dropped
    silently.
    """
    known = operators_by_designator(db)

    matched: List[Tuple] = []
    unmatched: Set[str] = set()
    for dsgn, name, tail, mms, _serial in rows:
        if dsgn not in known:
            unmatched.add(dsgn)
            continue
        operator_id, our_name = known[dsgn]
        matched.append((operator_id, our_name or name, tail, mms[:100] or None))

    stats = {
        "roster_rows": len(rows),
        "matched": len(matched),
        "unmatched_certs": len(unmatched),
        "operators": len({m[0] for m in matched}),
        "written": 0,
    }

    if dry_run or not matched:
        return stats

    # Batched multi-row upserts: one statement per row made a full ingest take
    # minutes against a remote database at ~250ms latency.
    BATCH = 500
    for start in range(0, len(matched), BATCH):
        chunk = matched[start:start + BATCH]
        values, params = [], {"month": snapshot_month, "source": SOURCE}
        for i, (operator_id, operator_name, tail, mms) in enumerate(chunk):
            values.append(
                f"(:op{i}, :nm{i}, :tl{i}, :mm{i}, :month, now(), :source)"
            )
            params[f"op{i}"] = operator_id
            params[f"nm{i}"] = operator_name
            params[f"tl{i}"] = tail
            params[f"mm{i}"] = mms
        db.execute(text(f"""
            INSERT INTO gtj.fleet_snapshots
                (operator_id, operator_name, tail_number, make_model,
                 snapshot_month, captured_at, source)
            VALUES {', '.join(values)}
            ON CONFLICT (operator_id, tail_number, snapshot_month, source)
            DO UPDATE SET operator_name = EXCLUDED.operator_name,
                          make_model    = EXCLUDED.make_model,
                          captured_at   = now()
        """), params)
        stats["written"] += len(chunk)

    db.commit()
    return stats


def report_churn(db, months_back: int = 12) -> None:
    """
    Churn from the D085 snapshots that exist, as a set difference of tails.

    Prints the inputs §3 needs — TailsAdded, TailsRemoved, BaselineVf — rather
    than Churneffective itself, which the calculator owns.
    """
    months = [
        r[0] for r in db.execute(text("""
            SELECT DISTINCT snapshot_month FROM gtj.fleet_snapshots
            WHERE source = :source ORDER BY snapshot_month DESC
        """), {"source": SOURCE})
    ]
    if len(months) < 2:
        print(f"\n  Only {len(months)} D085 snapshot(s) so far — churn needs two.")
        print("  Run weekly; the metric becomes meaningful once two months exist.")
        return

    current = months[0]
    # Closest snapshot at or before the 12-month mark, or the oldest we hold.
    baseline = next(
        (m for m in months if (current - m).days >= months_back * 28),
        months[-1],
    )

    print(f"\n  current  : {current}")
    print(f"  baseline : {baseline}  ({(current - baseline).days} days earlier)")

    def fleet_at(month: date) -> Dict[str, Set[str]]:
        out: Dict[str, Set[str]] = defaultdict(set)
        for operator_id, tail in db.execute(text("""
            SELECT operator_id, tail_number FROM gtj.fleet_snapshots
            WHERE source = :source AND snapshot_month = :month
        """), {"source": SOURCE, "month": month}):
            out[str(operator_id)].add(tail)
        return out

    now_fleet, then_fleet = fleet_at(current), fleet_at(baseline)
    names = {
        str(r[0]): r[1]
        for r in db.execute(text("SELECT operator_id, name FROM gtj.operators"))
    }

    moved = []
    for operator_id in set(now_fleet) | set(then_fleet):
        now_set = now_fleet.get(operator_id, set())
        then_set = then_fleet.get(operator_id, set())
        added, removed = now_set - then_set, then_set - now_set
        if added or removed:
            moved.append((
                names.get(operator_id, operator_id)[:38],
                len(then_set), len(now_set), len(added), len(removed),
            ))

    moved.sort(key=lambda r: -(r[3] + r[4]))
    print(f"\n  {len(moved):,} operator(s) changed fleet between those snapshots\n")
    print(f"  {'operator':<40}{'base':>6}{'now':>6}{'+':>5}{'-':>5}")
    print(f"  {'-' * 62}")
    for name, base, now_n, added, removed in moved[:25]:
        print(f"  {name:<40}{base:>6}{now_n:>6}{added:>5}{removed:>5}")
    if len(moved) > 25:
        print(f"  … and {len(moved) - 25:,} more")


def backfill(db, dry_run: bool) -> None:
    """
    Walk web.archive.org for historical rosters.

    The FAA overwrites this file, so the archive is the only route to a
    trailing-12-month baseline without waiting a year. One capture per month is
    enough — snapshot_month is monthly — so later captures in an
    already-ingested month are skipped.
    """
    print("\n  querying web.archive.org for historical captures…")
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            response = client.get(CDX_URL, params={
                "url": PART135_URL,
                "output": "json",
                "filter": "statuscode:200",
                "collapse": "timestamp:6",   # one capture per month
            })
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        print(f"  ⚠️  CDX query failed: {type(exc).__name__}: {str(exc)[:120]}")
        return

    if not payload or len(payload) < 2:
        print("  no captures found.")
        return

    stamps = [row[1] for row in payload[1:]]          # row[0] is the header
    print(f"  {len(stamps)} monthly capture(s) available")

    have = {
        r[0] for r in db.execute(text("""
            SELECT DISTINCT snapshot_month FROM gtj.fleet_snapshots
            WHERE source = :source
        """), {"source": SOURCE})
    }

    for stamp in stamps:
        captured = datetime.strptime(stamp[:8], "%Y%m%d").date()
        month = captured.replace(day=1)
        if month in have:
            print(f"  {month} already ingested, skipping")
            continue

        print(f"  {month} ← capture {stamp}")
        blob = fetch_roster(WAYBACK.format(ts=stamp, url=PART135_URL))
        time.sleep(_ARCHIVE_DELAY)
        if not blob:
            continue

        try:
            rows = parse_roster(blob)
        except Exception as exc:
            print(f"    ⚠️  unreadable workbook: {type(exc).__name__}")
            continue

        if len(rows) < _MIN_PLAUSIBLE_ROWS:
            print(f"    ⚠️  only {len(rows):,} rows — treating as partial, skipping")
            continue

        stats = write_snapshot(db, rows, month, dry_run)
        print(f"    {stats['matched']:,} matched / {stats['roster_rows']:,} rows"
              f" → {stats['written']:,} written")
        have.add(month)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest the FAA Part 135 D085 fleet table into fleet_snapshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be written, change nothing")
    parser.add_argument("--backfill", action="store_true",
                        help="also walk web.archive.org for historical rosters")
    parser.add_argument("--churn", action="store_true",
                        help="report churn from existing snapshots and exit")
    parser.add_argument("--month", default=None,
                        help="stamp as this month (YYYY-MM-DD); default: today")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.churn:
            report_churn(db)
            return 0

        if args.backfill:
            backfill(db, args.dry_run)

        month = (
            datetime.strptime(args.month, "%Y-%m-%d").date().replace(day=1)
            if args.month
            else datetime.now(timezone.utc).date().replace(day=1)
        )

        print(f"\n{'=' * 72}")
        print("  FAA PART 135 D085 FLEET INGEST")
        print(f"  source : {PART135_URL.rsplit('/', 1)[-1]}")
        print(f"  month  : {month}")
        if args.dry_run:
            print("  MODE   : dry run — nothing will be written")
        print(f"{'=' * 72}\n")

        blob = fetch_roster(PART135_URL)
        if not blob:
            print("  Could not download the roster. Nothing written.")
            return 1
        print(f"  downloaded {len(blob):,} bytes")

        rows = parse_roster(blob)
        print(f"  parsed {len(rows):,} authorized aircraft")

        # Refuse to overwrite a good month with a partial file.
        if len(rows) < _MIN_PLAUSIBLE_ROWS:
            print(f"\n  ⚠️  Only {len(rows):,} rows, expected ≥{_MIN_PLAUSIBLE_ROWS:,}.")
            print("  Treating as a truncated download rather than a real change.")
            print("  Nothing written — re-run, or pass --month to force a specific month.")
            return 1

        stats = write_snapshot(db, rows, month, args.dry_run)

        print(f"\n  matched to our operators : {stats['matched']:,}")
        print(f"  distinct operators       : {stats['operators']:,}")
        print(f"  certificates not known   : {stats['unmatched_certs']:,}")
        print(f"  rows written             : {stats['written']:,}")

        if not args.dry_run:
            total = db.execute(text("""
                SELECT COUNT(*), COUNT(DISTINCT snapshot_month)
                FROM gtj.fleet_snapshots WHERE source = :source
            """), {"source": SOURCE}).first()
            print(f"\n  {SOURCE} total: {total[0]:,} rows across {total[1]} month(s)")
            if total[1] < 2:
                print("  Churn needs two months — it stays 0 until the next run.")

        print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
