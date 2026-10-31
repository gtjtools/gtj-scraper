"""
TrustScore Calculator — Algorithm v5.0

Implements "TrustScore Algorithm v5.0 — Algorithmic Architecture & Engineering
Specification" (backend/TrustScore Algorithm v5.0.docx), which is the source of
truth for this module. Section numbers in the docstrings below refer to it.

v5.0 replaces v3's additive penalty model with an Exponential Decay
Multiplicative Health Model. Every risk category yields a health multiplier in
(0, 1]; multipliers compose, so one critical failure drives the composite toward
zero and the score to the 50-point floor rather than being averaged away by
clean categories.

    TrustScore = 50 + 50 * ((0.35 * Hsafety + 0.65 * Hts) * Hconduct * Cs)
    FleetScore = 50 + 50 * (Hos * Cs)        where Hos = Hsafety * Hconduct

Three structural properties follow from the spec (§1.1) and are load-bearing:

  * The Slander Floor. Scores are clamped to [50, 100]. Because every
    multiplier is in (0, 1], the formulas cannot mathematically produce a value
    outside that range — the clamp is defence in depth, not the mechanism.

  * Non-compensatory conduct gate. Hconduct multiplies the whole composite, so
    an insolvent or fraudulent certificate cannot be rescued by a clean
    airframe.

  * Certificate anchoring. All inputs must be resolved against the immutable
    4-character FAA certificate designator, never a marketing DBA (§8). This
    module consumes already-resolved data; enforcing it is the ingestion
    pipeline's job.

This module is pure: no I/O, no database, no network. Callers assemble the
dataclasses from the pipelines in §7 and receive a breakdown dict.

v3 (calculator.py) is left untouched and still in service. The two produce
materially different numbers and must not be mixed in a single comparison.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── Shared constants ─────────────────────────────────────────────────────────

#: Decay constant k = ln(2)/5 — a 5-year half-life on every severity sum (§4.1).
DECAY_K = math.log(2) / 5  # 0.138629...

#: Exponential transform rate for health multipliers: H = e^(-0.025 * risk).
HEALTH_RATE = 0.025

#: The Slander Floor and ceiling (§1.1).
SCORE_FLOOR = 50.0
SCORE_CEILING = 100.0

#: Composite weights for TrustScore (§2). Tail risk dominates: the client is
#: booking a specific airframe, not the certificate in the abstract.
W_SAFETY = 0.35
W_TAIL = 0.65


# ── §6 Standardized Severity Schedule ────────────────────────────────────────

class Severity:
    """
    Standardized severity points (§6).

    Values are fixed by the specification. Pipelines classify raw events into
    these buckets; the calculator never invents a severity of its own.
    """

    # §6.1 Physical safety — Orfbase, Iht, Lrisk
    FATAL_ACCIDENT = 50.0          # fatal accident, total hull loss
    SUBSTANTIAL_DAMAGE = 25.0      # non-fatal accident, substantial structural damage
    SERIOUS_INCIDENT = 15.0        # runway incursion/excursion, gear-up landing
    MAJOR_INCIDENT = 10.0          # severe turbulence injury, depressurization
    MINOR_LATENT = 5.0             # blown tire, bird strike with precautionary return

    # §6.2 Maintenance & service difficulty — Sdrpenalty, Sdrfleet
    SDR_IFSD = 20.0                # in-flight shutdown, uncontained engine failure
    SDR_ABORTED_TAKEOFF = 15.0     # aborted takeoff, flight control malfunction, emergency descent
    SDR_CABIN_SMOKE = 10.0         # in-flight cabin smoke or toxic fumes
    SDR_UNSCHEDULED_LANDING = 5.0  # divert on secondary subsystem failure

    # §6.3 Commercial & legal — ELI taxonomy
    ELI_CRITICAL = 35.0            # fraud, funds withheld, illegal charter/retaliation
    ELI_MAJOR = 25.0               # vendor default/labor strike, DOT consent order
    ELI_ENCUMBRANCE = 20.0         # active mechanic's/tax lien, systemic dispatch failure
    ELI_DECEPTIVE = 15.0           # unauthorized DBA, deceptive marketing


#: §6.3 ELI taxonomy. The extraction pipeline must emit one of these exact
#: enum strings; unstructured text must never reach the calculator.
ELI_TAXONOMY: Dict[str, float] = {
    # 35 — Critical Commercial Violation
    "FRAUD_OR_PONZI_SCHEME": Severity.ELI_CRITICAL,
    "BREACH_OF_CONTRACT_FUNDS_WITHHELD": Severity.ELI_CRITICAL,
    "ILLEGAL_CHARTER_OR_SAFETY_RETALIATION": Severity.ELI_CRITICAL,
    # 25 — Major Operational Enforcement
    "VENDOR_DEFAULT_OR_LABOR_STRIKE": Severity.ELI_MAJOR,
    "DOT_OACP_CONSENT_ORDER": Severity.ELI_MAJOR,
    # 20 — Asset Encumbrance & Systemic Dispatch Failure
    "ACTIVE_MECHANICS_OR_TAX_LIEN": Severity.ELI_ENCUMBRANCE,
    "SYSTEMIC_DISPATCH_DROPS_OR_FLEET_GROUNDING": Severity.ELI_ENCUMBRANCE,
    # 15 — Deceptive Trade Practices
    "UNAUTHORIZED_DBA_OR_DECEPTIVE_MARKETING": Severity.ELI_DECEPTIVE,
}

#: §5.2 Ownership modifiers (Ost).
OWNERSHIP_MODIFIERS: Dict[str, float] = {
    "exclusive": 1.00,       # certificate-owned or verified holding entity
    "holding_entity": 1.00,
    "fractional": 0.95,      # fractional ownership program
    "leased": 0.90,          # leased or third-party managed
    "managed": 0.90,
}

#: §2.1 Score tiers, as (inclusive lower bound, name), highest first.
SCORE_TIERS = (
    (90.0, "Pinnacle"),    # 90-100: exceptional operational and commercial stability
    (80.0, "Premier"),     # 80-89:  reliable, high-performing
    (70.0, "Benchmark"),   # 70-79:  cautionary; requires contractual protection
    (0.0, "Standard"),     # 50-69:  elevated risk; booking not recommended
)

#: §4.1 Lrisk is clamped before the exponential transform.
LRISK_CAP = 15.0
#: §5.3 Sdrpenalty is clamped per tail.
SDR_TAIL_CAP = 30.0
#: §5.3 Points per active tail-specific lien.
LIEN_TAIL_POINTS = 25.0
#: §3 Churn is capped so catastrophic churn cannot zero out Cs entirely.
CHURN_CAP = 0.65
#: §3 Organic fleet growth below this ratio is unpenalized.
ORGANIC_GROWTH_ALLOWANCE = 0.25
#: §3 Weight applied to expansion above the organic allowance.
EXPANSION_WEIGHT = 0.50


# ── Input contracts ──────────────────────────────────────────────────────────

@dataclass
class RiskEvent:
    """
    One decayable scored event.

    The calculator does not classify: `severity` must already be a §6 value,
    assigned by the ingesting pipeline. `event_date` drives time decay; an
    event with no parseable date is treated as undecayed (full weight), which
    is the conservative choice for a risk score.
    """

    severity: float
    event_date: Optional[Any] = None       # datetime | ISO string | None
    event_type: str = ""                   # free-text label, for the breakdown only
    source: str = ""                       # NTSB | AIDS | SDRS | ASN | DOCINDEX | OACP | WATCHDOG
    reference: str = ""                    # case/docket/control number, for audit


@dataclass
class OperatorData:
    """Certificate-level inputs (§3, §4). Anchored to certificate_designator."""

    certificate_designator: str            # immutable 4-char FAA ID (§8)
    operator_name: str = ""
    certificate_age_years: float = 0.0     # Agecert — since ORIGINAL certificate issuance

    # Whether `certificate_age_years` came from a real date or a default.
    #
    # §3 defines Agecert as years since original certificate issuance. No
    # ingested source carries that date: callers currently supply either
    # `operators.business_started_date` (business registration — a different,
    # usually earlier date) or a hardcoded fallback. Both produce a plausible
    # number, so the score cannot tell them apart without being told.
    #
    # Agecert feeds Cs and the Dscale damping, so an invented value quietly
    # props up every score derived from it. Callers that know the figure is a
    # default must say so; the flag does not change the arithmetic, it makes
    # the uncertainty visible to `missing_input_keys` and the risk audit.
    certificate_age_is_estimated: bool = False

    # Whether the risk lookups were anchored to the certificate (§8) or ran
    # against a single trade name.
    #
    # §8 requires an event filed under *any* historical identity of a
    # certificate to attach to that certificate. `common.entity_resolution`
    # does this by expanding one name into every name recorded against the
    # designator in `gtj.certificate_dbas`, then matching all of them.
    #
    # True means that expansion ran and the sources were searched under the
    # certificate's full name array. False means the operator is not on the
    # ingested Part 135 roster, so only the supplied name was searched and a
    # clean result may simply mean the history is filed elsewhere. Like
    # `certificate_age_is_estimated`, this changes no arithmetic — it tells
    # `missing_input_keys` whether a clean finding is evidenced or unexamined.
    lookups_certificate_anchored: bool = False
    fleet_size: int = 0                    # Vf — active tails on OpSpecs D085

    # §3 Churn, from trailing 12-month D085 snapshot diffs
    tails_added_12m: int = 0
    tails_removed_12m: int = 0
    baseline_fleet_size: Optional[int] = None   # BaselineVf; defaults to fleet_size

    # §4.1 Safety
    fleet_accident_events: List[RiskEvent] = field(default_factory=list)  # NTSB + AIDS
    fleet_sdr_events: List[RiskEvent] = field(default_factory=list)       # SDRS, all tails
    latent_risk_events: List[RiskEvent] = field(default_factory=list)     # ASN wikibase

    # §4.2 Conduct — ELI only in the v5.0 build
    legal_events: List[RiskEvent] = field(default_factory=list)           # DOCINDEX + OACP + watchdogs

    # §4.2 Deferred first-party telemetry (Source 9). Hardcoded to 0 in v5.0;
    # exposed as fields so future ingestion needs no structural refactor.
    bes_penalty: float = 0.0
    ffr: float = 0.0


@dataclass
class TailData:
    """Airframe-level inputs (§5)."""

    tail_number: str
    aircraft_age_years: float = 0.0
    ownership_classification: str = "exclusive"   # key into OWNERSHIP_MODIFIERS
    same_type_fleet_count: int = 1                # Vtype — sister ships of this make/model
    certificate_tenure_months: float = 999.0      # months on active D085

    tail_accident_events: List[RiskEvent] = field(default_factory=list)  # NTSB/AIDS, this N-number
    tail_sdr_events: List[RiskEvent] = field(default_factory=list)       # SDRS, this N-number
    tail_lien_events: List[RiskEvent] = field(default_factory=list)      # DOCINDEX M/T, this N-number


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(value: Any) -> Optional[datetime]:
    """
    Coerce a date into an aware UTC datetime.

    Accepts a datetime or an ISO-8601 string. Naive datetimes are assumed UTC.
    Unparseable values yield None, which callers treat as "no decay".
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y%m%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def decayed_sum(events: List[RiskEvent], now: Optional[datetime] = None) -> float:
    """
    Sum severities under exponential decay: SUM(Severity * e^(-k * delta_t)).

    delta_t is elapsed years. Events with no usable date contribute their full
    severity — undated risk is not discounted. Future-dated events are clamped
    to delta_t = 0 so a bad timestamp cannot inflate a score above its
    undecayed value.
    """
    if not events:
        return 0.0
    current = now or datetime.now(timezone.utc)
    total = 0.0
    for event in events:
        when = _parse_date(event.event_date)
        if when is None:
            total += event.severity
            continue
        delta_years = max(0.0, (current - when).days / 365.25)
        total += event.severity * math.exp(-DECAY_K * delta_years)
    return total


def _health(risk: float) -> float:
    """Transform a non-negative risk sum into a health multiplier in (0, 1]."""
    return math.exp(-HEALTH_RATE * max(0.0, risk))


def get_score_tier(score: float) -> str:
    """Return the §2.1 tier name for a score."""
    for threshold, name in SCORE_TIERS:
        if score >= threshold:
            return name
    return "Standard"


# ── §3 Confidence Score ──────────────────────────────────────────────────────

def calculate_churn_effective(data: OperatorData) -> float:
    """
    Churneffective — asymmetric fleet-volatility penalty (§3).

        Churneffective = MIN(0.65, removed/baseline
                                   + 0.50 * MAX(0, added/baseline - 0.25))

    Contraction is weighted 1.0x: tails leaving a certificate signal owner
    defections. Expansion is free up to 25% a year, then weighted 0.50x — rapid
    onboarding strains conformity and maintenance bridging without being
    inherently adverse.
    """
    baseline = data.baseline_fleet_size if data.baseline_fleet_size is not None else data.fleet_size
    if not baseline or baseline <= 0:
        return 0.0

    contraction = data.tails_removed_12m / baseline
    expansion = data.tails_added_12m / baseline
    excess_expansion = max(0.0, expansion - ORGANIC_GROWTH_ALLOWANCE)
    return min(CHURN_CAP, contraction + EXPANSION_WEIGHT * excess_expansion)


def calculate_confidence_score(data: OperatorData) -> float:
    """
    Cs — macro dampener in [0, 1] (§3).

        Cs = MAX(0, (1 - e^(-0.384 * Agecert)) * (1 - Churneffective))

    Penalizes unseasoned certificates and asymmetric fleet distress. A brand-new
    certificate approaches 0 regardless of a clean record, so no operator can
    score near 100 without tenure.
    """
    maturity = 1.0 - math.exp(-0.384 * max(0.0, data.certificate_age_years))
    churn = calculate_churn_effective(data)
    return max(0.0, maturity * (1.0 - churn))


# ── §4.1 Safety Health ───────────────────────────────────────────────────────

def calculate_d_scale(data: OperatorData) -> float:
    """
    Dscale — logarithmic operator damping (§4.1).

        Dscale = MAX(0.5, 1 - 0.035 * ln(Vf + 1) * ln(Agecert + 1))

    A continuous replacement for step-function fleet-size discounts. Large,
    mature certificates absorb incidents more gracefully, but the discount is
    floored at 50% so scale alone can never erase a safety record.
    """
    fleet_term = math.log(max(0, data.fleet_size) + 1)
    age_term = math.log(max(0.0, data.certificate_age_years) + 1)
    return max(0.5, 1.0 - 0.035 * fleet_term * age_term)


def calculate_safety_health(
    data: OperatorData, now: Optional[datetime] = None
) -> Dict[str, float]:
    """
    Hsafety = e^(-0.025 * Sro), where (§4.1)

        Sro = ((Orfbase + Sdrfleet) * Dscale) + Lrisk

    Orfbase and Sdrfleet are each normalized by MAX(1, SQRT(Vf)) so a large
    fleet is not penalized simply for having more airframes to generate events.
    Note the square root: the spec deliberately rejects linear normalization,
    which would let scale dilute incidents away entirely.

    Lrisk is added *after* damping and capped at 15, so sub-regulatory noise
    cannot dominate, and large operators get no discount on it.
    """
    exposure = max(1.0, math.sqrt(max(0, data.fleet_size)))

    orf_base = decayed_sum(data.fleet_accident_events, now) / exposure
    sdr_fleet = decayed_sum(data.fleet_sdr_events, now) / exposure
    l_risk = min(LRISK_CAP, decayed_sum(data.latent_risk_events, now))
    d_scale = calculate_d_scale(data)

    sro = ((orf_base + sdr_fleet) * d_scale) + l_risk
    return {
        "orf_base": orf_base,
        "sdr_fleet": sdr_fleet,
        "l_risk": l_risk,
        "d_scale": d_scale,
        "sro": sro,
        "h_safety": _health(sro),
    }


# ── §4.2 Conduct Health ──────────────────────────────────────────────────────

def calculate_conduct_health(
    data: OperatorData, now: Optional[datetime] = None
) -> Dict[str, float]:
    """
    Hconduct = e^(-0.025 * Cro), where Cro = Bespenalty + FFR + ELI (§4.2).

    In the v5.0 build Bespenalty and FFR are 0 (Source 9 deferred), so Cro is
    driven entirely by ELI — mechanic's liens, DOT consent orders, and
    watchdog-documented commercial violations. They remain as fields so future
    first-party telemetry needs no structural change.

    Hconduct gates the entire composite (§1.2): it is non-compensatory, and a
    clean airframe cannot offset a legally encumbered certificate.
    """
    eli = decayed_sum(data.legal_events, now)
    cro = data.bes_penalty + data.ffr + eli
    return {
        "eli": eli,
        "bes_penalty": data.bes_penalty,
        "ffr": data.ffr,
        "cro": cro,
        "h_conduct": _health(cro),
    }


# ── §5 Tail Health ───────────────────────────────────────────────────────────

def calculate_maintenance_health(age_years: float) -> float:
    """
    Mht — piecewise quadratic airframe-age curve (§5.1).

        Mht = MAX(0.20, 1.0 - 0.0020 * (Age - 3.5)^2)

    Peaks at 1.0 at 3.5 years. New airframes take a small teething penalty
    (0.975 at age 0); old ones decline toward the 0.20 floor reached at ~23.5
    years, capturing AOG parts scarcity and subsystem fatigue.

    The spec writes this as two branches, but below 3.5 years the quadratic
    never reaches the floor, so a single clamped expression is equivalent.
    """
    return max(0.20, 1.0 - 0.0020 * (max(0.0, age_years) - 3.5) ** 2)


def calculate_ownership_modifier(classification: str) -> float:
    """
    Ost — ownership structure modifier (§5.2).

    Operator-controlled airframes carry no penalty; fractional and
    leased/managed structures introduce availability risk outside the
    certificate's direct control. Unrecognized values fall back to the
    most conservative multiplier rather than silently scoring 1.00.
    """
    key = (classification or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in OWNERSHIP_MODIFIERS:
        return OWNERSHIP_MODIFIERS[key]
    for name, value in OWNERSHIP_MODIFIERS.items():
        if name in key:
            return value
    return 0.90


def calculate_recovery_modifier(same_type_fleet_count: int) -> float:
    """
    Rtype — in-fleet sister-ship recovery depth (§5.2).

    Measures whether an AOG failure can be recovered with the same make/model
    inside the certificate: >=5 tails 1.00, 2-4 tails 0.96, orphan 0.92.
    """
    count = max(0, same_type_fleet_count)
    if count >= 5:
        return 1.00
    if count >= 2:
        return 0.96
    return 0.92


def calculate_tenure_modifier(tenure_months: float) -> float:
    """
    Ttenure — certificate onboarding tenure (§5.2).

    Tails on the active D085 under 6 months carry conformity and maintenance
    bridging friction: 0.95. Seasoned tails: 1.00.
    """
    return 1.00 if tenure_months >= 6.0 else 0.95


def calculate_tail_history_health(
    tail: TailData, now: Optional[datetime] = None
) -> Dict[str, float]:
    """
    Htailhistory = e^(-0.025 * (Iht + Sdrpenalty + Lientail)) (§5.3).

      Iht       = 5 * SUM(severity * decay)   — 5x multiplier isolates localized
                                                physical risk to this airframe
      Sdrpenalty= MIN(30, SUM(severity * decay))
      Lientail  = SUM(25 * decay) per active mechanic's/tax lien on this N-number

    The lien penalty is deliberately charged twice: here against the airframe
    (immediate MRO grounding risk) and again in certificate-level ELI. That
    duplication is specified, not accidental.
    """
    iht = 5.0 * decayed_sum(tail.tail_accident_events, now)
    sdr_penalty = min(SDR_TAIL_CAP, decayed_sum(tail.tail_sdr_events, now))

    # Each lien contributes a flat 25 points, decayed by its recording date.
    lien_events = [
        RiskEvent(
            severity=LIEN_TAIL_POINTS,
            event_date=event.event_date,
            event_type=event.event_type,
            source=event.source,
            reference=event.reference,
        )
        for event in tail.tail_lien_events
    ]
    lien_tail = decayed_sum(lien_events, now)

    total = iht + sdr_penalty + lien_tail
    return {
        "iht": iht,
        "sdr_penalty": sdr_penalty,
        "lien_tail": lien_tail,
        "tail_history_risk": total,
        "h_tail_history": _health(total),
    }


def calculate_tail_health(
    tail: TailData, now: Optional[datetime] = None
) -> Dict[str, float]:
    """
    Hts = Mht * Ost * Rtype * Ttenure * Htailhistory (§5).

    Multiplicative throughout: deep sister-ship coverage cannot offset a
    damaged airframe, and a young airframe cannot offset an active lien.
    """
    mht = calculate_maintenance_health(tail.aircraft_age_years)
    ost = calculate_ownership_modifier(tail.ownership_classification)
    rtype = calculate_recovery_modifier(tail.same_type_fleet_count)
    ttenure = calculate_tenure_modifier(tail.certificate_tenure_months)
    history = calculate_tail_history_health(tail, now)

    h_ts = mht * ost * rtype * ttenure * history["h_tail_history"]
    return {
        "mht": mht,
        "ost": ost,
        "rtype": rtype,
        "ttenure": ttenure,
        **history,
        "h_ts": h_ts,
    }


# ── §2 Composite scores ──────────────────────────────────────────────────────

def _clamp_score(value: float) -> float:
    """Apply the Slander Floor and ceiling (§1.1)."""
    return max(SCORE_FLOOR, min(SCORE_CEILING, value))


def calculate_fleet_score(
    operator: OperatorData, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    FleetScore = 50 + 50 * (Hos * Cs), where Hos = Hsafety * Hconduct (§2).

    Certificate-level risk, evaluated before a specific tail is assigned.
    """
    safety = calculate_safety_health(operator, now)
    conduct = calculate_conduct_health(operator, now)
    confidence = calculate_confidence_score(operator)

    h_os = safety["h_safety"] * conduct["h_conduct"]
    score = _clamp_score(SCORE_FLOOR + 50.0 * (h_os * confidence))

    return {
        "fleet_score": round(score, 2),
        "tier": get_score_tier(score),
        "certificate_designator": operator.certificate_designator,
        "operator_name": operator.operator_name,
        "components": {
            **safety,
            **conduct,
            "h_os": h_os,
            "cs": confidence,
            "churn_effective": calculate_churn_effective(operator),
        },
        "formula": "50 + 50 * (Hos * Cs); Hos = Hsafety * Hconduct",
        "algorithm_version": "5.0",
    }


def calculate_trust_score(
    operator: OperatorData, tail: TailData, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    TrustScore = 50 + 50 * ((0.35*Hsafety + 0.65*Hts) * Hconduct * Cs) (§2).

    The client-facing score for a specific airframe on a specific certificate.
    Safety and tail health are blended additively — a weighted view of
    certificate-wide versus airframe-specific physical risk — then gated
    multiplicatively by conduct and confidence, so commercial or legal failure
    cannot be averaged away.

    Returns both scores plus a full component breakdown. Per §9 (the Black Box
    Rule), the `components` block must never be exposed to clients, exports, or
    external APIs — it is for internal audit and narrative generation only.
    """
    safety = calculate_safety_health(operator, now)
    conduct = calculate_conduct_health(operator, now)
    tail_health = calculate_tail_health(tail, now)
    confidence = calculate_confidence_score(operator)

    blended = (W_SAFETY * safety["h_safety"]) + (W_TAIL * tail_health["h_ts"])
    composite = blended * conduct["h_conduct"] * confidence
    score = _clamp_score(SCORE_FLOOR + 50.0 * composite)

    fleet = calculate_fleet_score(operator, now)

    return {
        "trust_score": round(score, 2),
        "tier": get_score_tier(score),
        "fleet_score": fleet["fleet_score"],
        "fleet_tier": fleet["tier"],
        "tail_number": tail.tail_number,
        "certificate_designator": operator.certificate_designator,
        "operator_name": operator.operator_name,
        "components": {
            **safety,
            **conduct,
            **tail_health,
            "cs": confidence,
            "churn_effective": calculate_churn_effective(operator),
            "blended_health": blended,
            "composite": composite,
        },
        "formula": "50 + 50 * ((0.35*Hsafety + 0.65*Hts) * Hconduct * Cs)",
        "algorithm_version": "5.0",

        # ── Backwards-compatible keys ────────────────────────────────────────
        # Persistence and reporting code written against v3 reads these names.
        # They are projections of v5.0 values, not v3 quantities: v3's
        # tail_score and operator_score were 0-100 additive sub-scores, whereas
        # these are the v5.0 health multipliers rendered on the same 50-100
        # scale as the composite. Do not compare them to stored v3 numbers.
        "score_tier": get_score_tier(score),
        "confidence_score": confidence,
        "tail_score": round(_clamp_score(SCORE_FLOOR + 50.0 * tail_health["h_ts"]), 2),
        "operator_score": round(
            _clamp_score(SCORE_FLOOR + 50.0 * safety["h_safety"] * conduct["h_conduct"]), 2
        ),
    }


# ── Convenience: build RiskEvents from pipeline output ───────────────────────

def eli_event(
    violation_type: str,
    event_date: Any = None,
    source: str = "",
    reference: str = "",
) -> Optional[RiskEvent]:
    """
    Build an ELI RiskEvent from a §6.3 taxonomy enum string.

    Returns None for an unrecognized violation type rather than guessing a
    severity — the spec requires strict enumeration so that extraction drops
    are visible rather than silently scored. Callers should log the miss.
    """
    severity = ELI_TAXONOMY.get((violation_type or "").strip().upper())
    if severity is None:
        return None
    return RiskEvent(
        severity=severity,
        event_date=event_date,
        event_type=violation_type.strip().upper(),
        source=source,
        reference=reference,
    )
