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

        # Match every name on this certificate (§8). A DOT order names the
        # respondent as filed, so an operator that has since rebranded would
        # otherwise appear to have no enforcement history.
        from src.common.entity_resolution import resolve_operator_names

        names = resolve_operator_names(
            operator_name, db_session_factory=db_session_factory
        ) or [normalized]

        session = db_session_factory()
        return (
            session.query(DOTEnforcementOrder)
            .filter(DOTEnforcementOrder.operator_name_normalized.in_(names))
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


#: Snapshot source holding the FAA Part 135 D085 authorization table — the
#: legally authorized fleet, which is what §3 means by Vf. Written weekly by
#: scripts/ingest_d085.py. Distinct from 'gtj.aircraft', JETNET's view of what
#: an operator holds.
D085_SOURCE = "opspecs_d085"

#: Shortest snapshot span that may be reported as churn.
#:
#: §3 asks for 12 months. Half of that is the point below which the figure
#: stops approximating the metric and starts misrepresenting it — a fleet with
#: real annual turnover is indistinguishable from a stable one over a few
#: weeks. Below this, fetch_churn returns None so GAP_CHURN keeps firing.
#:
#: Not set to the full 12 months because a 6-to-12-month window understates
#: churn without inventing it, and `window_days` is returned so a caller can
#: see how much history actually backed the number.
_MIN_CHURN_WINDOW_DAYS = 180


def fetch_churn(
    operator_name: str,
    months_back: int = 12,
    db_session_factory: Any = None,
) -> Optional[Dict[str, int]]:
    """
    Trailing D085 fleet churn — TailsAdded, TailsRemoved and BaselineVf (§3).

    Churn is a *differential*, so it cannot be derived from current state: it is
    the set difference of authorized N-numbers between the newest D085 snapshot
    and one about `months_back` earlier. gtj.aircraft is updated in place and
    keeps no history, which is why gtj.fleet_snapshots exists.

    Returns None — not zeroes — when churn cannot be computed, so the caller can
    distinguish "no movement" from "no history yet". Reporting 0 for both would
    make an operator with a single snapshot look stable rather than unmeasured,
    and `Churneffective` of 0 is a full confidence score under §3.

    Baseline selection: the oldest snapshot at or before the `months_back` mark,
    or the oldest held if history is shorter. A shorter window understates churn
    rather than inventing it, and `window_days` is returned so the caller can
    see how much history actually backed the figure.

    Args:
        operator_name: Operator name as it appears in gtj.operators.
        months_back: Target window. §3 specifies 12 months.
        db_session_factory: Callable returning a session; defaults to
            SessionLocal.

    Returns:
        {"tails_added", "tails_removed", "baseline_fleet_size", "window_days"},
        or None when fewer than two D085 snapshots exist for this operator.
    """
    if not operator_name:
        return None

    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal
            db_session_factory = SessionLocal

        from sqlalchemy import text

        session = db_session_factory()

        # Resolve through the certificate's full name array (§8), so an
        # operator that rebranded still matches its own snapshot history.
        try:
            from src.common.entity_resolution import resolve_operator_names
            names = resolve_operator_names(
                operator_name, db_session_factory=db_session_factory
            ) or [normalize_operator_name(operator_name)]
        except Exception:
            names = [normalize_operator_name(operator_name)]

        # Resolve to operator_ids in Python rather than matching names in SQL.
        # `names` are *normalized* ("TRITON AIR"), while gtj.operators holds the
        # raw name ("Triton Air Llc") and has no normalized column to join on —
        # unlike dot_enforcement_orders, where the ingestion pipeline stores
        # one. Comparing the two directly never matches.
        wanted = set(names)
        operator_ids = [
            str(r[0]) for r in session.execute(
                text("SELECT operator_id, name FROM gtj.operators WHERE name IS NOT NULL")
            )
            if normalize_operator_name(r[1]) in wanted
        ]
        if not operator_ids:
            return None

        months = [
            r[0] for r in session.execute(
                text("""
                    SELECT DISTINCT snapshot_month
                    FROM gtj.fleet_snapshots
                    WHERE source = :source
                      AND operator_id = ANY(CAST(:ids AS uuid[]))
                    ORDER BY snapshot_month DESC
                """),
                {"source": D085_SOURCE, "ids": operator_ids},
            )
        ]

        if len(months) < 2:
            return None

        current = months[0]
        baseline = next(
            (m for m in months if (current - m).days >= months_back * 28),
            months[-1],
        )

        # Refuse a window too short to mean anything.
        #
        # §3 defines churn over 12 months. A three-week diff is not a weak
        # version of that metric — it is a different and far noisier one: a
        # fleet that turns over twice a year looks identical to a stable one
        # when sampled three weeks apart.
        #
        # Returning a number here would be actively worse than returning
        # nothing, because Churneffective = 0 is a FULL confidence score under
        # §3. Every operator would clear GAP_CHURN and read as evidenced-stable
        # on evidence that cannot support it.
        #
        # This fires today and will keep firing: web.archive.org holds exactly
        # one usable capture of the D085 file (2026-10-18), so the trailing
        # window cannot be backfilled and has to accrue month by month.
        window_days = (current - baseline).days
        if window_days < _MIN_CHURN_WINDOW_DAYS:
            logger.info(
                "Churn window for %s is only %d days (need %d); reporting "
                "unmeasured rather than a figure §3 cannot support",
                operator_name, window_days, _MIN_CHURN_WINDOW_DAYS,
            )
            return None

        def tails_at(month) -> set:
            return {
                r[0] for r in session.execute(
                    text("""
                        SELECT tail_number
                        FROM gtj.fleet_snapshots
                        WHERE source = :source
                          AND snapshot_month = :month
                          AND operator_id = ANY(CAST(:ids AS uuid[]))
                    """),
                    {"source": D085_SOURCE, "month": month, "ids": operator_ids},
                )
            }

        now_set, then_set = tails_at(current), tails_at(baseline)
        if not then_set:
            return None

        return {
            "tails_added": len(now_set - then_set),
            "tails_removed": len(then_set - now_set),
            # §3 divides by the baseline, not the current fleet: an operator
            # that halved its fleet must be measured against what it had.
            "baseline_fleet_size": len(then_set),
            "window_days": (current - baseline).days,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Churn lookup failed for %s: %s", operator_name, exc)
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def fetch_tail_liens(
    tail_number: str,
    db_session_factory: Any = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Active lien filings against one N-number — `Lientail` in §4.2.

    Reads gtj.tail_liens, written weekly by scripts/ingest_tail_liens.py from
    the FAA DOCINDEX index. Only unreleased filings are returned: §4.2 charges
    unresolved encumbrances, and a lien discharged by a later REL/REP is not
    one.

    ONE ENCUMBRANCE PER FINANCING, NOT PER DOCUMENT
    -----------------------------------------------
    Rows are grouped by (doc_type, doc_date, party). Aircraft financing is
    routinely recorded as one document per collateral item — airframe, each
    engine, avionics — so a single secured loan arrives as a run of
    sequentially numbered filings:

        N402XT  S/A  2025-01-08  ARE016566074  GUNTRACK AVIATION LLC
        N402XT  S/A  2025-01-08  ARE016566076  GUNTRACK AVIATION LLC
        …16 documents, DOC-IDs stepping by 2, one party, one day

    That is one encumbrance. Charged per document it cost N402XT 18 §4.2
    penalties and drove the tail to 67.45 against 95.92 unencumbered — a normal
    secured loan scored as catastrophic distress.

    Note this is deliberately the INVERSE of the storage key (migration 082
    keys rows on DOC-ID *including* party-duplicates). The two serve different
    purposes and both are correct: the table is the factual record of what was
    filed, one row per document; this function answers "how many distinct
    encumbrances exist", which is what §4.2 charges. `reference` carries the
    document count so a risk audit can still say 16 documents were recorded.

    Returns None when the table has never been populated, and [] when it has
    been populated but holds nothing for this tail. The caller needs that
    distinction: [] is "looked, found nothing in the window", None is "never
    looked", and only the first is evidence of anything.

    Note that neither answer clears title. DOCINDEX is a ~180-day rolling
    window, so a lien recorded years ago and never released is absent from it
    entirely. GAP_TAIL_LIENS therefore stays raised regardless — see
    missing_input_keys.

    Args:
        tail_number: N-number, with or without the leading N.
        db_session_factory: Callable returning a session; defaults to
            SessionLocal.

    Returns:
        Records shaped for `build_tail_data(tail_lien_records=…)`, or None.
    """
    if not tail_number:
        return None

    normalized = str(tail_number).strip().upper()
    if normalized and not normalized.startswith("N"):
        normalized = f"N{normalized}"

    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal
            db_session_factory = SessionLocal

        from sqlalchemy import text

        session = db_session_factory()

        # An empty table means the ingest has never run; that is "unknown", not
        # "no liens", and must not be reported as a clean result.
        populated = session.execute(
            text("SELECT EXISTS (SELECT 1 FROM gtj.tail_liens)")
        ).scalar()
        if not populated:
            return None

        rows = session.execute(
            text("""
                SELECT doc_type, doc_date, party, COUNT(*) AS documents
                FROM gtj.tail_liens
                WHERE tail_number = :tail
                  AND superseded_by_release = false
                  -- The table also stores REL/REP rows, so that a release can
                  -- be matched against a lien recorded in a different 180-day
                  -- window. A release is not an encumbrance and must never be
                  -- charged as one.
                  AND doc_type IN ('S/A', 'CSC')
                GROUP BY doc_type, doc_date, party
                ORDER BY doc_date DESC NULLS LAST
            """),
            {"tail": normalized},
        ).mappings().all()

        # Who filed matters: a bank recording a loan is routine, while a
        # maintenance shop or fuel supplier files with the Registry only when
        # unpaid. Annotated rather than scored — §4.2 charges every active
        # encumbrance equally, and this classification is UNKNOWN for ~64% of
        # real parties, so it informs the narrative without moving a number.
        from src.common.lien_classification import classify_party, UNKNOWN

        out = []
        for row in rows:
            kind = classify_party(row["party"])
            reference = f"DOCINDEX {row['doc_type']} {normalized}"
            if row["party"]:
                reference += f" {row['party']}"
            if row["documents"] > 1:
                reference += f" ({row['documents']} documents)"
            if kind != UNKNOWN:
                reference += f" [{kind.lower()}]"
            out.append({
                "date": row["doc_date"].isoformat() if row["doc_date"] else None,
                "reference": reference,
            })
        return out
    except Exception as exc:  # pragma: no cover - defensive
        # A missing table or an unreachable database must narrow the score,
        # never fail it.
        logger.warning("Tail lien lookup failed for %s: %s", tail_number, exc)
        return None
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
    certificate_age_is_estimated: bool = False,
    fleet_size: Optional[int] = None,
    fleet_events: Optional[List[Dict[str, Any]]] = None,
    ucc_filings: Optional[List[Dict[str, Any]]] = None,
    watchdog_records: Optional[List[Dict[str, Any]]] = None,
    latent_risk_events: Optional[List[Dict[str, Any]]] = None,
    dot_orders: Optional[List[Any]] = None,
    include_dot_orders: bool = True,
    lookup_fleet_size: bool = True,
    tails_added_12m: Optional[int] = None,
    tails_removed_12m: Optional[int] = None,
    lookup_churn: bool = True,
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
        tails_added_12m / tails_removed_12m: D085 churn. Leave as None to look
            it up from gtj.fleet_snapshots; pass explicit values (including 0)
            to skip the lookup.
        lookup_churn: Set False to skip the churn lookup entirely — useful in
            tests, or wherever a database is not available.

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

    # §8 — did the risk lookups run against the certificate's full name array,
    # or just the one name the caller supplied? True only when this operator is
    # in gtj.certificate_dbas, since that table is what resolution expands
    # through. Checked here rather than inferred from the designator: a
    # designator can arrive from the operators row while the DBA array is
    # absent, and that combination is still a name-anchored search.
    lookups_anchored = False
    if include_dot_orders:  # proxy for "a database is available"
        try:
            from src.common.entity_resolution import resolve_certificate

            lookups_anchored = resolve_certificate(operator_name) is not None
        except Exception as exc:  # pragma: no cover - defensive
            # Unknown coverage must read as "not anchored", never crash a score.
            logger.warning(
                "Could not determine §8 anchoring for %s: %s", operator_name, exc
            )

    # §3 Churn, from D085 snapshot diffs. Looked up only when the caller did not
    # supply figures, so an explicit 0 still means "measured, no movement".
    #
    # baseline_fleet_size is taken from the churn window rather than the current
    # fleet: §3 divides by what the operator had at the start, so using today's
    # count would understate an operator that has shed aircraft.
    churn_baseline: Optional[int] = None
    if lookup_churn and tails_added_12m is None and tails_removed_12m is None:
        churn = fetch_churn(operator_name)
        if churn:
            tails_added_12m = churn["tails_added"]
            tails_removed_12m = churn["tails_removed"]
            churn_baseline = churn["baseline_fleet_size"]

    return OperatorData(
        certificate_designator=certificate_designator or operator_name,
        operator_name=operator_name,
        certificate_age_years=certificate_age_years,
        certificate_age_is_estimated=certificate_age_is_estimated,
        lookups_certificate_anchored=lookups_anchored,
        fleet_size=fleet_size,
        # None means "never measured"; the calculator's field is an int, so it
        # becomes 0 — the same no-penalty default as before, and GAP_CHURN still
        # reports the absence.
        tails_added_12m=tails_added_12m or 0,
        tails_removed_12m=tails_removed_12m or 0,
        baseline_fleet_size=churn_baseline,
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
    lookup_liens: bool = True,
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

    # §4.2 Lientail, from gtj.tail_liens. Looked up only when the caller did not
    # supply records, so an explicit [] still means "measured, none found".
    if lookup_liens and tail_lien_records is None:
        tail_lien_records = fetch_tail_liens(tail_number)

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


# Stable identifiers for each coverage gap, so callers can branch on them
# without pattern-matching the prose in missing_inputs(). The narrative layer
# uses these to decide whether a category's GREEN is evidenced or merely
# unexamined.
GAP_CERTIFICATE_UNRESOLVED = "certificate_designator_unresolved"
#: Raised when evidence was gathered under a single trade name rather than
#: under every name on the certificate. §8 resolution removes this for any
#: operator present in `gtj.certificate_dbas`; it remains for one absent from
#: the ingested Part 135 roster, where there is no DBA array to expand.
#: Distinct from GAP_CERTIFICATE_UNRESOLVED: an operator can have a perfectly
#: good designator (Red Wing has R3WA) and still have every lookup run against
#: its marketing name, which is the failure the specification describes.
GAP_NAME_ANCHORED_LOOKUPS = "lookups_anchored_to_trade_name"
GAP_CERTIFICATE_AGE = "certificate_age_unknown"
GAP_FLEET_SIZE = "fleet_size_unknown"
GAP_CHURN = "churn_not_captured"
GAP_LATENT_RISK = "asn_latent_risk_not_ingested"
GAP_DOT_ORDERS = "dot_orders_unmatched"
GAP_TAIL_TENURE = "tail_tenure_unknown"
GAP_SAME_TYPE_FLEET = "same_type_fleet_unknown"
GAP_TAIL_LIENS = "docindex_liens_not_parsed"


def missing_input_keys(operator: OperatorData, tail: TailData) -> List[str]:
    """
    The same findings as `missing_inputs`, as stable keys rather than prose.

    Prose is for humans and changes freely; these identifiers are what code
    should branch on.

    Returns:
        GAP_* identifiers for every input left at its neutral default.
    """
    keys: List[str] = []
    if operator.certificate_designator == operator.operator_name:
        keys.append(GAP_CERTIFICATE_UNRESOLVED)
    # §8 entity resolution now expands an operator into every name on its
    # certificate before querying NTSB, FAA enforcement and DOT, so this is no
    # longer unconditional. It still fires for an operator missing from the
    # ingested Part 135 roster: there, resolution finds no DBA array and falls
    # back to the single supplied name, which is the failure §8 describes.
    if not operator.lookups_certificate_anchored:
        keys.append(GAP_NAME_ANCHORED_LOOKUPS)
    # Fires for a missing age *or* an estimated one. A fallback of 10.0 is not
    # an observation, and treating it as one let Cs look fully evidenced on
    # operators whose certificate date nobody knows.
    if not operator.certificate_age_years or operator.certificate_age_is_estimated:
        keys.append(GAP_CERTIFICATE_AGE)
    if not operator.fleet_size:
        keys.append(GAP_FLEET_SIZE)
    if not operator.tails_added_12m and not operator.tails_removed_12m:
        keys.append(GAP_CHURN)
    if not operator.latent_risk_events:
        keys.append(GAP_LATENT_RISK)
    if not any(event.source == "DOT_OACP" for event in operator.legal_events):
        keys.append(GAP_DOT_ORDERS)
    if tail.certificate_tenure_months >= 999.0:
        keys.append(GAP_TAIL_TENURE)
    if tail.same_type_fleet_count <= 1:
        keys.append(GAP_SAME_TYPE_FLEET)
    # Raised unconditionally, even when liens WERE found.
    #
    # DOCINDEX — the only lien source ingested — is a ~180-day rolling suspense
    # index, so a lien recorded years ago and never released is absent from it
    # entirely. Finding filings proves encumbrance; finding none proves nothing
    # about title. Neither outcome licenses a clean legal_title finding, so the
    # gap stands until FAA CARES (permanent, life-of-airframe) is ingested.
    #
    # The found liens still score: they feed ELI through tail_lien_events. This
    # only governs whether the *category* may read as evidenced.
    keys.append(GAP_TAIL_LIENS)
    return keys


def missing_inputs(operator: OperatorData, tail: TailData) -> List[str]:
    """
    Report which v5.0 inputs were left at their neutral default.

    Every entry means a real risk signal the score cannot currently see. Callers
    should log this alongside the score so a high number is never mistaken for a
    fully-evidenced one.

    See `missing_input_keys` for the same findings in a form code can branch on.

    Returns:
        Human-readable descriptions of defaulted inputs.
    """
    gaps: List[str] = []

    if operator.certificate_designator == operator.operator_name:
        gaps.append(
            "certificate_designator unresolved (anchored to trade name; §8 requires "
            "the immutable 4-char FAA ID to defeat DBA rebranding)"
        )
    gaps.append(
        "evidence gathered by trade name, not certificate designator (§8): an "
        "operator that has rebranded will not match its own history"
    )
    if not operator.certificate_age_years:
        gaps.append("certificate_age_years is 0 (Agecert unknown; Cs will be near 0)")
    elif operator.certificate_age_is_estimated:
        gaps.append(
            f"certificate age is an estimate ({operator.certificate_age_years:.1f}y), "
            "not an observed issuance date — §3 wants years since the certificate "
            "was issued; no ingested source carries that date"
        )
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
