"""
FAA Releasable Aircraft Database parsers.

Field names, DOC-TYPE codes and the BOM are all pinned here because each one
was wrong on the first attempt and each failed *silently* — producing zero rows
or, worse, plausible-looking fabricated history.
"""

from datetime import date

from src.common import faa_registry as reg


def _csv(header, *rows):
    """A DOCINDEX/MASTER-shaped blob, with the UTF-8 BOM the real files carry."""
    body = ",".join(header) + "\n" + "\n".join(",".join(r) for r in rows) + "\n"
    return b"\xef\xbb\xbf" + body.encode("utf-8")


class TestBOM:
    """
    The real files start with a UTF-8 BOM. Decoding as Latin-1 first turns it
    into 'Ï»¿' and welds it to the first header name, making that column
    unfindable — every row is then skipped and the parser reports 0 results
    with no error. That is how a working-looking pipeline ingests nothing.
    """

    def test_first_column_is_reachable_despite_the_bom(self):
        blob = _csv(
            ["TYPE-COLLATERAL", "COLLATERAL", "PARTY", "DOC-ID", "DRDATE", "DOC-TYPE"],
            ["1", "1014A", "AERIS HOLDINGS LLC", "X1", "20250122", "S/A"],
        )
        records = list(reg.parse_docindex(blob))
        assert len(records) == 1
        assert records[0].tail_number == "N1014A"


class TestDocTypes:
    """
    Codes are three characters from the FAA's own ardata.pdf, not the single
    letters the v5.0 source document describes. Truncating to one character
    makes 'S/A' into 'S' and matches nothing.
    """

    def test_security_conveyance_is_a_lien(self):
        assert reg.DocIndexRecord("N1", "1", "P", "", "S/A", None).is_lien

    def test_release_is_not_a_lien(self):
        record = reg.DocIndexRecord("N1", "1", "P", "", "REL", None)
        assert record.is_release
        assert not record.is_lien

    def test_bill_of_sale_is_a_conveyance_not_a_lien(self):
        record = reg.DocIndexRecord("N1", "1", "P", "", "BOS", None)
        assert record.is_conveyance
        assert not record.is_lien

    def test_single_letter_codes_are_not_liens(self):
        """Guards against reintroducing the doc_type[:1] truncation."""
        for bad in ("S", "M", "T", "C"):
            assert not reg.DocIndexRecord("N1", "1", "P", "", bad, None).is_lien


class TestCollateralFiltering:
    """
    Only TYPE-COLLATERAL = 1 carries an N-number. Codes 2 and 3 carry engine
    and propeller identifiers; parsing those as tails would attribute an engine
    lien to whichever airframe the string happened to collide with.
    """

    def test_engine_and_propeller_collateral_are_skipped(self):
        blob = _csv(
            ["TYPE-COLLATERAL", "COLLATERAL", "PARTY", "DOC-ID", "DRDATE", "DOC-TYPE"],
            ["1", "102JE", "OWNER A", "X1", "20250124", "S/A"],
            ["2", "LYC O-320 L-1234", "OWNER B", "X2", "20250124", "S/A"],
            ["3", "HARTZELL HC-1234", "OWNER C", "X3", "20250124", "S/A"],
            ["5", "DOC 55512", "OWNER D", "X4", "20250124", "S/A"],
        )
        records = list(reg.parse_docindex(blob))
        assert [r.tail_number for r in records] == ["N102JE"]


class TestDates:
    def test_drdate_is_the_date_field(self):
        """There is no DOC-DATE column; the real field is DRDATE."""
        blob = _csv(
            ["TYPE-COLLATERAL", "COLLATERAL", "PARTY", "DOC-ID", "DRDATE", "DOC-TYPE"],
            ["1", "102JE", "OWNER", "X1", "20250124", "S/A"],
        )
        assert list(reg.parse_docindex(blob))[0].doc_date == date(2025, 1, 24)

    def test_malformed_dates_do_not_raise(self):
        for bad in ("", "   ", "0", "20259999", "notadate", None):
            assert reg._parse_date(bad) is None


class TestTailNormalization:
    def test_master_tails_gain_the_leading_n(self):
        assert reg._normalize_tail("1014A") == "N1014A"

    def test_existing_n_is_not_doubled(self):
        assert reg._normalize_tail("N1014A") == "N1014A"

    def test_blank_is_empty(self):
        assert reg._normalize_tail("") == ""
        assert reg._normalize_tail(None) == ""


class TestLienRecordContract:
    """to_lien_records must emit what adapter_v5.build_tail_data expects."""

    def test_only_liens_are_emitted(self):
        history = reg.TailTitleHistory(tail_number="N102JE")
        history.lien_filings = [
            reg.DocIndexRecord("N102JE", "1", "BANK", "D1", "S/A", date(2025, 1, 24)),
        ]
        records = reg.to_lien_records(history)
        assert len(records) == 1
        assert records[0]["date"] == "2025-01-24"
        assert "S/A" in records[0]["reference"]

    def test_no_liens_yields_no_records(self):
        assert reg.to_lien_records(reg.TailTitleHistory(tail_number="N1")) == []


class TestDocIndexIsNotClearance:
    """
    docindex_is_complete must default False. DOCINDEX is a ~180-day rolling
    window, so an empty lien list means "nothing filed recently", never "clear
    title" — the same class of error as treating an unqueried source as clean.
    """

    def test_default_is_incomplete(self):
        assert reg.TailTitleHistory(tail_number="N1").docindex_is_complete is False


class TestLienGapIsUnconditional:
    """
    GAP_TAIL_LIENS must be raised even when liens were found.

    DOCINDEX is a ~180-day rolling window, so finding filings proves
    encumbrance while finding none proves nothing about title. Neither licenses
    a clean legal_title finding. This is the same failure mode as
    GAP_NAME_ANCHORED_LOOKUPS: a gap that silently stops firing lets an
    unevidenced category read as verified.
    """

    def test_gap_raised_when_no_liens(self):
        from src.trustscore import adapter_v5

        tail = adapter_v5.build_tail_data(
            tail_number="N1", tail_lien_records=[], lookup_liens=False
        )
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=10.0, fleet_size=5,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )
        assert adapter_v5.GAP_TAIL_LIENS in adapter_v5.missing_input_keys(operator, tail)

    def test_gap_still_raised_when_liens_were_found(self):
        from src.trustscore import adapter_v5

        tail = adapter_v5.build_tail_data(
            tail_number="N1",
            tail_lien_records=[{"date": "2025-01-24", "reference": "DOCINDEX S/A N1"}],
            lookup_liens=False,
        )
        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=10.0, fleet_size=5,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )
        assert tail.tail_lien_events, "the lien must still reach the score"
        assert adapter_v5.GAP_TAIL_LIENS in adapter_v5.missing_input_keys(operator, tail)

    def test_found_liens_lower_the_score(self):
        """A lien must cost something, or ingesting them is pointless."""
        from src.trustscore import adapter_v5
        from src.trustscore.calculator_v5 import calculate_trust_score

        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=15.0, fleet_size=4,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )

        def score(records):
            return calculate_trust_score(operator, adapter_v5.build_tail_data(
                tail_number="N1", aircraft_age_years=10.0, same_type_fleet_count=3,
                tail_lien_records=records, lookup_liens=False,
            ))["trust_score"]

        assert score([{"date": "2025-01-24", "reference": "R"}]) < score([])


class TestLienLookupSafety:
    def test_blank_tail_returns_none(self):
        from src.trustscore import adapter_v5
        assert adapter_v5.fetch_tail_liens("") is None

    def test_dead_database_returns_none_rather_than_raising(self):
        from src.trustscore import adapter_v5

        def broken():
            raise RuntimeError("connection refused")

        assert adapter_v5.fetch_tail_liens("N1", db_session_factory=broken) is None

    def test_explicit_empty_list_skips_the_lookup(self):
        """Passing [] means 'measured, none found' and must not hit the DB."""
        from src.trustscore import adapter_v5

        original = adapter_v5.fetch_tail_liens
        adapter_v5.fetch_tail_liens = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not be called")
        )
        try:
            tail = adapter_v5.build_tail_data(tail_number="N1", tail_lien_records=[])
            assert tail.tail_lien_events == []
        finally:
            adapter_v5.fetch_tail_liens = original
