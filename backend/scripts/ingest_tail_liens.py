#!/usr/bin/env python3
"""
Ingest FAA DOCINDEX lien filings into gtj.tail_liens.

RUN THIS WEEKLY. DOCINDEX is a ~180-day rolling suspense index that the FAA
overwrites in place, so a filing that enters and leaves the window between two
runs is never observed — and cannot be recovered from the FAA afterwards.

WHAT THIS MAKES COMPUTABLE
--------------------------
Lientail (§4.2): the flat charge for an active mechanic's or tax lien against a
specific airframe. Until this table has rows, `tail_lien_events` is always
empty and no aircraft is ever charged for an encumbrance.

WHAT IT CANNOT TELL YOU
-----------------------
Absence of rows is NOT clear title. DOCINDEX only lists filings *received* in
roughly the last 180 days; a lien recorded two years ago and never released is
simply not in the file. Every row therefore carries
`observed_in_window_until`, and the scorer must keep reporting
GAP_TAIL_LIENS until the permanent record (FAA CARES) is ingested. Treating an
empty result as clearance is the same error as treating an unqueried source as
clean.

The FAA index also does not distinguish mechanic's from tax liens — both are
filed as S/A — so §4.2's separate charges cannot be told apart from this source.

USAGE
-----
    python scripts/ingest_tail_liens.py --dry-run        # report, write nothing
    python scripts/ingest_tail_liens.py                  # download + ingest
    python scripts/ingest_tail_liens.py --archive F.zip  # use a local zip
    python scripts/ingest_tail_liens.py --report         # show what is stored

SUGGESTED CRON (Tuesdays 03:00 — after Monday's D085 ingest)
    0 3 * * 2 cd /home/gtjadmin/gtj-scraper/backend && \\
              venv/bin/python3 scripts/ingest_tail_liens.py >> ~/liens.log 2>&1

ON THE DOWNLOAD
---------------
registry.faa.gov sits behind Akamai and refuses some clients outright (observed
403/503 from one network while www.faa.gov served fine from the same machine).
The download therefore retries, follows redirects, and fails loudly rather than
writing a partial result. `--archive` exists so an operator who obtained the
zip another way — or a backfill from web.archive.org — can still ingest it.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402
from src.common.faa_registry import (  # noqa: E402
    DOCINDEX_FILE,
    DOCINDEX_WINDOW_DAYS,
    LIEN_DOC_TYPES,
    RELEASE_DOC_TYPES,
    parse_docindex,
    read_member,
)

REGISTRY_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"

SOURCE = "faa_docindex"

_HTTP_TIMEOUT = 900.0
#: The archive is ~68 MB; anything much smaller is an error page, not a zip.
_MIN_ARCHIVE_BYTES = 20_000_000

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def download_archive(destination: Path) -> bool:
    """
    Fetch ReleasableAircraft.zip. Returns False rather than raising.

    Size-checked before being accepted: Akamai answers a refused request with a
    small HTML error page, and handing that to zipfile produces a confusing
    "not a zip file" rather than the real cause.
    """
    print(f"  downloading {REGISTRY_URL}")
    try:
        with httpx.Client(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _UA, "Accept": "application/zip,*/*"},
        ) as client:
            with client.stream("GET", REGISTRY_URL) as response:
                if response.status_code != 200:
                    print(f"  ⚠️  HTTP {response.status_code} from registry.faa.gov")
                    print("      This host sits behind Akamai and refuses some")
                    print("      networks. Use --archive with a zip obtained")
                    print("      elsewhere, or run from the production server.")
                    return False
                written = 0
                with destination.open("wb") as handle:
                    for chunk in response.iter_bytes(chunk_size=1 << 20):
                        handle.write(chunk)
                        written += len(chunk)
        print(f"  downloaded {written:,} bytes")

        if written < _MIN_ARCHIVE_BYTES:
            print(f"  ⚠️  only {written:,} bytes — expected ≥{_MIN_ARCHIVE_BYTES:,}.")
            print("      Treating as an error page rather than an archive.")
            return False
        return True
    except Exception as exc:
        print(f"  ⚠️  download failed: {type(exc).__name__}: {str(exc)[:160]}")
        return False


def d085_tails(db) -> Set[str]:
    """
    Tails worth asking about: the Part 135 charter fleet.

    DOCINDEX covers the entire US registry (~13,500 aircraft filings per
    window), the vast majority of which are not charter aircraft. Scoping to
    D085 keeps the write small and the table meaningful.
    """
    return {
        r[0] for r in db.execute(text("""
            SELECT DISTINCT tail_number
            FROM gtj.fleet_snapshots
            WHERE source = 'opspecs_d085'
        """))
    }


def ingest(db, archive: Path, dry_run: bool) -> Dict[str, int]:
    """Upsert lien filings for the Part 135 fleet from one registry archive."""
    blob = read_member(str(archive), DOCINDEX_FILE)
    if blob is None:
        print(f"  ⚠️  no {DOCINDEX_FILE} inside {archive.name}")
        return {}

    wanted = d085_tails(db)
    print(f"  Part 135 tails to match : {len(wanted):,}")

    liens: List = []
    releases: Dict[str, List] = {}
    total_rows = 0

    for record in parse_docindex(blob):
        total_rows += 1
        if record.tail_number not in wanted:
            continue
        if record.doc_type in LIEN_DOC_TYPES:
            liens.append(record)
        elif record.doc_type in RELEASE_DOC_TYPES:
            releases.setdefault(record.tail_number, []).append(record)

    # §4.2 charges only unresolved encumbrances. A release dated on or after a
    # lien discharges it; one dated earlier belongs to some prior filing and
    # leaves this one standing. Recorded as a flag rather than by dropping the
    # row, so the filed-then-released sequence stays visible.
    for record in liens:
        discharges = releases.get(record.tail_number) or []
        latest = max((r.doc_date for r in discharges if r.doc_date), default=None)
        record._superseded = bool(
            latest and record.doc_date and record.doc_date <= latest
        )

    # One filing per (tail, type, date, DOC-ID) — deliberately NOT per party.
    #
    # DOCINDEX indexes one filing once per party to it, so a single lien arrives
    # as a row for the lender, one for the owning LLC, and sometimes one per
    # individual:
    #
    #     N1029B  S/A  2025-01-13  ARE016569016  BANTERRA BANK
    #     N1029B  S/A  2025-01-13  ARE016569016  STONEWALL AVIATION LLC
    #     N1029B  S/A  2025-01-13  ARE016569016  WANZOR CHRISTOPHER DEVIN
    #
    # That is one encumbrance. Keying on party made it three, and therefore
    # three §4.2 charges — 2,145 keys for 878 real filings across the 2025-01
    # archive. See migration 082.
    #
    # DOC-ID is blank on 44% of rows, so blanks collapse to (tail, type, date).
    # Verified on the archive: 419 of 422 such groups hold several rows with the
    # same lender/owner pattern, so collapsing is right. The residual risk is
    # two genuinely distinct same-day liens with no DOC-ID on either, which
    # under-charges by one — safer than multiplying one lien by its party count.
    #
    # Postgres also rejects an INSERT ... ON CONFLICT whose own VALUES repeat a
    # constrained key, so this is required for the statement to run at all.
    #
    # `superseded` is OR-ed across the collapsed rows: if any copy is
    # discharged, the encumbrance is discharged.
    deduped: Dict[tuple, object] = {}
    for record in liens:
        key = (record.tail_number, record.doc_type, record.doc_date,
               record.doc_id or "")
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = record
        else:
            existing._superseded = existing._superseded or record._superseded
    collapsed = len(liens) - len(deduped)
    liens = list(deduped.values())

    today = datetime.now(timezone.utc).date()
    # How far back this file's window reaches. Reported per row so a reader can
    # see the limit of the observation rather than assuming completeness.
    window_until = today - timedelta(days=DOCINDEX_WINDOW_DAYS)

    stats = {
        "docindex_rows": total_rows,
        "matched_liens": len(liens),
        "duplicates_collapsed": collapsed,
        "active": sum(1 for r in liens if not r._superseded),
        "released": sum(1 for r in liens if r._superseded),
        "tails_affected": len({r.tail_number for r in liens}),
        "written": 0,
    }

    if dry_run or not liens:
        return stats

    # Batched upserts: one statement per row was minutes of round trips against
    # a remote database at ~250 ms latency.
    BATCH = 500
    for start in range(0, len(liens), BATCH):
        chunk = liens[start:start + BATCH]
        values, params = [], {
            "source": SOURCE, "seen": today, "window": window_until,
        }
        for i, record in enumerate(chunk):
            values.append(
                f"(:tl{i}, :dt{i}, :dd{i}, :pt{i}, :di{i}, :sp{i}, "
                f":window, :source, :seen, :seen)"
            )
            params[f"tl{i}"] = record.tail_number
            params[f"dt{i}"] = record.doc_type
            params[f"dd{i}"] = record.doc_date
            params[f"pt{i}"] = record.party[:255] or None
            params[f"di{i}"] = record.doc_id[:32] or None
            params[f"sp{i}"] = record._superseded

        # The unique index spans COALESCE expressions, so the conflict target
        # must repeat them exactly — naming the bare columns would not match it.
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
                -- A release seen in a later run must be able to flip this on,
                -- but never back off: a discharged lien stays discharged.
                superseded_by_release = gtj.tail_liens.superseded_by_release
                                        OR EXCLUDED.superseded_by_release,
                observed_in_window_until = EXCLUDED.observed_in_window_until,
                last_seen = EXCLUDED.last_seen,
                updated_at = now()
        """), params)
        stats["written"] += len(chunk)

    db.commit()
    return stats


def report(db) -> None:
    """What is stored, and what it does not prove."""
    summary = db.execute(text("""
        SELECT COUNT(*) AS filings,
               COUNT(DISTINCT tail_number) AS tails,
               COUNT(*) FILTER (WHERE superseded_by_release = false) AS active,
               MIN(observed_in_window_until) AS window_from,
               MAX(last_seen) AS last_run
        FROM gtj.tail_liens
    """)).mappings().first()

    print(f"\n  filings stored    : {summary['filings']:,}")
    print(f"  distinct tails    : {summary['tails']:,}")
    print(f"  active encumbrances: {summary['active']:,}")
    print(f"  observed back to  : {summary['window_from']}")
    print(f"  last ingest       : {summary['last_run']}")

    if not summary["filings"]:
        return

    print("\n  tails with active encumbrances:")
    rows = db.execute(text("""
        SELECT tail_number, COUNT(*) AS n,
               MIN(doc_date) AS earliest, MAX(doc_date) AS latest,
               string_agg(DISTINCT doc_type, ',') AS types
        FROM gtj.tail_liens
        WHERE superseded_by_release = false
        GROUP BY tail_number
        ORDER BY COUNT(*) DESC, tail_number
        LIMIT 20
    """)).mappings().all()
    print(f"    {'tail':<10}{'n':>3}  {'earliest':<12}{'latest':<12}types")
    print(f"    {'-' * 52}")
    for row in rows:
        print(f"    {row['tail_number']:<10}{row['n']:>3}  "
              f"{str(row['earliest']):<12}{str(row['latest']):<12}{row['types']}")

    print("\n  NOTE: DOCINDEX is a ~180-day rolling window. A tail absent from")
    print("        this table has no filing in that window — it is NOT evidence")
    print("        of clear title. The permanent record is FAA CARES.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest FAA DOCINDEX lien filings into gtj.tail_liens.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be written, change nothing")
    parser.add_argument("--archive", default=None,
                        help="path to an already-downloaded ReleasableAircraft.zip")
    parser.add_argument("--report", action="store_true",
                        help="show what is stored and exit")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.report:
            report(db)
            return 0

        print(f"\n{'=' * 72}")
        print("  FAA DOCINDEX LIEN INGEST")
        print(f"  window : trailing ~{DOCINDEX_WINDOW_DAYS} days")
        if args.dry_run:
            print("  MODE   : dry run — nothing will be written")
        print(f"{'=' * 72}\n")

        if args.archive:
            archive = Path(args.archive).expanduser()
            if not archive.exists():
                print(f"  {archive} does not exist.")
                return 1
            print(f"  using local archive: {archive.name}")
            stats = ingest(db, archive, args.dry_run)
        else:
            # Kept in a temp dir: the archive is ~68 MB and is of no use once
            # DOCINDEX has been read out of it.
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "ReleasableAircraft.zip"
                if not download_archive(archive):
                    print("\n  Nothing written.")
                    return 1
                stats = ingest(db, archive, args.dry_run)

        if not stats:
            return 1

        print(f"\n  DOCINDEX aircraft rows : {stats['docindex_rows']:,}")
        print(f"  matched Part 135 liens : {stats['matched_liens']:,}"
              f"  ({stats['duplicates_collapsed']:,} exact duplicate(s) collapsed)")
        print(f"    active               : {stats['active']:,}")
        print(f"    already released     : {stats['released']:,}")
        print(f"  tails affected         : {stats['tails_affected']:,}")
        print(f"  rows written           : {stats['written']:,}")

        if not args.dry_run:
            report(db)

        print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
