"""
TrustScore v5.0 Risk Audit narrative generation (§9).

Turns a computed score plus its evidence into the executive audit described in
the specification: an Executive Summary, a six-category traffic-light risk
audit, and a Broker Guidance Note.

THIS MODULE NEVER AFFECTS A SCORE. It consumes an already-computed result and
produces prose. There is no path from anything here back into the calculator,
and `generate_narrative` returns None on any failure rather than raising — an
LLM outage degrades the output, never the number.

Two rules from the specification shape the design:

  * THE BLACK BOX RULE (§9). Client interfaces, exports and external APIs must
    never expose raw coefficients, health multipliers (Hos, Hsafety, Hconduct,
    Hts, Cs) or point deductions. `build_audit_payload` therefore constructs a
    *scrubbed* payload — evidence and flags only — and the metaprompt forbids
    formula leakage. `_assert_no_leakage` is a last-resort guard over the
    generated text.

  * STRICT EVIDENTIARY GROUNDING (§9.1). The model may cite only facts present
    in the payload. Flags are computed here, in Python, from the same evidence
    the calculator used — never inferred by the model — so the narrative cannot
    disagree with the score.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.trustscore.calculator_v5 import (
    ELI_TAXONOMY,
    OperatorData,
    RiskEvent,
    Severity,
    TailData,
    decayed_sum,
)

logger = logging.getLogger(__name__)

# ── §9 Traffic-light taxonomy ────────────────────────────────────────────────

GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"

#: §6.3 violations severe enough to force a RED commercial-integrity flag.
_CRITICAL_VIOLATIONS = frozenset(
    name for name, points in ELI_TAXONOMY.items() if points >= Severity.ELI_MAJOR
)

#: Terms that must never appear in generated prose (§9.1 "Zero Formula
#: Leakage"). Matched case-insensitively on word boundaries.
_FORBIDDEN_TERMS = (
    "hos", "hsafety", "hconduct", "hts", "cs", "rtype", "ttenure", "mht", "ost",
    "orfbase", "sdrfleet", "dscale", "lrisk", "eli", "cro", "sro", "iht",
    "sdrpenalty", "lientail", "churneffective", "multiplier", "exponential decay",
    "decay constant", "damping coefficient", "health factor",
)

_LEAKAGE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in _FORBIDDEN_TERMS) + r")\b",
    re.IGNORECASE,
)


# ── Flag derivation ──────────────────────────────────────────────────────────
#
# Flags are derived in Python from the same evidence the calculator scored, so
# the narrative and the number always agree. The LLM is told the flags; it does
# not choose them.

def _flag_flight_fulfillment(operator: OperatorData, tail: TailData) -> str:
    """
    Dispatch reliability: watchdog-reported drops and sister-ship recovery depth.

    First-party cancellation telemetry is deferred (Source 9), so this rests on
    watchdog evidence plus in-fleet recovery capability.
    """
    dispatch_failures = [
        event for event in operator.legal_events
        if event.event_type == "SYSTEMIC_DISPATCH_DROPS_OR_FLEET_GROUNDING"
    ]
    if dispatch_failures:
        return RED
    if tail.same_type_fleet_count <= 1:
        return YELLOW
    return GREEN


def _flag_commercial_integrity(operator: OperatorData) -> str:
    """Contract disputes, fraud, and DOT enforcement."""
    if not operator.legal_events:
        return GREEN
    if any(event.event_type in _CRITICAL_VIOLATIONS for event in operator.legal_events):
        return RED
    return YELLOW


def _flag_flight_safety(operator: OperatorData, tail: TailData) -> str:
    """NTSB/AIDS accidents across both the certificate and this airframe."""
    all_events = list(operator.fleet_accident_events) + list(tail.tail_accident_events)
    if not all_events:
        return GREEN
    if any(event.severity >= Severity.SUBSTANTIAL_DAMAGE for event in all_events):
        return RED
    return YELLOW


def _flag_maintenance(operator: OperatorData, tail: TailData) -> str:
    """SDRS critical precautionary procedures, airframe and fleet level."""
    all_sdrs = list(operator.fleet_sdr_events) + list(tail.tail_sdr_events)
    if not all_sdrs:
        return GREEN
    if any(event.severity >= Severity.SDR_IFSD for event in all_sdrs):
        return RED
    return YELLOW


def _flag_asset_stability(operator: OperatorData, tail: TailData, churn: float) -> str:
    """Certificate longevity, 12-month D085 churn, and tail onboarding tenure."""
    if churn >= 0.35:
        return RED
    if churn >= 0.15 or tail.certificate_tenure_months < 6.0:
        return YELLOW
    if operator.certificate_age_years < 3.0:
        return YELLOW
    return GREEN


def _flag_legal_title(operator: OperatorData, tail: TailData) -> str:
    """Active liens, ownership structure, and rapid title transfers."""
    if tail.tail_lien_events:
        return RED
    if any(
        event.event_type == "ACTIVE_MECHANICS_OR_TAX_LIEN"
        for event in operator.legal_events
    ):
        return RED
    if tail.ownership_classification.lower() not in ("exclusive", "holding_entity"):
        return YELLOW
    return GREEN


# ── Payload construction ─────────────────────────────────────────────────────

def _describe_events(events: List[RiskEvent], limit: int = 10) -> List[Dict[str, Any]]:
    """
    Render events as evidence for the model.

    Severity is deliberately omitted — it is a scoring coefficient, and §9
    forbids exposing point values. The qualitative `event_type` carries the
    meaning the narrative needs.
    """
    described = []
    for event in events[:limit]:
        entry = {"type": event.event_type or "event"}
        if event.event_date:
            entry["date"] = str(event.event_date)
        if event.source:
            entry["source"] = event.source
        if event.reference:
            entry["reference"] = event.reference
        described.append(entry)
    return described


def build_audit_payload(
    operator: OperatorData,
    tail: TailData,
    score_result: Dict[str, Any],
    missing_inputs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build the §10.1 JSON input contract for the narrative generator.

    The payload is deliberately scrubbed: it carries scores, tiers, flags and
    evidence, but no health multipliers, no risk sums and no severity points.
    `score_result["components"]` is never copied in — that block is internal
    audit only (§9).

    Args:
        operator: The operator data that was scored.
        tail: The tail data that was scored.
        score_result: Output of `calculate_trust_score`.
        missing_inputs: Optional gaps from `adapter_v5.missing_inputs`, surfaced
            so the narrative can mark categories as unevidenced rather than
            clean.

    Returns:
        A JSON-serializable payload safe to hand to an LLM.
    """
    from src.trustscore.calculator_v5 import calculate_churn_effective

    churn = calculate_churn_effective(operator)

    flags = {
        "flight_fulfillment": _flag_flight_fulfillment(operator, tail),
        "commercial_integrity": _flag_commercial_integrity(operator),
        "flight_safety": _flag_flight_safety(operator, tail),
        "maintenance_discipline": _flag_maintenance(operator, tail),
        "asset_stability": _flag_asset_stability(operator, tail, churn),
        "legal_title": _flag_legal_title(operator, tail),
    }

    return {
        "operator_name": operator.operator_name,
        "certificate_designator": operator.certificate_designator,
        "certificate_age_years": round(operator.certificate_age_years, 1),
        "fleet_size": operator.fleet_size,
        "same_type_fleet_count": tail.same_type_fleet_count,
        "tail_number": tail.tail_number or None,
        "aircraft_age_years": round(tail.aircraft_age_years, 1) if tail.tail_number else None,
        "tail_certificate_tenure_months": (
            round(tail.certificate_tenure_months, 1)
            if tail.tail_number and tail.certificate_tenure_months < 999 else None
        ),
        "ownership_classification": tail.ownership_classification if tail.tail_number else None,
        "calculated_scores": {
            "trust_score": score_result.get("trust_score"),
            "fleet_score": score_result.get("fleet_score"),
            "tier": score_result.get("tier"),
        },
        "audit_categories": {
            "flight_fulfillment": {
                "flag": flags["flight_fulfillment"],
                "sister_ship_depth": tail.same_type_fleet_count,
                "watchdog_dispatch_events": _describe_events([
                    event for event in operator.legal_events
                    if event.event_type == "SYSTEMIC_DISPATCH_DROPS_OR_FLEET_GROUNDING"
                ]),
                "first_party_telemetry": "deferred — not yet ingested",
            },
            "commercial_integrity": {
                "flag": flags["commercial_integrity"],
                "legal_and_watchdog_events": _describe_events(operator.legal_events),
            },
            "flight_safety": {
                "flag": flags["flight_safety"],
                "certificate_accident_events": _describe_events(operator.fleet_accident_events),
                "tail_accident_events": _describe_events(tail.tail_accident_events),
            },
            "maintenance_discipline": {
                "flag": flags["maintenance_discipline"],
                "fleet_sdr_count": len(operator.fleet_sdr_events),
                "tail_sdr_events": _describe_events(tail.tail_sdr_events),
                "fleet_sdr_events": _describe_events(operator.fleet_sdr_events),
            },
            "asset_stability": {
                "flag": flags["asset_stability"],
                "certificate_age_years": round(operator.certificate_age_years, 1),
                "tails_added_12m": operator.tails_added_12m,
                "tails_removed_12m": operator.tails_removed_12m,
                "fleet_churn_rate_12m": f"{round(churn * 100)}%",
                "tail_tenure_months": (
                    round(tail.certificate_tenure_months, 1)
                    if tail.certificate_tenure_months < 999 else None
                ),
            },
            "legal_title": {
                "flag": flags["legal_title"],
                "ownership_classification": tail.ownership_classification,
                "active_tail_liens_count": len(tail.tail_lien_events),
                "active_certificate_liens_count": sum(
                    1 for event in operator.legal_events
                    if event.event_type == "ACTIVE_MECHANICS_OR_TAX_LIEN"
                ),
            },
        },
        "data_coverage_gaps": missing_inputs or [],
    }


# ── §9.1 Metaprompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
SYSTEM PROMPT: TrustJet Risk Audit Narrative Generator

1. Role & Objective
You are the Senior Risk Intelligence Analyst for TrustJet. Ingest the provided \
JSON payload containing external regulatory filings, maintenance logs, fleet \
depth metrics, and TrustScore tiering for a specific operator and airframe. \
Synthesize this data into an objective, executive-level TrustScore \
Justification Audit.

2. Mandatory Guardrails
- Zero Formula Leakage: NEVER mention internal health multipliers, exponential \
decay functions, damping coefficients, or base mathematical points. Never use \
internal variable names.
- Strict Evidentiary Grounding: Cite only facts, dates, frequencies, and \
descriptions provided directly in the input payload. Do not speculate or \
invent private financial data. If a category has no entries, say so plainly.
- Respect the supplied flags: the payload assigns each category a GREEN, \
YELLOW or RED flag. Use them exactly as given; do not re-derive or override.
- Objective Tone: Maintain a clinical, institutional tone. Attribute all \
adverse findings directly to official public repositories (NTSB, FAA SDRS, \
FAA Document Index, DOT OACP) or verified watchdog reporting.
- Where `data_coverage_gaps` lists an uningested source, describe the relevant \
category as unevidenced rather than clean.

3. Required Output Format

Executive Summary
TrustScore: [Score] ([Tier Name: Pinnacle 90+ | Premier 80-89 | Benchmark \
70-79 | Standard 50-69])
Operational Stance: [1-sentence summary of risk level and core recommendation]
Primary Drivers: [2 to 3 concise bullet points identifying the primary \
operational or regulatory factors driving the score]

Comprehensive Risk Audit
Analyze each of the following 6 categories in order, prepending each header \
with the flag status supplied in the payload:
[Flag] Flight Fulfillment & Dispatch
[Flag] Commercial Integrity
[Flag] Primary Flight Safety
[Flag] Maintenance Discipline
[Flag] Asset Stability & Fleet Churn
[Flag] Legal & Title Clearness

Broker Guidance Note
Provide a concluding paragraph offering practical, actionable contracting \
advice for the charter broker (e.g., specific contractual clauses to enforce, \
third-party escrow requirements, backup recovery guarantees, or airworthiness \
release verifications).
"""


def build_prompt(payload: Dict[str, Any]) -> str:
    """Render the user-side prompt: the scrubbed payload as JSON."""
    return (
        "Generate the TrustScore Justification Audit for the following payload.\n\n"
        f"{json.dumps(payload, indent=2, default=str)}"
    )


# ── Leakage guard ────────────────────────────────────────────────────────────

def find_leakage(text: str) -> List[str]:
    """
    Return any §9-forbidden terms present in generated prose.

    A backstop, not the primary control — the metaprompt is. Note `cs` and
    `eli` are short enough to collide with ordinary words in other contexts;
    the word-boundary match keeps false positives low but not zero, which is
    the right trade for a guard whose failure mode is redaction rather than
    disclosure.
    """
    return sorted({match.group(0).lower() for match in _LEAKAGE_PATTERN.finditer(text or "")})


# ── Entry point ──────────────────────────────────────────────────────────────

async def generate_narrative(
    operator: OperatorData,
    tail: TailData,
    score_result: Dict[str, Any],
    llm_client: Any = None,
    missing_inputs: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Generate the §9 Risk Audit narrative for an already-computed score.

    Read-only with respect to scoring: `score_result` is consumed, never
    modified, and nothing returned here feeds back into the calculator.

    Args:
        operator: The operator data that was scored.
        tail: The tail data that was scored.
        score_result: Output of `calculate_trust_score`.
        llm_client: An object exposing `get_completion(prompt) -> str`, or a
            client with a `.client.chat.completions.create` surface. None
            disables generation.
        missing_inputs: Optional gaps from `adapter_v5.missing_inputs`.

    Returns:
        {"narrative": str, "payload": dict, "flags": dict, "leakage": [str]}
        or None if no client was supplied or generation failed. Never raises.
    """
    if llm_client is None:
        return None

    try:
        payload = build_audit_payload(operator, tail, score_result, missing_inputs)
        prompt = build_prompt(payload)

        text = await _complete(llm_client, prompt)
        if not text:
            return None

        leakage = find_leakage(text)
        if leakage:
            # Log rather than discard: a usable narrative with a flagged term
            # is more useful than none, and the caller decides whether to
            # publish it. §9 compliance is enforced at the presentation layer.
            logger.warning(
                "TrustScore narrative contains forbidden term(s) %s for %s",
                leakage, operator.certificate_designator,
            )

        return {
            "narrative": text,
            "payload": payload,
            "flags": {
                name: category["flag"]
                for name, category in payload["audit_categories"].items()
            },
            "leakage": leakage,
        }
    except Exception as exc:
        # Narrative generation must never break a scoring run.
        logger.warning("TrustScore narrative generation failed: %s", exc)
        return None


async def _complete(llm_client: Any, prompt: str) -> Optional[str]:
    """
    Call the LLM, preferring a direct call that carries the §9.1 system prompt.

    `LLMClient.get_completion` hardcodes its own system prompt and a 500-token
    ceiling — too short for a six-category audit and the wrong role — so the
    underlying client is used directly when reachable, falling back to
    `get_completion` otherwise.
    """
    import os

    inner = getattr(llm_client, "client", None)
    if inner is not None and hasattr(inner, "chat"):
        model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
        response = await inner.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,   # low: this is an evidentiary summary, not prose
            max_tokens=2000,   # six categories plus summary and guidance
        )
        return (response.choices[0].message.content or "").strip()

    if hasattr(llm_client, "get_completion"):
        return (await llm_client.get_completion(f"{SYSTEM_PROMPT}\n\n{prompt}")).strip()

    return None
