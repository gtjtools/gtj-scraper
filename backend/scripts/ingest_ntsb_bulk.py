#!/usr/bin/env python3
"""
Ingest the NTSB bulk aviation export into `gtj.ntsb_incidents`.

WHY THIS EXISTS
---------------
Scoring queries NTSB CAROL live. On 2026-11-20 CAROL returned HTTP 500 to
every query — registration and operator name alike — for at least a day. The
scoring path caught the exception, assigned a perfect safety score and carried
on, so operators with fatal accidents on record came out Pinnacle. That hole
is now closed in the scorer (§3a: an unreachable source damps confidence and
flags safety GREY), but a flag is not evidence. This supplies the evidence.

NTSB publishes the whole dataset as a Microsoft Access database at
https://data.ntsb.gov/avdata — `avall.zip`, ~97 MB compressed, 564 MB of
`avall.mdb`. It stayed up throughout the CAROL outage, which is precisely when
a fallback is wanted.

WHAT THIS FIXES BEYOND THE OUTAGE
---------------------------------
`gtj.ntsb_incidents` was last written 2026-01-12 and held 247 rows with a
tail number on TWO of them. A tail-keyed lookup against it was therefore
useless. The bulk export carries a `regis_no` on 100% of aircraft rows,
because registration lives in the `aircraft` table rather than the `events`
summary — joining the two is what populates it.

Measured on the 2026-11-20 download:

    events                       31,453   2008-01-01 .. 2026-10-28
    aircraft rows                32,010
    with a registration          31,966   (100%)
    Part 135 aircraft               932
    fatal events                  6,421

READING AN MDB WITHOUT MDBTOOLS
-------------------------------
`access-parser` is a pure-Python Jet reader, so this needs no system binary —
mdbtools is not installed on the scoring host and cannot be added without a
package manager. The file is Standard Jet DB (Access 97 / Jet 3).

USAGE
-----
    python scripts/ingest_ntsb_bulk.py              # download, parse, load
    python scripts/ingest_ntsb_bulk.py --dry-run    # parse and report only
    python scripts/ingest_ntsb_bulk.py --part-135   # only Part 135 aircraft
    python scripts/ingest_ntsb_bulk.py --keep       # keep the download

Safe to re-run: rows are upserted on `ntsb_number`, so a second pass updates
rather than duplicates. Nothing is deleted.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402

AVALL_URL = (
    "https://data.ntsb.gov/avdata/FileDirectory/DownloadFile?fileID=avall.zip"
)

#: NTSB injury codes -> `gtj.ntsb_injury_level` enum labels.
#:
#: Verified against the live enum, not guessed: FATAL / SERIOUS / MINOR / NONE.
#: The bulk export uses four-letter codes (FATL/SERS/MINR/NONE), so these
#: cannot be passed through. An unmapped code falls back to the column default
#: rather than failing the row — the column is NOT NULL with default 'NONE'.
INJURY_LABELS = {
    "FATL": "FATAL",
    "SERS": "SERIOUS",
    "MINR": "MINOR",
    "NONE": "NONE",
}

#: NTSB damage codes -> `gtj.aircraft_damage_level` enum labels.
#:
#: DESTROYED is what the §4.1a hull-loss circuit breaker matches on
#: (CATASTROPHIC_DAMAGE_TERMS looks for "DESTROY"), so this mapping is what
#: makes a bulk-imported hull loss trip the breaker. UNK has no enum member
#: and is deliberately dropped rather than coerced to NONE — "unknown damage"
#: is not "no damage".
DAMAGE_LABELS = {
    "DEST": "DESTROYED",
    "SUBS": "SUBSTANTIAL",
    "MINR": "MINOR",
    "NONE": "NONE",
}

#: Registration placeholders that are not registrations.
#:
#: NTSB records an unidentified airframe as UNREG / UNKNOWN / "NOT REPORTE" /
#: "UNREGISTERE" (its own column is narrow, so its placeholders are truncated
#: mid-word). Storing these as tail numbers would make them matchable: a fleet
#: lookup for "UNKNOWN" would return unrelated accidents, and 153 rows share
#: "UNREG" alone. They are stored as NULL — the airframe is genuinely
#: unidentified, which is different from having a tail we failed to read.
REGISTRATION_PLACEHOLDERS = frozenset({
    "UNREG", "UNREGISTERED", "UNREGISTERE", "UNKNOWN", "UNK", "NONE",
    "NOT REPORTED", "NOT REPORTE", "NO REG", "NOREG",
})

#: gtj.ntsb_incidents.tail_number is varchar(10) and ntsb_number varchar(20).
#: Two real foreign registrations exceed 10 ("HP-1539 CMP", "GBR-OP-Z4N5"), so
#: they are truncated rather than dropped — a truncated foreign tail is still
#: more useful than no record of the accident.
TAIL_MAX = 10
NTSB_NUMBER_MAX = 20

#: NTSB event types -> `ntsb_event_type` enum. NOT NULL with no default, so an
#: unrecognised value has to resolve to something; ACCIDENT is the cautious
#: choice because it is the graver of the two.
EVENT_TYPE_LABELS = {
    "ACC": "ACCIDENT",
    "INC": "INCIDENT",
}


def download(destination: Path) -> Path:
    """Fetch avall.zip, streaming — it is ~97 MB."""
    print(f"  downloading {AVALL_URL}")
    with httpx.stream(
        "GET", AVALL_URL, timeout=600.0, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TrustJet/1.0)"},
    ) as response:
        response.raise_for_status()
        written = 0
        with open(destination, "wb") as handle:
            for chunk in response.iter_bytes(8 << 20):
                handle.write(chunk)
                written += len(chunk)
                print(f"\r    {written:,} bytes", end="", flush=True)
    print()
    return destination


def extract(archive: Path, target_dir: Path) -> Path:
    """Unpack avall.mdb. It is 564 MB, so this needs real disk."""
    with zipfile.ZipFile(archive) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".mdb"))
        out = target_dir / name
        print(f"  extracting {name}")
        with zf.open(name) as src, open(out, "wb") as dst:
            while True:
                chunk = src.read(8 << 20)
                if not chunk:
                    break
                dst.write(chunk)
    print(f"    {out.stat().st_size:,} bytes")
    return out


def _rows(table: Dict[str, List[Any]]) -> Iterator[Dict[str, Any]]:
    """
    access-parser returns {column: [values]}; yield row dicts instead.

    Columns are not guaranteed equal length on a damaged page, so this walks
    to the SHORTEST column rather than assuming a rectangle — a ragged read
    would otherwise raise IndexError partway through a 32,000-row table.
    """
    columns = list(table.keys())
    if not columns:
        return
    length = min(len(table[c]) for c in columns)
    for index in range(length):
        yield {c: table[c][index] for c in columns}


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)[:19])
    except (TypeError, ValueError):
        return None


def parse(mdb_path: Path, part_135_only: bool = False) -> List[Dict[str, Any]]:
    """
    Join `events` to `aircraft` and emit one record per aircraft involved.

    ONE ROW PER AIRCRAFT, NOT PER EVENT. A collision involves two airframes
    and both carry risk; keying on the event alone would drop one of them.
    This is the same multi-aircraft case `_extract_field_values` handles for
    the live CAROL path.
    """
    from access_parser import AccessParser

    print("  parsing MDB")
    db = AccessParser(str(mdb_path))
    events = {}
    for row in _rows(db.parse_table("events")):
        ev_id = _clean(row.get("ev_id"))
        if ev_id:
            events[ev_id] = row
    print(f"    events: {len(events):,}")

    # How many aircraft share each event. `gtj.ntsb_incidents.ntsb_number` is
    # UNIQUE, so a per-aircraft row needs a per-aircraft key — otherwise the
    # second airframe of a collision overwrites the first and is lost.
    # Measured: 548 of 31,453 events (1.7%) involve more than one aircraft,
    # up to 5. Single-aircraft events keep the bare NTSB number so they stay
    # joinable to anything already referencing it.
    aircraft_rows = list(_rows(db.parse_table("aircraft")))
    per_event: Dict[str, int] = {}
    for row in aircraft_rows:
        ev_id = _clean(row.get("ev_id"))
        if ev_id:
            per_event[ev_id] = per_event.get(ev_id, 0) + 1

    records: List[Dict[str, Any]] = []
    seen_keys: Dict[str, int] = {}
    skipped_no_event = 0
    for row in aircraft_rows:
        ev_id = _clean(row.get("ev_id"))
        if not ev_id:
            continue
        event = events.get(ev_id)
        if event is None:
            # An aircraft row whose event is absent cannot be dated or graded,
            # and an undated accident is treated as fully retained by the decay
            # arithmetic — so importing it would create a permanent maximum-
            # weight penalty from a broken join.
            skipped_no_event += 1
            continue

        far_part = _clean(row.get("far_part")) or ""
        if part_135_only and far_part != "135":
            continue

        injury = INJURY_LABELS.get(
            (_clean(event.get("ev_highest_injury")) or "").upper(), "NONE"
        )
        damage = DAMAGE_LABELS.get(
            (_clean(row.get("damage")) or "").upper()
        )
        event_type = EVENT_TYPE_LABELS.get(
            (_clean(event.get("ev_type")) or "").upper(), "ACCIDENT"
        )

        raw_tail = (_clean(row.get("regis_no")) or "").upper() or None
        if raw_tail in REGISTRATION_PLACEHOLDERS:
            # Unidentified airframe — NULL, not a matchable pseudo-tail.
            tail = None
        else:
            tail = raw_tail[:TAIL_MAX] if raw_tail else None

        # The PUBLIC NTSB number (WPR26MA063), not the internal ev_id
        # (20251218202182). CAROL returns the former, our catastrophe
        # references record the former, and a broker looking up a docket uses
        # the former — keying on ev_id made the table unjoinable to everything
        # else that mentions an accident. Present on all 31,453 events.
        ntsb_no = _clean(event.get("ntsb_no")) or ev_id

        # Suffix the key ONLY on multi-aircraft events, so the common case
        # keeps the plain NTSB number.
        #
        # The tail is not always a distinguisher: event 20180119X02802 is two
        # unregistered ultralights, both recorded as "UNREG". An ordinal is
        # appended so the second airframe is still imported rather than
        # colliding — the whole point of the per-aircraft key.
        key = ntsb_no
        if per_event.get(ev_id, 1) > 1:
            seen = seen_keys.get(ev_id, 0)
            seen_keys[ev_id] = seen + 1
            suffix = tail or f"{seen + 1}"
            key = f"{ntsb_no}#{suffix}"[:NTSB_NUMBER_MAX]

        records.append({
            "ntsb_number": key,
            "ntsb_event_id": ev_id,
            "public_docket": ntsb_no,
            "event_date": _as_date(event.get("ev_date")),
            "tail_number": tail,
            "aircraft_make_model": " ".join(
                p for p in (_clean(row.get("acft_make")),
                            _clean(row.get("acft_model"))) if p
            ) or None,
            "aircraft_damage": damage,
            "highest_injury": injury,
            "total_fatalities": _as_int(event.get("inj_tot_f")),
            "location_city": _clean(event.get("ev_city")),
            "location_state": _clean(event.get("ev_state")),
            "location_country": _clean(event.get("ev_country")),
            "operator_name": _clean(row.get("oper_name")),
            "far_part": far_part or None,
            "event_type": event_type,
            "ev_type_raw": _clean(event.get("ev_type")),
        })

    if skipped_no_event:
        print(f"    skipped {skipped_no_event:,} aircraft rows with no matching event")
    print(f"    records: {len(records):,}")
    return records


def load(records: List[Dict[str, Any]], batch: int = 2000) -> int:
    """
    Upsert into gtj.ntsb_incidents, batched.

    Keyed on `ntsb_number`, which `parse` makes unique per AIRCRAFT rather
    than per event — a collision involves several airframes and each is a
    separate row. Re-running updates rather than duplicating; nothing is ever
    deleted.

    USES execute_values, NOT ONE EXECUTE PER ROW. The first version issued
    32,010 separate statements and ran at roughly 100 rows/minute — a 3-to-4
    hour load, measured, for a dataset that fits in memory. Every refresh
    would have paid that. Batched multi-row VALUES brings it to minutes.

    The whole load is ONE transaction per batch, so an interruption leaves
    completed batches committed and the rest absent — safe to re-run, since
    the upsert is idempotent.
    """
    import json

    from psycopg2.extras import execute_values

    from src.common.config import engine

    columns = (
        "ntsb_number", "public_docket", "event_date", "event_type",
        "highest_injury", "aircraft_damage", "tail_number",
        "aircraft_make_model", "operator_name", "total_fatalities",
        "location_city", "location_state", "location_country", "raw_data",
    )

    # The three enum columns need an explicit cast in the VALUES template;
    # psycopg2 sends them as text and Postgres will not coerce implicitly.
    template = (
        "(%(ntsb_number)s, %(public_docket)s, %(event_date)s,"
        " CAST(%(event_type)s AS gtj.ntsb_event_type),"
        " CAST(%(highest_injury)s AS gtj.ntsb_injury_level),"
        " CAST(%(aircraft_damage)s AS gtj.aircraft_damage_level),"
        " %(tail_number)s, %(aircraft_make_model)s, %(operator_name)s,"
        " %(total_fatalities)s, %(location_city)s, %(location_state)s,"
        " %(location_country)s, 'NTSB_BULK_AVALL', now(),"
        " CAST(%(raw_data)s AS jsonb))"
    )

    sql = f"""
        INSERT INTO gtj.ntsb_incidents (
            {", ".join(columns[:-1])}, data_source, last_verified, raw_data
        ) VALUES %s
        ON CONFLICT (ntsb_number) DO UPDATE SET
            event_date = EXCLUDED.event_date,
            event_type = EXCLUDED.event_type,
            highest_injury = EXCLUDED.highest_injury,
            aircraft_damage = EXCLUDED.aircraft_damage,
            public_docket = EXCLUDED.public_docket,
            tail_number = COALESCE(EXCLUDED.tail_number,
                                   gtj.ntsb_incidents.tail_number),
            aircraft_make_model = EXCLUDED.aircraft_make_model,
            operator_name = EXCLUDED.operator_name,
            total_fatalities = EXCLUDED.total_fatalities,
            location_city = EXCLUDED.location_city,
            location_state = EXCLUDED.location_state,
            location_country = EXCLUDED.location_country,
            data_source = 'NTSB_BULK_AVALL',
            last_verified = now(),
            raw_data = EXCLUDED.raw_data
    """

    written = 0
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            for start in range(0, len(records), batch):
                slice_ = records[start:start + batch]
                rows = [
                    {**{k: record.get(k) for k in columns[:-1]},
                     "raw_data": json.dumps(record, default=str)}
                    for record in slice_
                ]
                execute_values(cursor, sql, rows, template=template,
                               page_size=batch)
                raw.commit()
                written += len(slice_)
                print(f"\r    loaded {written:,}/{len(records):,}",
                      end="", flush=True)
        print()
        return written
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and report, write nothing")
    parser.add_argument("--part-135", action="store_true",
                        help="import only Part 135 aircraft")
    parser.add_argument("--keep", action="store_true",
                        help="keep the downloaded archive and MDB")
    parser.add_argument("--mdb", help="use an already-extracted MDB")
    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print("  NTSB bulk ingest (avall.mdb)")
    print(f"{'=' * 70}")

    workdir = Path(tempfile.mkdtemp(prefix="ntsb_bulk_"))
    try:
        if args.mdb:
            mdb = Path(args.mdb)
            print(f"  using {mdb}")
        else:
            archive = download(workdir / "avall.zip")
            mdb = extract(archive, workdir)

        records = parse(mdb, part_135_only=args.part_135)
        if not records:
            print("  nothing parsed — aborting rather than writing an empty set")
            return 1

        dated = [r for r in records if r["event_date"]]
        tailed = [r for r in records if r["tail_number"]]
        fatal = [r for r in records if (r["total_fatalities"] or 0) > 0]
        print()
        print(f"  with a date:        {len(dated):,}")
        print(f"  with a tail number: {len(tailed):,} "
              f"({100 * len(tailed) / len(records):.0f}%)")
        print(f"  fatal:              {len(fatal):,}")
        if dated:
            print(f"  newest event:       "
                  f"{max(r['event_date'] for r in dated).date()}")

        if args.dry_run:
            print("\n  --dry-run: nothing written")
            return 0

        print()
        written = load(records)
        print(f"\n  upserted {written:,} rows into gtj.ntsb_incidents")
        return 0
    finally:
        if not args.keep and not args.mdb:
            import shutil
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
