#!/usr/bin/env python3
"""
Re-score every operator under TrustScore v5.0, with retries and resume.

Bypasses the Hatchet batch workflow deliberately. That task carries a 2-hour
`execution_timeout`, and a full pass is roughly 77 hours of work — so a single
dispatch scores ~48 operators and is then killed, silently, with no way to
resume. This drives `POST /scoring/full-scoring-flow` one operator at a time
instead, which has no timeout and can be stopped and restarted freely.

Nothing existing is modified: this only calls an endpoint that already exists.

FAILURE HANDLING
----------------
An operator that errors is pushed to a retry queue rather than abandoned. The
queue is drained after the main pass, up to --max-attempts times per operator,
with a growing backoff. Most failures here are transient — a Browserbase
session that will not start, an FAA timeout, a dropped connection — and succeed
on a second attempt minutes later. Whatever still fails is written to the
progress file with its error so it can be chased individually.

Progress is flushed to disk after every operator, so a kill -9 loses at most
one operator's work and `--resume` picks up from there.

USAGE
-----
    python scripts/rescore_all_operators.py --dry-run         # list, score nothing
    python scripts/rescore_all_operators.py --limit 5         # try a few first
    python scripts/rescore_all_operators.py --state TX        # one state
    python scripts/rescore_all_operators.py                   # everything

    python scripts/rescore_all_operators.py --resume ~/rescore_progress.jsonl

RUN IT DETACHED — a full pass takes days:

    tmux new -s rescore
    venv/bin/python3 scripts/rescore_all_operators.py 2>&1 | tee ~/rescore.log
    # Ctrl-B then D to detach; `tmux attach -t rescore` to return

    # or
    nohup venv/bin/python3 scripts/rescore_all_operators.py > ~/rescore.log 2>&1 &

BEFORE RUNNING
--------------
This overwrites `trust_score` and `rating_tiers` for every operator. Take a
backup first:

    python scripts/backup_trustscore_tables.py backup --label pre-v5-full-rescore
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402

API_BASE = "http://localhost:8000"
ENDPOINT = "/scoring/full-scoring-flow"

#: Generous: one operator runs NTSB (plus PDF download and LLM analysis), UCC
#: across three states via Browserbase, FAA, SDRS and the narrative. Observed
#: around 150s; this allows for a slow Browserbase session without giving up on
#: work that is still progressing.
_REQUEST_TIMEOUT = 900.0

#: Fallback when an operator has no faa_state. The parameter only selects which
#: UCC registries are searched, and UCC does not feed v5.0 scoring at all, so a
#: wrong guess costs nothing but a few seconds.
_DEFAULT_STATE = "TX"

DEFAULT_PROGRESS = Path.home() / "rescore_progress.jsonl"

_stop_requested = False


def _handle_sigint(_signum, _frame) -> None:
    """Finish the operator in flight, then stop — rather than losing its work."""
    global _stop_requested
    if _stop_requested:
        print("\n  Second interrupt — exiting now.")
        sys.exit(130)
    _stop_requested = True
    print("\n  Interrupt received. Finishing the current operator, then stopping.")
    print("  Press Ctrl-C again to abort immediately.")


def fetch_operators(state: Optional[str], limit: Optional[int]) -> List[Dict[str, Any]]:
    """
    Operators to score, in a stable order so --resume walks the same sequence.

    Ordered by name rather than by id: a human reading the log can tell roughly
    how far through the alphabet a multi-day run has reached.
    """
    clauses, params = [], {}
    if state:
        clauses.append("faa_state = :state")
        params["state"] = state.upper()

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT operator_id, name, faa_state, faa_dsgn_code, trust_score
        FROM gtj.operators
        {where}
        ORDER BY name
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    session = SessionLocal()
    try:
        return [dict(r) for r in session.execute(text(sql), params).mappings()]
    finally:
        session.close()


def load_completed(path: Optional[Path]) -> Set[str]:
    """
    Operator names already scored successfully in a previous run.

    Only successes are skipped. A row recorded as failed is retried, which is
    what makes --resume useful after a run that ended with errors.
    """
    if not path or not path.exists():
        return set()
    done: Set[str] = set()
    with path.open() as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # truncated final line from a killed run
            if row.get("ok") and row.get("operator_name"):
                done.add(row["operator_name"])
    return done


def score_operator(client: httpx.Client, operator: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score one operator. Returns a result row; never raises.

    A failure here must not end the pass — the caller queues it for retry.
    """
    name = operator["name"]
    state = (operator.get("faa_state") or _DEFAULT_STATE).strip() or _DEFAULT_STATE
    url = f"{API_BASE}{ENDPOINT}?operator_name={quote(name)}&faa_state={quote(state)}"

    started = time.time()
    try:
        response = client.post(url)
        elapsed = time.time() - started

        if response.status_code != 200:
            return {
                "ok": False,
                "operator_name": name,
                "error": f"HTTP {response.status_code}: {response.text[:150]}",
                "elapsed_s": round(elapsed, 1),
            }

        body = response.json()
        trust = body.get("trust_score") or {}
        return {
            "ok": True,
            "operator_name": name,
            "certificate_designator": trust.get("certificate_designator"),
            "trust_score": trust.get("trust_score"),
            "tier": trust.get("tier"),
            "fleet_score": trust.get("fleet_score"),
            "flags": (trust.get("risk_audit") or {}).get("flags"),
            "saved": body.get("saved_to_supabase"),
            "elapsed_s": round(elapsed, 1),
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "operator_name": name,
            "error": f"{type(exc).__name__}: {str(exc)[:150]}",
            "elapsed_s": round(time.time() - started, 1),
        }


def _append(path: Path, row: Dict[str, Any]) -> None:
    """Append one JSON line and flush, so a crash loses at most one operator."""
    with path.open("a") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
        handle.flush()


def run(args: argparse.Namespace) -> int:
    operators = fetch_operators(args.state, args.limit)
    if not operators:
        print("\n  No operators matched.\n")
        return 1

    progress_path = Path(args.resume) if args.resume else DEFAULT_PROGRESS
    completed = load_completed(progress_path if args.resume else None)
    pending = [o for o in operators if o["name"] not in completed]

    eta_hours = len(pending) * (150 + args.delay) / 3600

    print(f"\n{'=' * 72}")
    print("  FULL OPERATOR RESCORE — TrustScore v5.0")
    print(f"  matched      : {len(operators):,}")
    if completed:
        print(f"  already done : {len(completed):,} (skipped via --resume)")
    print(f"  to score     : {len(pending):,}")
    print(f"  delay        : {args.delay}s between operators")
    print(f"  max attempts : {args.max_attempts} per operator")
    print(f"  rough ETA    : {eta_hours:.1f} hours ({eta_hours / 24:.1f} days)")
    print(f"  progress     : {progress_path}")
    print(f"{'=' * 72}\n")

    if args.dry_run:
        for o in pending[:30]:
            print(f"  {o['faa_dsgn_code'] or '----':<6} {o['faa_state'] or '--':<3} "
                  f"{o['name'][:46]:<48} current={o['trust_score']}")
        if len(pending) > 30:
            print(f"  … and {len(pending) - 30:,} more")
        print("\n  Dry run — nothing scored.\n")
        return 0

    # Confirm before overwriting every score, unless explicitly waived.
    if not args.yes and len(pending) > 50:
        print(f"  This overwrites trust_score and rating_tiers for {len(pending):,} operators.")
        print(f"  Take a backup first if you have not:")
        print(f"    python scripts/backup_trustscore_tables.py backup --label pre-v5-full-rescore\n")
        if input("  Type 'yes' to continue: ").strip().lower() != "yes":
            print("\n  Aborted.\n")
            return 1
        print()

    signal.signal(signal.SIGINT, _handle_sigint)

    # Operators that errored, with their attempt count. Drained after the main
    # pass — retrying immediately would usually hit the same transient fault.
    retry_queue: List[Dict[str, Any]] = []
    scored = failed = 0
    started = datetime.now(timezone.utc)

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:

        def attempt(operator: Dict[str, Any], label: str) -> bool:
            nonlocal scored, failed
            result = score_operator(client, operator)
            result["attempt"] = operator.get("_attempts", 0) + 1
            _append(progress_path, result)

            if result["ok"]:
                scored += 1
                flags = result.get("flags") or {}
                reds = sum(1 for v in flags.values() if v == "RED")
                greys = sum(1 for v in flags.values() if v == "GREY")
                print(f"{label}  {result['trust_score']} ({result['tier']})"
                      f"  {reds}R/{greys}G  {result['elapsed_s']}s")
                return True

            failed += 1
            print(f"{label}  FAILED: {result['error'][:70]}")
            return False

        # ── main pass ────────────────────────────────────────────────────────
        for index, operator in enumerate(pending, start=1):
            if _stop_requested:
                print("\n  Stopping as requested.")
                break

            label = f"  [{index}/{len(pending)}] {operator['name'][:36]:<38}"
            if not attempt(operator, label):
                operator["_attempts"] = 1
                retry_queue.append(operator)

            if index < len(pending) and not _stop_requested and args.delay:
                time.sleep(args.delay)

        # ── retry pass ───────────────────────────────────────────────────────
        # Most failures are transient (Browserbase session refused, FAA
        # timeout). Retrying after the main pass gives them minutes to clear
        # rather than seconds.
        round_number = 1
        while retry_queue and not _stop_requested and round_number < args.max_attempts:
            round_number += 1
            backoff = args.delay * round_number
            print(f"\n{'─' * 72}")
            print(f"  RETRY ROUND {round_number}: {len(retry_queue)} operator(s), "
                  f"{backoff}s apart")
            print(f"{'─' * 72}\n")

            still_failing: List[Dict[str, Any]] = []
            for index, operator in enumerate(retry_queue, start=1):
                if _stop_requested:
                    still_failing.extend(retry_queue[index - 1:])
                    break

                label = f"  [r{round_number} {index}/{len(retry_queue)}] " \
                        f"{operator['name'][:30]:<32}"
                operator["_attempts"] = operator.get("_attempts", 1)
                if attempt(operator, label):
                    failed -= 1  # it had been counted on the failing attempt
                else:
                    operator["_attempts"] += 1
                    still_failing.append(operator)

                if index < len(retry_queue) and not _stop_requested:
                    time.sleep(backoff)

            retry_queue = still_failing

    elapsed_h = (datetime.now(timezone.utc) - started).total_seconds() / 3600
    print(f"\n{'=' * 72}")
    print(f"  scored        : {scored:,}")
    print(f"  still failing : {len(retry_queue):,}")
    print(f"  elapsed       : {elapsed_h:.1f} hours")
    print(f"  progress file : {progress_path}")

    if retry_queue:
        print(f"\n  Exhausted {args.max_attempts} attempts on:")
        for operator in retry_queue[:20]:
            print(f"    {operator['name']}")
        if len(retry_queue) > 20:
            print(f"    … and {len(retry_queue) - 20} more")
        print(f"\n  Re-run with --resume {progress_path} to try them again;")
        print("  successful operators are skipped.")
    print(f"{'=' * 72}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-score every operator under TrustScore v5.0.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--delay", type=float, default=5.0,
                        help="seconds between operators (default: 5)")
    parser.add_argument("--limit", type=int, default=None, help="score at most N")
    parser.add_argument("--state", default=None, help="only this faa_state, e.g. TX")
    parser.add_argument("--max-attempts", type=int, default=3,
                        help="attempts per operator before giving up (default: 3)")
    parser.add_argument("--resume", default=None,
                        help="progress .jsonl to append to, skipping successes")
    parser.add_argument("--dry-run", action="store_true", help="list, score nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the overwrite confirmation")
    parser.add_argument("--api", default=API_BASE,
                        help=f"API base URL (default: {API_BASE})")
    args = parser.parse_args()

    # Rebound so score_operator picks it up; declared before any use in this
    # function, which Python requires.
    globals()["API_BASE"] = args.api

    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
