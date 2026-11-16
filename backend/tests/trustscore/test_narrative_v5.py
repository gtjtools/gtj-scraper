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
    def test_unresolvable_operator_with_no_sources_is_grey(self):
        """
        GREY requires TOTAL blindness in a category, not merely a gap.

        This previously asserted that a clean operator reads GREY in all six
        categories, on the reasoning that lookups ran against a trade name and
        several feeds were un-ingested. §8 entity resolution has since shipped,
        and the blanket reading was itself an overclaim in the other direction:
        it made "we looked and found nothing" indistinguishable from "we could
        not look", so a well-run operator could never earn a clean flag.

        Here NOTHING was consulted — no fleet count, no DOT, no tail, no
        certificate age — so GREY is the honest answer for every category that
        has a gating source.
        """
        operator = adapter_v5.build_operator_data(
            operator_name="Opaque",
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )
        tail = adapter_v5.build_tail_data(
            tail_number="N1AA", lookup_liens=False,
        )
        operator.safety_sources_queried = False
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        flags = {name: c["flag"] for name, c in payload["audit_categories"].items()}
        for category in ("commercial_integrity", "flight_safety", "legal_title"):
            assert flags[category] == narrative_v5.GREY, category

        # asset_stability is YELLOW rather than GREY: with no certificate age
        # the raw flag is already adverse (a sub-3-year certificate is a real
        # finding), and coverage never softens a non-GREEN verdict.
        assert flags["asset_stability"] == narrative_v5.YELLOW

    def test_queried_and_clean_operator_is_green_not_grey(self):
        """
        The regression this spec change exists to prevent.

        A long-established operator whose sources were all searched and came
        back clean must read GREEN. Zero churn is stable retention; an empty
        DOCINDEX result for a searched tail is clear title; no DOT match is a
        clean regulatory record. Each is a favourable finding, and reporting
        them as "not assessed" told the broker nothing and penalised the
        operators who had earned the clean result.
        """
        operator = adapter_v5.build_operator_data(
            operator_name="Clean", certificate_designator="ABCD",
            certificate_age_years=25.0, fleet_size=30,
            tails_added_12m=0, tails_removed_12m=0,
            include_dot_orders=True, lookup_fleet_size=False, lookup_churn=False,
        )
        operator.lookups_certificate_anchored = True
        tail = adapter_v5.build_tail_data(
            tail_number="N1AA", aircraft_age_years=3.5,
            ownership_classification="exclusive", same_type_fleet_count=8,
            certificate_tenure_months=60.0,
            tail_lien_records=[], lookup_liens=False, ownership_observed=True,
        )
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        flags = {name: c["flag"] for name, c in payload["audit_categories"].items()}
        assert set(flags.values()) == {narrative_v5.GREEN}, flags

        # The nil returns must be offered to the narrative as positives, or the
        # model has nothing affirmative to cite.
        assert payload["verified_clean_searches"], "clean searches must be surfaced"

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
        """An adverse verdict is never softened by a coverage gap."""
        gaps = frozenset([adapter_v5.GAP_SAFETY_SOURCES])
        assert narrative_v5._apply_coverage(
            narrative_v5.GREEN, "flight_safety", gaps) == narrative_v5.GREY
        assert narrative_v5._apply_coverage(
            narrative_v5.YELLOW, "flight_safety", gaps) == narrative_v5.YELLOW
        assert narrative_v5._apply_coverage(
            narrative_v5.RED, "flight_safety", gaps) == narrative_v5.RED

    def test_name_gap_alone_does_not_grey_out_airframe_evidence(self):
        """
        §8 name resolution is irrelevant to N-number-keyed evidence.

        NTSB, AIDS and SDRS records attach to the registration, which is
        immutable and was searched directly, so a clean airframe history stands
        regardless of what the operator currently calls itself. Applying the
        name gap to all six categories (the previous behaviour) greyed out
        findings that the operator's name had no bearing on.
        """
        gaps = frozenset([adapter_v5.GAP_NAME_ANCHORED_LOOKUPS,
                          adapter_v5.GAP_CERTIFICATE_UNRESOLVED])
        assert narrative_v5._apply_coverage(
            narrative_v5.GREEN, "flight_safety", gaps) == narrative_v5.GREEN
        assert narrative_v5._apply_coverage(
            narrative_v5.GREEN, "maintenance_discipline", gaps) == narrative_v5.GREEN
        # Entity-keyed categories still go GREY: those records are filed under
        # a name, and we could not establish which names to search.
        assert narrative_v5._apply_coverage(
            narrative_v5.GREEN, "commercial_integrity", gaps) == narrative_v5.GREY
        assert narrative_v5._apply_coverage(
            narrative_v5.GREEN, "legal_title", gaps) == narrative_v5.GREY

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

    def _legal_flag(self, tail_lien_records):
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_designator="ABCD",
            certificate_age_years=20.0, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False,
        )
        # legal_title is entity-keyed, so an unresolved operator greys it out
        # regardless of the liens. Resolve it here to isolate the tier logic.
        operator.lookups_certificate_anchored = True
        tail = adapter_v5.build_tail_data(
            tail_number="N1", same_type_fleet_count=5, certificate_tenure_months=24.0,
            tail_lien_records=tail_lien_records, ownership_observed=True,
        )
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        return payload["audit_categories"]["legal_title"]["flag"]

    def test_material_tail_lien_yields_yellow_legal(self):
        """
        §2B: an untiered or unclassifiable filing is material, not crippling.

        This asserted RED for ANY lien. Filing count is a poor risk proxy —
        that rule ranked a fleet carrying routine bank financings alongside one
        carrying a tax levy — so severity now drives the flag.
        """
        assert self._legal_flag(
            [{"event_date": "2025-06-01"}]
        ) == narrative_v5.YELLOW

    def test_crippling_lien_forces_red_legal_on_one_filing(self):
        """A single tax levy is enough: the claimant can ground the aircraft."""
        assert self._legal_flag([
            {"event_date": "2025-06-01", "doc_type": "S/A",
             "party": "INTERNAL REVENUE SERVICE"},
        ]) == narrative_v5.RED

    def test_routine_financing_does_not_move_the_flag(self):
        """
        §2B: many small bank/lessor filings must not read as distress.

        A recorded loan or lease is what a financed aircraft looks like.
        """
        assert self._legal_flag([
            {"event_date": "2025-06-01", "doc_type": "S/A",
             "party": "FIRST FARMERS BANK & TRUST"},
            {"event_date": "2025-03-01", "doc_type": "S/A",
             "party": "NBH BANK"},
            {"event_date": "2024-11-01", "doc_type": "S/A",
             "party": "DYNAMIC AVLEASE INC"},
        ]) == narrative_v5.GREEN

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


class TestFlagDecay:
    """
    A flag must agree with the score it accompanies.

    §4.1 decays severity on a five-year half-life, so Hsafety forgets an old
    event. The flags did not, so N722BD showed RED flight safety on a 1988
    accident while Hsafety read 0.9988 — a ~0.1% deduction presented to a
    broker as a current hazard.
    """

    def _operator(self, year, severity):
        from src.trustscore.calculator_v5 import OperatorData, RiskEvent

        return OperatorData(
            certificate_designator="BFYA", operator_name="X",
            certificate_age_years=33.9, fleet_size=5,
            fleet_accident_events=[RiskEvent(
                severity=float(severity), event_date=f"{year}-08-25",
                event_type="accident", source="NTSB", reference=f"X{year}",
            )],
        )

    def _tail(self):
        from src.trustscore.calculator_v5 import TailData
        return TailData(tail_number="N722BD")

    def test_recent_serious_accident_is_red(self):
        from src.trustscore.calculator_v5 import Severity

        flag = narrative_v5._flag_flight_safety(
            self._operator(2024, Severity.SUBSTANTIAL_DAMAGE), self._tail()
        )
        assert flag == narrative_v5.RED

    def test_decades_old_accident_is_not_red(self):
        """The 1988 case. Yellow, not red — and never green."""
        from src.trustscore.calculator_v5 import Severity

        flag = narrative_v5._flag_flight_safety(
            self._operator(1988, Severity.SUBSTANTIAL_DAMAGE), self._tail()
        )
        assert flag == narrative_v5.YELLOW

    def test_old_event_is_never_green(self):
        """
        A decayed finding is disclosed, not erased. GREEN would claim the
        operator has no accident on record, which is false.
        """
        from src.trustscore.calculator_v5 import Severity

        for year in (1988, 2000, 2010):
            flag = narrative_v5._flag_flight_safety(
                self._operator(year, Severity.FATAL_ACCIDENT), self._tail()
            )
            assert flag != narrative_v5.GREEN

    def test_no_events_is_green(self):
        from src.trustscore.calculator_v5 import OperatorData

        flag = narrative_v5._flag_flight_safety(
            OperatorData(certificate_designator="B", operator_name="X",
                         certificate_age_years=10.0, fleet_size=5),
            self._tail(),
        )
        assert flag == narrative_v5.GREEN

    def test_severity_still_matters_independently_of_recency(self):
        """A recent but minor incident must not reach RED."""
        from src.trustscore.calculator_v5 import Severity

        flag = narrative_v5._flag_flight_safety(
            self._operator(2026, Severity.MAJOR_INCIDENT), self._tail()
        )
        assert flag == narrative_v5.YELLOW

    def test_threshold_is_two_half_lives(self):
        """
        0.25 retained = ten years. Pinned because comparing a decayed value
        against the raw §6 thresholds instead makes RED unreachable — decay
        only reduces, so every finding collapses to YELLOW.
        """
        assert narrative_v5._FLAG_RECENCY_FLOOR == 0.25

    def test_undated_events_are_fully_retained(self):
        """§4.1 does not discount undated risk, so it must still flag."""
        from src.trustscore.calculator_v5 import OperatorData, RiskEvent, Severity

        operator = OperatorData(
            certificate_designator="B", operator_name="X",
            certificate_age_years=10.0, fleet_size=5,
            fleet_accident_events=[RiskEvent(
                severity=float(Severity.SUBSTANTIAL_DAMAGE), event_date=None,
                event_type="accident", source="NTSB", reference="U",
            )],
        )
        assert narrative_v5._flag_flight_safety(operator, self._tail()) \
            == narrative_v5.RED

    def test_maintenance_flag_decays_too(self):
        """An IFSD from 2009 says little about maintenance discipline today."""
        from src.trustscore.calculator_v5 import OperatorData, RiskEvent, Severity

        def sdr(year):
            return OperatorData(
                certificate_designator="B", operator_name="X",
                certificate_age_years=10.0, fleet_size=5,
                fleet_sdr_events=[RiskEvent(
                    severity=float(Severity.SDR_IFSD), event_date=f"{year}-01-01",
                    event_type="sdr", source="SDRS", reference=f"S{year}",
                )],
            )

        assert narrative_v5._flag_maintenance(sdr(2025), self._tail()) \
            == narrative_v5.RED
        assert narrative_v5._flag_maintenance(sdr(2009), self._tail()) \
            == narrative_v5.YELLOW


class TestEstimatedCertificateAgeIsWithheld:
    """
    An estimated certificate age must not reach the model at all.

    10.0 years is a hardcoded fallback — no ingested source carries the
    operator's certificate issuance date, and both substitute routes are
    tested and dead. Instructing the model not to assert it gave only partial
    compliance: it dropped the bare claim but still volunteered "active for
    10.0 years" inside a could-not-be-assessed paragraph.

    A number in the payload invites being quoted, so the figure is omitted
    rather than caveated. §9.1 grounding means the model cannot cite what it
    was not given.
    """

    def _payload(self, estimated):
        from src.trustscore import adapter_v5
        from src.trustscore.calculator_v5 import calculate_trust_score

        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=10.0,
            certificate_age_is_estimated=estimated, fleet_size=5,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )
        tail = adapter_v5.build_tail_data(
            tail_number="N1", aircraft_age_years=23.0, same_type_fleet_count=2,
            lookup_liens=False,
        )
        return narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail),
            missing_inputs=adapter_v5.missing_inputs(operator, tail),
        )

    def test_omitted_when_estimated(self):
        payload = self._payload(True)
        assert "certificate_age_years" not in payload
        assert "certificate_age_years" not in payload["audit_categories"]["asset_stability"]

    def test_supplied_when_real(self):
        payload = self._payload(False)
        assert payload["certificate_age_years"] == 10.0

    def test_flag_is_always_present(self):
        """The model must be able to tell 'absent because estimated' from a bug."""
        for estimated in (True, False):
            assert self._payload(estimated)["certificate_age_is_estimated"] is estimated

    def test_the_figure_appears_nowhere_in_the_serialized_payload(self):
        """
        Belt and braces: grep the JSON the model actually receives. A caveated
        mention elsewhere in the structure would still be quotable.
        """
        import json

        blob = json.dumps(self._payload(True))
        assert "10.0" not in blob
