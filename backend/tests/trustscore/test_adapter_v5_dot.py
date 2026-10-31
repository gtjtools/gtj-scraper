"""
Tests for DOT OACP enforcement orders feeding ELI (Pipeline 8, §6.3).

Every test passes `dot_orders` explicitly or `include_dot_orders=False, lookup_fleet_size=False`. None
of them touch a database: `build_operator_data` performs a live lookup by
default, and a test that forgets to disable it would query production.
"""

import pytest

from src.trustscore import adapter_v5
from src.trustscore.calculator_v5 import Severity, calculate_trust_score


class _Row:
    """Stand-in for a DOTEnforcementOrder ORM row."""

    def __init__(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)


def _operator(**overrides):
    base = dict(
        operator_name="Test Air",
        certificate_age_years=20.0,
        fleet_size=10,
        include_dot_orders=False, lookup_fleet_size=False,
    )
    base.update(overrides)
    return adapter_v5.build_operator_data(**base)


def _tail():
    return adapter_v5.build_tail_data(
        tail_number="N1AA", same_type_fleet_count=5, certificate_tenure_months=24.0
    )


# ── Order-type filtering ─────────────────────────────────────────────────────

class TestOrderTypeFiltering:
    @pytest.mark.parametrize("order_type", ["consent_order", "settlement", "enforcement_action"])
    def test_adverse_order_types_score(self, order_type):
        events = adapter_v5.dot_orders_to_legal_events(
            [{"order_type": order_type, "effective_date": "2025-06-01"}]
        )
        assert len(events) == 1
        assert events[0].severity == Severity.ELI_MAJOR

    @pytest.mark.parametrize("order_type", ["dismissal", "unknown", "", None, "something_else"])
    def test_non_adverse_order_types_are_skipped(self, order_type):
        """A dismissed complaint is not a violation and must not be penalized."""
        assert adapter_v5.dot_orders_to_legal_events(
            [{"order_type": order_type, "effective_date": "2025-06-01"}]
        ) == []

    def test_mixed_batch_scores_only_adverse(self):
        orders = [
            {"order_type": "consent_order", "effective_date": "2025-06-01"},
            {"order_type": "dismissal", "effective_date": "2025-05-01"},
            {"order_type": "settlement", "effective_date": "2025-04-01"},
            {"order_type": "unknown", "effective_date": "2025-03-01"},
        ]
        assert len(adapter_v5.dot_orders_to_legal_events(orders)) == 2

    def test_case_and_whitespace_tolerant(self):
        assert len(adapter_v5.dot_orders_to_legal_events(
            [{"order_type": "  Consent_Order  ", "effective_date": "2025-06-01"}]
        )) == 1


# ── Input shapes ─────────────────────────────────────────────────────────────

class TestInputShapes:
    def test_accepts_orm_rows(self):
        rows = [
            _Row(order_type="consent_order", effective_date="2025-06-01", order_number="R1"),
            _Row(order_type="dismissal", effective_date="2025-06-01", order_number="R2"),
        ]
        events = adapter_v5.dot_orders_to_legal_events(rows)
        assert len(events) == 1
        assert events[0].reference == "R1"

    def test_accepts_dicts(self):
        events = adapter_v5.dot_orders_to_legal_events(
            [{"order_type": "consent_order", "effective_date": "2025-06-01", "order_number": "D1"}]
        )
        assert events[0].reference == "D1"

    def test_empty_and_none_are_safe(self):
        assert adapter_v5.dot_orders_to_legal_events([]) == []
        assert adapter_v5.dot_orders_to_legal_events(None) == []

    def test_missing_date_still_scores(self):
        """An undated federal order is not less real for lacking a date."""
        events = adapter_v5.dot_orders_to_legal_events(
            [{"order_type": "consent_order", "effective_date": None}]
        )
        assert len(events) == 1
        assert events[0].event_date is None

    def test_missing_order_number_is_tolerated(self):
        events = adapter_v5.dot_orders_to_legal_events(
            [{"order_type": "consent_order", "effective_date": "2025-06-01"}]
        )
        assert events[0].reference == ""


# ── Scoring impact ───────────────────────────────────────────────────────────

class TestScoringImpact:
    def test_adverse_orders_lower_the_score(self):
        clean = calculate_trust_score(_operator(), _tail())["trust_score"]
        penalized = calculate_trust_score(
            _operator(dot_orders=[
                {"order_type": "consent_order", "effective_date": "2025-06-01"},
                {"order_type": "settlement", "effective_date": "2025-03-01"},
            ]),
            _tail(),
        )["trust_score"]
        assert penalized < clean

    def test_dismissal_only_operator_is_not_penalized(self):
        clean = calculate_trust_score(_operator(), _tail())["trust_score"]
        dismissed = calculate_trust_score(
            _operator(dot_orders=[{"order_type": "dismissal", "effective_date": "2025-01-01"}]),
            _tail(),
        )["trust_score"]
        assert dismissed == clean

    def test_orders_decay_over_time(self):
        recent = calculate_trust_score(
            _operator(dot_orders=[{"order_type": "consent_order", "effective_date": "2026-09-01"}]),
            _tail(),
        )["trust_score"]
        old = calculate_trust_score(
            _operator(dot_orders=[{"order_type": "consent_order", "effective_date": "2010-01-01"}]),
            _tail(),
        )["trust_score"]
        assert old > recent

    def test_orders_land_in_conduct_not_safety(self):
        """DOT orders are commercial conduct; they must not move Hsafety."""
        baseline = calculate_trust_score(_operator(), _tail())["components"]
        with_orders = calculate_trust_score(
            _operator(dot_orders=[{"order_type": "consent_order", "effective_date": "2025-06-01"}]),
            _tail(),
        )["components"]
        assert with_orders["h_safety"] == baseline["h_safety"]
        assert with_orders["h_conduct"] < baseline["h_conduct"]


# ── Lookup plumbing ──────────────────────────────────────────────────────────

class TestLookup:
    def test_empty_name_short_circuits_without_a_query(self):
        """Must not open a session for a name that cannot match."""
        def explode():
            raise AssertionError("session should not have been created")

        assert adapter_v5.fetch_dot_orders_for_operator("", db_session_factory=explode) == []

    def test_lookup_failure_returns_empty_rather_than_raising(self):
        def failing_factory():
            raise RuntimeError("database unavailable")

        assert adapter_v5.fetch_dot_orders_for_operator(
            "Test Air", db_session_factory=failing_factory
        ) == []

    def test_include_dot_orders_false_skips_the_lookup(self):
        """Guards against tests and offline callers hitting a live database."""
        operator = adapter_v5.build_operator_data(
            operator_name="Test Air",
            certificate_age_years=20.0,
            fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        assert operator.legal_events == []

    def test_explicit_orders_skip_the_lookup(self):
        operator = adapter_v5.build_operator_data(
            operator_name="Test Air",
            certificate_age_years=20.0,
            fleet_size=10,
            dot_orders=[{"order_type": "consent_order", "effective_date": "2025-06-01"}],
        )
        assert len(operator.legal_events) == 1


# ── Name normalization agreement ─────────────────────────────────────────────

class TestNormalizationAgreement:
    @pytest.mark.parametrize(
        "raw,expected",
        [("Aira Aviation LLC", "AIRA AVIATION"),
         ("JET EXCELLENCE, INC.", "JET EXCELLENCE"),
         ("Red Wing Aviation Co.", "RED WING AVIATION"),
         ("Bellair  Ltd", "BELLAIR"),
         ("", "")],
    )
    def test_matches_ingestion_pipeline_normalization(self, raw, expected):
        """
        Must stay identical to faa_enforcement_service.normalize_operator_name,
        which populates operator_name_normalized. If these drift, every
        score-time lookup silently misses.
        """
        assert adapter_v5.normalize_operator_name(raw) == expected


# ── Coverage reporting ───────────────────────────────────────────────────────

class TestCoverageReporting:
    def test_missing_dot_coverage_is_reported(self):
        gaps = adapter_v5.missing_inputs(_operator(), _tail())
        assert any("DOT OACP" in gap for gap in gaps)

    def test_matched_orders_clear_the_gap(self):
        operator = _operator(
            dot_orders=[{"order_type": "consent_order", "effective_date": "2025-06-01"}]
        )
        gaps = adapter_v5.missing_inputs(operator, _tail())
        assert not any("DOT OACP" in gap for gap in gaps)


# ── Operator-level scoring (no airframe) ─────────────────────────────────────

class TestNeutralTail:
    def test_empty_tail_number_yields_fully_neutral_modifiers(self):
        """
        Operator-level scoring must not penalize a nonexistent airframe.

        The dataclass defaults are NOT neutral — age 0 gives Mht 0.9755 and
        Vtype 1 gives Rtype 0.92 — so without this special case every
        operator-level score carried a ~10% phantom penalty.
        """
        from src.trustscore.calculator_v5 import calculate_tail_health

        health = calculate_tail_health(adapter_v5.build_tail_data(tail_number=""))
        assert health["mht"] == 1.0
        assert health["ost"] == 1.0
        assert health["rtype"] == 1.0
        assert health["ttenure"] == 1.0
        assert health["h_ts"] == 1.0

    def test_named_tail_still_uses_real_modifiers(self):
        from src.trustscore.calculator_v5 import calculate_tail_health

        health = calculate_tail_health(
            adapter_v5.build_tail_data(tail_number="N1AA", aircraft_age_years=20.0,
                                       same_type_fleet_count=1)
        )
        assert health["mht"] < 1.0
        assert health["rtype"] == 0.92


# ── Fleet size (Vf) ──────────────────────────────────────────────────────────

class TestFleetSize:
    def test_explicit_fleet_size_skips_the_lookup(self):
        def explode():
            raise AssertionError("lookup should not have run")

        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=10.0, fleet_size=42,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        assert operator.fleet_size == 42

    def test_lookup_disabled_defaults_to_zero(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=10.0,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        assert operator.fleet_size == 0

    def test_empty_name_returns_zero_without_a_query(self):
        def explode():
            raise AssertionError("session should not have been created")

        assert adapter_v5.fetch_fleet_size("", db_session_factory=explode) == 0

    def test_lookup_failure_returns_zero_rather_than_raising(self):
        def failing():
            raise RuntimeError("database unavailable")

        assert adapter_v5.fetch_fleet_size("X", db_session_factory=failing) == 0

    def test_larger_fleet_dilutes_identical_risk(self):
        """§4.1: risk is normalized by MAX(1, SQRT(Vf))."""
        from src.trustscore.calculator_v5 import calculate_trust_score

        events = [{"event_type": "Accident", "injury_level": "Fatal",
                   "event_date": "2025-01-01"}]
        scores = []
        for size in (1, 25, 100):
            operator = adapter_v5.build_operator_data(
                operator_name="X", certificate_age_years=20.0, fleet_size=size,
                fleet_events=events, include_dot_orders=False, lookup_fleet_size=False,
            )
            scores.append(calculate_trust_score(
                operator, adapter_v5.build_tail_data(tail_number="")
            )["trust_score"])
        assert scores[0] < scores[1] < scores[2]


# ── Age_cert provenance ──────────────────────────────────────────────────────

class TestCertificateAgeProvenance:
    """
    §3 defines Agecert as years since original certificate issuance. No ingested
    source carries that date, so callers supply either business registration or
    a hardcoded fallback. Both look like a real number to the calculator, which
    let an invented 10.0 prop up Cs on operators nobody could date.
    """

    def test_estimated_age_raises_the_gap(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=10.0,
            certificate_age_is_estimated=True, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="")
        assert adapter_v5.GAP_CERTIFICATE_AGE in adapter_v5.missing_input_keys(operator, tail)

    def test_observed_age_does_not(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=33.9,
            certificate_age_is_estimated=False, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="")
        assert adapter_v5.GAP_CERTIFICATE_AGE not in adapter_v5.missing_input_keys(operator, tail)

    def test_zero_age_still_raises_it(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=0.0,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="")
        assert adapter_v5.GAP_CERTIFICATE_AGE in adapter_v5.missing_input_keys(operator, tail)

    def test_the_flag_does_not_change_the_score(self):
        """Disclosure only — the arithmetic must be untouched."""
        from src.trustscore.calculator_v5 import calculate_trust_score

        def score(estimated):
            operator = adapter_v5.build_operator_data(
                operator_name="X", certificate_age_years=10.0,
                certificate_age_is_estimated=estimated, fleet_size=10,
                include_dot_orders=False, lookup_fleet_size=False,
            )
            return calculate_trust_score(
                operator, adapter_v5.build_tail_data(tail_number="")
            )["trust_score"]

        assert score(True) == score(False)

    def test_prose_names_the_estimate(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=10.0,
            certificate_age_is_estimated=True, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="")
        gaps = " ".join(adapter_v5.missing_inputs(operator, tail))
        assert "estimate" in gaps and "issuance" in gaps
