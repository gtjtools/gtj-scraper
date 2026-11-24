#!/usr/bin/env python3
"""
Ingest a manually-exported FAA "Air Operator 14 CFR Search" DBA file.

WHY THIS EXISTS
---------------
Our only automated DBA source is the Part 135 roster, which lists the
certificate holder's LEGAL name and nothing else. A trade name filed with the
FAA but not reflected in that roster is invisible to us, so a broker quoted by
a marketing name could not be matched to the certificate it actually flies on.

The FAA's Air Operator 14 CFR Search carries the legal name AND a separate DBA
column. Its data lives in a Tableau view on explore.dot.gov, which returns 403
from both the dev machine and the production server (§13.3 of
TRUSTSCORE_DATA_SOURCES.md), so the file cannot be fetched automatically. It is
exported by hand from the browser and loaded with this script.

WHAT IT MEASURABLY ADDS (export dated 2026-11-23)
-------------------------------------------------
    rows in file                      2,146
    rows carrying a DBA               1,084
    (certificate, name) pairs         2,897
    already in certificate_dbas       1,939
    NEW pairs                           958
    NEW on a certificate we score       911   across 644 certificates

JEM Air Holdings (3JMA) is the worked example: the Part 135 roster gave one
name, and this export gives four — BELLAIR, FLYBELLAIR, JEM AIR and JET
EXCELLENCE. That is the exact failure this closes.

FILE FORMAT — NOT ACTUALLY CSV
------------------------------
Despite the .csv extension, Tableau exports UTF-16LE with a BOM, TAB
delimiters and CRLF line endings. Reading it as UTF-8 comma-separated yields
one meaningless column, so the encoding and delimiter are both pinned below
rather than sniffed.

The DBA column header is EMPTY — the file's seventh field has no name — so it
is addressed by position, with the header checked to make sure the layout has
not shifted under us.

    Air_Operator_Name  14 CFR Part  DSGN_CODE  Certificate_Number
    Cert_Issue_Date    INDEX()      <unnamed: the DBA>

USAGE
-----
    python scripts/ingest_dba_export.py ~/Downloads/DBA.csv
    python scripts/ingest_dba_export.py ~/Downloads/DBA.csv --dry-run

Additive and idempotent: rows are upserted on
(certificate_designator, operator_name_normalized), nothing is deleted, and
no existing name is demoted — see IS_CURRENT below for why.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402
from src.trustscore.adapter_v5 import normalize_operator_name  # noqa: E402

#: Tableau's export encoding and delimiter. Pinned, not sniffed — see the
#: FILE FORMAT note above.
ENCODING = "utf-16"
DELIMITER = "\t"

#: Column positions. The DBA column is unnamed, so position is all we have.
COL_LEGAL, COL_PART, COL_DSGN, COL_CERT, COL_ISSUED, COL_INDEX, COL_DBA = range(7)

#: Header labels used to verify the layout before trusting the positions.
EXPECTED_HEADER = [
    "Air_Operator_Name", "14 CFR Part", "DSGN_CODE",
    "Certificate_Number", "Cert_Issue_Date", "INDEX()", "",
]

SOURCE = "faa_14cfr_search"

#: Values that appear in the DBA column but are not names. "N/A" and
#: "NONE AUTHORIZED" are the FAA's own way of saying there is no trade name;
#: storing them would make them matchable, and a fleet lookup for an operator
#: called "N/A" would return unrelated certificates.
NOT_A_NAME = frozenset({
    "N/A", "NA", "NONE", "NONE AUTHORIZED", "NOT APPLICABLE", "-", "--",
})


def _clean(value: str) -> str:
    return (value or "").strip()


def _is_name(value: str) -> bool:
    return bool(value) and value.upper() not in NOT_A_NAME


def split_dba_text(value: str) -> List[str]:
    """
    Split the FAA's own "DBA" wording out of a trade-name cell.

    Five cells in the 2026-11-23 export embed the literal word DBA, in three
    shapes, and each breaks matching in a different way:

        "DBA: PHOENIX AIR"                            prefix
        "DBA, WEST COAST AVIATION SERVICES"           prefix
        "BEND AIR TAXI DBA SAVAGE AVIATION CHARTERS"  TWO names in one cell
        "JB AVIATION, LLC DBA BEYOND JETS"            TWO names in one cell

    Left alone, `normalize_operator_name` drops the bare DBA token but keeps
    everything else, so "DBA: PHOENIX AIR" normalises to ": PHOENIX AIR" — a
    stray colon that can never match "PHOENIX AIR" — and the compound cells
    normalise to one merged string ("BEND AIR TAXI SAVAGE AVIATION CHARTERS")
    that matches neither of the two real names in it.

    A leading DBA marker is stripped; an infix one splits the cell, because
    both halves are names the operator trades under and a broker could quote
    either.
    """
    text_value = _clean(value)
    if not text_value:
        return []

    upper = text_value.upper()

    # Leading marker: "DBA:", "DBA,", "DBA " — strip it, keep the remainder.
    for prefix in ("DBA:", "DBA,", "DBA "):
        if upper.startswith(prefix):
            remainder = _clean(text_value[len(prefix):].lstrip(":, "))
            return [remainder] if remainder else []

    # Infix marker: the cell holds the legal name AND the trade name.
    marker = " DBA "
    index = upper.find(marker)
    if index > 0:
        left = _clean(text_value[:index])
        right = _clean(text_value[index + len(marker):])
        return [part for part in (left, right) if part]

    return [text_value]


def parse(path: Path) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    """
    Read the export into (certificate, name) records.

    Both the legal name and every DBA become a name for the same certificate,
    because a broker may quote under either and both must resolve.
    """
    raw = path.read_bytes()
    text_data = raw.decode(ENCODING)
    rows = list(csv.reader(io.StringIO(text_data), delimiter=DELIMITER))
    if not rows:
        raise SystemExit("  file is empty")

    header = [_clean(h) for h in rows[0]]
    if header[:6] != EXPECTED_HEADER[:6]:
        raise SystemExit(
            f"  unexpected header layout — refusing to guess column positions.\n"
            f"    expected: {EXPECTED_HEADER}\n"
            f"    found:    {header}"
        )

    stats = {
        "rows": 0, "with_dba": 0, "skipped_placeholder": 0,
        "skipped_no_cert": 0, "non_135": 0, "split_compound": 0,
    }
    seen: set = set()
    records: List[Dict[str, str]] = []

    for row in rows[1:]:
        if not any(_clean(c) for c in row):
            continue
        stats["rows"] += 1

        designator = _clean(row[COL_DSGN]).upper() if len(row) > COL_DSGN else ""
        if not designator:
            stats["skipped_no_cert"] += 1
            continue

        part = _clean(row[COL_PART]) if len(row) > COL_PART else ""
        if "135" not in part:
            # Part 135 is what the scorer covers. Other parts are kept out
            # rather than silently widening what certificate_dbas describes.
            stats["non_135"] += 1
            continue

        names = []
        legal = _clean(row[COL_LEGAL]) if len(row) > COL_LEGAL else ""
        if _is_name(legal):
            names.append(legal)

        dba = _clean(row[COL_DBA]) if len(row) > COL_DBA else ""
        if dba:
            stats["with_dba"] += 1
            if _is_name(dba):
                parts = split_dba_text(dba)
                if len(parts) > 1:
                    stats["split_compound"] += 1
                names.extend(p for p in parts if _is_name(p))
            else:
                stats["skipped_placeholder"] += 1

        for name in names:
            normalized = normalize_operator_name(name)
            if not normalized:
                continue
            key = (designator, normalized)
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "designator": designator,
                "name": name,
                "normalized": normalized,
            })

    return records, stats


def load(records: List[Dict[str, str]], seen_on: date) -> Dict[str, int]:
    """
    Upsert into gtj.certificate_dbas.

    IS_CURRENT IS FALSE FOR EVERY ROW, and no existing name is demoted.

    The Part 135 roster is the live source: it says which single name the
    certificate holds TODAY, and ingest_part135 maintains exactly one current
    name per certificate on that basis. This export is a point-in-time manual
    snapshot with no such guarantee — it lists several concurrent trade names
    per certificate, which is the whole reason it is useful. Marking any of
    them current would overwrite the roster's answer with a guess, so these
    rows are added as additional known names and the roster keeps authority
    over which one is current.
    """
    import json

    from psycopg2.extras import execute_values

    from src.common.config import engine

    before = 0
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM gtj.certificate_dbas")
            before = cursor.fetchone()[0]

            # ONE batched statement, not one per row. The database is a remote
            # Supabase host, so a per-row execute+commit pays a network
            # round-trip each time — 2,758 of them does not finish in any
            # reasonable time. execute_values sends them as a single
            # multi-row VALUES list.
            execute_values(cursor, """
                INSERT INTO gtj.certificate_dbas
                    (certificate_designator, operator_name,
                     operator_name_normalized, is_current,
                     first_seen, last_seen, source)
                VALUES %s
                ON CONFLICT (certificate_designator, operator_name_normalized)
                DO UPDATE SET
                    last_seen  = GREATEST(gtj.certificate_dbas.last_seen,
                                          EXCLUDED.last_seen),
                    first_seen = LEAST(gtj.certificate_dbas.first_seen,
                                       EXCLUDED.first_seen),
                    updated_at = now()
            """, [
                (r["designator"], r["name"], r["normalized"],
                 False, seen_on, seen_on, SOURCE)
                for r in records
            ], page_size=1000)
            raw.commit()

            cursor.execute("SELECT COUNT(*) FROM gtj.certificate_dbas")
            after = cursor.fetchone()[0]

        # "added" is the net row growth, which is the only honest number a
        # single batched upsert can report: ON CONFLICT DO UPDATE gives no
        # per-row insert/update flag, and on a re-run every row is an update
        # so the growth is correctly zero.
        return {"added": after - before, "submitted": len(records)}
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="the exported DBA file")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and report, write nothing")
    parser.add_argument("--seen", default=None,
                        help="date to record as first/last seen "
                             "(default: today). Use the export's own date.")
    args = parser.parse_args()

    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"  not found: {path}")
        return 1

    seen_on = date.fromisoformat(args.seen) if args.seen else date.today()

    print(f"\n{'=' * 72}")
    print("  FAA Air Operator 14 CFR Search — DBA ingest")
    print(f"{'=' * 72}")
    print(f"  file:  {path}")
    print(f"  seen:  {seen_on}")

    records, stats = parse(path)
    print()
    print(f"  rows read                 {stats['rows']:>6,}")
    print(f"  rows carrying a DBA       {stats['with_dba']:>6,}")
    print(f"  placeholder DBAs skipped  {stats['skipped_placeholder']:>6,}")
    print(f"  compound cells split      {stats['split_compound']:>6,}")
    print(f"  rows with no designator   {stats['skipped_no_cert']:>6,}")
    print(f"  non-135 rows skipped      {stats['non_135']:>6,}")
    print(f"  (certificate, name) pairs {len(records):>6,}")
    certificates = {r["designator"] for r in records}
    print(f"  distinct certificates     {len(certificates):>6,}")

    if not records:
        print("\n  nothing to load — aborting rather than writing an empty set")
        return 1

    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    print()
    counts = load(records, seen_on)
    print(f"  pairs submitted           {counts['submitted']:>6,}")
    print(f"  NEW names added           {counts['added']:>6,}")
    print(f"  already present           "
          f"{counts['submitted'] - counts['added']:>6,}")

    session = SessionLocal()
    try:
        total, certs = session.execute(text("""
            SELECT COUNT(*), COUNT(DISTINCT certificate_designator)
            FROM gtj.certificate_dbas
        """)).first()
        multi = session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT certificate_designator FROM gtj.certificate_dbas
                GROUP BY certificate_designator HAVING COUNT(*) > 1
            ) t
        """)).scalar()
        print()
        print(f"  certificate_dbas now      {total:,} names / {certs:,} certificates")
        print(f"  certificates with >1 name {multi:,}")
    finally:
        session.close()

    print(f"\n{'=' * 72}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
