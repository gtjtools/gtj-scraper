#!/usr/bin/env python3
"""
Populate gtj.aircraft.registered_owner from the FAA MASTER registry.

WHY THIS EXISTS
---------------
`registered_owner` is 0% populated across all 11,182 aircraft. The column was
created for the v3 calculator's ownership check and left empty when v5
replaced it — the two places that ever set it (src/scoring/router.py and
src/workflows/batch_verify_workflow.py) are inside the commented-out v3 block,
and both passed `registered_owner=operator_name`, i.e. they assumed the
operator owned every tail.

v5 reads ownership through `TailData.ownership_observed`, whose default is
False precisely so that an unobserved default is not mistaken for an observed
one — `GAP_OWNERSHIP` already fires for any tail scored without it. So this is
an unfilled gap the system admits to, not a silent inflation. Filling it turns
"we did not look" into evidence.

WHY IT MATTERS FOR Ost (§5.2)
-----------------------------
Exclusive operator ownership scores better than a managed tail, because a
private owner can pull the aircraft, veto a trip, or refuse a weekend AOG
part. JEM Air Holdings is the worked example: of its 13 tails, exactly ONE
(N560MC) is registered to JEM. The other 11 belong to single-purpose entities
— N118DL LLC, N560MC LLC, 824 HOLDCO LLC, PLANE TO SEA LLC, ND AVIATION LLC
(x2) — which is the signature of third-party managed aircraft.

SOURCE
------
MASTER.txt inside ReleasableAircraft.zip from registry.faa.gov. That host
403s from the dev machine but serves the production server (§9.6), so the
archive is downloaded where it works and the path passed in here.

    https://registry.faa.gov/database/ReleasableAircraft.zip

MATCHING
--------
On tail number only. MASTER's `serial_number` is NOT used as a fallback:
serials are unique per manufacturer, not globally, so matching on serial alone
would attribute one airframe's owner to another's. A tail that has changed
hands since our aircraft row was written will show its CURRENT registered
owner, which is the correct answer for "who can pull this aircraft today".

USAGE
-----
    python scripts/ingest_aircraft_ownership.py /tmp/ReleasableAircraft.zip
    python scripts/ingest_aircraft_ownership.py /tmp/ReleasableAircraft.zip --dry-run

Only `registered_owner` is written. `registered_owner_state` and
`fractional_owner` are left untouched: MASTER as parsed here carries neither,
and guessing either would put an unobserved value in a column that currently
reads honestly as unknown.

Safe to re-run: a straight UPDATE keyed on tail number, no deletes, no inserts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal, engine  # noqa: E402
from src.common.faa_registry import parse_master, read_member  # noqa: E402

MASTER_MEMBER = "MASTER.txt"

#: gtj.aircraft.registered_owner is varchar(255). MASTER's NAME field is 50
#: characters, so truncation should never trigger — but a silently truncated
#: owner is a wrong owner, so it is counted rather than assumed impossible.
OWNER_MAX = 255


def load_master_owners(archive: Path) -> Dict[str, str]:
    """Tail number -> current registered owner, from MASTER.txt."""
    print(f"  reading {MASTER_MEMBER} from {archive.name}")
    blob = read_member(str(archive), MASTER_MEMBER)
    if not blob:
        raise SystemExit(f"  {MASTER_MEMBER} not found in {archive}")

    owners: Dict[str, str] = {}
    for record in parse_master(blob):
        tail = (record.tail_number or "").strip().upper()
        owner = (record.owner_name or "").strip()
        if tail and owner:
            owners[tail] = owner
    print(f"    {len(owners):,} registered aircraft")
    return owners


def match(owners: Dict[str, str]) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    """Pair our aircraft rows against MASTER by tail number."""
    stats = {"ours": 0, "matched": 0, "unmatched": 0, "truncated": 0}
    updates: List[Dict[str, str]] = []

    session = SessionLocal()
    try:
        rows = session.execute(text("""
            SELECT aircraft_id, tail_number
            FROM gtj.aircraft
            WHERE tail_number IS NOT NULL
        """)).all()
    finally:
        session.close()

    for aircraft_id, tail in rows:
        stats["ours"] += 1
        key = (tail or "").strip().upper()
        owner = owners.get(key)
        if not owner:
            stats["unmatched"] += 1
            continue
        if len(owner) > OWNER_MAX:
            stats["truncated"] += 1
            owner = owner[:OWNER_MAX]
        stats["matched"] += 1
        updates.append({"id": str(aircraft_id), "owner": owner})

    return updates, stats


def apply(updates: List[Dict[str, str]], batch: int = 2000) -> int:
    """
    Write registered_owner.

    Batched with execute_values against a VALUES list rather than one UPDATE
    per row: the database is a remote Supabase host, so per-row round-trips do
    not finish in reasonable time at this volume.
    """
    from psycopg2.extras import execute_values

    written = 0
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            for start in range(0, len(updates), batch):
                chunk = updates[start:start + batch]
                execute_values(cursor, """
                    UPDATE gtj.aircraft AS a
                    SET registered_owner = v.owner,
                        updated_at = now()
                    FROM (VALUES %s) AS v(aircraft_id, owner)
                    WHERE a.aircraft_id = v.aircraft_id::uuid
                """, [(u["id"], u["owner"]) for u in chunk], page_size=batch)
                raw.commit()
                written += len(chunk)
                print(f"\r    {written:,}/{len(updates):,}", end="", flush=True)
        print()
        return written
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def report() -> None:
    """Show what the fill means for Ost — managed vs operator-owned."""
    session = SessionLocal()
    try:
        total, filled = session.execute(text("""
            SELECT COUNT(*), COUNT(registered_owner) FROM gtj.aircraft
        """)).first()
        print(f"\n  registered_owner populated: {filled:,} of {total:,} "
              f"({100 * filled / max(1, total):.0f}%)")

        # An operator "owns" a tail when its name appears in the registered
        # owner. Reported only, never written: this is a rough signal for
        # whoever wires Ost, and a name comparison is weaker evidence than the
        # owner string itself.
        #
        # THE PUNCTUATION STRIP IS NOT COSMETIC. A first attempt took
        # SPLIT_PART(o.name,' ',1), which turns 'Flexjet, Llc' into 'FLEXJET,'
        # — comma included — and that is not a substring of 'FLEXJET LLC'. It
        # reported Flexjet as 0% owned across 288 tails every one of which is
        # registered to FLEXJET LLC. Corporate suffixes and punctuation are
        # stripped from both sides before comparing.
        owned, managed = session.execute(text("""
            WITH cmp AS (
              SELECT
                REGEXP_REPLACE(
                  REGEXP_REPLACE(UPPER(o.name),
                    '[^A-Z0-9 ]', '', 'g'),
                  '\\s+(LLC|INC|LTD|CORP|CO|LP|LLP|SA|SRL|COMPANY)\\s*$',
                  '', 'g') AS op_name,
                REGEXP_REPLACE(UPPER(a.registered_owner),
                  '[^A-Z0-9 ]', '', 'g') AS owner_name
              FROM gtj.aircraft a
              JOIN gtj.operators o ON o.operator_id = a.operator_id
              WHERE a.registered_owner IS NOT NULL
            )
            SELECT
              COUNT(*) FILTER (WHERE op_name <> ''
                               AND POSITION(op_name IN owner_name) > 0),
              COUNT(*) FILTER (WHERE op_name = ''
                               OR POSITION(op_name IN owner_name) = 0)
            FROM cmp
        """)).first()
        both = owned + managed
        if both:
            print(f"  operator name appears in the owner: {owned:,} "
                  f"({100 * owned / both:.0f}%)")
            print(f"  it does not (likely managed):       {managed:,} "
                  f"({100 * managed / both:.0f}%)")
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help="path to ReleasableAircraft.zip")
    parser.add_argument("--dry-run", action="store_true",
                        help="match and report, write nothing")
    args = parser.parse_args()

    archive = Path(args.archive).expanduser()
    if not archive.exists():
        print(f"  not found: {archive}")
        return 1

    print(f"\n{'=' * 70}")
    print("  FAA MASTER registry -> gtj.aircraft.registered_owner")
    print(f"{'=' * 70}")

    owners = load_master_owners(archive)
    updates, stats = match(owners)

    print()
    print(f"  our aircraft rows         {stats['ours']:>7,}")
    print(f"  matched in MASTER         {stats['matched']:>7,}")
    print(f"  not in MASTER             {stats['unmatched']:>7,}")
    if stats["truncated"]:
        print(f"  owner names truncated     {stats['truncated']:>7,}")

    if not updates:
        print("\n  nothing matched — aborting rather than writing nothing")
        return 1

    if args.dry_run:
        print("\n  sample of what would be written:")
        for u in updates[:6]:
            print(f"    {u['owner']}")
        print("\n  --dry-run: nothing written")
        return 0

    print()
    apply(updates)
    report()
    print(f"\n{'=' * 70}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
