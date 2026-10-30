#!/usr/bin/env python3
"""
Ingest the FAA Part 135 certificate holder roster into gtj.certificate_dbas.

RUN THIS MONTHLY. The roster is point-in-time: it lists each certificate
designator with the name it operates under *today*. A rebrand is only visible
as a difference between two months, so a month not ingested is a rename that
may never be observed. Names already recorded are never deleted — a name that
stops appearing is exactly the one an old NTSB or FAA filing will be under.

WHY THIS MATTERS (TrustScore v5.0 §8)
-------------------------------------
Every pipeline currently searches by one current marketing name, so an operator
that rebrands sheds its history and scores as though it had none. The DBA array
this builds is what lets a lookup ask "every name this certificate has used"
instead.

USAGE
-----
    python scripts/ingest_part135.py --dry-run      # report, write nothing
    python scripts/ingest_part135.py                # ingest today's roster
    python scripts/ingest_part135.py --backfill     # also walk web.archive.org
    python scripts/ingest_part135.py --report       # show known rebrands

SUGGESTED CRON (2nd of the month, 04:00 — after the fleet snapshot)
    0 4 2 * * cd /home/gtjadmin/gtj-scraper/backend && \\
              venv/bin/python3 scripts/ingest_part135.py >> ~/part135.log 2>&1

ON --backfill
-------------
web.archive.org holds snapshots of this file back to roughly March 2023.
Walking them recovers renames that happened before ingestion started — the only
way to see backwards. It is slow and rate-limited, so it is opt-in and intended
to be run once.

WHAT THIS FILE DOES NOT PROVIDE
-------------------------------
No DBA column and no certificate issue date. `Age_cert` (§3) therefore still
falls back to 10.0 years, which inflates Cs. That needs a different FAA source.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import openpyxl  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402
from src.trustscore.adapter_v5 import normalize_operator_name  # noqa: E402

PART135_URL = (
    "https://www.faa.gov/about/officeorg/headquartersoffices/avs/"
    "faa-certificated-aircraft-operators-legal-part-135-holders.xlsx"
)
PART135_PAGE = PART135_URL[: -len(".xlsx")]

CDX_URL = "http://web.archive.org/cdx/search/cdx"
WAYBACK = "http://web.archive.org/web/{ts}id_/{url}"

#: Column positions in the roster: CFR, CHDO, DSGN, Name, M/M/S, Reg No, Serial.
COL_DSGN, COL_NAME, COL_TAIL = 2, 3, 5

_HTTP_TIMEOUT = 120.0
#: Pause between archive fetches. archive.org returns 429 readily.
_ARCHIVE_DELAY = 3.0


def fetch_roster(url: str) -> Optional[bytes]:
    """Download a roster workbook, returning None rather than raising."""
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as exc:
        print(f"    ⚠ fetch failed: {str(exc)[:70]}")
        return None


def parse_roster(blob: bytes) -> Dict[str, Dict[str, Any]]:
    """
    Reduce a roster workbook to {designator: {name, tails}}.

    One row per aircraft, so a certificate appears many times; the name is taken
    from the first row seen and tails are accumulated for the fleet count.
    """
    workbook = openpyxl.load_workbook(BytesIO(blob), read_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    next(rows, None)  # header

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if len(row) <= COL_NAME:
            continue
        designator = str(row[COL_DSGN] or "").strip().upper()
        name = str(row[COL_NAME] or "").strip()
        if not designator or not name:
            continue
        entry = out.setdefault(designator, {"name": name, "tails": set()})
        tail = str(row[COL_TAIL] or "").strip().upper() if len(row) > COL_TAIL else ""
        if tail:
            entry["tails"].add(tail)
    return out


def upsert_names(
    roster: Dict[str, Dict[str, Any]],
    observed: date,
    is_current: bool,
    source: str = "faa_part135",
) -> Tuple[int, int]:
    """
    Record every (designator, name) pair seen in a roster.

    A name already present has its `last_seen` extended; a new name is inserted.
    Nothing is ever deleted — a name that disappears from the roster is the
    former identity, which is the whole point of the table.

    `is_current` is only set true for the live roster, and is cleared from the
    other names of any certificate whose current name has changed.

    Returns:
        (rows_inserted, rows_updated)
    """
    if not roster:
        return 0, 0

    # Built as one multi-row statement rather than a loop of single inserts.
    # Per-row round trips through PgBouncer took minutes for 1,794 rows and
    # timed out; batching makes it one statement and a couple of seconds.
    payload = []
    for designator, entry in roster.items():
        normalized = normalize_operator_name(entry["name"])
        if not normalized:
            continue
        payload.append({
            "d": designator, "n": entry["name"], "nn": normalized,
            "cur": is_current, "seen": observed, "src": source,
        })
    if not payload:
        return 0, 0

    session = SessionLocal()
    try:
        before = session.execute(
            text("SELECT COUNT(*) FROM gtj.certificate_dbas")
        ).scalar() or 0

        session.execute(text("""
            INSERT INTO gtj.certificate_dbas
                (certificate_designator, operator_name, operator_name_normalized,
                 is_current, first_seen, last_seen, source)
            VALUES (:d, :n, :nn, :cur, :seen, :seen, :src)
            ON CONFLICT (certificate_designator, operator_name_normalized)
            DO UPDATE SET
                last_seen  = GREATEST(gtj.certificate_dbas.last_seen, EXCLUDED.last_seen),
                first_seen = LEAST(gtj.certificate_dbas.first_seen, EXCLUDED.first_seen),
                is_current = EXCLUDED.is_current OR gtj.certificate_dbas.is_current,
                updated_at = now()
        """), payload)

        # Only one name per certificate is current, so demote the rest when
        # ingesting the live roster. Done as a single set-based statement for
        # the same reason as above.
        if is_current:
            session.execute(text("""
                UPDATE gtj.certificate_dbas d
                SET is_current = false, updated_at = now()
                FROM (
                    SELECT UNNEST(CAST(:designators AS text[])) AS designator,
                           UNNEST(CAST(:names AS text[]))       AS name
                ) cur
                WHERE d.certificate_designator = cur.designator
                  AND d.operator_name_normalized <> cur.name
                  AND d.is_current = true
            """), {
                "designators": [row["d"] for row in payload],
                "names": [row["nn"] for row in payload],
            })

        after = session.execute(
            text("SELECT COUNT(*) FROM gtj.certificate_dbas")
        ).scalar() or 0
        session.commit()

        inserted = after - before
        return inserted, len(payload) - inserted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def seed_from_operators() -> int:
    """
    Add names already present in gtj.operators.

    An operator row often carries a trade name while the FAA roster carries the
    legal entity — a difference that already breaks lookups today, before any
    rebrand is considered. Both belong in the array.
    """
    session = SessionLocal()
    try:
        rows = session.execute(text("""
            SELECT faa_dsgn_code, name, dba_name, faa_operator_name
            FROM gtj.operators
            WHERE faa_dsgn_code IS NOT NULL AND faa_dsgn_code <> ''
        """)).mappings().all()

        today = datetime.now(timezone.utc).date()

        # Collected then inserted in one statement — see upsert_names for why.
        # Deduplicated here because an operator's name, dba_name and
        # faa_operator_name often normalise to the same value, and a multi-row
        # INSERT cannot ON CONFLICT against a duplicate inside its own payload.
        seen_pairs = set()
        payload = []
        for row in rows:
            designator = str(row["faa_dsgn_code"]).strip().upper()
            for candidate in (row["name"], row["dba_name"], row["faa_operator_name"]):
                if not candidate:
                    continue
                normalized = normalize_operator_name(str(candidate))
                if not normalized or (designator, normalized) in seen_pairs:
                    continue
                seen_pairs.add((designator, normalized))
                payload.append({
                    "d": designator, "n": str(candidate).strip(),
                    "nn": normalized, "seen": today,
                })

        if not payload:
            return 0

        before = session.execute(
            text("SELECT COUNT(*) FROM gtj.certificate_dbas")
        ).scalar() or 0

        session.execute(text("""
            INSERT INTO gtj.certificate_dbas
                (certificate_designator, operator_name, operator_name_normalized,
                 is_current, first_seen, last_seen, source)
            VALUES (:d, :n, :nn, false, :seen, :seen, 'gtj.operators')
            ON CONFLICT (certificate_designator, operator_name_normalized)
            DO NOTHING
        """), payload)

        after = session.execute(
            text("SELECT COUNT(*) FROM gtj.certificate_dbas")
        ).scalar() or 0
        session.commit()
        return after - before
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def archive_snapshots(limit: int = 60) -> List[str]:
    """
    Timestamps of archived roster pages, oldest first, one per month.

    `collapse=timestamp:6` asks the CDX index for one capture per YYYYMM, which
    is the granularity a rename is visible at.
    """
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(CDX_URL, params={
                "url": PART135_PAGE, "output": "text",
                "fl": "timestamp,statuscode",
                "collapse": "timestamp:6", "limit": limit,
            })
            response.raise_for_status()
    except Exception as exc:
        print(f"  ⚠ archive index unreachable: {str(exc)[:70]}")
        return []

    stamps = []
    for line in response.text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "200":
            stamps.append(parts[0])
    return sorted(stamps)


def backfill_from_archive() -> None:
    """
    Walk archived rosters to recover renames that predate ingestion.

    This is the only way to see backwards: the live roster knows only today's
    name. Rate-limited, and intended to be run once.
    """
    stamps = archive_snapshots()
    if not stamps:
        print("  No archived snapshots available.")
        return

    print(f"  {len(stamps)} archived snapshot(s), {stamps[0][:6]} to {stamps[-1][:6]}\n")
    for index, stamp in enumerate(stamps, start=1):
        observed = datetime.strptime(stamp[:8], "%Y%m%d").date()
        print(f"  [{index}/{len(stamps)}] {observed} …", end=" ", flush=True)

        blob = fetch_roster(WAYBACK.format(ts=stamp, url=PART135_URL))
        if not blob or not blob.startswith(b"PK"):
            print("no workbook")
            time.sleep(_ARCHIVE_DELAY)
            continue

        try:
            roster = parse_roster(blob)
        except Exception as exc:
            print(f"unparseable ({str(exc)[:40]})")
            time.sleep(_ARCHIVE_DELAY)
            continue

        ins, upd = upsert_names(roster, observed, is_current=False,
                                source=f"faa_part135_archive")
        print(f"{len(roster):,} certs — {ins} new name(s)")
        time.sleep(_ARCHIVE_DELAY)


def report_rebrands() -> None:
    """Show certificates recorded under more than one name."""
    session = SessionLocal()
    try:
        rows = session.execute(text("""
            SELECT certificate_designator,
                   COUNT(*) AS names,
                   MIN(first_seen) AS first_seen,
                   STRING_AGG(operator_name, ' | ' ORDER BY first_seen) AS all_names
            FROM gtj.certificate_dbas
            GROUP BY certificate_designator
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, certificate_designator
            LIMIT 40
        """)).mappings().all()

        total = session.execute(text(
            "SELECT COUNT(DISTINCT certificate_designator) FROM gtj.certificate_dbas"
        )).scalar()
        names = session.execute(text(
            "SELECT COUNT(*) FROM gtj.certificate_dbas"
        )).scalar()

        print(f"\n  certificates tracked : {total:,}")
        print(f"  names recorded       : {names:,}")
        print(f"  with multiple names  : {len(rows):,}\n")
        for row in rows:
            print(f"    {row['certificate_designator']}  ({row['names']}) "
                  f"{row['all_names'][:88]}")
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest the FAA Part 135 roster into gtj.certificate_dbas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--backfill", action="store_true",
                        help="also walk web.archive.org for historical rosters")
    parser.add_argument("--report", action="store_true",
                        help="show certificates with more than one recorded name")
    parser.add_argument("--no-seed", dest="seed", action="store_false", default=True,
                        help="skip seeding names from gtj.operators")
    args = parser.parse_args()

    if args.report:
        report_rebrands()
        return 0

    print(f"\n{'=' * 70}")
    print("  FAA PART 135 ROSTER INGEST")
    print(f"  mode : {'DRY RUN (no writes)' if args.dry_run else 'LIVE'}")
    print(f"  time : {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 70}\n")

    print("  fetching current roster…")
    blob = fetch_roster(PART135_URL)
    if not blob:
        print("\n  Could not fetch the roster. Nothing written.\n")
        return 1

    roster = parse_roster(blob)
    tails = sum(len(v["tails"]) for v in roster.values())
    print(f"    {len(roster):,} certificates, {tails:,} tails")

    if args.dry_run:
        print("\n  Dry run — nothing written.\n")
        return 0

    today = datetime.now(timezone.utc).date()
    ins, upd = upsert_names(roster, today, is_current=True)
    print(f"    {ins:,} new name(s), {upd:,} existing confirmed")

    if args.seed:
        print("\n  seeding names from gtj.operators…")
        print(f"    {seed_from_operators():,} additional name(s)")

    if args.backfill:
        print("\n  walking web.archive.org for historical rosters…")
        print("  (slow and rate-limited; intended to be run once)\n")
        backfill_from_archive()

    report_rebrands()
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
