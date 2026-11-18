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


class TestCatastrophicCircuitBreaker:
    """
    §4.1a. A fatal accident or hull loss must floor the score and force RED.

    WHY THIS EXISTS. An operator was reported scoring 81 weeks after a fatal
    crash. Investigating it found the arithmetic diluting a catastrophe through
    three compounding mechanisms — exposure normalization (MAX(1, SQRT(Vf))),
    Dscale operator damping, and five-year exponential decay — so a 50-point
    FATAL_ACCIDENT against a mid-size fleet landed as a single-digit Sro and
    left Hsafety near 0.9.

    Worse, an OPEN NTSB docket carries no injury or damage codes for weeks, so
    a crash from last month graded as severity 0 and the flag read GREEN. The
    breaker therefore reads raw facts (fatalities, damage) and not a severity
    value the pipeline may not have been able to assign yet.
    """

    def _operator(self, events, fleet_size=12):
        operator = adapter_v5.build_operator_data(
            operator_name="Aurora Aviation, Inc.",
            certificate_designator="GLRA",
            certificate_age_years=15.0, fleet_size=fleet_size,
            include_dot_orders=True, lookup_fleet_size=False, lookup_churn=False,
        )
        operator.lookups_certificate_anchored = True
        operator.fleet_accident_events = events
        return operator

    def _tail(self):
        return adapter_v5.build_tail_data(
            tail_number="N722BD", aircraft_age_years=25.0,
            same_type_fleet_count=2, certificate_tenure_months=24.0,
            tail_lien_records=[], lookup_liens=False, ownership_observed=True,
        )

    def _crash(self, **kwargs):
        defaults = dict(
            severity=0.0, event_date="2026-11-01", event_type="Accident",
            source="NTSB", reference="ERA27MA026",
        )
        defaults.update(kwargs)
        return RiskEvent(**defaults)

    def _tail_with_crash(self, **kwargs):
        """A tail whose OWN airframe suffered the catastrophe (tier 1)."""
        tail = self._tail()
        tail.tail_accident_events = [self._crash(**kwargs)]
        return tail

    def test_open_docket_hull_loss_floors_the_score(self):
        """
        The reported failure: destroyed aircraft, docket open, no injury codes.

        Severity is 0 here because nothing has been graded yet. Before §4.1a
        this produced Hsafety 1.0000 and a Benchmark score.
        """
        operator = self._operator([])
        tail = self._tail_with_crash(
            aircraft_damage="DESTROYED", investigation_status="OPEN",
        )
        result = calculate_trust_score(operator, tail)

        assert result["trust_score"] == 50.0
        assert result["components"]["h_safety"] == 0.0
        assert result["components"]["circuit_breaker_tripped"] is True
        assert result["components"]["circuit_breaker_scope"] == "this_airframe"

    def test_fatalities_floor_the_score(self):
        operator = self._operator([])
        result = calculate_trust_score(
            operator, self._tail_with_crash(fatalities=2)
        )
        assert result["trust_score"] == 50.0

    def test_flight_safety_is_red(self):
        operator = self._operator([
            self._crash(aircraft_damage="DESTROYED", investigation_status="OPEN"),
        ])
        tail = self._tail()
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail)
        )
        safety = payload["audit_categories"]["flight_safety"]
        assert safety["flag"] == narrative_v5.RED
        # The narrative must be told to lead with it, not merely be given the
        # event in a list.
        assert "catastrophic_events" in safety
        assert safety["catastrophic_events"]["count"] == 1

    def test_a_large_fleet_cannot_dilute_it(self):
        """Exposure normalization must not apply to a catastrophe."""
        small = calculate_trust_score(
            self._operator([], 1), self._tail_with_crash(fatalities=1)
        )
        large = calculate_trust_score(
            self._operator([], 200), self._tail_with_crash(fatalities=1)
        )
        assert small["trust_score"] == large["trust_score"] == 50.0

    def test_a_healthy_tail_cannot_offset_it(self):
        """
        Zeroing Hsafety alone is insufficient — it carries only 0.35 weight.

        Without the composite-level override the 0.65 tail term would carry a
        clean airframe to roughly 74, a Benchmark score for an operator that
        has just destroyed an aircraft.
        """
        operator = self._operator([])
        tail = adapter_v5.build_tail_data(
            tail_number="N722BD", aircraft_age_years=1.0,
            same_type_fleet_count=8, certificate_tenure_months=60.0,
            tail_lien_records=[], lookup_liens=False, ownership_observed=True,
        )
        tail.tail_accident_events = [self._crash(fatalities=1)]
        assert calculate_trust_score(operator, tail)["trust_score"] == 50.0

    def test_an_old_catastrophe_does_not_trip_it(self):
        """
        Outside the 36-month window the ordinary decayed arithmetic resumes.

        An operator must not be defined forever by one event — that is what
        the decay schedule is for.
        """
        operator = self._operator([self._crash(
            event_date="2015-01-01", fatalities=3, severity=Severity.FATAL_ACCIDENT,
        )])
        result = calculate_trust_score(operator, self._tail())
        assert result["components"].get("circuit_breaker_tripped") is not True
        assert result["trust_score"] > 50.0

    def test_a_survivable_incident_does_not_trip_it(self):
        """Substantial damage with no fatalities is YELLOW territory, not RED."""
        operator = self._operator([self._crash(
            event_type="Incident", fatalities=0, aircraft_damage="SUBSTANTIAL",
            severity=Severity.SUBSTANTIAL_DAMAGE,
        )])
        result = calculate_trust_score(operator, self._tail())
        assert result["components"].get("circuit_breaker_tripped") is not True
        assert result["trust_score"] > 50.0

    def test_a_bare_open_docket_does_not_trip_it(self):
        """
        An open investigation with nothing populated is not proof of a
        catastrophe. Tripping on investigation_status alone would flag every
        minor incident under review.
        """
        operator = self._operator([self._crash(investigation_status="OPEN")])
        result = calculate_trust_score(operator, self._tail())
        assert result["components"].get("circuit_breaker_tripped") is not True

    def test_a_tail_crash_trips_it_for_that_tail(self):
        """
        calculate_safety_health sees only operator data, so a crash recorded
        against the tail alone must still be caught at the composite level.
        """
        operator = self._operator([])
        tail = self._tail()
        tail.tail_accident_events = [self._crash(fatalities=1)]
        assert calculate_trust_score(operator, tail)["trust_score"] == 50.0

    def test_an_undated_catastrophe_trips_it(self):
        """A crash we cannot date is not thereby old."""
        operator = self._operator([])
        tail = self._tail_with_crash(event_date=None, fatalities=1)
        assert calculate_trust_score(operator, tail)["trust_score"] == 50.0


class TestTradeNamesInReport:
    """
    §8. Every name a certificate trades under must appear in the report.

    Entity resolution has expanded an operator into all of its certificate's
    names since the §8 work — but only for SEARCHING. The payload carried no
    DBA field at all, so a broker reading the report never learned that the
    operator they were quoted by also trades under another name.

    That is the material fact: a charter is sold under a trade name while the
    safety and enforcement record attaches to the certificate. Certificate
    3KSC is held by Asher Air LLC and also trades as Blue Spruce Air; 44 of
    1,870 certificates currently carry more than one name.
    """

    def _payload(self, trade_names):
        operator = adapter_v5.build_operator_data(
            operator_name="Asher Air, Llc.", certificate_designator="3KSC",
            certificate_age_years=15.0, fleet_size=4,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )
        tail = adapter_v5.build_tail_data(
            tail_number="N1AA", tail_lien_records=[], lookup_liens=False,
            ownership_observed=True,
        )
        return narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail),
            trade_names=trade_names,
        )

    def test_trade_names_reach_the_payload(self):
        payload = self._payload([
            {"name": "BLUE SPRUCE AIR, LLC.", "is_current": True,
             "first_seen": "2023-03-24", "last_seen": "2026-11-02"},
            {"name": "Asher Air, Llc.", "is_current": False,
             "first_seen": "2026-10-30", "last_seen": "2026-10-30"},
        ])
        names = [entry["name"] for entry in payload["trade_names"]]
        assert "BLUE SPRUCE AIR, LLC." in names
        assert len(payload["trade_names"]) == 2

    def test_current_and_former_are_distinguishable(self):
        """
        A former identity reads very differently from a concurrent dba and
        must not be presented as one.
        """
        payload = self._payload([
            {"name": "Current Name LLC", "is_current": True,
             "first_seen": None, "last_seen": None},
            {"name": "Old Name Inc", "is_current": False,
             "first_seen": None, "last_seen": None},
        ])
        states = {e["name"]: e["is_current"] for e in payload["trade_names"]}
        assert states["Current Name LLC"] is True
        assert states["Old Name Inc"] is False

    def test_empty_list_is_not_a_claim_of_no_other_names(self):
        """
        An unresolved certificate must not read as "this operator has one
        identity" — the prompt requires it be reported as unestablished.
        """
        payload = self._payload([])
        assert payload["trade_names"] == []
        assert "trade_names" in payload

    def test_trade_names_do_not_leak_internals(self):
        """§9: adding a payload field must not breach the Black Box Rule."""
        payload = self._payload([
            {"name": "Some Operator LLC", "is_current": True,
             "first_seen": "2023-01-01", "last_seen": "2026-01-01"},
        ])
        blob = json.dumps(payload).lower()
        for forbidden in ("h_safety", "components", "sro", "composite"):
            assert forbidden not in blob

    def test_prompt_requires_them(self):
        """The payload field is useless if the model is not told to use it."""
        prompt = narrative_v5.SYSTEM_PROMPT
        assert "trade_names" in prompt
        assert "Operating As" in prompt
        # The current/former distinction must be instructed, not inferred.
        assert "is_current" in prompt


class TestSisterShipCatastropheIsGraduated:
    """
    §4.1a tier 2. A fatality on ANOTHER aircraft on the same certificate must
    weigh heavily without forcing the floor.

    The first implementation of the circuit breaker applied the hard floor to
    fleet-level events too, so a clean airframe scored exactly 50.0 — identical
    to the aircraft that had actually been destroyed. That told a broker nothing
    about which situation they were in.

    Both are RED and both are disclosed. The difference is that the floor is
    reserved for "the aircraft you would be flying on crashed", and a sister
    ship is instead a severe judgement about the operator.
    """

    def _crash(self, ref="SIS1", **kwargs):
        defaults = dict(
            severity=0.0, event_date="2026-11-01", event_type="Accident",
            source="NTSB", reference=ref, fatalities=2,
        )
        defaults.update(kwargs)
        return RiskEvent(**defaults)

    def _operator(self, fleet_events):
        operator = adapter_v5.build_operator_data(
            operator_name="Aurora Aviation, Inc.",
            certificate_designator="GLRA",
            certificate_age_years=15.0, fleet_size=12,
            include_dot_orders=True, lookup_fleet_size=False, lookup_churn=False,
        )
        operator.lookups_certificate_anchored = True
        operator.fleet_accident_events = fleet_events
        return operator

    def _clean_tail(self):
        return adapter_v5.build_tail_data(
            tail_number="N999ZZ", aircraft_age_years=5.0,
            same_type_fleet_count=4, certificate_tenure_months=36.0,
            tail_lien_records=[], lookup_liens=False, ownership_observed=True,
        )

    def test_heavily_penalised_but_not_floored(self):
        operator = self._operator([self._crash()])
        result = calculate_trust_score(operator, self._clean_tail())
        baseline = calculate_trust_score(self._operator([]), self._clean_tail())

        assert result["trust_score"] > 50.0, "the floor is for the crashed tail"
        # A large, unmistakable penalty — tens of points, not a rounding error.
        assert baseline["trust_score"] - result["trust_score"] > 25.0
        assert result["components"]["circuit_breaker_scope"] == "sister_ship"

    def test_still_red(self):
        """Graduated scoring must not soften the flag."""
        operator = self._operator([self._crash()])
        tail = self._clean_tail()
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail),
            trade_names=[],
        )
        assert payload["audit_categories"]["flight_safety"]["flag"] == \
            narrative_v5.RED

    def test_multiple_fleet_catastrophes_compound(self):
        """Two fatal crashes in 36 months is a different claim from one."""
        one = calculate_trust_score(
            self._operator([self._crash("A")]), self._clean_tail()
        )["trust_score"]
        two = calculate_trust_score(
            self._operator([self._crash("A"), self._crash("B")]),
            self._clean_tail(),
        )["trust_score"]
        three = calculate_trust_score(
            self._operator([self._crash("A"), self._crash("B"), self._crash("C")]),
            self._clean_tail(),
        )["trust_score"]
        assert one > two > three > 50.0

    def test_the_narrative_is_told_which_aircraft(self):
        """
        Conflating "this aircraft crashed" with "a sister ship did" is a
        serious misstatement in either direction, so the payload separates them.
        """
        operator = self._operator([self._crash()])
        tail = self._clean_tail()
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail),
            trade_names=[],
        )
        block = payload["audit_categories"]["flight_safety"]["catastrophic_events"]
        assert block["on_this_airframe"] == []
        assert len(block["on_other_fleet_aircraft"]) == 1
        assert "ANOTHER AIRCRAFT" in block["guidance"]
        assert "was NOT involved" in block["guidance"]

    def test_this_airframe_takes_precedence(self):
        """A crash on the quoted tail floors it even alongside fleet events."""
        operator = self._operator([self._crash("SIS")])
        tail = self._clean_tail()
        tail.tail_accident_events = [self._crash("THIS")]
        result = calculate_trust_score(operator, tail)
        assert result["trust_score"] == 50.0
        assert result["components"]["circuit_breaker_scope"] == "this_airframe"
        # Both events are still disclosed.
        assert result["components"]["catastrophic_event_count"] == 2

    def test_fleet_score_reflects_it_without_being_pinned(self):
        """
        FleetScore is a judgement about the certificate alone, so a fleet
        catastrophe should drive it very low — but it is still not the
        "this aircraft crashed" finding.
        """
        operator = self._operator([self._crash()])
        result = calculate_trust_score(operator, self._clean_tail())
        assert 50.0 <= result["fleet_score"] < 60.0


class TestUnmeasuredChurnIsNotPublished:
    """
    An unmeasured zero must never reach the payload as a finding.

    Observed live on Triton Air after deploying §10: the narrative said
    "added zero tails and removed zero tails, resulting in a 0% fleet churn
    rate" and then, two sentences later, "D085 churn could not be measured due
    to insufficient historical snapshots". A self-contradiction in one
    paragraph.

    The cause was not the model. `tails_added_12m`, `tails_removed_12m` and
    `fleet_churn_rate_12m` were published unconditionally, so an operator with
    no fleet history was handed three zeros and reported them. Suppressing the
    claim from `verified_clean_searches` was not enough while the raw figures
    were still in the category block.

    Same reasoning as the estimated certificate age: a number in the payload
    invites being quoted, so the surest way not to publish a fabricated figure
    is not to supply it.
    """

    def _block(self, **extra):
        kwargs = dict(
            operator_name="Triton Air Llc", certificate_designator="70TA",
            certificate_age_years=15.3, fleet_size=4,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )
        kwargs.update(extra)
        operator = adapter_v5.build_operator_data(**kwargs)
        tail = adapter_v5.build_tail_data(
            tail_number="", lookup_liens=False, tail_lien_records=[],
        )
        payload = narrative_v5.build_audit_payload(
            operator, tail, calculate_trust_score(operator, tail),
            trade_names=[],
        )
        return payload["audit_categories"]["asset_stability"]

    def test_figures_absent_when_unmeasured(self):
        block = self._block()
        assert "tails_added_12m" not in block
        assert "tails_removed_12m" not in block
        assert "fleet_churn_rate_12m" not in block
        # Stated explicitly, so the model knows it is absent by design rather
        # than missing by accident.
        assert block["fleet_churn_measured"] is False

    def test_figures_present_when_measured(self):
        block = self._block(tails_added_12m=2, tails_removed_12m=1)
        assert block["tails_added_12m"] == 2
        assert block["tails_removed_12m"] == 1
        assert "fleet_churn_rate_12m" in block
        assert "fleet_churn_measured" not in block

    def test_a_measured_zero_is_still_published(self):
        """Measured stability IS a finding and must survive the suppression."""
        block = self._block(tails_added_12m=0, tails_removed_12m=0)
        assert block["tails_added_12m"] == 0
        assert block["fleet_churn_rate_12m"] == "0%"

    def test_prompt_forbids_inventing_a_rate(self):
        prompt = narrative_v5.SYSTEM_PROMPT
        assert "fleet_churn_measured" in prompt
        assert "do not say the operator added or removed zero aircraft" in \
            prompt.replace("\\\n", "").replace("\n", " ").lower() or \
            "removed zero aircraft" in prompt


class TestLienTypeIsNotOverclaimed:
    """
    A filing must never be described as more than the record supports.

    REPORTED: the audit for Skyway Aviation Services said the operator had
    "tax and mechanics liens" when its filings were ordinary UCC-1 style debt
    financing. The model was not hallucinating — every lien event was
    hardcoded `event_type="ACTIVE_MECHANICS_OR_TAX_LIEN"`, and event_type is
    copied verbatim into the narrative payload, so the report repeated the
    label we handed it.

    The FAA files every security interest as S/A ("Security Conveyance/Lien")
    and does NOT distinguish a mechanic's lien from a tax lien from an
    aircraft loan — a fact `common.faa_registry` already documented while the
    adapter contradicted it. A state UCC-1 is a financing statement, which is
    weaker still.

    Severity is unchanged by this: an active encumbrance scores the same. Only
    the claim about its NATURE is withdrawn.
    """

    def test_docindex_filing_is_not_called_a_tax_or_mechanics_lien(self):
        tail = adapter_v5.build_tail_data(
            tail_number="N1AA", lookup_liens=False,
            tail_lien_records=[
                {"doc_type": "S/A", "party": "FIRST FARMERS BANK & TRUST",
                 "date": "2026-01-01", "reference": "R1"},
            ],
        )
        types = {event.event_type for event in tail.tail_lien_events}
        assert types == {"ACTIVE_SECURITY_INTEREST"}
        assert "MECHANICS" not in " ".join(types)
        assert "TAX" not in " ".join(types)

    def test_ucc_filing_is_labelled_a_financing_statement(self):
        events = adapter_v5.ucc_filings_to_legal_events([
            {"status": "active", "filing_date": "2026-01-01", "file_number": "U1"},
        ])
        assert len(events) == 1
        assert events[0].event_type == "ACTIVE_UCC_FINANCING_STATEMENT"

    def test_doc_type_drives_the_label(self):
        assert adapter_v5._lien_event_type({"doc_type": "S/A"}) \
            == "ACTIVE_SECURITY_INTEREST"
        assert adapter_v5._lien_event_type({"doc_type": "CSC"}) \
            == "OWNERSHIP_WITH_SECURITY_INTEREST"
        assert adapter_v5._lien_event_type({"doc_type": "CRT"}) \
            == "COURT_DOCUMENT"

    def test_absent_and_unknown_doc_types_stay_generic(self):
        """
        An absent key, an empty value and an unrecognised code are three
        different facts. None of them licenses a specific claim.
        """
        assert adapter_v5._lien_event_type({}) == "ACTIVE_ENCUMBRANCE"
        assert adapter_v5._lien_event_type({"doc_type": ""}) == "ACTIVE_ENCUMBRANCE"
        assert adapter_v5._lien_event_type({"doc_type": "ZZZ"}) == "ACTIVE_ENCUMBRANCE"

    def test_stored_events_under_the_old_label_still_score(self):
        """
        The old name is retained in the taxonomy and the encumbrance set.
        Dropping it would silently stop scoring every already-stored lien.
        """
        from src.trustscore.calculator_v5 import ELI_TAXONOMY

        assert "ACTIVE_MECHANICS_OR_TAX_LIEN" in ELI_TAXONOMY
        assert "ACTIVE_ENCUMBRANCE" in ELI_TAXONOMY
        assert ELI_TAXONOMY["ACTIVE_ENCUMBRANCE"] \
            == ELI_TAXONOMY["ACTIVE_MECHANICS_OR_TAX_LIEN"]

        old = RiskEvent(severity=0.0, event_date="2026-01-01",
                        event_type="ACTIVE_MECHANICS_OR_TAX_LIEN")
        new = RiskEvent(severity=0.0, event_date="2026-01-01",
                        event_type="ACTIVE_SECURITY_INTEREST")
        assert narrative_v5._is_encumbrance(old)
        assert narrative_v5._is_encumbrance(new)

    def test_certificate_lien_flag_recognises_the_new_labels(self):
        """_flag_legal_title matched the old string literally; a renamed event
        would otherwise stop forcing RED."""
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_designator="ABCD",
            certificate_age_years=20.0, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )
        operator.lookups_certificate_anchored = True
        operator.legal_events = [
            RiskEvent(severity=20.0, event_date="2026-01-01",
                      event_type="ACTIVE_SECURITY_INTEREST", source="DOCINDEX"),
        ]
        tail = adapter_v5.build_tail_data(
            tail_number="N1", tail_lien_records=[], lookup_liens=False,
            ownership_observed=True, same_type_fleet_count=5,
            certificate_tenure_months=24.0,
        )
        assert narrative_v5._flag_legal_title(operator, tail) == narrative_v5.RED

    def test_prompt_forbids_inventing_a_lien_category(self):
        prompt = narrative_v5.SYSTEM_PROMPT
        assert "NEVER CHARACTERISE A LIEN BEYOND ITS RECORDED TYPE" in prompt
        assert "security interest" in prompt


class TestLienProxySignals:
    """
    §2A proxy signals, standing in for the claim amounts DOCINDEX never
    publishes.

    Each proxy is bounded by what the data can actually evidence. Two were
    narrowed during development because the obvious reading inverted the very
    ranking the tiering exists to protect — both corrections are asserted here
    so they cannot be undone by someone reading only the spec.
    """

    from datetime import date as _date
    NOW = _date(2026, 11, 18)

    def _tier(self, **kwargs):
        from src.common.lien_classification import lien_tier
        kwargs.setdefault("doc_type", "S/A")
        kwargs.setdefault("now", self.NOW)
        return lien_tier(**kwargs)

    # ── Proxy 1: claimant keywords ───────────────────────────────────────────

    @pytest.mark.parametrize("party", [
        "INTERNAL REVENUE SERVICE", "FRANCHISE TAX BOARD",
        "TEXAS COMPTROLLER OF PUBLIC ACCOUNTS", "COUNTY TAX COLLECTOR",
        "ROLLS-ROYCE CORPORATION", "PRATT & WHITNEY CANADA",
        "HONEYWELL INTERNATIONAL INC", "WILLIAMS INTERNATIONAL CO LLC",
        "JET SUPPORT SERVICES INC",
    ])
    def test_tax_court_and_engine_programmes_are_crippling(self, party):
        assert self._tier(party=party) == 3

    @pytest.mark.parametrize("party", [
        "WEST STAR AVIATION LLC", "DUNCAN AVIATION INC",
        "SIGNATURE FLIGHT SUPPORT", "ATLANTIC AVIATION FBO INC",
        "WORLD FUEL SERVICES INC",
    ])
    def test_mro_and_fuel_networks_are_material(self, party):
        assert self._tier(party=party) == 2

    def test_oem_finance_arm_is_not_a_programme_default(self):
        """
        Textron, Bombardier et al run captive LENDERS as well as parts and
        programme businesses. Matching the bare marque would promote an
        ordinary aircraft loan to the most severe tier, so a support word is
        required and an explicit finance word disqualifies.
        """
        assert self._tier(party="TEXTRON AVIATION PARTS & PROGRAMS") == 3
        assert self._tier(party="GULFSTREAM AEROSPACE SERVICE CENTER") == 3
        assert self._tier(party="TEXTRON FINANCIAL CORPORATION") == 1
        assert self._tier(party="BOMBARDIER CAPITAL INC") == 1

    def test_a_trade_creditor_named_capital_stays_adverse(self):
        """Loosening CAPITAL/CREDIT must not sweep in fuel and FBO vendors."""
        assert self._tier(party="CAPITAL AVIATION FUEL LLC") == 2
        assert self._tier(party="CAPITAL CITY JET CENTER") == 2

    # ── Proxy 2: persistence ─────────────────────────────────────────────────

    def test_stale_named_claim_promotes(self):
        fresh = self._tier(party="AERIS HOLDINGS LLC", doc_date="2026-11-01")
        stale = self._tier(party="AERIS HOLDINGS LLC", doc_date="2025-01-01")
        assert stale >= fresh

    def test_a_small_measured_claim_left_stale_promotes(self):
        assert self._tier(claim_amount=2000, doc_date="2026-11-01") == 1
        assert self._tier(claim_amount=2000, doc_date="2025-01-01") == 2

    def test_a_bank_loan_is_exempt_from_persistence(self):
        """
        THE CORRECTION THAT MATTERS MOST HERE. An aircraft loan is meant to sit
        unreleased for its term — five to ten years. Measured on live data, 401
        of 680 active filings are older than 180 days, and the old ones include
        PNC BANK NA and BANC OF AMERICA LEASING behaving exactly as intended.
        Promoting on age alone moved 290 filings to Tier 2 and would have
        marked most financed aircraft as distressed.
        """
        assert self._tier(party="NBH BANK", doc_date="2024-09-01") == 1
        assert self._tier(party="PNC BANK NA", doc_date="2024-09-01") == 1

    def test_an_unnamed_filing_is_exempt_from_persistence(self):
        """
        77% of active filings carry no party. Without knowing who filed, we
        cannot say whether prompt release was ever expected — a lender's lien
        should outlive the window, a vendor's should not. Age is evidence only
        once that is known.
        """
        assert self._tier(party=None, doc_date="2024-09-01") == 1

    def test_an_undated_filing_is_never_promoted(self):
        assert self._tier(party="AERIS HOLDINGS LLC") == 2  # already material
        assert self._tier(party="NBH BANK") == 1

    # ── Proxy 3: multi-tail contagion ────────────────────────────────────────

    def _contagion(self, filings):
        from src.common.lien_classification import promote_for_contagion
        return promote_for_contagion(filings, now=self.NOW)

    def _filing(self, tail, party, date="2026-10-01"):
        return {"tail_number": tail, "party": party,
                "doc_type": "S/A", "doc_date": date}

    def test_one_vendor_across_two_tails_is_systemic(self):
        result = self._contagion([
            self._filing("N1", "WEST STAR AVIATION LLC"),
            self._filing("N2", "WEST STAR AVIATION LLC"),
        ])
        assert result == {"N1": 3, "N2": 3}

    def test_two_different_vendors_across_the_fleet_is_systemic(self):
        result = self._contagion([
            self._filing("N1", "DUNCAN AVIATION INC"),
            self._filing("N2", "WORLD FUEL SERVICES INC"),
        ])
        assert result == {"N1": 3, "N2": 3}

    def test_one_vendor_on_one_tail_is_a_dispute_not_contagion(self):
        assert self._contagion([
            self._filing("N1", "WEST STAR AVIATION LLC"),
        ]) == {"N1": 2}

    def test_one_lender_across_a_whole_fleet_is_not_contagion(self):
        """
        THE OTHER CORRECTION. A single bank financing several tails is the most
        ordinary arrangement in aviation — a fleet bought on one credit
        facility. The first implementation escalated all three tails to Tier 3,
        which would have flagged every well-financed operator RED.
        """
        assert self._contagion([
            self._filing("N1", "NBH BANK", "2026-11-01"),
            self._filing("N2", "NBH BANK", "2026-11-01"),
            self._filing("N3", "NBH BANK", "2026-11-01"),
        ]) == {"N1": 1, "N2": 1, "N3": 1}

    def test_unnamed_claimants_cannot_evidence_contagion(self):
        """Two blanks are not provably the same claimant."""
        assert self._contagion([
            self._filing("N1", None, "2026-11-01"),
            self._filing("N2", None, "2026-11-01"),
        ]) == {"N1": 1, "N2": 1}

    def test_releases_are_not_encumbrances(self):
        assert self._contagion([
            {"tail_number": "N1", "party": "WEST STAR AVIATION LLC",
             "doc_type": "REL", "doc_date": "2026-10-01"},
        ]) == {}
