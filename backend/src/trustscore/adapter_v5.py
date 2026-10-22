"""
Adapter: existing pipeline output -> TrustScore v5.0 inputs.

The ingestion pipelines emit loosely-typed event dicts shaped for the v3
calculator. v5.0 expects typed `RiskEvent` objects carrying a severity drawn
from the §6 schedule. This module translates between the two so call sites stay
small and the calculator stays pure.

Keeping the mapping here — rather than in the workflow or the router — means
there is one place to change when a pipeline's output shape moves, and one
place to read when asking "where did this severity come from?".

IMPORTANT — v5.0 is not yet fully fed. Several inputs the specification
requires have no pipeline behind them today:

    Churneffective  needs monthly OpSpecs D085 snapshots (none are captured)
    Vtype           needs same-type fleet depth from D085
    Ttenure         needs per-tail D085 onboarding dates
    Lientail        needs FAA DOCINDEX.txt conveyance parsing
    Ost             needs MASTER.txt registrant cross-referencing

Where data is absent this adapter applies the *neutral* value (no penalty), so
missing pipelines never invent risk. That is deliberate but it is not
free: an operator with real churn or a real lien will currently score better
than it should. See `missing_inputs()` for a machine-readable list of what was
defaulted on any given call.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.trustscore.calculator_v5 import (
    ELI_TAXONOMY,
    OperatorData,
    RiskEvent,
    Severity,
    TailData,
    eli_event,
)

logger = logging.getLogger(__name__)

# Business suffixes stripped when matching operator names. Mirrors
# faa_enforcement_service.normalize_operator_name, which the DOT ingestion
# pipeline uses to populate operator_name_normalized — the two must agree or
# score-time lookups will miss. Duplicated rather than imported to keep this
# module free of that module's openpyxl and database dependencies.
_STRIP_SUFFIXES = re.compile(
    r"\b(LLC\.?|INC\.?|CORP\.?|CO\.?|LTD\.?|L\.?L\.?C\.?|"
    r"INCORPORATED|CORPORATION|COMPANY|LIMITED|DBA)\b",
    re.IGNORECASE,
)


def normalize_operator_name(raw_name: str) -> str:
    """
    Normalize an operator name for matching.

    Must stay byte-for-byte equivalent to
    `faa_enforcement_service.normalize_operator_name`: that function populates
    `dot_enforcement_orders.operator_name_normalized`, and this one queries it.

    Args:
        raw_name: The original operator name string.

    Returns:
        Cleaned, uppercase operator name suitable for comparison.
    """
    if not raw_name:
        return ""
    name = _STRIP_SUFFIXES.sub("", raw_name)
    name = re.sub(r"[.,]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.upper()

# ── Severity mapping for legacy event dicts ──────────────────────────────────

#: NTSB/AIDS injury levels that denote a fatal accident (§6.1 — 50 points).
_FATAL_MARKERS = ("fatal", "fatality", "fatalities")

#: Phrases marking substantial structural damage (§6.1 — 25 points).
_SUBSTANTIAL_MARKERS = ("substantial", "destroyed", "hull loss", "total loss")

#: Phrases marking a serious incident (§6.1 — 15 points).
_SERIOUS_MARKERS = ("serious", "excursion", "incursion", "gear-up", "gear up")

#: Phrases marking a major operational incident (§6.1 — 10 points).
_MAJOR_MARKERS = ("turbulence", "depressuriz", "major")


def classify_accident_severity(event: Dict[str, Any]) -> float:
    """
    Map an NTSB/AIDS event dict onto the §6.1 physical safety schedule.

    The pipelines record free-text `event_type`, `injury_level` and `severity`
    fields rather than a schedule value, so the bucket is inferred from those.
    An event that matches nothing falls to the lowest bucket (5) rather than
    zero: it reached a federal accident database, so it is not nothing.

    Args:
        event: Legacy event dict from the NTSB or AIDS pipeline.

    Returns:
        One of the §6.1 severity values.
    """
    blob = " ".join(
        str(event.get(key) or "")
        for key in ("event_type", "injury_level", "severity", "aircraft_damage", "summary")
    ).lower()

    if any(marker in blob for marker in _FATAL_MARKERS):
        return Severity.FATAL_ACCIDENT
    if any(marker in blob for marker in _SUBSTANTIAL_MARKERS):
        return Severity.SUBSTANTIAL_DAMAGE
    if any(marker in blob for marker in _SERIOUS_MARKERS):
        return Severity.SERIOUS_INCIDENT
    if any(marker in blob for marker in _MAJOR_MARKERS):
        return Severity.MAJOR_INCIDENT
    if "accident" in blob:
        return Severity.SUBSTANTIAL_DAMAGE
    return Severity.MINOR_LATENT


def _event_date(event: Dict[str, Any]) -> Any:
    """Pull whichever date key a pipeline happened to use."""
    for key in ("event_date", "date", "filing_date", "date_known", "report_date"):
        value = event.get(key)
        if value:
            return value
    return None


def _reference(event: Dict[str, Any]) -> str:
    """Pull whichever identifier a pipeline happened to use, for audit trails."""
    for key in ("event_id", "faa_case_number", "case_number", "file_number", "control_number"):
        value = event.get(key)
        if value:
            return str(value)
    return ""


def split_fleet_events(
    fleet_events: List[Dict[str, Any]],
) -> Tuple[List[RiskEvent], List[RiskEvent], List[RiskEvent]]:
    """
    Split a mixed legacy event list into the three v5.0 buckets.

    v3 pooled NTSB accidents, FAA enforcement actions and SDRs into one list.
    v5.0 routes them to different terms — accidents to `Orfbase`, SDRs to
    `Sdrfleet`, enforcement to `ELI` — because they decay into different health
    multipliers.

    Args:
        fleet_events: Mixed event dicts from the pipelines.

    Returns:
        (accident_events, sdr_events, legal_events)
    """
    accidents: List[RiskEvent] = []
    sdrs: List[RiskEvent] = []
    legal: List[RiskEvent] = []

    for event in fleet_events or []:
        event_type = str(event.get("event_type") or "").lower()
        date = _event_date(event)
        ref = _reference(event)

        if event_type == "faa_sdr":
            # sdrs_service pre-classifies against the §6.2 schedule.
            sdrs.append(RiskEvent(
                severity=float(event.get("sdr_severity") or Severity.SDR_UNSCHEDULED_LANDING),
                event_date=date,
                event_type="faa_sdr",
                source="SDRS",
                reference=ref,
            ))
        elif event_type == "faa_enforcement":
            # FAA enforcement is regulatory conduct, so it feeds ELI. The AGC
            # report set has no §6.3 taxonomy code, so it is mapped to the
            # enforcement bucket rather than guessed into a more severe one.
            legal.append(RiskEvent(
                severity=Severity.ELI_MAJOR,
                event_date=date,
                event_type="FAA_ENFORCEMENT",
                source="FAA_AGC",
                reference=ref,
            ))
        else:
            accidents.append(RiskEvent(
                severity=classify_accident_severity(event),
                event_date=date,
                event_type=str(event.get("event_type") or "accident"),
                source="NTSB",
                reference=ref,
            ))

    return accidents, sdrs, legal


def ucc_filings_to_legal_events(ucc_filings: List[Dict[str, Any]]) -> List[RiskEvent]:
    """
    Map UCC filings onto the §6.3 encumbrance bucket.

    v5.0 has no `FSF` term; liens feed `ELI` instead. Only *unresolved* filings
    are scored — a lapsed or terminated lien is not an active encumbrance.

    Note this is a near-neighbour of, not a substitute for, the specification's
    intent: §7 Pipeline 3 calls for FAA DOCINDEX.txt conveyance codes (M/T),
    which capture aviation mechanic's liens specifically. State UCC filings are
    broader and noisier. When DOCINDEX parsing lands, prefer it.

    Args:
        ucc_filings: Legacy UCC filing dicts.

    Returns:
        RiskEvents for filings that appear active.
    """
    events: List[RiskEvent] = []
    for filing in ucc_filings or []:
        status = str(filing.get("status") or "").lower()
        if any(word in status for word in ("lapsed", "terminated", "released", "resolved", "expired")):
            continue
        events.append(RiskEvent(
            severity=Severity.ELI_ENCUMBRANCE,
            event_date=filing.get("filing_date"),
            event_type="ACTIVE_MECHANICS_OR_TAX_LIEN",
            source="UCC",
            reference=str(filing.get("file_number") or ""),
        ))
    return events


#: DOT order types that represent an adverse finding against the operator.
#: `dismissal` is deliberately excluded — a dismissed complaint is not a
#: violation, and scoring it would penalize operators who were cleared.
#: `unknown` is also excluded: the LLM extractor emits it when it could not
#: classify the order, and an unclassified row is not evidence of wrongdoing.
_DOT_SCORED_ORDER_TYPES = frozenset({"consent_order", "settlement", "enforcement_action"})

#: §6.3 mapping for DOT order types. A formal consent order is the taxonomy's
#: named DOT case (25 points); settlements and other enforcement actions carry
#: the same weight, being equally formal federal outcomes.
_DOT_TYPE_TO_VIOLATION = {
    "consent_order": "DOT_OACP_CONSENT_ORDER",
    "settlement": "DOT_OACP_CONSENT_ORDER",
    "enforcement_action": "DOT_OACP_CONSENT_ORDER",
}


def dot_orders_to_legal_events(orders: List[Any]) -> List[RiskEvent]:
    """
    Map DOT OACP enforcement orders onto the §6.3 taxonomy.

    Implements Pipeline 8. Accepts either `DOTEnforcementOrder` ORM rows or
    plain dicts with the same field names, so callers can pass query results
    directly.

    Dismissals and unclassified rows are skipped — see `_DOT_SCORED_ORDER_TYPES`.
    An order with no `effective_date` still scores, undecayed, because an
    undated federal enforcement action is not less real for lacking a date.

    Args:
        orders: DOTEnforcementOrder rows or equivalent dicts.

    Returns:
        RiskEvents for orders that represent an adverse finding.
    """
    events: List[RiskEvent] = []
    for order in orders or []:
        get = order.get if isinstance(order, dict) else lambda k, o=order: getattr(o, k, None)

        order_type = str(get("order_type") or "unknown").strip().lower()
        if order_type not in _DOT_SCORED_ORDER_TYPES:
            continue

        event = eli_event(
            _DOT_TYPE_TO_VIOLATION[order_type],
            event_date=get("effective_date"),
            source="DOT_OACP",
            reference=str(get("order_number") or ""),
        )
        if event is not None:
            events.append(event)
    return events


def fetch_dot_orders_for_operator(operator_name: str, db_session_factory: Any = None) -> List[Any]:
    """
    Look up DOT enforcement orders for an operator by normalized name.

    The ingestion pipeline stores no operator_id foreign key, so matching is by
    `operator_name_normalized` — the same normalization this module and
    `faa_enforcement_service` apply, so the two sides agree.

    Name matching is weaker than §8 would like: it cannot follow a certificate
    through a rebrand the way a certificate-designator anchor would. Until the
    historical-DBA array exists, an operator that renamed itself after an order
    was filed will not match.

    Returns an empty list on any failure — a database or schema problem must
    never fail a scoring run.

    Args:
        operator_name: Operator trade name.
        db_session_factory: Callable returning a SQLAlchemy session. Defaults to
            the application's SessionLocal.

    Returns:
        Matching DOTEnforcementOrder rows, or [] if none or on error.
    """
    if not operator_name:
        return []

    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal
            db_session_factory = SessionLocal

        from src.common.models import DOTEnforcementOrder

        normalized = normalize_operator_name(operator_name)
        if not normalized:
            return []

        session = db_session_factory()
        return (
            session.query(DOTEnforcementOrder)
            .filter(DOTEnforcementOrder.operator_name_normalized == normalized)
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("DOT enforcement lookup failed for %s: %s", operator_name, exc)
        return []
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def fetch_fleet_size(operator_name: str, db_session_factory: Any = None) -> int:
    """
    Count active tails on an operator's certificate — `Vf` in §4.1.

    Counts `gtj.aircraft` rows joined to the operator by name. The
    specification sources `Vf` from OpSpecs D085 via JETNET (Pipeline 2); this
    is a stand-in until that pipeline exists, and it is a close one — the
    aircraft table is populated from the same registry data.

    `Vf` normalizes accident risk by `MAX(1, SQRT(Vf))`, so getting this wrong
    is not cosmetic. A 671-aircraft operator scored as `Vf=1` carries roughly
    26x the per-incident penalty it should.

    Returns 0 on any failure, which the calculator treats as "unknown" and
    normalizes by 1 — the same conservative behaviour as before this lookup
    existed.

    Args:
        operator_name: Operator name as it appears in gtj.operators.
        db_session_factory: Callable returning a SQLAlchemy session. Defaults
            to the application's SessionLocal.

    Returns:
        Number of aircraft on the certificate, or 0 if unknown.
    """
    if not operator_name:
        return 0

    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal
            db_session_factory = SessionLocal

        from sqlalchemy import text

        session = db_session_factory()
        count = session.execute(
            text("""
                SELECT COUNT(a.aircraft_id)
                FROM gtj.aircraft a
                JOIN gtj.operators o ON o.operator_id = a.operator_id
                WHERE o.name = :name
            """),
            {"name": operator_name},
        ).scalar()
        return int(count or 0)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Fleet size lookup failed for %s: %s", operator_name, exc)
        return 0
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def watchdog_to_legal_events(records: List[Dict[str, Any]]) -> List[RiskEvent]:
    """
    Map micro-LLM watchdog/OACP extractions onto §6.3.

    Expects the extraction contract from §7 Pipeline 7:
    `{"operator_name", "violation_type", "date"}`. A `violation_type` outside
    the taxonomy is dropped and reported, never guessed — §6.3 requires strict
    enumeration so extraction failures stay visible.

    Args:
        records: Extracted violation records.

    Returns:
        RiskEvents for records whose violation_type is in the taxonomy.
    """
    events: List[RiskEvent] = []
    for record in records or []:
        event = eli_event(
            record.get("violation_type", ""),
            event_date=record.get("date"),
            source=str(record.get("source") or "WATCHDOG"),
            reference=str(record.get("reference") or ""),
        )
        if event is not None:
            events.append(event)
    return events


# ── Assembly ─────────────────────────────────────────────────────────────────

def build_operator_data(
    *,
    operator_name: str,
    certificate_designator: Optional[str] = None,
    certificate_age_years: float = 0.0,
    fleet_size: Optional[int] = None,
    fleet_events: Optional[List[Dict[str, Any]]] = None,
    ucc_filings: Optional[List[Dict[str, Any]]] = None,
    watchdog_records: Optional[List[Dict[str, Any]]] = None,
    latent_risk_events: Optional[List[Dict[str, Any]]] = None,
    dot_orders: Optional[List[Any]] = None,
    include_dot_orders: bool = True,
    lookup_fleet_size: bool = True,
    tails_added_12m: int = 0,
    tails_removed_12m: int = 0,
) -> OperatorData:
    """
    Assemble `OperatorData` from whatever the pipelines produced.

    `certificate_designator` falls back to the operator name when the Part 135
    certificate ID has not been resolved. That is a known gap, not a design
    choice: §8 requires anchoring to the immutable 4-character designator, and
    name-anchored data is exactly what the DBA shell game defeats.

    Args:
        operator_name: Operator trade name.
        certificate_designator: 4-char FAA certificate ID, when known.
        certificate_age_years: Agecert. See caveat in module docstring.
        fleet_size: Vf — active tails.
        fleet_events: Mixed legacy event dicts.
        ucc_filings: Legacy UCC filing dicts.
        watchdog_records: Micro-LLM extractions (§6.3 taxonomy).
        latent_risk_events: ASN wikibase events.
        dot_orders: Pre-fetched DOTEnforcementOrder rows. When omitted and
            `include_dot_orders` is true, they are looked up by normalized
            operator name.
        include_dot_orders: Set False to skip the DOT lookup entirely — useful
            in tests, or wherever a database is not available.
        tails_added_12m / tails_removed_12m: D085 churn, when available.

    Returns:
        OperatorData ready for the v5.0 calculator.
    """
    # Vf — count active tails when the caller did not supply a figure. Passing
    # an explicit fleet_size (including 0) skips the lookup.
    if fleet_size is None:
        fleet_size = fetch_fleet_size(operator_name) if lookup_fleet_size else 0

    accidents, sdrs, enforcement = split_fleet_events(fleet_events or [])

    legal = enforcement
    legal += ucc_filings_to_legal_events(ucc_filings or [])
    legal += watchdog_to_legal_events(watchdog_records or [])

    # Pipeline 8 — DOT OACP. Fetched here rather than at the call sites so
    # every caller gets it without repeating the lookup.
    if dot_orders is None and include_dot_orders:
        dot_orders = fetch_dot_orders_for_operator(operator_name)
    legal += dot_orders_to_legal_events(dot_orders or [])

    latent = [
        RiskEvent(
            severity=classify_accident_severity(event),
            event_date=_event_date(event),
            event_type=str(event.get("event_type") or "latent"),
            source="ASN",
            reference=_reference(event),
        )
        for event in (latent_risk_events or [])
    ]

    return OperatorData(
        certificate_designator=certificate_designator or operator_name,
        operator_name=operator_name,
        certificate_age_years=certificate_age_years,
        fleet_size=fleet_size,
        tails_added_12m=tails_added_12m,
        tails_removed_12m=tails_removed_12m,
        fleet_accident_events=accidents,
        fleet_sdr_events=sdrs,
        latent_risk_events=latent,
        legal_events=legal,
    )


def build_tail_data(
    *,
    tail_number: str,
    aircraft_age_years: float = 0.0,
    ownership_classification: str = "exclusive",
    same_type_fleet_count: int = 1,
    certificate_tenure_months: float = 999.0,
    tail_events: Optional[List[Dict[str, Any]]] = None,
    tail_lien_records: Optional[List[Dict[str, Any]]] = None,
) -> TailData:
    """
    Assemble `TailData` for one airframe.

    `tail_events` must contain only events for THIS registration number. Do not
    pass the fleet-wide list: `Iht` carries a 5x multiplier (§5.3), so charging
    every fleet incident against every airframe inflates the tail penalty
    enormously. The v3 code made exactly that mistake.

    OPERATOR-LEVEL SCORING: pass `tail_number=""` and nothing else. The result
    is a *neutral* tail — every modifier 1.0 — so `Hts` contributes no penalty
    and the score reflects the certificate alone.

    This matters because the defaults are not neutral. An unspecified airframe
    would otherwise be scored as age 0 (Mht 0.9755, new-airframe teething) with
    no sister ships (Rtype 0.92, orphan fleet), producing Hts ≈ 0.90 — a 10%
    penalty for an aircraft that does not exist. Since Hts carries the 0.65
    weight in the composite, that phantom penalty would dominate every
    operator-level score.

    Args:
        tail_number: N-number. Empty string selects neutral operator-level mode.
        aircraft_age_years: Airframe age, for Mht.
        ownership_classification: Key into OWNERSHIP_MODIFIERS.
        same_type_fleet_count: Vtype — sister ships of this make/model.
        certificate_tenure_months: Months on the active D085.
        tail_events: Events for this tail only.
        tail_lien_records: DOCINDEX M/T records against this tail.

    Returns:
        TailData ready for the v5.0 calculator.
    """
    # Operator-level scoring: no airframe, therefore no airframe risk. Age 3.5
    # is Mht's peak (1.0) and Vtype 5 is the deep-recovery threshold (1.0), so
    # every tail modifier resolves to 1.0 and Hts reduces to Htailhistory,
    # which is 1.0 with no tail events.
    if not tail_number:
        return TailData(
            tail_number="",
            aircraft_age_years=3.5,
            ownership_classification="exclusive",
            same_type_fleet_count=5,
            certificate_tenure_months=999.0,
            tail_accident_events=[],
            tail_sdr_events=[],
            tail_lien_events=[],
        )

    accidents, sdrs, _ = split_fleet_events(tail_events or [])

    liens = [
        RiskEvent(
            severity=0.0,  # the calculator applies the flat 25-point charge
            event_date=_event_date(record),
            event_type="ACTIVE_MECHANICS_OR_TAX_LIEN",
            source="DOCINDEX",
            reference=_reference(record),
        )
        for record in (tail_lien_records or [])
    ]

    return TailData(
        tail_number=tail_number,
        aircraft_age_years=aircraft_age_years,
        ownership_classification=ownership_classification,
        same_type_fleet_count=same_type_fleet_count,
        certificate_tenure_months=certificate_tenure_months,
        tail_accident_events=accidents,
        tail_sdr_events=sdrs,
        tail_lien_events=liens,
    )


def missing_inputs(operator: OperatorData, tail: TailData) -> List[str]:
    """
    Report which v5.0 inputs were left at their neutral default.

    Every entry means a real risk signal the score cannot currently see. Callers
    should log this alongside the score so a high number is never mistaken for a
    fully-evidenced one.

    Returns:
        Human-readable descriptions of defaulted inputs.
    """
    gaps: List[str] = []

    if operator.certificate_designator == operator.operator_name:
        gaps.append(
            "certificate_designator unresolved (anchored to trade name; §8 requires "
            "the immutable 4-char FAA ID to defeat DBA rebranding)"
        )
    if not operator.certificate_age_years:
        gaps.append("certificate_age_years is 0 (Agecert unknown; Cs will be near 0)")
    if not operator.fleet_size:
        gaps.append("fleet_size is 0 (Vf unknown; no exposure normalization)")
    if not operator.tails_added_12m and not operator.tails_removed_12m:
        gaps.append("D085 churn not captured (Churneffective = 0; fleet volatility invisible)")
    if not operator.latent_risk_events:
        gaps.append("ASN latent risk not ingested (Lrisk = 0)")
    if not any(event.source == "DOT_OACP" for event in operator.legal_events):
        gaps.append(
            "no DOT OACP orders matched (either none exist, or the operator's "
            "name differs from the filed respondent — matching is by name, not "
            "certificate designator)"
        )
    if tail.certificate_tenure_months >= 999.0:
        gaps.append("tail D085 tenure unknown (Ttenure assumed seasoned)")
    if tail.same_type_fleet_count <= 1:
        gaps.append("same-type fleet depth unknown (Vtype treated as orphan)")
    if not tail.tail_lien_events:
        gaps.append("DOCINDEX liens not parsed (Lientail = 0)")

    return gaps
