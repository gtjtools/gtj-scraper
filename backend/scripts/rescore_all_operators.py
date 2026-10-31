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

Two kinds of failure are treated differently:

  * A *degraded* result — HTTP 200, so a score exists, but a source named in
    --retry-on-source-error failed. Retried, because a missing NTSB record is
    indistinguishable from a clean safety history. After --accept-after
    attempts (default 5) the score is accepted as-is and the missing sources
    are recorded on the progress row as `accepted_degraded` /
    `degraded_sources`, so a four-day run is never held up by one dead
    endpoint. Grep those rows later to re-score once the source recovers.

  * A *hard* failure — no score at all (HTTP 500, timeout, connection
    refused). Never accepted, because there is nothing to accept. These remain
    in the failing list for --resume.

UCC is excluded from retries by default: California is permanently blocked by
Incapsula, and UCC does not feed v5.0 scoring. Its failure is still recorded.

Progress is flushed to disk after every operator, so a kill -9 loses at most
one operator's work and `--resume` picks up from there.

USAGE
-----
    python scripts/rescore_all_operators.py --dry-run         # list, score nothing
    python scripts/rescore_all_operators.py --limit 5         # try a few first
    python scripts/rescore_all_operators.py --state TX        # one state
    python scripts/rescore_all_operators.py                   # everything

    python scripts/rescore_all_operators.py --resume ~/rescore_progress.jsonl

PACING
------
30s between operators by default. Each operator already spends ~150s mostly on
network calls, so the pause adds about 16% to a run already measured in days —
cheap insurance against a rate-limit block from NTSB, FAA SDRS or FAA AGC
partway through, which would cost far more to recover from. Matches the pacing
used by scripts/score_all_tails.py against the same endpoints.

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

#: Sources whose failure is worth another attempt, because it is usually
#: transient — an FAA timeout, a dropped connection, a Browserbase session that
#: would not start.
#:
#: `ucc` is deliberately absent. California sits behind Incapsula and fails on
#: every run, by design rather than by accident; including it would retry all
#: 1,839 operators three times for a result that cannot change, turning a
#: 92-hour pass into roughly 276 hours of guaranteed-futile work. UCC also
#: feeds nothing in v5.0 — liens are specified to come from DOCINDEX — so its
#: failure costs no score accuracy at all.
_DEFAULT_RETRY_SOURCES = ("ntsb", "trust_score")

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

        # The endpoint isolates each source, so a scrape that failed still
        # yields HTTP 200 with the failure named here. Carried through so the
        # caller can decide whether a partial result is worth retrying.
        source_errors = {
            source: message
            for source, message in (body.get("errors") or {}).items()
            if message
        }

        return {
            "ok": True,
            "operator_name": name,
            "source_errors": source_errors or None,
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

    # Sources whose failure demotes an HTTP 200 to a retry. Normalised here so
    # "--retry-on-source-error ''" cleanly means "accept any 200".
    retry_sources = {
        part.strip().lower()
        for part in args.retry_on_source_error.split(",")
        if part.strip()
    }

    # Not an error -- the operator may know something we don't -- but loud,
    # because it multiplies runtime by --max-attempts for no gain.
    if "ucc" in retry_sources:
        print("  ⚠️  'ucc' is in --retry-on-source-error. California is permanently")
        print("      blocked, so nearly every operator will exhaust its retries and")
        print("      still fail. Runtime grows ~{}x. Remove it unless deliberate.\n"
              .format(args.max_attempts))

    eta_hours = len(pending) * (150 + args.delay) / 3600

    print(f"\n{'=' * 72}")
    print("  FULL OPERATOR RESCORE — TrustScore v5.0")
    print(f"  matched      : {len(operators):,}")
    if completed:
        print(f"  already done : {len(completed):,} (skipped via --resume)")
    print(f"  to score     : {len(pending):,}")
    print(f"  delay        : {args.delay}s between operators")
    print(f"  max attempts : {args.max_attempts} per operator")
    print(f"  accept after : {args.accept_after} attempts (degraded score kept, "
          f"missing sources recorded)")
    print(f"  retry on     : {', '.join(sorted(retry_sources)) or 'request failure only'}")
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

    # Scored, but on incomplete evidence after exhausting --accept-after
    # attempts. Reported at the end so these are not silently equivalent to
    # clean scores.
    accepted_degraded: List[Dict[str, Any]] = []
    scored = failed = 0
    started = datetime.now(timezone.utc)

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:

        def attempt(operator: Dict[str, Any], label: str) -> bool:
            nonlocal scored, failed
            result = score_operator(client, operator)
            result["attempt"] = operator.get("_attempts", 0) + 1

            # A partial result — HTTP 200, but a source we care about errored —
            # is treated as a failure so it goes to the retry queue. Without
            # this, an operator scored while NTSB was timing out is
            # indistinguishable from one that genuinely has no accidents.
            #
            # Demoted before _append so the persisted row carries ok=false;
            # logging the pre-demotion result would make --resume skip it.
            degraded = sorted(
                set(result.get("source_errors") or {}) & set(retry_sources)
            )
            if result["ok"] and degraded:
                detail = "; ".join(
                    f"{d}: {result['source_errors'][d][:60]}" for d in degraded
                )

                # Past --accept-after attempts, stop fighting it. The score on
                # the server is real — the request returned 200 — it is just
                # based on thinner evidence. Keep ok=true so --resume does not
                # retry it forever, but record what was missing so the score can
                # be audited or re-run later.
                if result["attempt"] >= args.accept_after:
                    result["accepted_degraded"] = True
                    result["degraded_sources"] = degraded
                    result["error"] = (
                        f"accepted after {result['attempt']} attempts without "
                        f"{', '.join(degraded)} — {detail}"
                    )
                else:
                    result["ok"] = False
                    result["degraded_sources"] = degraded
                    result["error"] = f"scored, but {detail}"

            _append(progress_path, result)

            if result["ok"]:
                scored += 1
                flags = result.get("flags") or {}
                reds = sum(1 for v in flags.values() if v == "RED")
                greys = sum(1 for v in flags.values() if v == "GREY")
                suffix = ""
                if result.get("accepted_degraded"):
                    accepted_degraded.append(result)
                    suffix = f"  ⚠️  no {','.join(result['degraded_sources'])}"
                print(f"{label}  {result['trust_score']} ({result['tier']})"
                      f"  {reds}R/{greys}G  {result['elapsed_s']}s{suffix}")
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
        # Enough rounds to let a degraded operator reach --accept-after, since
        # acceptance only happens on an attempt that actually runs.
        max_rounds = max(args.max_attempts, args.accept_after)

        round_number = 1
        while retry_queue and not _stop_requested and round_number < max_rounds:
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
    if accepted_degraded:
        print(f"    of which    : {len(accepted_degraded):,} on incomplete evidence")
    print(f"  still failing : {len(retry_queue):,}")
    print(f"  elapsed       : {elapsed_h:.1f} hours")
    print(f"  progress file : {progress_path}")

    if accepted_degraded:
        # These carry a real score but thinner evidence. Surfaced explicitly so
        # they can be re-run once the failing source recovers.
        by_source: Dict[str, int] = {}
        for row in accepted_degraded:
            for source in row.get("degraded_sources") or []:
                by_source[source] = by_source.get(source, 0) + 1

        print(f"\n  Accepted after {args.accept_after} attempts, missing data:")
        for source, count in sorted(by_source.items(), key=lambda kv: -kv[1]):
            print(f"    {source:<14} {count:,} operator(s)")
        for row in accepted_degraded[:10]:
            print(f"    {row['operator_name'][:44]:<46} "
                  f"no {','.join(row['degraded_sources'])}")
        if len(accepted_degraded) > 10:
            print(f"    … and {len(accepted_degraded) - 10:,} more "
                  f"(grep '\"accepted_degraded\": true' {progress_path})")

    if retry_queue:
        print(f"\n  No score at all after {max(args.max_attempts, args.accept_after)} "
              f"attempts:")
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
    parser.add_argument("--delay", type=float, default=30.0,
                        help="seconds between operators (default: 30)")
    parser.add_argument("--limit", type=int, default=None, help="score at most N")
    parser.add_argument("--state", default=None, help="only this faa_state, e.g. TX")
    parser.add_argument("--retry-on-source-error", default=",".join(_DEFAULT_RETRY_SOURCES),
                        metavar="ntsb,trust_score",
                        help="sources whose failure forces a retry even on HTTP 200 "
                             "(default: %(default)s; empty string disables; avoid 'ucc', "
                             "permanently blocked so retries cannot help)")
    parser.add_argument("--max-attempts", type=int, default=3,
                        help="attempts per operator before giving up (default: 3)")
    parser.add_argument("--accept-after", type=int, default=5,
                        help="after N attempts, accept a degraded score (one that "
                             "returned 200 but lost a source in --retry-on-source-error) "
                             "and record the missing sources (default: 5). Does not "
                             "apply to hard failures, which have no score to accept")
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
