#!/usr/bin/env python3
"""
Score every tail in gtj.aircraft, pausing between each one.

Wraps scripts/score_tail.py in a loop. The pause matters: each tail triggers a
live NTSB query and an SDRS fetch, so running 11,000 of them back to back would
hammer federal endpoints and risk rate limiting or a block. 30 seconds is the
default; raise it if the FAA starts refusing connections.

WHERE RESULTS GO
----------------
gtj.trust_scores is keyed by operator_id and has no tail_number column, so a
per-tail score has nowhere to live in the current schema. Rather than invent a
storage shape, results go to:

  1. A local .jsonl in `data/tail_scores/`, appended and flushed per tail.
     This is the write-ahead record: it survives a crash, a lost network, or a
     failed upload, and it is what --resume reads.

  2. S3, uploaded at the end of the run (and periodically during it), to
     `s3://$S3_BUCKET/trustscore/tails/<file>.jsonl`.

The local file is written first and never deleted. An S3 outage degrades the
run to local-only rather than losing scores that took minutes each to compute.

Requires S3_BUCKET plus normal AWS credentials (env, profile, or instance
role). Without them the run still works and simply skips the upload.

USAGE
-----
    python scripts/score_all_tails.py --dry-run          # list what would run
    python scripts/score_all_tails.py --limit 5          # try a handful first
    python scripts/score_all_tails.py --operator "NetJets Aviation, Inc."
    python scripts/score_all_tails.py                    # everything

    python scripts/score_all_tails.py --delay 60         # slower
    python scripts/score_all_tails.py --resume out.jsonl # skip tails already done

TIMING
------
A single tail takes roughly 10-40s depending on how the scrapers respond. With
the default 30s pause, budget about a minute per tail: ~11,000 tails is on the
order of a week of wall-clock time. Use --operator or --limit for anything
other than a deliberate full run, and prefer --resume over starting again.

Ctrl-C is handled: the run stops cleanly and whatever completed stays in the
output file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402

# Reuse the single-tail scorer rather than duplicating its logic.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "score_tail", Path(__file__).resolve().parent / "score_tail.py"
)
score_tail = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score_tail)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "tail_scores"

# Mirrors gtj-serverless/lib/common/s3.js: bucket from S3_BUCKET (default
# gtj-assets), region from AWS_REGION (default us-east-1), path-style keys.
S3_BUCKET = os.getenv("S3_BUCKET", "gtj-assets")
S3_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_PREFIX = "trustscore/tails"

# Set by the SIGINT handler so an in-flight tail finishes before stopping.
_stop_requested = False


def _handle_sigint(_signum, _frame) -> None:
    global _stop_requested
    if _stop_requested:
        print("\n  Second interrupt — exiting immediately.")
        sys.exit(130)
    _stop_requested = True
    print("\n  Interrupt received — finishing the current tail, then stopping.")
    print("  Press Ctrl-C again to abort now.")


def fetch_tails(operator: Optional[str], limit: Optional[int]) -> List[Dict[str, Any]]:
    """
    List the tails to score, newest-registered first.

    Ordered deterministically so a --resume run walks the same sequence.
    """
    clauses, params = [], {}
    if operator:
        clauses.append("o.name ILIKE :operator")
        params["operator"] = f"%{operator}%"

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT a.tail_number, a.make_model, a.year, o.name AS operator_name
        FROM gtj.aircraft a
        JOIN gtj.operators o ON o.operator_id = a.operator_id
        {where}
        ORDER BY o.name, a.tail_number
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    session = SessionLocal()
    try:
        return [dict(r) for r in session.execute(text(sql), params).mappings()]
    finally:
        session.close()


def load_completed(path: Optional[Path]) -> Set[str]:
    """Tail numbers already present in a previous output file, for --resume."""
    if not path or not path.exists():
        return set()
    done: Set[str] = set()
    with path.open() as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # a partial final line from an aborted run
            tail = row.get("tail_number")
            if tail:
                done.add(tail.upper())
    return done


def upload_to_s3(path: Path) -> Optional[str]:
    """
    Upload the results file to S3, returning its URL.

    Deliberately non-fatal. Scores cost minutes of scraping each, and they are
    already safe in `path` before this runs — a credentials or network problem
    must not end the run or discard work. Returns None and explains itself on
    any failure.
    """
    if not path.exists() or path.stat().st_size == 0:
        return None

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        print("  ⚠ boto3 not installed — results stayed local only.")
        return None

    key = f"{S3_PREFIX}/{path.name}"
    try:
        boto3.client("s3", region_name=S3_REGION).upload_file(
            str(path), S3_BUCKET, key,
            ExtraArgs={"ContentType": "application/x-ndjson"},
        )
    except NoCredentialsError:
        print("  ⚠ no AWS credentials — results stayed local only.")
        return None
    except (BotoCoreError, ClientError) as exc:
        print(f"  ⚠ S3 upload failed ({str(exc)[:60]}) — results stayed local only.")
        return None

    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"


async def run(args: argparse.Namespace) -> int:
    tails = fetch_tails(args.operator, args.limit)
    if not tails:
        print("\n  No tails matched.\n")
        return 1

    completed = load_completed(Path(args.resume) if args.resume else None)
    pending = [t for t in tails if t["tail_number"].upper() not in completed]

    estimate_min = len(pending) * (args.delay + 25) / 60

    print(f"\n{'=' * 70}")
    print("  BATCH TAIL SCORING")
    print(f"  tails matched : {len(tails):,}")
    if completed:
        print(f"  already done  : {len(completed):,} (skipped via --resume)")
    print(f"  to score      : {len(pending):,}")
    print(f"  delay         : {args.delay}s between tails")
    print(f"  rough ETA     : {estimate_min / 60:.1f} hours"
          if estimate_min > 90 else f"  rough ETA     : {estimate_min:.0f} minutes")
    print(f"  narrative     : {'yes' if args.narrative else 'no'}")
    print(f"{'=' * 70}\n")

    if args.dry_run:
        for t in pending[:40]:
            print(f"  {t['tail_number']:<10} {t['operator_name'][:40]:<42} {t['make_model']}")
        if len(pending) > 40:
            print(f"  … and {len(pending) - 40:,} more")
        print("\n  Dry run — nothing scored.\n")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.resume) if args.resume else OUTPUT_DIR / f"tail_scores_{stamp}.jsonl"
    print(f"  writing to {out_path}\n")

    signal.signal(signal.SIGINT, _handle_sigint)

    scored = failed = 0
    started = datetime.now(timezone.utc)

    for index, row in enumerate(pending, start=1):
        if _stop_requested:
            print("\n  Stopping as requested.")
            break

        tail = row["tail_number"]
        prefix = f"  [{index}/{len(pending)}] {tail}"

        try:
            outcome = await score_tail.score(tail, args.narrative)
        except Exception as exc:
            failed += 1
            print(f"{prefix}  ERROR: {str(exc)[:60]}")
            _append(out_path, {
                "tail_number": tail,
                "operator_name": row["operator_name"],
                "error": str(exc),
                "scored_at": datetime.now(timezone.utc).isoformat(),
            })
            outcome = None

        if outcome is not None:
            result, gaps, record = outcome
            scored += 1
            print(f"{prefix}  {result['trust_score']} ({result['tier']})"
                  f"   fleet {result['fleet_score']}   gaps {len(gaps)}")
            _append(out_path, {
                "tail_number": tail,
                "operator_name": record["operator_name"],
                "certificate_designator": record.get("faa_dsgn_code"),
                "trust_score": result["trust_score"],
                "tier": result["tier"],
                "fleet_score": result["fleet_score"],
                "components": result["components"],
                "unevidenced_inputs": gaps,
                "risk_audit": result.get("risk_audit"),
                "scored_at": datetime.now(timezone.utc).isoformat(),
            })

        # Checkpoint to S3 periodically so a long run is recoverable from
        # anywhere, not just this machine.
        if args.s3 and args.checkpoint_every and index % args.checkpoint_every == 0:
            if upload_to_s3(out_path):
                print(f"  … checkpointed to S3 after {index} tails")

        # Pause between tails, but never after the last one.
        if index < len(pending) and not _stop_requested:
            await asyncio.sleep(args.delay)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 60
    print(f"\n{'=' * 70}")
    print(f"  scored  : {scored:,}")
    print(f"  failed  : {failed:,}")
    print(f"  elapsed : {elapsed:.1f} minutes")
    print(f"  output  : {out_path}")

    if args.s3:
        url = upload_to_s3(out_path)
        if url:
            print(f"  s3      : {url}")
    else:
        print("  s3      : skipped (--no-s3)")
    if scored:
        print("\n  NOTE: these scores are in the file above only. gtj.trust_scores")
        print("  has no tail_number column, so per-tail results are not persisted")
        print("  to the database — that needs a schema decision first.")
    print(f"{'=' * 70}\n")
    return 0


def _append(path: Path, row: Dict[str, Any]) -> None:
    """Append one JSON line, flushed immediately so a crash loses nothing."""
    with path.open("a") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
        handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score every tail in gtj.aircraft, pausing between each.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--delay", type=float, default=30.0,
                        help="seconds to wait between tails (default: 30)")
    parser.add_argument("--limit", type=int, default=None,
                        help="score at most N tails")
    parser.add_argument("--operator", default=None,
                        help="only tails whose operator name matches (ILIKE)")
    parser.add_argument("--narrative", action="store_true",
                        help="also generate the §9 LLM audit per tail (slower, costs tokens)")
    parser.add_argument("--resume", default=None,
                        help="existing .jsonl to append to, skipping tails already in it")
    parser.add_argument("--dry-run", action="store_true",
                        help="list the tails that would be scored, then stop")
    parser.add_argument("--no-s3", dest="s3", action="store_false", default=True,
                        help="keep results local; skip the S3 upload")
    parser.add_argument("--checkpoint-every", type=int, default=50,
                        help="upload to S3 every N tails during the run (0 disables)")
    args = parser.parse_args()

    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
