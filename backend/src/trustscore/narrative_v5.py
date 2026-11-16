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

from src.trustscore import adapter_v5
from src.trustscore.calculator_v5 import (
    CATASTROPHIC_LOOKBACK_MONTHS,
    ELI_TAXONOMY,
    OperatorData,
    RiskEvent,
    Severity,
    TailData,
    catastrophic_events,
    decayed_sum,
)

logger = logging.getLogger(__name__)

# ── §9 Traffic-light taxonomy ────────────────────────────────────────────────

GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"

# A fourth state the specification does not name, added because the three it
# does name cannot express "we did not look".
#
# The flag functions below infer a category from the evidence gathered. With no
# evidence they return GREEN — which reads as "clean" but actually means
# "nothing found". For a category whose sources are not ingested at all
# (DOCINDEX liens, ASN latent risk, D085 churn), or for an operator whose
# lookups ran against a trade name rather than its certificate designator
# (§8), that is an overclaim: the operator may be spotless, or may have a
# record filed under a name nobody searched.
#
# GREY is therefore applied only where a GREEN would have rested on an
# unqueried source. RED and YELLOW are never downgraded — evidence of a problem
# stands regardless of what else is missing.
GREY = "GREY"

#: The ANCHOR sources for each category: the gaps that, *all together*, mean
#: total blindness.
#:
#: This is an OR-gate, not an AND-gate, and that is the whole point. A category
#: stays assessable while ANY ONE of its anchors is intact; it goes GREY only
#: when every anchor listed here is missing. Partial coverage is not ignorance —
#: if one primary source answered, the category gets a real colour derived from
#: what that source said.
#:
#: The earlier model inverted this: any single gap in a long list forced GREY.
#: Because GAP_TAIL_LIENS was raised unconditionally and GAP_CHURN fired on a
#: measured zero, legal_title and asset_stability were structurally incapable of
#: ever reading GREEN — so a spotless operator was indistinguishable from an
#: unexamined one, and the flag conveyed nothing.
#:
#: Supplementary sources (ASN latent risk, tail tenure, the DOCINDEX lookback
#: limit) are deliberately NOT anchors. They are disclosed as scope notes, and
#: they refine the prose, but they cannot hold a category hostage when a primary
#: source has answered.
_CATEGORY_ANCHORS = {
    # Sister-ship recovery depth. Known once the fleet has been counted.
    "flight_fulfillment": (adapter_v5.GAP_SAME_TYPE_FLEET,),
    # §1C: a DOT/watchdog query that ran and matched nothing is a clean record.
    "commercial_integrity": (adapter_v5.GAP_DOT_ORDERS,),
    # §1D: NTSB/AIDS is the anchor. ASN is explicitly ignored for flag purposes.
    "flight_safety": (adapter_v5.GAP_SAFETY_SOURCES,),
    # SDRS is queried with the fleet; nothing else gates this category.
    "maintenance_discipline": (),
    # §1A: certificate age OR measured churn is sufficient.
    "asset_stability": (adapter_v5.GAP_CERTIFICATE_AGE, adapter_v5.GAP_CHURN),
    # §1B: FAA ownership classification OR an executed lien lookup.
    "legal_title": (adapter_v5.GAP_TAIL_LIENS, adapter_v5.GAP_OWNERSHIP),
}

#: Categories where a §8 name-resolution failure genuinely undermines a clean
#: finding, because the evidence is keyed to the operator's *identity*.
#:
#: Previously applied to all six. For safety and maintenance that was wrong:
#: NTSB, AIDS and SDRS records attach to the N-number, which is immutable and
#: was searched directly, so a clean airframe history stands regardless of what
#: the operator calls itself. Legal, conduct and churn records attach to the
#: entity, so there the concern is real.
_NAME_SENSITIVE = frozenset({
    "commercial_integrity",
    "legal_title",
    "asset_stability",
    "flight_fulfillment",
})

_NAME_GAPS = (adapter_v5.GAP_NAME_ANCHORED_LOOKUPS,
              adapter_v5.GAP_CERTIFICATE_UNRESOLVED)


def _apply_coverage(flag: str, category: str, gap_keys: frozenset) -> str:
    """
    Downgrade a GREEN to GREY only under total category blindness (§1).

    A category is assessable while at least one anchor source answered. GREY
    means "we could not look at all", never "we looked and found nothing" —
    the latter is what a clean operator looks like and must read GREEN.

    Only GREEN is affected. A RED or YELLOW rests on evidence that was actually
    found, and missing *other* sources does not make that finding less real.
    """
    if flag != GREEN:
        return flag

    anchors = _CATEGORY_ANCHORS.get(category, ())
    # Every anchor missing → nothing was consulted → genuinely not assessed.
    # An empty anchor tuple means the category has no gating source and stays
    # assessable, which is why `anchors and ...` guards the check.
    if anchors and all(anchor in gap_keys for anchor in anchors):
        return GREY

    # §8: evidence filed under a name nobody searched. Applies only where the
    # evidence is entity-keyed, and only when the operator could not be
    # resolved at all.
    if category in _NAME_SENSITIVE and all(gap in gap_keys for gap in _NAME_GAPS):
        return GREY

    return GREEN

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


#: Fraction of its original severity an event must retain to still drive a
#: flag by itself.
#:
#: §4.1 decays severity on a five-year half-life, so the arithmetic forgets an
#: old event: a 1988 accident retains ~0.5% of its weight by 2026 and Hsafety
#: reads 0.9988 — effectively perfect. The flags did not decay, so that
#: operator still showed RED flight safety. A broker reads RED as a current
#: hazard, and nothing in the score supported it.
#:
#: Expressed as a *fraction* rather than an absolute severity on purpose.
#: Comparing a decayed value against the raw §6 thresholds cannot work: decay
#: only ever reduces, so `decayed >= SUBSTANTIAL_DAMAGE` is unreachable for
#: anything but a brand-new maximum-severity event, and every finding collapses
#: to YELLOW. The fraction separates the two questions the flag actually asks —
#: how bad was it (the §6 schedule) and how recent is it (the decay).
#:
#: 0.25 is two half-lives, i.e. ten years. An event inside that window still
#: flags at its §6 severity; beyond it the finding is disclosed but no longer
#: presented as a current condition.
_FLAG_RECENCY_FLOOR = 0.25


def _retained(event: RiskEvent, now=None) -> float:
    """
    Fraction of its original severity this event still carries, in (0, 1].

    Computed via `decayed_sum` so the flag and the score share one decay
    constant and cannot drift apart. An event with no usable date is treated as
    fully retained: undated risk is not discounted, matching §4.1.
    """
    if not event.severity:
        return 0.0
    return decayed_sum([event], now=now) / float(event.severity)


def _flag_flight_safety(operator: OperatorData, tail: TailData, now=None) -> str:
    """
    NTSB/AIDS accidents across both the certificate and this airframe.

    Severity is compared *after* decay, so the flag agrees with the score. An
    event old enough that Hsafety has effectively forgotten it no longer shows
    RED — it drops to YELLOW while still being disclosed in the narrative,
    because the event did happen and a reader should know.
    """
    all_events = list(operator.fleet_accident_events) + list(tail.tail_accident_events)
    if not all_events:
        return GREEN

    # §4.1a circuit breaker, checked FIRST and without reference to decay or
    # severity grading. A fatal crash or hull loss inside the lookback window
    # is RED, full stop.
    #
    # This must not go through the severity/decay test below: an open NTSB
    # docket carries no injury or damage codes for weeks, so a crash from last
    # month scores severity 0 and would read GREEN — which is exactly the
    # failure this guards. See calculator_v5.is_catastrophic.
    if catastrophic_events(operator, tail, now):
        return RED

    # RED needs a finding that is both serious (§6) and still current (decay).
    if any(
        event.severity >= Severity.SUBSTANTIAL_DAMAGE
        and _retained(event, now=now) >= _FLAG_RECENCY_FLOOR
        for event in all_events
    ):
        return RED

    # Something is on record but has either decayed or was never severe enough
    # to read as a current hazard. Never GREEN: the event did happen, and
    # presenting that as clean would overstate the operator.
    return YELLOW


def _flag_maintenance(operator: OperatorData, tail: TailData, now=None) -> str:
    """
    SDRS critical precautionary procedures, airframe and fleet level.

    Decay-aware for the same reason as flight safety: an in-flight shutdown
    from 2009 says little about maintenance discipline today, and the score has
    already discounted it to nearly nothing.
    """
    all_sdrs = list(operator.fleet_sdr_events) + list(tail.tail_sdr_events)
    if not all_sdrs:
        return GREEN

    if any(
        event.severity >= Severity.SDR_IFSD
        and _retained(event, now=now) >= _FLAG_RECENCY_FLOOR
        for event in all_sdrs
    ):
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
    """
    Active liens, ownership structure, and rapid title transfers.

    Severity-tiered per §2B, because filing count is a poor risk proxy. Any
    lien used to force RED, which meant a fleet carrying routine bank
    financings — what every financed aircraft looks like — ranked alongside one
    carrying a tax levy.

    Now:
        tier 3 (tax levy, judgment, programme default)  -> RED, on one filing
        tier 2 (material MRO / fuel / unclassified)     -> YELLOW
        tier 1 only (bank, lessor, administrative)      -> does not by itself
                                                           move the flag
    """
    tiers = {
        event.severity_tier or 2  # untiered events keep the old material weight
        for event in tail.tail_lien_events
    }

    # A single crippling encumbrance is enough: the claimant can detain the
    # airframe at an FBO, so count is irrelevant.
    if 3 in tiers:
        return RED
    # Certificate-level liens carry no tier (they arrive via ELI, not DOCINDEX)
    # and are material by construction.
    if any(
        event.event_type == "ACTIVE_MECHANICS_OR_TAX_LIEN"
        for event in operator.legal_events
    ):
        return RED
    if 2 in tiers:
        return YELLOW
    if tail.ownership_classification.lower() not in ("exclusive", "holding_entity"):
        return YELLOW
    # Tier 1 filings only, or none at all. Routine financing is not a defect,
    # so this is GREEN — the narrative still discloses the filings and explains
    # their low magnitude (§2B).
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
    trade_names: Optional[List[Dict[str, Any]]] = None,
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
        trade_names: Optional DBA records from
            `common.entity_resolution.resolve_trade_names`. Looked up here when
            not supplied; pass `[]` to skip the lookup entirely (tests, and any
            caller that must not touch the database).

    Returns:
        A JSON-serializable payload safe to hand to an LLM.
    """
    from src.trustscore.calculator_v5 import calculate_churn_effective

    churn = calculate_churn_effective(operator)

    # Resolved here rather than required of every caller, so an existing call
    # site gains the names without changing. A failure inside
    # resolve_trade_names returns [] rather than raising — a reporting detail
    # must never fail a score.
    if trade_names is None:
        from src.common.entity_resolution import resolve_trade_names

        trade_names = resolve_trade_names(
            operator.operator_name,
            operator.certificate_designator,
        )

    raw_flags = {
        "flight_fulfillment": _flag_flight_fulfillment(operator, tail),
        "commercial_integrity": _flag_commercial_integrity(operator),
        "flight_safety": _flag_flight_safety(operator, tail),
        "maintenance_discipline": _flag_maintenance(operator, tail),
        "asset_stability": _flag_asset_stability(operator, tail, churn),
        "legal_title": _flag_legal_title(operator, tail),
    }

    # Downgrade any GREEN whose sources were never consulted. Without this a
    # rebranded operator — whose lookups all ran against a name nobody filed
    # under — reads as six green flags and a Pinnacle score.
    gap_keys = frozenset(adapter_v5.missing_input_keys(operator, tail))
    flags = {
        name: _apply_coverage(flag, name, gap_keys)
        for name, flag in raw_flags.items()
    }

    # §4.1a. Surfaced as its own payload block when tripped, because a
    # catastrophe must not arrive as one entry in a list of accident events —
    # the narrative has to lead with it.
    breaker = catastrophic_events(operator, tail, None)
    catastrophic: Dict[str, Any] = {}
    if breaker:
        catastrophic = {
            "catastrophic_events": {
                "count": len(breaker),
                "within_months": CATASTROPHIC_LOOKBACK_MONTHS,
                "events": _describe_events(breaker),
                "guidance": (
                    "A fatal accident or hull loss on this certificate within "
                    f"the last {CATASTROPHIC_LOOKBACK_MONTHS} months. This "
                    "overrides every other consideration in the report: lead "
                    "the Executive Summary with it, state it in the "
                    "Operational Stance, and do not offset it against clean "
                    "findings elsewhere. Where the NTSB investigation is "
                    "still open, say so and say that cause has not been "
                    "determined — but never present an open docket as though "
                    "the event itself were unconfirmed."
                ),
            }
        }

    return {
        "operator_name": operator.operator_name,
        "certificate_designator": operator.certificate_designator,
        # Every name this certificate trades under (§8).
        #
        # A charter is sold under a trade name while the safety and
        # enforcement record attaches to the certificate, so the two can
        # differ — certificate 3KSC is held by Asher Air LLC and also trades
        # as Blue Spruce Air. A broker quoted by one has no way to know the
        # other is the same operator, which is exactly the arrangement §8
        # exists to defeat. Entity resolution already searched all of these;
        # until now it never told the reader what they were.
        "trade_names": trade_names,
        # Omitted entirely when estimated, rather than sent with a
                # caveat. Instructing the model not to assert an estimated
                # figure gave only partial compliance: it dropped the bare
                # claim but still volunteered "active for 10.0 years" inside a
                # could-not-be-assessed paragraph. A number in the payload
                # invites being quoted, and 10.0 is a hardcoded fallback -- no
                # source carries the real issuance date (docs §1a). The surest
                # way not to publish a fabricated figure is not to supply it.
                **({} if operator.certificate_age_is_estimated else {
                    "certificate_age_years": round(operator.certificate_age_years, 1),
                }),
                "certificate_age_is_estimated": operator.certificate_age_is_estimated,
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
                # §4.1a. Present only when the breaker tripped, so its mere
                # presence is the signal. The narrative must lead with this.
                **catastrophic,
            },
            "maintenance_discipline": {
                "flag": flags["maintenance_discipline"],
                "fleet_sdr_count": len(operator.fleet_sdr_events),
                "tail_sdr_events": _describe_events(tail.tail_sdr_events),
                "fleet_sdr_events": _describe_events(operator.fleet_sdr_events),
            },
            "asset_stability": {
                "flag": flags["asset_stability"],
                # Omitted entirely when estimated, rather than sent with a
                # caveat. Instructing the model not to assert an estimated
                # figure gave only partial compliance: it dropped the bare
                # claim but still volunteered "active for 10.0 years" inside a
                # could-not-be-assessed paragraph. A number in the payload
                # invites being quoted, and 10.0 is a hardcoded fallback -- no
                # source carries the real issuance date (docs §1a). The surest
                # way not to publish a fabricated figure is not to supply it.
                **({} if operator.certificate_age_is_estimated else {
                    "certificate_age_years": round(operator.certificate_age_years, 1),
                }),
                "certificate_age_is_estimated": operator.certificate_age_is_estimated,
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
                # §2B framing depends on severity, not count: several small
                # vendor filings must not be narrated as financial distress,
                # and one tax levy must not be buried because the count is 1.
                "lien_profile": _lien_severity_summary(tail),
            },
        },
        # Sources that WERE consulted and came back clean. The counterpart to
        # data_coverage_gaps, and the reason the model can tell a favourable
        # nil return from an unexamined one: without this it sees only an
        # absence and has no way to know whether anyone looked.
        "verified_clean_searches": _clean_searches(operator, tail),
        # Residual scope limits. NOT a licence to call a GREEN category
        # unevidenced — see the guardrails in SYSTEM_PROMPT.
        "data_coverage_gaps": missing_inputs or [],
    }


def _lien_severity_summary(tail: TailData) -> Dict[str, Any]:
    """
    Per-tier lien counts plus the framing §2B requires for each shape.

    `guidance` is supplied rather than left to the model because the two
    failure modes are symmetrical and both are easy to fall into: narrating
    many trivial filings as distress, and under-reporting one catastrophic
    filing because the count is low.
    """
    counts = {1: 0, 2: 0, 3: 0}
    for event in tail.tail_lien_events:
        counts[event.severity_tier or 2] = counts.get(event.severity_tier or 2, 0) + 1

    summary: Dict[str, Any] = {
        "nuisance_administrative": counts[1],
        "material_mro_or_fuel": counts[2],
        "crippling_tax_judgment_or_programme": counts[3],
    }

    if counts[3]:
        summary["guidance"] = (
            "A single crippling encumbrance gives the claimant legal standing "
            "to detain or ground the aircraft at an FBO without notice. State "
            "this plainly and do not dilute it by noting the low filing count."
        )
    elif counts[2]:
        summary["guidance"] = (
            "Material filings are on record. Report them as a working-capital "
            "signal worth confirming before departure, without asserting "
            "distress that the filing count alone does not establish."
        )
    elif counts[1]:
        summary["guidance"] = (
            "These are routine financing or administrative filings — a "
            "recorded bank loan or lease is what a financed aircraft looks "
            "like, not a defect. Reassure the broker explicitly that their "
            "low magnitude poses negligible risk of seizure or AOG grounding. "
            "Do NOT frame this operator as financially distressed."
        )
    return summary


#: Human-readable confirmations of a search that ran and found nothing.
#:
#: Phrased as findings rather than absences ("queried, 0 returned") so the
#: narrative has something affirmative to cite. §1 of the flag spec requires a
#: nil return from a queried source to read as evidence of clean conduct, and
#: the model cannot honour that if the payload only ever lists what is missing.
def _clean_searches(operator: OperatorData, tail: TailData) -> List[str]:
    """Affirmative nil-return findings, for the narrative to cite as positives."""
    clean: List[str] = []

    if operator.conduct_sources_queried and not operator.legal_events:
        clean.append(
            "DOT OACP enforcement orders and watchdog records: queried under "
            "the operator's legal name and known trade names, 0 matching "
            "violations or complaints"
        )
    if operator.safety_sources_queried and not (
        operator.fleet_accident_events or tail.tail_accident_events
    ):
        clean.append(
            "NTSB and FAA accident/incident databases: queried for the "
            "certificate and airframe, 0 recorded accidents or incidents"
        )
    if operator.safety_sources_queried and not (
        operator.fleet_sdr_events or tail.tail_sdr_events
    ):
        clean.append(
            "FAA Service Difficulty Reports: queried fleet-wide and for this "
            "airframe, 0 reported structural or system defects"
        )
    if tail.liens_queried and not tail.tail_lien_events:
        clean.append(
            "FAA Document Index (DOCINDEX): searched for this airframe, 0 "
            "active mechanics' liens, fuel claims or financial encumbrances"
        )
    # Only claimed when the window actually supports it. D085 currently holds a
    # ~31-day span against a 180-day minimum, so fetch_churn returns None and
    # churn_measured stays False for every operator -- the narrative then rests
    # on certificate longevity alone rather than asserting a 12-month retention
    # finding no snapshot can back.
    if operator.churn_measured and not (
        operator.tails_added_12m or operator.tails_removed_12m
    ):
        clean.append(
            "OpSpecs D085 fleet roster: compared across the trailing 12 "
            "months, 0 aircraft added or removed (stable fleet retention)"
        )
    return clean


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
YELLOW, RED or GREY flag. Use them exactly as given; do not re-derive or \
override.
- GREY means NOT ASSESSED, not "clean". It is applied when the sources behind \
that category were not consulted — an uningested feed, or a lookup that ran \
against a trade name rather than the operator's certificate. For a GREY \
category, state plainly that it could not be assessed and name the missing \
source from `data_coverage_gaps`. Never describe a GREY category as clear, \
satisfactory, or without findings.
- Certificate age: when `certificate_age_is_estimated` is true, \
`certificate_age_years` is ABSENT from the payload because no ingested source \
carries the operator's certificate issuance date. Do not state, estimate or \
infer a certificate age in that case — not even approximately, and not inside \
a caveat. Say the issuance date is unavailable, or omit the subject.
- TRADE NAMES ARE MANDATORY. `trade_names` lists every name this certificate \
operates under. You MUST name all of them in the Executive Summary. A charter \
is sold under a trade name while the safety record attaches to the \
certificate, so a broker who only knows one name cannot otherwise tell that \
the others are the same operator. Distinguish the two states: a name with \
`is_current` true is a CONCURRENT trade name ("also operates as X"), while \
`is_current` false is a FORMER identity ("previously operated as X"). Never \
describe a former name as current or the reverse. Where more than one name is \
listed, state explicitly that the findings in this report cover all of them. \
If `trade_names` is empty the certificate could not be resolved — say the \
operator's other trading identities could not be established, and do not imply \
it has none.
- CATASTROPHIC EVENTS OVERRIDE EVERYTHING. If the flight-safety block carries \
a `catastrophic_events` key, a fatal accident or hull loss occurred on this \
certificate recently. Lead the Executive Summary with it, name it in the \
Operational Stance, and never let clean findings in other categories soften or \
balance it. Do not describe the operator as low-risk, well-run or \
recommendable. If the investigation is open, state that cause has not yet been \
determined — but an open docket means the cause is unknown, NOT that the crash \
is unconfirmed. Never imply the latter.
- Objective Tone: Maintain a clinical, institutional tone. Attribute all \
adverse findings directly to official public repositories (NTSB, FAA SDRS, \
FAA Document Index, DOT OACP) or verified watchdog reporting.
- ABSENCE OF FINDINGS IS A POSITIVE RESULT, NOT A GAP. `data_coverage_gaps` \
lists residual scope limits; it does NOT make a GREEN category unevidenced. \
Only a GREY flag means "not assessed". Where a category is GREEN and a source \
WAS queried, a nil return is affirmative evidence of clean conduct and you \
must present it as such — state explicitly that the search was run and \
returned nothing, and that this is a favourable indicator. Never hedge a GREEN \
category with "unevidenced", "could not be verified", "no data available", or \
similar. A queried source that found nothing has told us something good.
- Scope notes: if a gap is listed for a category that is GREEN, you may note \
the residual limit in at most one clause (e.g. the FAA Document Index covers a \
rolling recent window, so filings older than that window are not reflected). \
Do not let that clause displace the positive finding or imply the category is \
unassessed.

3. Required Output Format

Executive Summary
TrustScore: [Score] ([Tier Name: Pinnacle 90+ | Premier 80-89 | Benchmark \
70-79 | Standard 50-69])
Operating As: [every entry in `trade_names`, marking each as a current trade \
name or a former identity. Omit this line only when `trade_names` holds a \
single name matching the operator name; if the list is empty, state that other \
trading identities could not be established.]
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

4. Mandatory "So-What" Elaboration Standard

A broker does not want a recitation of database variables. "The operator has 2 \
sister ships and 0 SDRs" is a fact with no decision attached to it. EVERY \
datapoint you cite in the Executive Summary and in all 6 category blocks must \
follow a three-part structure:

  1. THE FACT — the concrete metric or finding from the payload.
  2. THE OPERATIONAL MECHANISM — what that metric actually proves about how \
this operator runs its fleet behind the scenes.
  3. THE LIVE-TRIP IMPACT — how it protects or threatens the broker's client, \
schedule and buyout margin on departure day.

Worked examples of the required depth:

- Sister-ship redundancy. Shallow: "4 aircraft, 2 of the same type." Required: \
name the count and type, then explain that a '1-of-1' orphan tail leaves the \
operator no in-house recovery when it goes AOG on the ramp — they must buy from \
the wholesale sub-charter market and typically pass the recovery buyout back to \
the broker — whereas an identical sister ship on the same certificate shares \
type-rated crews and parts inventory and can be swapped internally.

- Airframe age vs maintenance discipline. Shallow: "1981 model, 0 SDRs." \
Required: acknowledge the age carries a baseline component-fatigue penalty, \
then explain that older jets are not inherently unsafe where preventive \
maintenance is rigorous, and that zero FAA-reported structural or system \
defects indicates the maintenance programme is staying ahead of age-related \
dispatch failures.

- Ownership structure. Shallow: "ownership is exclusive." Required: explain \
that on a third-party managed tail the private owner can pull the aircraft for \
personal use, veto a charter, or refuse to approve a weekend AOG part, whereas \
exclusive operator ownership means full dispatch control and direct financial \
alignment to keep the aircraft flying.

- Certificate longevity and fleet churn. Shallow: "certificate is 15.3 years \
old with 0% churn." Required: explain that fly-by-night and distressed \
carriers shed tails as owners pull jets over unpaid bills, and cycle through \
short-lived certificates — so sustained continuous certification paired with \
stable fleet retention signals institutional stability and aircraft-owner \
retention. Only cite a churn figure if one is present in the payload.

- Liens and encumbrances. Shallow: "0 active liens." Required: state that the \
FAA Document Index search returned no active mechanics' liens, fuel claims or \
financial encumbrances, then explain that when an operator falls behind on MRO \
or contract-fuel accounts, creditors file FAA liens and FBOs place the tail on \
cash-only status — which can physically block refuelling or departure mid- \
itinerary with passengers aboard. Clear title indicates vendors are being paid \
on time.

- Commercial integrity. Shallow: "no legal or watchdog events." Required: name \
the corpora queried (DOT OACP enforcement orders, watchdog records) and the \
names searched, then explain that bad-actor operators mask fleet shortages by \
double-selling tails, conducting unauthorized brokerage, or running last-minute \
bait-and-switch tail substitutions — so a clean record indicates the operator \
honours signed charter contracts.

Do not reuse this wording verbatim. Apply the same depth to whatever the \
payload actually contains, and never assert a figure the payload does not carry.
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
    trade_names: Optional[List[Dict[str, Any]]] = None,
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
        payload = build_audit_payload(
            operator, tail, score_result, missing_inputs, trade_names
        )
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
    # Use the same model llm_client picks. That module chooses in code rather
    # than from OPENROUTER_MODEL on purpose ("matching backend"), so reading
    # the env var here would silently send narrative traffic to a different
    # model than every other LLM call in the service — and to one the account
    # may not even have access to.
    from src.trustscore.llm_client import OPENROUTER_DEFAULT_MODEL

    inner = getattr(llm_client, "client", None)
    if inner is not None and hasattr(inner, "chat"):
        response = await inner.chat.completions.create(
            model=OPENROUTER_DEFAULT_MODEL,
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
