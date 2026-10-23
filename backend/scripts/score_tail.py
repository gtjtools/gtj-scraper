#!/usr/bin/env python3
"""
Score a single tail number from the terminal — no API, no auth, no Hatchet.

TrustScore v5.0 §2 weights tail health at 0.65 against the certificate's 0.35,
and calls the tail-specific score "the primary client-facing deliverable".
Neither deployed endpoint supports it: both `full-scoring-flow` and the batch
workflow pass `build_tail_data(tail_number="")`, which yields a neutral tail
(Hts = 1.0) and collapses TrustScore into FleetScore.

This script fills that gap until a proper endpoint exists.

USAGE
-----
    python scripts/score_tail.py N717XJ
    python scripts/score_tail.py N717XJ --json
    python scripts/score_tail.py N717XJ --narrative     # adds the §9 LLM audit

WHAT IT MEASURES, AND WHAT IT CANNOT
------------------------------------
Derived from data already in the database:

    Mht          airframe age        gtj.aircraft.year
    Rtype        sister-ship depth   count of same make_model on the operator
    Ost          ownership           operator-owned unless stated otherwise
    Iht          tail accidents      NTSB events matched to this N-number
    Sdrpenalty   tail SDRs           SDRS filtered to this N-number

Left NEUTRAL because no pipeline exists (§7 Pipelines 2 and 3):

    Ttenure      months on OpSpecs D085
    Lientail     FAA DOCINDEX mechanic's/tax liens

A neutral input is NO PENALTY, so a high tail score here means "no evidence
found", not "verified clean". The gaps are printed alongside the score so the
two are never confused.

Operator-level inputs (Hsafety, Hconduct, Cs) are fetched the same way the
scoring flow does, so the composite is directly comparable to a full run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.common.config import SessionLocal  # noqa: E402
from src.trustscore import adapter_v5  # noqa: E402
from src.trustscore.calculator_v5 import calculate_trust_score  # noqa: E402


def _normalize_tail(raw: str) -> str:
    """Uppercase and ensure the leading N, matching sdrs_service's convention."""
    value = (raw or "").strip().upper()
    if not value:
        return ""
    return value if value.startswith("N") else f"N{value}"


def lookup_tail(tail: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a tail number to its aircraft row, operator, and sister-ship depth.

    Returns None when the tail is not in gtj.aircraft — scoring an unknown
    airframe would silently produce a neutral tail and a misleadingly high
    score, so the caller must handle the miss explicitly.
    """
    session = SessionLocal()
    try:
        row = session.execute(
            text("""
                SELECT a.tail_number, a.make_model, a.year, a.current_status,
                       o.operator_id, o.name AS operator_name,
                       o.faa_dsgn_code, o.business_started_date
                FROM gtj.aircraft a
                JOIN gtj.operators o ON o.operator_id = a.operator_id
                WHERE UPPER(a.tail_number) = :tail
            """),
            {"tail": tail},
        ).mappings().first()
        if not row:
            return None

        record = dict(row)

        # Vtype — same make/model on the same certificate (§5.2).
        record["same_type_fleet_count"] = session.execute(
            text("""
                SELECT COUNT(*) FROM gtj.aircraft
                WHERE operator_id = :op AND make_model = :mm
            """),
            {"op": record["operator_id"], "mm": record["make_model"]},
        ).scalar() or 1

        record["fleet_size"] = session.execute(
            text("SELECT COUNT(*) FROM gtj.aircraft WHERE operator_id = :op"),
            {"op": record["operator_id"]},
        ).scalar() or 0

        return record
    finally:
        session.close()


async def collect_events(operator_name: str, tail: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Gather fleet-wide and tail-specific events from the live sources.

    Each source is wrapped: a scraper being down must degrade the evidence, not
    abort the score. Failures are reported rather than hidden.
    """
    fleet: List[Dict[str, Any]] = []
    tail_events: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}

    # NTSB — fleet-wide, then filtered to this tail for Iht.
    try:
        from src.scoring.service import NTSBService
        raw = await NTSBService.query_ntsb_incidents(operator_name)
        incidents = NTSBService.parse_ntsb_response(raw)
        fleet = [i.dict() for i in incidents]
        tail_events = [
            e for e in fleet
            if _normalize_tail(str(e.get("tail_number") or e.get("registration") or "")) == tail
        ]
    except Exception as exc:
        errors["ntsb"] = str(exc)

    # FAA AGC enforcement — certificate-level only.
    try:
        from src.scoring.faa_enforcement_service import FAAEnforcementService
        fleet += FAAEnforcementService.query_actions_as_fleet_events(operator_name) or []
    except Exception as exc:
        errors["faa_enforcement"] = str(exc)

    # SDRS — already supports per-tail filtering.
    try:
        from src.scoring.sdrs_service import SDRSService
        fleet += await SDRSService.query_as_fleet_events(operator_name) or []
        tail_events += await SDRSService.query_as_fleet_events(
            operator_name, tail_numbers=[tail]
        ) or []
    except Exception as exc:
        errors["sdrs"] = str(exc)

    return {"fleet": fleet, "tail": tail_events, "errors": errors}


def _age_years(year: Optional[int]) -> float:
    if not year:
        return 0.0
    return max(0.0, datetime.now(timezone.utc).year - int(year))


def _certificate_age(started: Optional[datetime]) -> float:
    if not started:
        return 10.0  # same fallback the scoring flow uses
    return round((datetime.now() - started).days / 365.25, 1)


async def score(tail_raw: str, want_narrative: bool):
    tail = _normalize_tail(tail_raw)
    record = lookup_tail(tail)
    if record is None:
        print(f"\n  Tail {tail} not found in gtj.aircraft.\n")
        print("  Scoring an unknown airframe would produce a neutral tail and a")
        print("  misleadingly high score, so this stops here.\n")
        return None

    print(f"\n{'=' * 70}")
    print(f"  TAIL SCORE — {tail}")
    print(f"  operator    : {record['operator_name']}")
    print(f"  certificate : {record['faa_dsgn_code'] or '(unresolved)'}")
    print(f"  aircraft    : {record['make_model']} ({record['year'] or 'year unknown'})")
    print(f"  fleet       : {record['fleet_size']} tails, "
          f"{record['same_type_fleet_count']} of this type")
    print(f"{'=' * 70}\n")

    print("  gathering events…")
    events = await collect_events(record["operator_name"], tail)
    for source, message in events["errors"].items():
        print(f"    ⚠ {source}: {message[:70]}")
    print(f"    fleet events: {len(events['fleet'])}   tail events: {len(events['tail'])}")

    operator = adapter_v5.build_operator_data(
        operator_name=record["operator_name"],
        certificate_designator=record["faa_dsgn_code"],
        certificate_age_years=_certificate_age(record["business_started_date"]),
        fleet_size=record["fleet_size"],
        fleet_events=events["fleet"],
    )
    tail_data = adapter_v5.build_tail_data(
        tail_number=tail,
        aircraft_age_years=_age_years(record["year"]),
        same_type_fleet_count=record["same_type_fleet_count"],
        tail_events=events["tail"],
        # Ttenure and Lientail stay at their neutral defaults — no pipeline.
    )

    result = calculate_trust_score(operator, tail_data)
    gaps = adapter_v5.missing_inputs(operator, tail_data)

    if want_narrative:
        try:
            from src.trustscore import narrative_v5
            from src.trustscore.llm_client import LLMClient, LLMProvider
            narrative = await narrative_v5.generate_narrative(
                operator, tail_data, result,
                llm_client=LLMClient(provider=LLMProvider.OPENROUTER),
                missing_inputs=gaps,
            )
            if narrative:
                result["risk_audit"] = {
                    "narrative": narrative["narrative"],
                    "flags": narrative["flags"],
                }
        except Exception as exc:
            print(f"    ⚠ narrative skipped: {exc}")

    return result, gaps, record


def render(result: Dict[str, Any], gaps: List[str]) -> None:
    c = result["components"]
    print(f"\n{'=' * 70}")
    print(f"  TrustScore : {result['trust_score']}  ({result['tier']})")
    print(f"  FleetScore : {result['fleet_score']}  ({result['fleet_tier']})")
    print(f"{'=' * 70}\n")

    print("  TAIL HEALTH (Hts weighted 0.65)")
    for label, key in [("Mht  airframe age", "mht"), ("Ost  ownership", "ost"),
                       ("Rtype sister ships", "rtype"), ("Ttenure onboarding", "ttenure"),
                       ("Htailhistory", "h_tail_history")]:
        print(f"    {label:<22} {c[key]:.4f}")
    print(f"    {'= Hts':<22} {c['h_ts']:.4f}\n")

    print("  TAIL RISK")
    for label, key in [("Iht  accidents x5", "iht"), ("Sdrpenalty", "sdr_penalty"),
                       ("Lientail", "lien_tail")]:
        print(f"    {label:<22} {c[key]:.2f}")

    print("\n  CERTIFICATE")
    for label, key in [("Hsafety", "h_safety"), ("Hconduct", "h_conduct"), ("Cs", "cs")]:
        print(f"    {label:<22} {c[key]:.4f}")

    if gaps:
        print(f"\n  UNEVIDENCED INPUTS ({len(gaps)}) — neutral means NO PENALTY,")
        print("  so a high score here is 'nothing found', not 'verified clean':")
        for gap in gaps:
            print(f"    - {gap}")

    if result.get("risk_audit"):
        print(f"\n{'=' * 70}\n  RISK AUDIT\n{'=' * 70}")
        print(result["risk_audit"]["narrative"])
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one tail number from the terminal.")
    parser.add_argument("tail_number", help="e.g. N717XJ")
    parser.add_argument("--json", action="store_true", help="emit raw JSON instead of a table")
    parser.add_argument("--narrative", action="store_true", help="also generate the §9 LLM audit")
    args = parser.parse_args()

    try:
        outcome = asyncio.run(score(args.tail_number, args.narrative))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130

    if outcome is None:
        return 1

    result, gaps, _record = outcome
    if args.json:
        print(json.dumps({**result, "unevidenced_inputs": gaps}, indent=2, default=str))
    else:
        render(result, gaps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
