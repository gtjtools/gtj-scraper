#!/usr/bin/env python3
"""
Back up (and restore) the tables that TrustScore v5.0 rescoring will modify.

Run this BEFORE any v5.0 rescore. v5.0 produces materially different numbers
from v3 — different formulas, different inputs — so a rescore overwrites every
operator's standing score with no way back unless it was captured first.

WHAT IS AFFECTED
----------------
Two tables, found by tracing every write in the scoring path
(`scoring/router.py` and `workflows/batch_verify_workflow.py`):

  gtj.operators      UPDATED IN PLACE — the destructive one. Three columns are
                     overwritten per operator and the previous values are not
                     retained anywhere:
                        trust_score
                        trust_score_updated_at
                        rating_tiers
                     Only these three are backed up; the rest of the row is
                     untouched by scoring and restoring it could clobber
                     unrelated edits.

  gtj.trust_scores   APPEND-ONLY — one new row per scoring run. Historical rows
                     are not modified, so this table is recoverable by deleting
                     rows created after a known timestamp. It is captured anyway
                     so a restore can return the table to an exact prior state.

`gtj.quote_options.trust_score` is NOT affected: it is a snapshot written at
quote time and never updated by a rescore.

USAGE
-----
    python scripts/backup_trustscore_tables.py backup
    python scripts/backup_trustscore_tables.py backup --label pre-v5-cutover
    python scripts/backup_trustscore_tables.py verify  <file>
    python scripts/backup_trustscore_tables.py restore <file> --dry-run
    python scripts/backup_trustscore_tables.py restore <file> --confirm

Backups are gzipped JSON under `backups/` with a UTC timestamp in the name.
Restore refuses to run without `--confirm`, and `--dry-run` reports exactly
what would change without writing.

SAFETY
------
`backup` and `verify` are read-only. `restore` writes, and defaults to a dry
run. The script prints the target host and schema before doing anything, so a
wrong-environment mistake is visible before it is irreversible.
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import json
import os
import socket
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

# Allow running as `python scripts/backup_trustscore_tables.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.common.config import DATABASE_URL, SessionLocal  # noqa: E402

SCHEMA = os.getenv("DB_SCHEMA", "gtj")
BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"

#: The only `operators` columns a rescore touches. Restoring more than this
#: risks reverting unrelated edits made since the backup.
OPERATOR_SCORE_COLUMNS = ("trust_score", "trust_score_updated_at", "rating_tiers")

#: Full column list for trust_scores — the table is append-only, so a complete
#: capture lets a restore rebuild it exactly.
TRUST_SCORE_COLUMNS = (
    "trust_score_id", "operator_id", "overall_score", "safety_score",
    "financial_score", "regulatory_score", "aog_score", "factors",
    "calculated_at", "version", "expires_at", "confidence_level",
)

FORMAT_VERSION = 1


# ── JSON helpers ─────────────────────────────────────────────────────────────

def _encode(value: Any) -> Any:
    """
    Make a database value JSON-safe without losing precision.

    Decimals become strings, not floats: a score of 97.14 must survive a
    round-trip exactly, and float would not guarantee that.
    """
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, float):
        return value
    return str(value)


def _decode(value: Any) -> Any:
    """Inverse of `_encode`."""
    if isinstance(value, dict):
        if "__decimal__" in value:
            return Decimal(value["__decimal__"])
        if "__datetime__" in value:
            return datetime.fromisoformat(value["__datetime__"])
        if "__uuid__" in value:
            return UUID(value["__uuid__"])
    return value


def _decode_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _decode(value) for key, value in row.items()}


# ── Environment reporting ────────────────────────────────────────────────────

def _target_description() -> str:
    """
    Describe the database this script will act on, without leaking the password.

    Printed before every operation so a wrong-environment run is caught by the
    operator, not discovered afterwards.
    """
    try:
        after_at = DATABASE_URL.split("@", 1)[1]
        host = after_at.split("/", 1)[0]
    except (IndexError, AttributeError):
        host = "unknown"
    return f"{host}  schema={SCHEMA}"


def _print_target(action: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {action}")
    print(f"  target : {_target_description()}")
    print(f"  time   : {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 72}\n")


# ── Backup ───────────────────────────────────────────────────────────────────

def backup(label: Optional[str] = None, output: Optional[Path] = None) -> Path:
    """
    Capture the current state of both affected tables.

    Read-only. Returns the path to the written archive.

    Args:
        label: Optional tag embedded in the filename, e.g. "pre-v5-cutover".
        output: Explicit output path, overriding the generated name.

    Returns:
        Path to the gzipped JSON backup.
    """
    _print_target("BACKUP (read-only)")

    session = SessionLocal()
    try:
        operator_rows = [
            dict(row._mapping) for row in session.execute(text(f"""
                SELECT operator_id, name, certificate_number,
                       {", ".join(OPERATOR_SCORE_COLUMNS)}
                FROM {SCHEMA}.operators
                ORDER BY operator_id
            """))
        ]
        print(f"  gtj.operators     : {len(operator_rows):,} rows")

        scored = sum(1 for row in operator_rows if row.get("trust_score") is not None)
        print(f"                      {scored:,} with a trust_score set")

        trust_rows = [
            dict(row._mapping) for row in session.execute(text(f"""
                SELECT {", ".join(TRUST_SCORE_COLUMNS)}
                FROM {SCHEMA}.trust_scores
                ORDER BY calculated_at
            """))
        ]
        print(f"  gtj.trust_scores  : {len(trust_rows):,} rows")

        versions: Dict[str, int] = {}
        for row in trust_rows:
            key = str(row.get("version") or "unknown")
            versions[key] = versions.get(key, 0) + 1
        if versions:
            summary = ", ".join(f"v{k}={v:,}" for k, v in sorted(versions.items()))
            print(f"                      by version: {summary}")
    finally:
        session.close()

    payload = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": f"{getpass.getuser()}@{socket.gethostname()}",
        "label": label,
        "target": _target_description(),
        "schema": SCHEMA,
        "note": (
            "Pre-TrustScore-v5.0 backup. operators rows carry only the three "
            "score columns a rescore overwrites; trust_scores rows are complete."
        ),
        "tables": {
            "operators": {
                "restorable_columns": list(OPERATOR_SCORE_COLUMNS),
                "key": "operator_id",
                "rows": [
                    {key: _encode(value) for key, value in row.items()}
                    for row in operator_rows
                ],
            },
            "trust_scores": {
                "restorable_columns": list(TRUST_SCORE_COLUMNS),
                "key": "trust_score_id",
                "rows": [
                    {key: _encode(value) for key, value in row.items()}
                    for row in trust_rows
                ],
            },
        },
    }

    if output is None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = f"_{label}" if label else ""
        output = BACKUP_DIR / f"trustscore_backup_{stamp}{suffix}.json.gz"

    with gzip.open(output, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    size_mb = output.stat().st_size / 1_048_576
    print(f"\n  ✓ written: {output}")
    print(f"    {size_mb:.2f} MB gzipped\n")
    return output


# ── Verify ───────────────────────────────────────────────────────────────────

def verify(path: Path) -> bool:
    """
    Check an archive is readable and report how it differs from the live tables.

    Read-only. Run this after a rescore to see exactly what moved, and before a
    restore to confirm the archive is intact.

    Returns:
        True if the archive parses and its schema matches the current target.
    """
    _print_target(f"VERIFY (read-only): {path.name}")

    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        print(f"  ✗ could not read archive: {exc}\n")
        return False

    print(f"  created    : {payload.get('created_at')}")
    print(f"  by         : {payload.get('created_by')}")
    print(f"  label      : {payload.get('label') or '(none)'}")
    print(f"  source     : {payload.get('target')}")

    if payload.get("format_version") != FORMAT_VERSION:
        print(f"  ⚠ format version {payload.get('format_version')} "
              f"(this script writes {FORMAT_VERSION})")

    if payload.get("target") != _target_description():
        print(f"  ⚠ archive came from a DIFFERENT target than the current one:")
        print(f"      archive : {payload.get('target')}")
        print(f"      current : {_target_description()}")

    operators = payload["tables"]["operators"]["rows"]
    trust_scores = payload["tables"]["trust_scores"]["rows"]
    print(f"\n  archived   : {len(operators):,} operators, {len(trust_scores):,} trust_scores")

    session = SessionLocal()
    try:
        live_ops = {
            str(row._mapping["operator_id"]): dict(row._mapping)
            for row in session.execute(text(f"""
                SELECT operator_id, {", ".join(OPERATOR_SCORE_COLUMNS)}
                FROM {SCHEMA}.operators
            """))
        }
        live_trust_count = session.execute(
            text(f"SELECT COUNT(*) FROM {SCHEMA}.trust_scores")
        ).scalar()
    finally:
        session.close()

    changed: List[str] = []
    missing = 0
    for archived in operators:
        operator_id = _decode(archived["operator_id"])
        live = live_ops.get(str(operator_id))
        if live is None:
            missing += 1
            continue
        for column in OPERATOR_SCORE_COLUMNS:
            if _decode(archived.get(column)) != live.get(column):
                changed.append(
                    f"{archived.get('name') or operator_id}: "
                    f"{column} {_decode(archived.get(column))!r} -> {live.get(column)!r}"
                )
                break

    print(f"  live now   : {len(live_ops):,} operators, {live_trust_count:,} trust_scores")
    print(f"\n  operators differing from archive : {len(changed):,}")
    if missing:
        print(f"  operators in archive but now gone: {missing:,}")
    for line in changed[:15]:
        print(f"      {line}")
    if len(changed) > 15:
        print(f"      … and {len(changed) - 15:,} more")

    delta = live_trust_count - len(trust_scores)
    if delta:
        print(f"\n  trust_scores rows added since backup: {delta:,}")
    print()
    return True


# ── Restore ──────────────────────────────────────────────────────────────────

def restore(path: Path, confirm: bool = False, dry_run: bool = True) -> bool:
    """
    Roll the affected tables back to an archived state.

    Restores only `OPERATOR_SCORE_COLUMNS` on `operators` — deliberately not the
    whole row, so unrelated edits made since the backup survive.

    For `trust_scores`, rows present in the archive are left alone and rows
    created *after* the backup are deleted. That is what makes the rollback
    exact; it is also destructive, which is why `--confirm` is required.

    Args:
        path: Archive to restore from.
        confirm: Must be True to write anything.
        dry_run: Report what would change without writing.

    Returns:
        True if the operation completed (or would have, in dry-run).
    """
    mode = "DRY RUN" if dry_run or not confirm else "RESTORE (WRITES)"
    _print_target(f"{mode}: {path.name}")

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)

    if payload.get("target") != _target_description():
        print("  ✗ REFUSING: archive was taken from a different database.")
        print(f"      archive : {payload.get('target')}")
        print(f"      current : {_target_description()}")
        print("    Restoring across environments is almost never intended.\n")
        return False

    archived_ops = [_decode_row(row) for row in payload["tables"]["operators"]["rows"]]
    archived_trust_ids = {
        str(_decode(row["trust_score_id"]))
        for row in payload["tables"]["trust_scores"]["rows"]
    }

    session = SessionLocal()
    try:
        live_ops = {
            str(row._mapping["operator_id"]): dict(row._mapping)
            for row in session.execute(text(f"""
                SELECT operator_id, {", ".join(OPERATOR_SCORE_COLUMNS)}
                FROM {SCHEMA}.operators
            """))
        }

        to_update = [
            row for row in archived_ops
            if str(row["operator_id"]) in live_ops
            and any(
                row.get(column) != live_ops[str(row["operator_id"])].get(column)
                for column in OPERATOR_SCORE_COLUMNS
            )
        ]

        live_trust_ids = {
            str(row._mapping["trust_score_id"])
            for row in session.execute(
                text(f"SELECT trust_score_id FROM {SCHEMA}.trust_scores")
            )
        }
        to_delete = live_trust_ids - archived_trust_ids

        print(f"  operators to revert      : {len(to_update):,}")
        print(f"  trust_scores to delete   : {len(to_delete):,}")
        print("    (rows created after the backup; archived rows are untouched)")

        if dry_run or not confirm:
            print("\n  Nothing written. Re-run with --confirm to apply.\n")
            return True

        for row in to_update:
            session.execute(
                text(f"""
                    UPDATE {SCHEMA}.operators
                    SET trust_score = :trust_score,
                        trust_score_updated_at = :updated_at,
                        rating_tiers = :rating_tiers
                    WHERE operator_id = :operator_id
                """),
                {
                    "trust_score": row.get("trust_score"),
                    "updated_at": row.get("trust_score_updated_at"),
                    "rating_tiers": row.get("rating_tiers"),
                    "operator_id": row["operator_id"],
                },
            )

        if to_delete:
            session.execute(
                text(f"""
                    DELETE FROM {SCHEMA}.trust_scores
                    WHERE trust_score_id = ANY(:ids)
                """),
                {"ids": list(to_delete)},
            )

        session.commit()
        print(f"\n  ✓ reverted {len(to_update):,} operators, "
              f"deleted {len(to_delete):,} trust_scores rows\n")
        return True
    except Exception as exc:
        session.rollback()
        print(f"\n  ✗ restore failed, rolled back: {exc}\n")
        return False
    finally:
        session.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Back up / restore tables affected by TrustScore rescoring.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backup_cmd = sub.add_parser("backup", help="capture current state (read-only)")
    backup_cmd.add_argument("--label", help="tag for the filename, e.g. pre-v5-cutover")
    backup_cmd.add_argument("--output", type=Path, help="explicit output path")

    verify_cmd = sub.add_parser("verify", help="check an archive and diff it against live")
    verify_cmd.add_argument("file", type=Path)

    restore_cmd = sub.add_parser("restore", help="roll back to an archived state")
    restore_cmd.add_argument("file", type=Path)
    restore_cmd.add_argument("--confirm", action="store_true",
                             help="actually write; without this it is a dry run")
    restore_cmd.add_argument("--dry-run", action="store_true", default=False,
                             help="report changes without writing (default without --confirm)")

    args = parser.parse_args()

    try:
        if args.command == "backup":
            backup(label=args.label, output=args.output)
        elif args.command == "verify":
            if not args.file.exists():
                print(f"No such file: {args.file}")
                return 1
            return 0 if verify(args.file) else 1
        elif args.command == "restore":
            if not args.file.exists():
                print(f"No such file: {args.file}")
                return 1
            dry = args.dry_run or not args.confirm
            return 0 if restore(args.file, confirm=args.confirm, dry_run=dry) else 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
