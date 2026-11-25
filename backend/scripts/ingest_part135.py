#!/usr/bin/env python3
"""
Ingest the FAA Part 135 certificate holder roster.

Two destinations, from one download:

  gtj.certificate_dbas  every (designator, name) pair, so a rebrand does not
                        erase an operator's history (§8).
  gtj.aircraft          the roster's per-tail fleet — ADDITIVE ONLY, feeding
                        `Vf` in §4.1. See upsert_aircraft for why absence from
                        the roster is never treated as a delete signal.

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
    python scripts/ingest_part135.py --no-aircraft  # names only, skip gtj.aircraft
    python scripts/ingest_part135.py --backfill     # also walk web.archive.org
    python scripts/ingest_part135.py --report       # show known rebrands

Safe to re-run: the aircraft pass inserts only tails it does not already hold
and fills only blank make_model / serial_number, so a second run on the same
roster reports 0 inserted and 0 enriched.

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
No DBA column and no certificate issue date. Both now come from the FAA
14 CFR air operator search export instead — see ingest_dba_export.py, which
feeds `Age_cert` (§3) via resolve_certificate_age_years(). That export is a
manual download (explore.dot.gov blocks automated fetches from every host we
have tried); this roster is fetched directly, which is why the two are
separate scripts.
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
from psycopg2.extras import Json  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal, engine  # noqa: E402
from src.trustscore.adapter_v5 import normalize_operator_name  # noqa: E402

PART135_URL = (
    "https://www.faa.gov/about/officeorg/headquartersoffices/avs/"
    "faa-certificated-aircraft-operators-legal-part-135-holders.xlsx"
)
PART135_PAGE = PART135_URL[: -len(".xlsx")]

CDX_URL = "http://web.archive.org/cdx/search/cdx"
WAYBACK = "http://web.archive.org/web/{ts}id_/{url}"

#: Column positions in the roster: CFR, CHDO, DSGN, Name, M/M/S, Reg No, Serial.
COL_CFR, COL_CHDO, COL_DSGN, COL_NAME = 0, 1, 2, 3
COL_MMS, COL_TAIL, COL_SERIAL = 4, 5, 6

#: gtj.aircraft column widths, read from information_schema — NOT guessed.
#: A first attempt assumed 20/255/100 and died on
#: StringDataRightTruncation partway through a batch.
#:
#: tail_number is varchar(10) and a truncated tail is a DIFFERENT aircraft, so
#: an over-long registration is skipped rather than cut down. make_model and
#: serial_number are descriptive, so those are truncated.
TAIL_MAX = 10
MAKE_MODEL_MAX = 100
SERIAL_MAX = 50

#: Written to gtj.aircraft.extra_attributes->>'source' on rows this script
#: creates, so a later correction can tell them from operator-supplied rows.
AIRCRAFT_SOURCE = "faa_part135_roster"

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
    Reduce a roster workbook to {designator: {name, chdo, tails, aircraft}}.

    One row per aircraft, so a certificate appears many times; the name is taken
    from the first row seen and tails are accumulated for the fleet count.

    `aircraft` carries the per-tail detail the roster also publishes — make /
    model / series, serial number, and the CHDO (the FAA field office holding
    oversight). `tails` is kept as a plain set because callers use it only to
    count the fleet, and several already do.
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

        def cell(index: int) -> str:
            return str(row[index] or "").strip() if len(row) > index else ""

        entry = out.setdefault(designator, {
            "name": name,
            # CHDO is a property of the certificate, not the airframe; the first
            # row that carries one wins. CFR is kept for the same reason — a
            # handful of holders are '121/135' rather than plain '135'.
            "chdo": cell(COL_CHDO).upper(),
            "cfr": cell(COL_CFR),
            "tails": set(),
            "aircraft": {},
        })
        if not entry["chdo"]:
            entry["chdo"] = cell(COL_CHDO).upper()

        tail = cell(COL_TAIL).upper()
        if not tail:
            # 37 rows carry no registration (aircraft on the certificate but
            # not yet registered). They are real fleet entries we cannot key,
            # so they are skipped rather than invented.
            entry["skipped_no_tail"] = entry.get("skipped_no_tail", 0) + 1
            continue
        if len(tail) > TAIL_MAX:
            # 4 rows in the 2026-11 roster: three ICAO-style 'FA3HTYPAP3/USA'
            # codes and one 'N325CT EXCLUSIVE USE'. Neither is a registration
            # that would match gtj.aircraft, and truncating would invent a
            # different tail, so they are recorded as skipped.
            entry.setdefault("skipped_long_tail", []).append(tail)
            continue
        entry["tails"].add(tail)
        # Last row wins on a repeated tail within one certificate; the roster
        # does repeat a tail across certificates when an aircraft is on two.
        entry["aircraft"][tail] = {
            "make_model": cell(COL_MMS)[:MAKE_MODEL_MAX],
            "serial_number": cell(COL_SERIAL)[:SERIAL_MAX] or None,
        }
    return out


def upsert_aircraft(
    roster: Dict[str, Dict[str, Any]],
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Add the roster's aircraft to gtj.aircraft, and only ever add.

    NOTHING IS EVER DELETED OR UNLINKED. This is a deliberate constraint, not
    caution: 1,710 of our tails are absent from the roster, and 1,503 of those
    belong to a certificate that IS on it. A tail missing from one monthly
    snapshot means the aircraft was sold, re-registered, or recorded under a
    different certificate — never that it should be removed. Treating absence
    as a delete signal would discard ~1,500 live aircraft.

    WHY THIS MATTERS FOR SCORING (§4.1)
    -----------------------------------
    `Vf` (fleet size) normalizes accident risk by MAX(1, SQRT(Vf)), and
    fetch_fleet_size derives it by counting these rows. Undercounting a fleet
    therefore inflates the per-incident penalty: a 38-aircraft operator holding
    one row carries 6.2x the penalty it should. 693 certificates currently
    disagree with the roster on fleet size, and 34 hold zero rows while the FAA
    lists aircraft against them.

    MATCHING
    --------
    On `faa_dsgn_code`, the certificate designator — not the operator name.
    The designator is the roster's own key and is stable across the rebrands
    this script exists to track; matching on a name would miss exactly the
    operators that have renamed.

    Only rows for operators already in gtj.operators are written. A designator
    we do not hold is counted and reported, never inserted: creating an operator
    shell with no profile, no contacts and no entitlements would put a row in
    front of users that nothing else in the system can populate.

    Writes platform-level rows (organization_id IS NULL), which is what the
    partial unique index on tail_number covers and where the other 11,178
    registry-sourced rows already live.
    """
    stats = {
        "roster_aircraft": 0, "unknown_designator": 0, "unknown_aircraft": 0,
        "inserted": 0, "enriched": 0, "already_present": 0, "conflict_skipped": 0,
        "skipped_no_tail": sum(e.get("skipped_no_tail", 0) for e in roster.values()),
        "skipped_long_tail": sum(
            len(e.get("skipped_long_tail", ())) for e in roster.values()
        ),
    }

    session = SessionLocal()
    try:
        known = {
            str(designator).strip().upper(): operator_id
            for designator, operator_id in session.execute(text("""
                SELECT faa_dsgn_code, operator_id
                FROM gtj.operators
                WHERE faa_dsgn_code IS NOT NULL
            """)).all()
        }
        # Existing platform tails, with what they already know, so enrichment
        # only fills blanks and never overwrites a curated value.
        existing = {
            str(tail).strip().upper(): (aircraft_id, make_model, serial_number)
            for aircraft_id, tail, make_model, serial_number in session.execute(text("""
                SELECT aircraft_id, tail_number, make_model, serial_number
                FROM gtj.aircraft
                WHERE tail_number IS NOT NULL AND organization_id IS NULL
            """)).all()
        }
    finally:
        session.close()

    inserts: List[Tuple[Any, ...]] = []
    updates: List[Tuple[Any, ...]] = []
    unknown_designators: Set[str] = set()

    for designator, entry in roster.items():
        operator_id = known.get(designator)
        for tail, detail in entry["aircraft"].items():
            stats["roster_aircraft"] += 1
            if operator_id is None:
                unknown_designators.add(designator)
                stats["unknown_designator"] += 1
                stats["unknown_aircraft"] += 1
                continue

            found = existing.get(tail)
            if found is None:
                # make_model is NOT NULL. The roster's M/M/S is the only value
                # available, and a row with an empty one would fail the insert,
                # so an unknown model is recorded as such rather than blank.
                inserts.append((
                    tail,
                    str(operator_id),
                    detail["make_model"] or "UNKNOWN",
                    detail["serial_number"],
                    AIRCRAFT_SOURCE,
                    entry.get("chdo") or None,
                ))
                continue

            aircraft_id, make_model, serial_number = found
            needs_model = (not make_model or make_model.upper() == "UNKNOWN") \
                and bool(detail["make_model"])
            needs_serial = not serial_number and bool(detail["serial_number"])
            if needs_model or needs_serial:
                updates.append((
                    str(aircraft_id),
                    detail["make_model"] if needs_model else None,
                    detail["serial_number"] if needs_serial else None,
                ))
            else:
                stats["already_present"] += 1

    if unknown_designators:
        stats["unknown_designator"] = len(unknown_designators)

    if dry_run:
        stats["inserted"] = len(inserts)
        stats["enriched"] = len(updates)
        return stats

    from psycopg2.extras import execute_values

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            # ON CONFLICT targets the partial unique index on tail_number for
            # platform rows. DO NOTHING, not DO UPDATE: a tail that appears on
            # two certificates must not have its operator reassigned by whichever
            # row the loop reached last.
            for start in range(0, len(inserts), 1000):
                chunk = inserts[start:start + 1000]
                # current_status is omitted so its column DEFAULT ('AVAILABLE')
                # applies. It must not be cast here: `aircraft_status` exists in
                # public, gtj and gtj-test, so naming a schema binds the wrong
                # type, and casting unqualified resolves by search_path rather
                # than by the column being written.
                execute_values(cursor, """
                    INSERT INTO gtj.aircraft
                        (tail_number, operator_id, make_model, serial_number,
                         organization_id, extra_attributes)
                    VALUES %s
                    ON CONFLICT (tail_number) WHERE organization_id IS NULL
                    DO NOTHING
                """, [
                    (tail, operator, model, serial, None,
                     Json({"source": source, "faa_chdo": chdo}))
                    for tail, operator, model, serial, source, chdo in chunk
                ], template="(%s, %s::uuid, %s, %s, %s, %s)")
                raw.commit()
                # rowcount is per-statement, so it counts only the rows this
                # batch actually inserted — conflicts are excluded by DO NOTHING.
                if cursor.rowcount and cursor.rowcount > 0:
                    stats["inserted"] += cursor.rowcount

            for start in range(0, len(updates), 1000):
                chunk = updates[start:start + 1000]
                execute_values(cursor, """
                    UPDATE gtj.aircraft AS a
                    SET make_model    = COALESCE(v.make_model, a.make_model),
                        serial_number = COALESCE(v.serial_number, a.serial_number),
                        updated_at    = now()
                    FROM (VALUES %s) AS v(aircraft_id, make_model, serial_number)
                    WHERE a.aircraft_id = v.aircraft_id::uuid
                """, chunk, page_size=1000)
                raw.commit()
                stats["enriched"] += len(chunk)
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()

    stats["conflict_skipped"] = len(inserts) - stats["inserted"]
    return stats


def _print_aircraft_stats(stats: Dict[str, int]) -> None:
    """Report what the aircraft pass did, including what it declined to do."""
    print(f"    roster aircraft           {stats['roster_aircraft']:>7,}")
    print(f"    inserted                  {stats['inserted']:>7,}")
    print(f"    enriched (model/serial)   {stats['enriched']:>7,}")
    print(f"    already complete          {stats['already_present']:>7,}")
    if stats["unknown_aircraft"]:
        print(f"    skipped — operator not in gtj.operators:"
              f" {stats['unknown_aircraft']:,} aircraft across "
              f"{stats['unknown_designator']:,} certificate(s)")
    if stats["skipped_no_tail"]:
        print(f"    skipped — no registration on the roster row:"
              f" {stats['skipped_no_tail']:,}")
    if stats["skipped_long_tail"]:
        print(f"    skipped — registration too long for varchar(10):"
              f" {stats['skipped_long_tail']:,}")
    if stats["conflict_skipped"] > 0:
        # A tail held on two certificates, or added concurrently. The first
        # writer keeps the operator link; see the DO NOTHING note above.
        print(f"    skipped — tail already held: {stats['conflict_skipped']:,}")
    print("    (no aircraft is ever deleted or unlinked by this script)")


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
    parser.add_argument("--no-aircraft", dest="aircraft", action="store_false",
                        default=True,
                        help="skip adding the roster's aircraft to gtj.aircraft")
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
        if args.aircraft:
            print("\n  aircraft that WOULD be written:")
            _print_aircraft_stats(upsert_aircraft(roster, dry_run=True))
        print("\n  Dry run — nothing written.\n")
        return 0

    today = datetime.now(timezone.utc).date()
    ins, upd = upsert_names(roster, today, is_current=True)
    print(f"    {ins:,} new name(s), {upd:,} existing confirmed")

    if args.aircraft:
        print("\n  adding roster aircraft to gtj.aircraft (additive only)…")
        _print_aircraft_stats(upsert_aircraft(roster))

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
