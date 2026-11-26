#!/usr/bin/env python3
"""
Repoint aircraft whose recorded "operator" is actually their OWNER.

THE PROBLEM
-----------
gtj.aircraft holds one operator_id, but a charter aircraft usually involves two
companies: the owner that holds title (often a single-purpose entity existing
only to own that one airframe) and the Part 135 certificate holder that
actually flies it. JetNet reports only the owner, so for some tails the owner
landed in the operator slot.

N286N is the canonical case: owned by INFINITY & BEYOND, LLC, operated by
Skyway Aviation Services, Inc. (certificate B90A). Our row named the owner.

That is not a cosmetic mislabel. Safety is the operator's responsibility, and
gtj.trust_scores, gtj.ntsb_incidents and gtj.fleet_snapshots all key on
operator_id — so an airframe filed under its owner attributes its history to a
company that never flew it, and withholds that history from the company that
did.

WHAT THIS SCRIPT CHANGES, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------------------
Only aircraft whose CURRENT operator row holds no FAA certificate
(faa_dsgn_code IS NULL) while the Part 135 roster names a certificated holder
for that tail. A company with no certificate cannot legally operate the
aircraft, so "owner recorded as operator" is the only reading available. 19
tails in the 2026-11 roster.

It does NOT touch the 387 tails where BOTH our operator and the roster's hold
live certificates (N787QS: ours NetJets DXTA, roster Executive Jet Management
CWQA). Those are real managed-aircraft arrangements or a roster snapshot newer
than our record, and moving an airframe between two legitimate operators moves
accident and lien history with it. That needs per-row review, not a bulk
UPDATE. Run with --report-ambiguous to list them.

NOTHING IS DELETED. The owner's operator row is kept: it is accurate about
ownership and is referenced by existing trust_scores rows. Those scores are
left in place but reported, because a score computed for a company that was
never the operator is stale by definition and should be recomputed rather than
silently trusted or silently dropped.

USAGE
-----
    python scripts/repoint_owner_as_operator.py --dry-run
    python scripts/repoint_owner_as_operator.py
    python scripts/repoint_owner_as_operator.py --report-ambiguous

Requires the roster workbook. Fetched directly unless --roster is given:
    python scripts/repoint_owner_as_operator.py --roster /tmp/p135.xlsx

Safe to re-run: once a tail points at a certificated operator it no longer
matches the selection criteria, so a second run finds nothing.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal, engine  # noqa: E402
from src.trustscore.adapter_v5 import normalize_operator_name  # noqa: E402

#: parse_roster and the download URL live in the ingest script; importing by
#: path avoids duplicating the column positions and the varchar(10) tail rule.
_INGEST = Path(__file__).resolve().parent / "ingest_part135.py"


def _load_ingest() -> Any:
    spec = importlib.util.spec_from_file_location("_ingest_part135", _INGEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def roster_tail_operators(blob: bytes, ingest: Any) -> Dict[str, List[str]]:
    """Tail number -> the certificate designators the roster lists it under."""
    out: Dict[str, List[str]] = {}
    for designator, entry in ingest.parse_roster(blob).items():
        for tail in entry["aircraft"]:
            out.setdefault(tail, []).append(designator)
    return out


def classify(tail_designators: Dict[str, List[str]]) -> Dict[str, List[Tuple]]:
    """
    Split operator disagreements by cause.

    Returns {"repoint": [...], "ambiguous": [...], "multi": [...]}, where
    `repoint` is the only group this script writes.
    """
    session = SessionLocal()
    try:
        by_designator = {
            str(designator).strip().upper(): (operator_id, name)
            for designator, operator_id, name in session.execute(text("""
                SELECT faa_dsgn_code, operator_id, name FROM gtj.operators
                WHERE faa_dsgn_code IS NOT NULL
            """)).all()
        }
        rows = session.execute(text("""
            SELECT a.aircraft_id, UPPER(TRIM(a.tail_number)), a.operator_id,
                   o.name, o.faa_dsgn_code
            FROM gtj.aircraft a
            JOIN gtj.operators o ON o.operator_id = a.operator_id
            WHERE a.tail_number IS NOT NULL
              AND a.organization_id IS NULL
        """)).all()
    finally:
        session.close()

    groups: Dict[str, List[Tuple]] = {"repoint": [], "ambiguous": [], "multi": []}
    for aircraft_id, tail, operator_id, name, designator in rows:
        listed = tail_designators.get(tail)
        if not listed:
            continue
        current = (designator or "").strip().upper()
        if current and current in listed:
            continue
        if len(listed) > 1:
            # On two certificates at once; which one "operates" it is not a
            # question this file can answer.
            groups["multi"].append((tail, name, current, listed))
            continue

        target = by_designator.get(listed[0])
        if target is None:
            # Roster names a certificate we hold no row for. ingest_part135.py
            # creates those; nothing to repoint to until it has run.
            continue
        if current:
            # Both sides certificated — see the module docstring.
            groups["ambiguous"].append((tail, name, current, target[1], listed[0]))
            continue

        same_company = (
            normalize_operator_name(name or "")
            == normalize_operator_name(target[1] or "")
        )
        groups["repoint"].append((
            str(aircraft_id), tail, str(operator_id), name,
            str(target[0]), target[1], listed[0], same_company,
        ))
    return groups


def orphan_report(repoints: List[Tuple]) -> None:
    """
    Report what the owner rows look like after their aircraft move away.

    A trust score computed while the owner occupied the operator slot describes
    a company that never operated the aircraft. Printed rather than deleted:
    recomputation is a scoring decision, and silently removing a score is worse
    than reporting a stale one.
    """
    owner_ids = sorted({row[2] for row in repoints})
    if not owner_ids:
        return
    session = SessionLocal()
    try:
        rows = session.execute(text("""
            SELECT o.name,
                   (SELECT COUNT(*) FROM gtj.aircraft a
                     WHERE a.operator_id = o.operator_id) AS fleet,
                   (SELECT COUNT(*) FROM gtj.trust_scores t
                     WHERE t.operator_id = o.operator_id) AS scores
            FROM gtj.operators o
            WHERE o.operator_id = ANY(CAST(:ids AS uuid[]))
            ORDER BY scores DESC, o.name
        """), {"ids": owner_ids}).all()
    finally:
        session.close()

    stale = [r for r in rows if r[2]]
    print(f"\n  owner rows kept: {len(rows)}  (ownership is real data; not deleted)")
    if stale:
        print(f"  of those, carrying a trust score computed as the OPERATOR: "
              f"{len(stale)}")
        print("  these describe a company that never operated the aircraft and")
        print("  should be recomputed:")
        for name, fleet, scores in stale[:20]:
            print(f"    {str(name)[:46]:<46} fleet_now={fleet}  scores={scores}")


def apply_repoints(repoints: List[Tuple]) -> int:
    """Point each aircraft at the certificate holder the roster names."""
    if not repoints:
        return 0
    from psycopg2.extras import execute_values

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            # Guarded on the operator still being the owner we read, so a
            # concurrent correction is not overwritten by a stale plan.
            execute_values(cursor, """
                UPDATE gtj.aircraft AS a
                SET operator_id = v.new_operator_id::uuid,
                    updated_at  = now()
                FROM (VALUES %s) AS v(aircraft_id, old_operator_id, new_operator_id)
                WHERE a.aircraft_id  = v.aircraft_id::uuid
                  AND a.operator_id  = v.old_operator_id::uuid
            """, [(row[0], row[2], row[4]) for row in repoints], page_size=500)
            written = cursor.rowcount
            raw.commit()
        return written if written and written > 0 else 0
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="report the plan, write nothing")
    parser.add_argument("--report-ambiguous", action="store_true",
                        help="list the two-certificate cases and exit")
    parser.add_argument("--roster", help="path to a roster .xlsx (default: download)")
    args = parser.parse_args()

    ingest = _load_ingest()

    if args.roster:
        blob: Optional[bytes] = Path(args.roster).expanduser().read_bytes()
        print(f"  roster: {args.roster}")
    else:
        print("  fetching the Part 135 roster…")
        blob = ingest.fetch_roster(ingest.PART135_URL)
    if not blob:
        print("  could not obtain the roster. Nothing written.")
        return 1

    tail_designators = roster_tail_operators(blob, ingest)
    print(f"    {len(tail_designators):,} tails on the roster")

    groups = classify(tail_designators)
    repoints = groups["repoint"]

    if args.report_ambiguous:
        rows = groups["ambiguous"]
        print(f"\n  TWO-CERTIFICATE CASES — not changed by this script ({len(rows)}):")
        print(f"  {'tail':<9}{'our operator':<34}{'ours':<7}{'roster operator':<34}roster")
        for tail, ours, our_dsgn, theirs, their_dsgn in sorted(rows):
            print(f"  {tail:<9}{str(ours)[:33]:<34}{our_dsgn:<7}"
                  f"{str(theirs)[:33]:<34}{their_dsgn}")
        print("\n  Both hold live certificates, so neither is provably wrong.")
        print("  Repointing moves accident and lien history between two real")
        print("  operators — review individually.")
        return 0

    print(f"\n  owner-recorded-as-operator (no certificate on our side): "
          f"{len(repoints)}")
    print(f"  {'tail':<9}{'owner (ours)':<34}{'certificated operator (roster)':<34}cert")
    for row in sorted(repoints, key=lambda r: r[1]):
        note = "  [same company — duplicate row]" if row[7] else ""
        print(f"  {row[1]:<9}{str(row[3])[:33]:<34}{str(row[5])[:33]:<34}{row[6]}{note}")

    dupes = [r for r in repoints if r[7]]
    if dupes:
        print(f"\n  {len(dupes)} of these are the SAME company held twice — one row")
        print("  with a certificate, one without. Repointing consolidates the")
        print("  fleet onto the certificated row.")

    print(f"\n  not changed: {len(groups['ambiguous'])} two-certificate cases, "
          f"{len(groups['multi'])} on multiple certificates")
    print("  (see --report-ambiguous)")

    if args.dry_run:
        orphan_report(repoints)
        print("\n  Dry run — nothing written.\n")
        return 0

    written = apply_repoints(repoints)
    print(f"\n  repointed: {written} aircraft")
    if written != len(repoints):
        print(f"  {len(repoints) - written} skipped — operator changed since the "
              f"plan was built; re-run to pick them up")
    orphan_report(repoints)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
