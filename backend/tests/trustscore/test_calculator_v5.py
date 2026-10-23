"""
Tests for the TrustScore v5.0 calculator.

These assert the properties the specification guarantees — the Slander Floor,
the non-compensatory conduct gate, square-root fleet normalization, the 5-year
half-life — rather than golden numbers. A refactor that preserves the spec
should keep these green; one that breaks a guarantee should fail loudly.

Section references are to "TrustScore Algorithm v5.0".
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from src.trustscore.calculator_v5 import (
    ELI_TAXONOMY,
    OperatorData,
    RiskEvent,
    Severity,
    TailData,
    calculate_churn_effective,
    calculate_confidence_score,
    calculate_conduct_health,
    calculate_d_scale,
    calculate_fleet_score,
    calculate_maintenance_health,
    calculate_ownership_modifier,
    calculate_recovery_modifier,
    calculate_safety_health,
    calculate_tenure_modifier,
    calculate_trust_score,
    decayed_sum,
    eli_event,
    get_score_tier,
)

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def _clean_operator(**overrides):
    """A mature certificate with no adverse history."""
    base = dict(
        certificate_designator="ABCD",
        operator_name="Clean Air",
        certificate_age_years=40.0,
        fleet_size=30,
    )
    base.update(overrides)
    return OperatorData(**base)


def _clean_tail(**overrides):
    """A peak-age, operator-owned airframe with deep sister-ship cover."""
    base = dict(
        tail_number="N1AA",
        aircraft_age_years=3.5,
        ownership_classification="exclusive",
        same_type_fleet_count=8,
        certificate_tenure_months=60.0,
    )
    base.update(overrides)
    return TailData(**base)


# ── §1.1 The Slander Floor ───────────────────────────────────────────────────

class TestSlanderFloor:
    def test_pristine_operator_reaches_ceiling(self):
        result = calculate_trust_score(_clean_operator(), _clean_tail(), now=NOW)
        assert result["trust_score"] == 100.0
        assert result["tier"] == "Pinnacle"

    def test_catastrophic_record_approaches_but_never_crosses_floor(self):
        """§1.2: the composite drives asymptotically toward the floor."""
        operator = _clean_operator(
            fleet_size=5,
            fleet_accident_events=[RiskEvent(Severity.FATAL_ACCIDENT, "2026-01-01")] * 12,
            legal_events=[eli_event("FRAUD_OR_PONZI_SCHEME", "2026-01-01")] * 12,
        )
        tail = _clean_tail(
            aircraft_age_years=25.0,
            ownership_classification="leased",
            same_type_fleet_count=1,
            certificate_tenure_months=1.0,
            tail_accident_events=[RiskEvent(Severity.FATAL_ACCIDENT, "2026-01-01")] * 6,
        )
        score = calculate_trust_score(operator, tail, now=NOW)["trust_score"]
        assert score == 50.0

    @pytest.mark.parametrize("event_count", [0, 1, 5, 25, 100])
    def test_score_always_within_bounds(self, event_count):
        operator = _clean_operator(
            fleet_size=3,
            fleet_accident_events=[RiskEvent(Severity.FATAL_ACCIDENT, "2026-01-01")] * event_count,
            legal_events=[eli_event("FRAUD_OR_PONZI_SCHEME", "2026-01-01")] * event_count,
        )
        result = calculate_trust_score(operator, _clean_tail(), now=NOW)
        assert 50.0 <= result["trust_score"] <= 100.0
        assert 50.0 <= result["fleet_score"] <= 100.0


# ── §1.2 Non-compensatory conduct gate ───────────────────────────────────────

class TestConductGate:
    def test_clean_airframe_cannot_mask_fraudulent_certificate(self):
        clean = calculate_trust_score(_clean_operator(), _clean_tail(), now=NOW)
        gated = calculate_trust_score(
            _clean_operator(legal_events=[eli_event("FRAUD_OR_PONZI_SCHEME", "2026-06-01")] * 3),
            _clean_tail(),
            now=NOW,
        )
        assert gated["trust_score"] < clean["trust_score"] - 20

    def test_conduct_multiplies_rather_than_averages(self):
        """A multiplicative gate must bite harder than any additive term could."""
        operator = _clean_operator(legal_events=[eli_event("FRAUD_OR_PONZI_SCHEME", "2026-10-01")] * 4)
        components = calculate_trust_score(operator, _clean_tail(), now=NOW)["components"]
        assert components["h_conduct"] < 0.05


# ── §3 Confidence Score ──────────────────────────────────────────────────────

class TestConfidenceScore:
    def test_new_certificate_is_heavily_damped(self):
        assert calculate_confidence_score(_clean_operator(certificate_age_years=0.5)) < 0.25

    def test_mature_certificate_approaches_one(self):
        assert calculate_confidence_score(_clean_operator(certificate_age_years=40.0)) > 0.99

    def test_organic_growth_under_25_percent_is_free(self):
        operator = _clean_operator(fleet_size=100, tails_added_12m=25, tails_removed_12m=0)
        assert calculate_churn_effective(operator) == 0.0

    def test_expansion_above_allowance_is_weighted_half(self):
        operator = _clean_operator(fleet_size=100, tails_added_12m=45, tails_removed_12m=0)
        # (0.45 - 0.25) * 0.50
        assert calculate_churn_effective(operator) == pytest.approx(0.10)

    def test_contraction_is_weighted_fully(self):
        operator = _clean_operator(fleet_size=100, tails_added_12m=0, tails_removed_12m=20)
        assert calculate_churn_effective(operator) == pytest.approx(0.20)

    def test_churn_is_capped(self):
        operator = _clean_operator(fleet_size=10, tails_added_12m=50, tails_removed_12m=50)
        assert calculate_churn_effective(operator) == 0.65

    def test_zero_baseline_does_not_divide_by_zero(self):
        operator = _clean_operator(fleet_size=0, tails_added_12m=5, tails_removed_12m=5)
        assert calculate_churn_effective(operator) == 0.0


# ── §4.1 Safety Health ───────────────────────────────────────────────────────

class TestSafetyHealth:
    def test_fleet_exposure_uses_square_root_not_linear(self):
        """A 100x fleet must divide risk by 10, not 100 (§4.1)."""
        def orf(size):
            operator = _clean_operator(
                certificate_age_years=10.0,
                fleet_size=size,
                fleet_accident_events=[RiskEvent(Severity.FATAL_ACCIDENT, "2026-01-01")],
            )
            return calculate_safety_health(operator, now=NOW)["orf_base"]

        assert orf(1) / orf(100) == pytest.approx(10.0, abs=0.01)

    def test_damping_is_floored_at_fifty_percent(self):
        operator = _clean_operator(fleet_size=10_000, certificate_age_years=100.0)
        assert calculate_d_scale(operator) == 0.5

    def test_damping_is_one_for_a_brand_new_single_tail(self):
        operator = _clean_operator(fleet_size=0, certificate_age_years=0.0)
        assert calculate_d_scale(operator) == pytest.approx(1.0)

    def test_latent_risk_is_capped_at_fifteen(self):
        operator = _clean_operator(
            latent_risk_events=[RiskEvent(Severity.SERIOUS_INCIDENT, "2026-10-01")] * 20
        )
        assert calculate_safety_health(operator, now=NOW)["l_risk"] == 15.0

    def test_latent_risk_bypasses_damping(self):
        """Lrisk is added after Dscale, so scale gives no discount on it (§4.1)."""
        operator = _clean_operator(
            fleet_size=500,
            latent_risk_events=[RiskEvent(Severity.MINOR_LATENT, "2026-10-08")],
        )
        components = calculate_safety_health(operator, now=NOW)
        assert components["sro"] == pytest.approx(components["l_risk"])


# ── §4.2 Conduct Health ──────────────────────────────────────────────────────

class TestConductHealth:
    def test_deferred_telemetry_defaults_to_zero(self):
        """Source 9 is deferred: Cro == ELI in the v5.0 build."""
        operator = _clean_operator(legal_events=[eli_event("DOT_OACP_CONSENT_ORDER", "2026-10-08")])
        components = calculate_conduct_health(operator, now=NOW)
        assert components["bes_penalty"] == 0.0
        assert components["ffr"] == 0.0
        assert components["cro"] == pytest.approx(components["eli"])

    def test_telemetry_fields_are_wired_for_future_use(self):
        """The fields must already affect Cro so future ingestion needs no refactor."""
        operator = _clean_operator(bes_penalty=10.0, ffr=5.0)
        assert calculate_conduct_health(operator, now=NOW)["cro"] == pytest.approx(15.0)

    def test_clean_certificate_has_full_conduct_health(self):
        assert calculate_conduct_health(_clean_operator(), now=NOW)["h_conduct"] == 1.0


# ── §5 Tail Health ───────────────────────────────────────────────────────────

class TestTailHealth:
    def test_maintenance_curve_peaks_at_three_and_a_half_years(self):
        assert calculate_maintenance_health(3.5) == 1.0

    def test_new_airframe_takes_teething_penalty(self):
        assert calculate_maintenance_health(0.0) == pytest.approx(0.9755, abs=0.0001)

    def test_maintenance_floor_is_reached_and_held(self):
        assert calculate_maintenance_health(23.5) == pytest.approx(0.20, abs=0.001)
        assert calculate_maintenance_health(60.0) == 0.20

    @pytest.mark.parametrize(
        "classification,expected",
        [("exclusive", 1.00), ("holding_entity", 1.00), ("fractional", 0.95),
         ("leased", 0.90), ("managed", 0.90), ("Leased / Third-Party Managed", 0.90)],
    )
    def test_ownership_modifiers(self, classification, expected):
        assert calculate_ownership_modifier(classification) == expected

    def test_unknown_ownership_is_conservative(self):
        """An unmapped value must not silently score as operator-owned."""
        assert calculate_ownership_modifier("something unrecognized") == 0.90

    @pytest.mark.parametrize("count,expected", [(8, 1.00), (5, 1.00), (4, 0.96), (2, 0.96), (1, 0.92), (0, 0.92)])
    def test_recovery_modifiers(self, count, expected):
        assert calculate_recovery_modifier(count) == expected

    def test_tenure_modifier_boundary(self):
        assert calculate_tenure_modifier(6.0) == 1.00
        assert calculate_tenure_modifier(5.9) == 0.95

    def test_tail_sdr_penalty_is_capped(self):
        tail = _clean_tail(tail_sdr_events=[RiskEvent(Severity.SDR_IFSD, "2026-10-08")] * 10)
        from src.trustscore.calculator_v5 import calculate_tail_health
        assert calculate_tail_health(tail, now=NOW)["sdr_penalty"] == 30.0

    def test_tail_accidents_carry_five_times_multiplier(self):
        tail = _clean_tail(tail_accident_events=[RiskEvent(Severity.SUBSTANTIAL_DAMAGE, NOW)])
        from src.trustscore.calculator_v5 import calculate_tail_health
        assert calculate_tail_health(tail, now=NOW)["iht"] == pytest.approx(125.0)

    def test_tail_lien_is_charged_on_top_of_certificate_eli(self):
        """§5.3 specifies this double charge; it is not a bug."""
        operator = _clean_operator(
            legal_events=[eli_event("ACTIVE_MECHANICS_OR_TAX_LIEN", "2026-01-01")]
        )
        without = calculate_trust_score(operator, _clean_tail(), now=NOW)["trust_score"]
        with_lien = calculate_trust_score(
            operator, _clean_tail(tail_lien_events=[RiskEvent(0.0, "2026-01-01")]), now=NOW
        )["trust_score"]
        assert with_lien < without


# ── §6 Severity schedule ─────────────────────────────────────────────────────

class TestSeveritySchedule:
    def test_physical_safety_values(self):
        assert Severity.FATAL_ACCIDENT == 50
        assert Severity.SUBSTANTIAL_DAMAGE == 25
        assert Severity.SERIOUS_INCIDENT == 15
        assert Severity.MAJOR_INCIDENT == 10
        assert Severity.MINOR_LATENT == 5

    def test_maintenance_values(self):
        assert Severity.SDR_IFSD == 20
        assert Severity.SDR_ABORTED_TAKEOFF == 15
        assert Severity.SDR_CABIN_SMOKE == 10
        assert Severity.SDR_UNSCHEDULED_LANDING == 5

    @pytest.mark.parametrize(
        "violation,expected",
        [("FRAUD_OR_PONZI_SCHEME", 35), ("BREACH_OF_CONTRACT_FUNDS_WITHHELD", 35),
         ("ILLEGAL_CHARTER_OR_SAFETY_RETALIATION", 35), ("VENDOR_DEFAULT_OR_LABOR_STRIKE", 25),
         ("DOT_OACP_CONSENT_ORDER", 25), ("ACTIVE_MECHANICS_OR_TAX_LIEN", 20),
         ("SYSTEMIC_DISPATCH_DROPS_OR_FLEET_GROUNDING", 20),
         ("UNAUTHORIZED_DBA_OR_DECEPTIVE_MARKETING", 15)],
    )
    def test_eli_taxonomy_is_complete(self, violation, expected):
        assert ELI_TAXONOMY[violation] == expected
        assert eli_event(violation).severity == expected

    def test_unknown_violation_returns_none_rather_than_guessing(self):
        """Strict enumeration: extraction drops must be visible, not silently scored."""
        assert eli_event("NOT_IN_THE_TAXONOMY") is None
        assert eli_event("") is None


# ── Decay ────────────────────────────────────────────────────────────────────

class TestDecay:
    def test_five_year_half_life(self):
        event = RiskEvent(50.0, NOW - timedelta(days=int(365.25 * 5)))
        assert decayed_sum([event], NOW) == pytest.approx(25.0, abs=0.05)

    def test_undated_events_are_not_discounted(self):
        assert decayed_sum([RiskEvent(50.0, None)], NOW) == 50.0

    def test_future_dates_are_clamped(self):
        """A bad timestamp must not inflate an event above its raw severity."""
        assert decayed_sum([RiskEvent(50.0, NOW + timedelta(days=3650))], NOW) == 50.0

    def test_unparseable_date_falls_back_to_full_weight(self):
        assert decayed_sum([RiskEvent(50.0, "not a date")], NOW) == 50.0

    @pytest.mark.parametrize("fmt", ["2024-03-15", "03/15/2024", "15-Mar-2024", "20240315"])
    def test_accepts_common_date_formats(self, fmt):
        assert decayed_sum([RiskEvent(50.0, fmt)], NOW) < 50.0

    def test_empty_event_list(self):
        assert decayed_sum([], NOW) == 0.0


# ── §2.1 Tiers ───────────────────────────────────────────────────────────────

class TestTiers:
    @pytest.mark.parametrize(
        "score,tier",
        [(100, "Pinnacle"), (90, "Pinnacle"), (89, "Premier"), (80, "Premier"),
         (79, "Benchmark"), (70, "Benchmark"), (69, "Standard"), (50, "Standard")],
    )
    def test_tier_boundaries(self, score, tier):
        assert get_score_tier(score) == tier


# ── §2 Composite ─────────────────────────────────────────────────────────────

class TestComposite:
    def test_fleet_score_ignores_tail_specifics(self):
        """FleetScore is certificate-level: a bad airframe must not move it."""
        operator = _clean_operator()
        good = calculate_trust_score(operator, _clean_tail(), now=NOW)["fleet_score"]
        bad = calculate_trust_score(
            operator,
            _clean_tail(aircraft_age_years=30.0, same_type_fleet_count=1),
            now=NOW,
        )["fleet_score"]
        assert good == bad

    def test_tail_weighting_dominates_safety(self):
        """§2 weights tail health 0.65 against certificate safety 0.35."""
        operator = _clean_operator()
        degraded_tail = calculate_trust_score(
            operator, _clean_tail(aircraft_age_years=30.0), now=NOW
        )["trust_score"]
        degraded_safety = calculate_trust_score(
            _clean_operator(
                fleet_accident_events=[RiskEvent(Severity.SERIOUS_INCIDENT, "2026-10-01")]
            ),
            _clean_tail(),
            now=NOW,
        )["trust_score"]
        assert degraded_tail < degraded_safety

    def test_result_exposes_version_and_formula(self):
        result = calculate_trust_score(_clean_operator(), _clean_tail(), now=NOW)
        assert result["algorithm_version"] == "5.0"
        assert "Hconduct" in result["formula"]

    def test_components_present_for_internal_audit(self):
        """§9 forbids exposing these to clients, but they must exist internally."""
        components = calculate_trust_score(_clean_operator(), _clean_tail(), now=NOW)["components"]
        for key in ("h_safety", "h_conduct", "h_ts", "cs", "sro", "cro"):
            assert key in components
