#!/usr/bin/env python3
"""
Backfill lien history from archived FAA registry snapshots.

WHY THIS EXISTS
---------------
DOCINDEX.txt inside ReleasableAircraft.zip is a rolling window — measured at
206 days in the January-2025 archive — and the FAA overwrites the file nightly.
Once a filing ages out it is gone from every public flat file; only FAA CARES
holds it permanently, and CARES refuses us (docs §9.6).

So the live ingest can only ever see the last ~6 months. Everything older is
recoverable *today* from web.archive.org and unrecoverable once those captures
are the only copy and we have not read them.

Measured: the January-2025 and May-2026 captures share **zero** filings — 5,803
rows exist only in the first, 2,279 only in the second. Each capture is a
disjoint slice of history, so this is additive rather than redundant.

web.archive.org holds **67 captures of the registry zip since 2023**. At ~66 MB
each that is ~4.4 GB if you take all of them; `--every-days 90` samples instead,
which guarantees overlap against a 206-day window and cuts it to roughly a
dozen downloads.

USAGE
-----
    python scripts/backfill_tail_liens.py --list           # show captures, fetch nothing
    python scripts/backfill_tail_liens.py --max-captures 4 # try a few first
    python scripts/backfill_tail_liens.py                  # full backfill
    python scripts/backfill_tail_liens.py --every-days 180 # coarser, fewer downloads

RUN IT DETACHED. Each capture is ~66 MB and web.archive.org is slow — observed
around 1.5 MB/min from a laptop, so a dozen captures is hours, not minutes.

    tmux new -s backfill
    venv/bin/python3 -u scripts/backfill_tail_liens.py 2>&1 | tee ~/backfill.log

ON IDEMPOTENCY
--------------
Rows upsert on the same key the live ingest uses — (tail, doc_type, doc_date,
doc_id) — so re-running costs bandwidth and changes nothing. `first_seen` keeps
the earliest observation; `last_seen` advances.

WHAT THIS DOES NOT DO
---------------------
It does not make `legal_title` green. Even three years of DOCINDEX is still a
window, not the permanent record, and a lien filed in 2019 and never released
remains invisible. It narrows the gap; CARES closes it.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402
from src.common.faa_registry import (  # noqa: E402
    DOCINDEX_FILE,
    LIEN_DOC_TYPES,
    RELEASE_DOC_TYPES,
    parse_docindex,
    read_member,
)

REGISTRY_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
CDX_URL = "http://web.archive.org/cdx/search/cdx"
#: `id_` returns the original bytes rather than an archive-rewritten page.
WAYBACK = "http://web.archive.org/web/{ts}id_/{url}"

SOURCE = "faa_docindex_archive"

_HTTP_TIMEOUT = 1800.0
#: The archive is ~66 MB; anything much smaller is an error page.
_MIN_ARCHIVE_BYTES = 20_000_000
#: web.archive.org rate-limits readily.
_ARCHIVE_DELAY = 5.0


def list_captures(every_days: int, since: str = "2023") -> List[str]:
    """
    Wayback timestamps for the registry zip, thinned to ~`every_days` apart.

    Thinning here rather than downloading everything: captures cluster (29 in
    2026 alone), and consecutive ones hold nearly identical DOCINDEX windows.
    Spacing below the ~206-day window guarantees no blind spot.
    """
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(CDX_URL, params={
                "url": REGISTRY_URL.replace("https://", ""),
                "output": "json",
                "filter": "statuscode:200",
                "from": since,
            })
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        print(f"  ⚠️  CDX query failed: {type(exc).__name__}: {str(exc)[:140]}")
        return []

    if not payload or len(payload) < 2:
        return []

    stamps = sorted(row[1] for row in payload[1:])
    kept: List[str] = []
    last: Optional[date] = None
    for stamp in stamps:
        try:
            when = datetime.strptime(stamp[:8], "%Y%m%d").date()
        except ValueError:
            continue
        if last is None or (when - last).days >= every_days:
            kept.append(stamp)
            last = when
    return kept


def fetch_capture(stamp: str, destination: Path) -> bool:
    """Download one archived zip. Returns False rather than raising."""
    url = WAYBACK.format(ts=stamp, url=REGISTRY_URL)
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    print(f"    HTTP {response.status_code}")
                    return False
                written = 0
                with destination.open("wb") as handle:
                    for chunk in response.iter_bytes(chunk_size=1 << 20):
                        handle.write(chunk)
                        written += len(chunk)
        if written < _MIN_ARCHIVE_BYTES:
            print(f"    only {written:,} bytes — treating as an error page")
            return False
        print(f"    {written:,} bytes")
        return True
    except Exception as exc:
        print(f"    download failed: {type(exc).__name__}: {str(exc)[:120]}")
        return False


def d085_tails(db) -> Set[str]:
    """The Part 135 charter fleet — the only tails worth storing liens for."""
    return {
        r[0] for r in db.execute(text("""
            SELECT DISTINCT tail_number FROM gtj.fleet_snapshots
            WHERE source = 'opspecs_d085'
        """))
    }


def ingest_capture(db, archive: Path, wanted: Set[str], dry_run: bool) -> Dict:
    """
    Upsert the lien filings in one archived capture.

    Release netting is intentionally NOT done here. A release may sit in a
    different capture from the lien it discharges, so deciding
    `superseded_by_release` per-capture would mark liens active that a later
    window shows released. `reconcile_releases` does it once, across everything
    stored.
    """
    blob = read_member(str(archive), DOCINDEX_FILE)
    if blob is None:
        return {"error": f"no {DOCINDEX_FILE}"}

    liens: List = []
    releases = 0
    rows = 0
    dates: List[date] = []
    for record in parse_docindex(blob):
        rows += 1
        if record.doc_date:
            dates.append(record.doc_date)
        if record.tail_number not in wanted:
            continue
        if record.doc_type in LIEN_DOC_TYPES:
            liens.append(record)
        elif record.doc_type in RELEASE_DOC_TYPES:
            releases += 1

    # Collapse to one row per financing, matching the live ingest: a lender
    # files once per collateral item, so DOC-ID distinguishes documents while
    # (tail, type, date, doc_id) is the storage key.
    deduped: Dict[Tuple, object] = {}
    for record in liens:
        key = (record.tail_number, record.doc_type, record.doc_date,
               record.doc_id or "")
        if key not in deduped:
            deduped[key] = record
    unique = list(deduped.values())

    stats = {
        "docindex_rows": rows,
        "window_from": min(dates) if dates else None,
        "window_to": max(dates) if dates else None,
        "part135_liens": len(liens),
        "unique_filings": len(unique),
        "releases_seen": releases,
        "written": 0,
    }

    if dry_run or not unique:
        return stats

    today = datetime.now(timezone.utc).date()
    BATCH = 500
    for start in range(0, len(unique), BATCH):
        chunk = unique[start:start + BATCH]
        values, params = [], {"source": SOURCE, "seen": today}
        for i, record in enumerate(chunk):
            values.append(
                f"(:tl{i}, :dt{i}, :dd{i}, :pt{i}, :di{i}, false, "
                f":wu{i}, :source, :seen, :seen)"
            )
            params[f"tl{i}"] = record.tail_number
            params[f"dt{i}"] = record.doc_type
            params[f"dd{i}"] = record.doc_date
            params[f"pt{i}"] = (record.party or "")[:255] or None
            params[f"di{i}"] = (record.doc_id or "")[:32] or None
            # How far back THIS capture's window reached, not today's.
            params[f"wu{i}"] = stats["window_from"]

        db.execute(text(f"""
            INSERT INTO gtj.tail_liens
                (tail_number, doc_type, doc_date, party, doc_id,
                 superseded_by_release, observed_in_window_until,
                 source, first_seen, last_seen)
            VALUES {', '.join(values)}
            ON CONFLICT (tail_number, doc_type,
                         COALESCE(doc_date, DATE '1900-01-01'),
                         COALESCE(doc_id, ''))
            DO UPDATE SET
                -- Keep the earliest observation and the widest window; a
                -- backfilled capture legitimately reaches further back than
                -- the live file that may already hold this row.
                observed_in_window_until = LEAST(
                    gtj.tail_liens.observed_in_window_until,
                    EXCLUDED.observed_in_window_until),
                first_seen = LEAST(gtj.tail_liens.first_seen,
                                   EXCLUDED.first_seen),
                party = COALESCE(gtj.tail_liens.party, EXCLUDED.party),
                updated_at = now()
        """), params)
        stats["written"] += len(chunk)

    db.commit()
    return stats


def reconcile_releases(db) -> int:
    """
    Net liens against releases across everything stored, in one pass.

    Must run after all captures are in: a release and the lien it discharges
    often sit in different 180-day windows, so per-capture netting would leave
    liens marked active that a later capture shows released.

    A release dated on or after a lien, for the same tail, discharges it.
    """
    result = db.execute(text("""
        UPDATE gtj.tail_liens AS lien
        SET superseded_by_release = true, updated_at = now()
        WHERE lien.doc_type IN ('S/A', 'CSC')
          AND lien.superseded_by_release = false
          AND EXISTS (
            SELECT 1 FROM gtj.tail_liens AS rel
            WHERE rel.tail_number = lien.tail_number
              AND rel.doc_type IN ('REL', 'REP')
              AND rel.doc_date IS NOT NULL
              AND lien.doc_date IS NOT NULL
              AND rel.doc_date >= lien.doc_date
          )
    """))
    db.commit()
    return result.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill lien history from archived FAA registry snapshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--list", action="store_true",
                        help="show which captures would be fetched, then exit")
    parser.add_argument("--every-days", type=int, default=90,
                        help="minimum spacing between captures (default: 90, "
                             "safely under the ~206-day DOCINDEX window)")
    parser.add_argument("--max-captures", type=int, default=None,
                        help="stop after N captures — use this first")
    parser.add_argument("--since", default="2023",
                        help="earliest capture year (default: 2023)")
    parser.add_argument("--dry-run", action="store_true",
                        help="download and parse, write nothing")
    args = parser.parse_args()

    print(f"\n{'=' * 72}")
    print("  FAA LIEN HISTORY BACKFILL")
    print(f"  spacing : >= {args.every_days} days between captures")
    if args.dry_run:
        print("  MODE    : dry run — nothing will be written")
    print(f"{'=' * 72}\n")

    print("  querying web.archive.org…")
    stamps = list_captures(args.every_days, args.since)
    if not stamps:
        print("  no captures found.")
        return 1

    if args.max_captures:
        stamps = stamps[-args.max_captures:]   # newest first — most relevant
    print(f"  {len(stamps)} capture(s) selected, ~66 MB each "
          f"(~{len(stamps) * 66 / 1024:.1f} GB total)\n")

    for stamp in stamps:
        print(f"    {datetime.strptime(stamp[:8], '%Y%m%d').date()}  ({stamp})")

    if args.list:
        print("\n  --list: nothing fetched.\n")
        return 0

    db = SessionLocal()
    try:
        wanted = d085_tails(db)
        print(f"\n  Part 135 tails to match: {len(wanted):,}\n")

        before = db.execute(text("SELECT COUNT(*) FROM gtj.tail_liens")).scalar()
        totals = {"written": 0, "failed": 0}

        for index, stamp in enumerate(stamps, start=1):
            when = datetime.strptime(stamp[:8], "%Y%m%d").date()
            print(f"  [{index}/{len(stamps)}] {when}")

            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "r.zip"
                if not fetch_capture(stamp, archive):
                    totals["failed"] += 1
                    continue

                stats = ingest_capture(db, archive, wanted, args.dry_run)
                if "error" in stats:
                    print(f"    {stats['error']}")
                    totals["failed"] += 1
                    continue

                print(f"    window {stats['window_from']} .. {stats['window_to']}"
                      f"  ({stats['docindex_rows']:,} rows)")
                print(f"    Part 135: {stats['part135_liens']} filings"
                      f" → {stats['unique_filings']} unique"
                      f" → {stats['written']} written")
                totals["written"] += stats["written"]

            import time
            time.sleep(_ARCHIVE_DELAY)

        if not args.dry_run:
            print("\n  reconciling releases across all stored captures…")
            discharged = reconcile_releases(db)
            print(f"    {discharged:,} lien(s) marked released")

            after = db.execute(text("SELECT COUNT(*) FROM gtj.tail_liens")).scalar()
            active = db.execute(text("""
                SELECT COUNT(DISTINCT (doc_type, doc_date, party))
                FROM gtj.tail_liens WHERE superseded_by_release = false
            """)).scalar()
            span = db.execute(text("""
                SELECT MIN(doc_date), MAX(doc_date) FROM gtj.tail_liens
            """)).first()

            print(f"\n{'=' * 72}")
            print(f"  rows        : {before:,} → {after:,}  (+{after - before:,})")
            print(f"  active encumbrances : {active:,}")
            print(f"  history span: {span[0]} .. {span[1]}")
            print(f"  captures failed: {totals['failed']}")
            print(f"{'=' * 72}\n")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
