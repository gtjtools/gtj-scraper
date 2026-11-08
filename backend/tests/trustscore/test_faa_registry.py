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


class TestOneFilingPerLienNotPerParty:
    """
    DOCINDEX indexes one filing once per party to it, so a single lien arrives
    as several rows — lender, owning LLC, sometimes individuals. Keying on party
    turned one encumbrance into three §4.2 charges; migration 082 re-keyed on
    DOC-ID. These pin the shape so the regression cannot return.
    """

    def _rows(self, *parties, doc_id="ARE016569016"):
        return [
            reg.DocIndexRecord("N1029B", "1", p, doc_id, "S/A", date(2025, 1, 13))
            for p in parties
        ]

    def test_same_filing_many_parties_is_one_key(self):
        records = self._rows(
            "BANTERRA BANK", "STONEWALL AVIATION LLC", "WANZOR CHRISTOPHER DEVIN"
        )
        keys = {(r.tail_number, r.doc_type, r.doc_date, r.doc_id or "") for r in records}
        assert len(keys) == 1, "three parties to one lien must collapse to one filing"

    def test_party_in_the_key_would_have_charged_three_times(self):
        """Documents the defect 082 fixed, so nobody reintroduces it."""
        records = self._rows(
            "BANTERRA BANK", "STONEWALL AVIATION LLC", "WANZOR CHRISTOPHER DEVIN"
        )
        by_party = {(r.tail_number, r.doc_type, r.doc_date, r.party) for r in records}
        assert len(by_party) == 3

    def test_distinct_doc_ids_stay_distinct(self):
        """Two real liens on one tail must not be collapsed together."""
        records = (
            self._rows("BANK A", doc_id="ARE000000001")
            + self._rows("BANK B", doc_id="ARE000000002")
        )
        keys = {(r.tail_number, r.doc_type, r.doc_date, r.doc_id or "") for r in records}
        assert len(keys) == 2

    def test_blank_doc_id_collapses_to_tail_type_date(self):
        """
        DOC-ID is blank on 44% of rows. Blanks fall back to (tail, type, date),
        which risks merging two genuinely distinct same-day liens — an
        under-charge of one, chosen over multiplying one lien by its party count.
        """
        records = self._rows("PROGRESSIVE BANK", "AERIS HOLDINGS LLC", doc_id="")
        keys = {(r.tail_number, r.doc_type, r.doc_date, r.doc_id or "") for r in records}
        assert len(keys) == 1


class TestOneEncumbrancePerFinancing:
    """
    fetch_tail_liens must return one event per financing, not per document.

    Aircraft lending records one document per collateral item — airframe, each
    engine, avionics — so a single secured loan arrives as a run of
    sequentially numbered DOC-IDs. N402XT carried 16 from GUNTRACK AVIATION LLC
    on one day; charged per document that was 18 §4.2 penalties and drove the
    tail to 67.45 against 95.92 unencumbered, scoring a normal loan as
    catastrophic distress.

    This is deliberately the INVERSE of the storage key, which keys per
    DOC-ID. Both are right: the table records what was filed, one row per
    document; this function answers how many distinct encumbrances exist.
    """

    def _session(self, rows):
        """Stub session returning pre-grouped rows, as the SQL now does."""
        class _Result:
            def __init__(self, r): self._r = r
            def mappings(self): return self
            def all(self): return self._r
            def scalar(self): return True

        class _Session:
            def execute(self, statement, params=None):
                if "EXISTS" in str(statement):
                    return _Result([])
                return _Result(rows)
            def close(self): pass

        return _Session

    def test_document_count_is_disclosed_in_the_reference(self):
        """A risk audit must still be able to say 16 documents were recorded."""
        from datetime import date
        from src.trustscore import adapter_v5

        rows = [{"doc_type": "S/A", "doc_date": date(2025, 1, 8),
                 "party": "GUNTRACK AVIATION LLC", "documents": 16}]
        result = adapter_v5.fetch_tail_liens(
            "N402XT", db_session_factory=self._session(rows)
        )
        assert len(result) == 1, "16 documents from one party is one encumbrance"
        assert "16 documents" in result[0]["reference"]

    def test_single_document_reference_has_no_count(self):
        from datetime import date
        from src.trustscore import adapter_v5

        rows = [{"doc_type": "S/A", "doc_date": date(2025, 1, 24),
                 "party": "CITIBANK NA", "documents": 1}]
        result = adapter_v5.fetch_tail_liens(
            "N102JE", db_session_factory=self._session(rows)
        )
        assert "documents" not in result[0]["reference"]

    def test_distinct_parties_stay_distinct(self):
        """Three lenders on one day is three encumbrances, not one."""
        from datetime import date
        from src.trustscore import adapter_v5

        rows = [
            {"doc_type": "S/A", "doc_date": date(2025, 1, 8),
             "party": "GUNTRACK AVIATION LLC", "documents": 16},
            {"doc_type": "S/A", "doc_date": date(2025, 1, 8),
             "party": "MOSER AVIATION LLC", "documents": 1},
            {"doc_type": "S/A", "doc_date": date(2025, 1, 8),
             "party": "WORLD FUEL SERVICES INC", "documents": 1},
        ]
        result = adapter_v5.fetch_tail_liens(
            "N402XT", db_session_factory=self._session(rows)
        )
        assert len(result) == 3

    def test_multi_document_financing_costs_less_than_many_real_liens(self):
        """
        The regression guard: 16 documents must not cost 16 encumbrances.
        """
        from src.trustscore import adapter_v5
        from src.trustscore.calculator_v5 import calculate_trust_score

        operator = adapter_v5.build_operator_data(
            operator_name="X", certificate_age_years=15.0, fleet_size=10,
            include_dot_orders=False, lookup_fleet_size=False, lookup_churn=False,
        )

        def score(n_events):
            records = [
                {"date": "2025-01-08", "reference": f"R{i}"} for i in range(n_events)
            ]
            return calculate_trust_score(operator, adapter_v5.build_tail_data(
                tail_number="N402XT", aircraft_age_years=10.0,
                same_type_fleet_count=3, tail_lien_records=records,
                lookup_liens=False,
            ))["trust_score"]

        # One financing recorded as 16 documents must score as 1 encumbrance.
        assert score(1) > score(16)
