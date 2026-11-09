"""
Party classification: telling routine financing from distress.

Measured on the real January-2025 archive restricted to Part 135 tails (345
filings, 170 parties): 25% financier, 11% distress, 64% UNKNOWN. The UNKNOWN
majority is the honest answer — party names are free text and the FAA's Part
145 repair-station list, which would raise the hit rate, is unreachable.
"""

from src.common.lien_classification import (
    DISTRESS, FINANCIER, UNKNOWN, classify_party, normalize_party,
)


class TestFinanciers:
    """A bank recording a loan is expected, not adverse."""

    def test_named_institutions(self):
        for party in ("BANK OF UTAH", "WILMINGTON TRUST", "PNC BANK NA",
                      "TVPX AIRCRAFT SOLUTIONS INC TRUSTEE",
                      "BANC OF AMERICA LEASING", "ATLANTIC UNION BANK",
                      "CITIZENS NATIONAL BANK", "BANTERRA BANK"):
            assert classify_party(party) == FINANCIER, party

    def test_generic_markers(self):
        for party in ("SOMEWHERE STATE BANK", "ACME EQUIPMENT FINANCE LLC",
                      "REGIONAL CREDIT UNION"):
            assert classify_party(party) == FINANCIER, party

    def test_financial_services_is_not_distress(self):
        """
        The regression this guards: a bare SERVICES keyword trapped
        'AFC FINANCIAL SERVICES LLC' as a trade creditor. It is a lender.
        """
        assert classify_party("AFC FINANCIAL SERVICES LLC") == FINANCIER


class TestDistress:
    """An MRO, FBO or tax authority files with the Registry when unpaid."""

    def test_fuel_supplier(self):
        """
        WORLD FUEL SERVICES filed 37 of 345 Part 135 lien filings in the
        January-2025 archive — the second most prolific party. A fuel supplier
        recording a conveyance against an airframe means unpaid fuel.
        """
        assert classify_party("WORLD FUEL SERVICES INC") == DISTRESS

    def test_maintenance_and_avionics(self):
        for party in ("BOCA AIRCRAFT MAINTENANCE LLC",
                      "AERO MAINTENANCE SERVICES LLC",
                      "PRECISION AVIONICS INC",
                      "SOMETOWN JET CENTER"):
            assert classify_party(party) == DISTRESS, party

    def test_tax_authorities(self):
        for party in ("IRS", "INTERNAL REVENUE SERVICE",
                      "DEPARTMENT OF REVENUE", "STATE OF OHIO TAX COMMISSION"):
            assert classify_party(party) == DISTRESS, party

    def test_distress_wins_when_both_match(self):
        """
        A false DISTRESS flags something for a human; a false FINANCIER
        quietly clears it. The safer error is preferred.
        """
        assert classify_party("AVIATION SERVICES FINANCIAL LLC") == DISTRESS


class TestUnknownIsTheHonestDefault:
    """
    64% of real parties are unclassifiable from the name. Returning UNKNOWN
    rather than guessing is the point — the same discipline as GAP_TAIL_LIENS.
    """

    def test_holding_companies_and_individuals(self):
        for party in ("AERIS HOLDINGS LLC", "STONEWALL AVIATION LLC",
                      "WANZOR CHRISTOPHER DEVIN", "LIKOVICH ROBERT B JR",
                      "SEVIER COUNTY CHOPPERS INC"):
            assert classify_party(party) == UNKNOWN, party

    def test_blank(self):
        assert classify_party("") == UNKNOWN
        assert classify_party(None) == UNKNOWN


class TestNormalization:
    def test_punctuation_and_case(self):
        assert normalize_party("  pnc bank, n.a.  ") == "PNC BANK NA"

    def test_classification_is_case_insensitive(self):
        assert classify_party("world fuel services inc") == DISTRESS
