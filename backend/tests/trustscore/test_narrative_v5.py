"""
Tests for TrustScore v5.0 narrative generation (§9).

The central guarantee is negative: generating a narrative must never change a
score, and must never fail a scoring run. Most of these tests exist to keep
that true under future edits.
"""

import asyncio
import copy
import json

import pytest

from src.trustscore import adapter_v5, narrative_v5
from src.trustscore.calculator_v5 import RiskEvent, Severity, calculate_trust_score


def _scored():
    """An operator/tail pair with a mixed evidence record, plus its score."""
    operator = adapter_v5.build_operator_data(
        operator_name="Jet Excellence",
        certificate_designator="RWAA",
        certificate_age_years=21.0,
        fleet_size=28,
        fleet_events=[
            {"event_type": "Accident", "injury_level": "Fatal", "event_date": "2024-08-20"},
            {"event_type": "faa_sdr", "sdr_severity": 20.0, "event_date": "2025-06-01"},
        ],
        ucc_filings=[{"status": "active", "filing_date": "2025-09-22", "file_number": "U1"}],
        tails_added_12m=10,
        tails_removed_12m=4,
            include_dot_orders=False, lookup_fleet_size=False,
        )
    tail = adapter_v5.build_tail_data(
        tail_number="N772XJ",
        aircraft_age_years=10.0,
        ownership_classification="leased",
        same_type_fleet_count=8,
        certificate_tenure_months=4.0,
    )
    return operator, tail, calculate_trust_score(operator, tail)


class _FakeClient:
    def __init__(self, text="Executive Summary\nTrustScore: 55 (Standard)"):
        self.text = text

    async def get_completion(self, prompt):
        return self.text


class _FailingClient:
    async def get_completion(self, prompt):
        raise RuntimeError("API unavailable")


# ── The guarantee ────────────────────────────────────────────────────────────

class TestNarrativeCannotAffectScore:
    def test_score_unchanged_with_no_client(self):
        operator, tail, result = _scored()
        before = copy.deepcopy(result)
        asyncio.run(narrative_v5.generate_narrative(operator, tail, result, llm_client=None))
        assert result == before

    def test_score_unchanged_when_llm_succeeds(self):
        operator, tail, result = _scored()
        before = copy.deepcopy(result)
        asyncio.run(
            narrative_v5.generate_narrative(operator, tail, result, llm_client=_FakeClient())
        )
        # generate_narrative returns its output; it does not mutate the input
        assert result["trust_score"] == before["trust_score"]
        assert result["fleet_score"] == before["fleet_score"]
        assert result["components"] == before["components"]

    def test_llm_failure_returns_none_without_raising(self):
        operator, tail, result = _scored()
        before = copy.deepcopy(result)
        output = asyncio.run(
            narrative_v5.generate_narrative(operator, tail, result, llm_client=_FailingClient())
        )
        assert output is None
        assert result == before

    def test_no_client_returns_none(self):
        operator, tail, result = _scored()
        assert asyncio.run(
            narrative_v5.generate_narrative(operator, tail, result, llm_client=None)
        ) is None

    def test_recomputing_after_narrative_gives_same_score(self):
        """Inputs must survive narrative generation unmodified."""
        operator, tail, result = _scored()
        asyncio.run(
            narrative_v5.generate_narrative(operator, tail, result, llm_client=_FakeClient())
        )
        assert calculate_trust_score(operator, tail)["trust_score"] == result["trust_score"]


# ── §9 Black Box Rule ────────────────────────────────────────────────────────

class TestBlackBoxRule:
    def test_payload_excludes_internal_components(self):
        operator, tail, result = _scored()
        payload = narrative_v5.build_audit_payload(operator, tail, result)
        blob = json.dumps(payload).lower()
        for forbidden in (
            "components", "h_safety", "h_conduct", "h_ts", "sro", "cro",
            "d_scale", "composite", "blended_health", "orf_base", "l_risk",
        ):
            assert forbidden not in blob

    def test_payload_excludes_severity_points(self):
        """Severity is a scoring coefficient; §9 forbids exposing point values."""
        operator, tail, result = _scored()
        payload = narrative_v5.build_audit_payload(operator, tail, result)
        assert "severity" not in json.dumps(payload).lower()

    def test_payload_retains_evidence_and_scores(self):
        operator, tail, result = _scored()
        payload = narrative_v5.build_audit_payload(operator, tail, result)
        assert payload["calculated_scores"]["trust_score"] == result["trust_score"]
        assert payload["certificate_designator"] == "RWAA"
        assert len(payload["audit_categories"]) == 6

    def test_leakage_guard_detects_forbidden_terms(self):
        assert narrative_v5.find_leakage("Hsafety was 0.77") == ["hsafety"]
        assert "multiplier" in narrative_v5.find_leakage("the multiplier applied")

    def test_leakage_guard_passes_clean_prose(self):
        clean = (
            "The operator maintains a 21-year certificate history with zero "
            "recorded enforcement actions in the FAA Document Index."
        )
        assert narrative_v5.find_leakage(clean) == []

    def test_leakage_is_reported_not_suppressed(self):
        operator, tail, result = _scored()
        output = asyncio.run(
            narrative_v5.generate_narrative(
                operator, tail, result, llm_client=_FakeClient("Hsafety drove this score.")
            )
        )
        assert output is not None
        assert "hsafety" in output["leakage"]


# ── Flag derivation ──────────────────────────────────────────────────────────

class TestFlagDerivation:
    def test_clean_operator_with_uningested_sources_is_grey_not_green(self):
        """
        An operator with no adverse findings is not thereby clean.

        Until §8 entity resolution lands, every lookup runs against a trade
        name, so "nothing found" may only mean "nothing found under the name we
        searched". Several sources (DOCINDEX liens, ASN latent risk, D085
        churn) are not ingested at all. Reporting GREEN here is the overclaim
        that let Red Wing Aeroplane — the specification's own example of a
        rebranded bad actor — score Pinnacle with six green flags.
        """
        operator = adapter_v5.build_operator_data(
            operator_name="Clean", certificate_designator="ABCD",
            certificate_age_years=25.0, fleet_size=30,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(
            tail_number="N1AA", aircraft_age_years=3.5,
            ownership_classification="exclusive", same_type_fleet_count=8,
            certificate_tenure_months=60.0,
        )
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        flags = {name: c["flag"] for name, c in payload["audit_categories"].items()}
        assert set(flags.values()) == {narrative_v5.GREY}

    def test_grey_never_overrides_an_adverse_finding(self):
        """Missing sources must not soften evidence that WAS found."""
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=20.0, fleet_size=10,
            fleet_events=[{"event_type": "Accident", "injury_level": "Fatal",
                           "event_date": "2025-01-01"}],
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="N1", same_type_fleet_count=5,
                                          certificate_tenure_months=24.0)
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        assert payload["audit_categories"]["flight_safety"]["flag"] == narrative_v5.RED

    def test_coverage_downgrade_only_touches_green(self):
        gaps = frozenset([adapter_v5.GAP_NAME_ANCHORED_LOOKUPS])
        assert narrative_v5._apply_coverage(
            narrative_v5.GREEN, "flight_safety", gaps) == narrative_v5.GREY
        assert narrative_v5._apply_coverage(
            narrative_v5.YELLOW, "flight_safety", gaps) == narrative_v5.YELLOW
        assert narrative_v5._apply_coverage(
            narrative_v5.RED, "flight_safety", gaps) == narrative_v5.RED

    def test_green_survives_when_nothing_is_missing(self):
        """A fully-evidenced category must still be able to read GREEN."""
        assert narrative_v5._apply_coverage(
            narrative_v5.GREEN, "maintenance_discipline", frozenset()
        ) == narrative_v5.GREEN

    def test_fatal_accident_forces_red_safety(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=20.0, fleet_size=10,
            fleet_events=[{"event_type": "Accident", "injury_level": "Fatal",
                           "event_date": "2025-01-01"}],
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="N1", same_type_fleet_count=5,
                                          certificate_tenure_months=24.0)
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        assert payload["audit_categories"]["flight_safety"]["flag"] == narrative_v5.RED

    def test_critical_violation_forces_red_commercial(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=20.0, fleet_size=10,
            watchdog_records=[{"violation_type": "FRAUD_OR_PONZI_SCHEME", "date": "2025-01-01"}],
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="N1", same_type_fleet_count=5,
                                          certificate_tenure_months=24.0)
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        assert payload["audit_categories"]["commercial_integrity"]["flag"] == narrative_v5.RED

    def test_active_tail_lien_forces_red_legal(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=20.0, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(
            tail_number="N1", same_type_fleet_count=5, certificate_tenure_months=24.0,
            tail_lien_records=[{"event_date": "2025-06-01"}],
        )
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        assert payload["audit_categories"]["legal_title"]["flag"] == narrative_v5.RED

    def test_orphan_fleet_type_yields_yellow_fulfillment(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=20.0, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="N1", same_type_fleet_count=1,
                                          certificate_tenure_months=24.0)
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        assert payload["audit_categories"]["flight_fulfillment"]["flag"] == narrative_v5.YELLOW

    def test_recent_onboarding_yields_yellow_asset_stability(self):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=20.0, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        tail = adapter_v5.build_tail_data(tail_number="N1", same_type_fleet_count=5,
                                          certificate_tenure_months=4.0)
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        assert payload["audit_categories"]["asset_stability"]["flag"] == narrative_v5.YELLOW


# ── Coverage gaps ────────────────────────────────────────────────────────────

class TestCoverageGaps:
    def test_gaps_are_passed_through_to_the_model(self):
        operator, tail, result = _scored()
        gaps = adapter_v5.missing_inputs(operator, tail)
        payload = narrative_v5.build_audit_payload(operator, tail, result, missing_inputs=gaps)
        assert payload["data_coverage_gaps"] == gaps

    def test_prompt_contains_the_payload(self):
        operator, tail, result = _scored()
        payload = narrative_v5.build_audit_payload(operator, tail, result)
        assert "RWAA" in narrative_v5.build_prompt(payload)

    def test_system_prompt_states_the_guardrails(self):
        assert "Zero Formula Leakage" in narrative_v5.SYSTEM_PROMPT
        assert "Strict Evidentiary Grounding" in narrative_v5.SYSTEM_PROMPT
