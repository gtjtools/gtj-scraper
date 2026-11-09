"""
Classify who filed a lien, to tell routine financing from distress.

A `S/A` filing in DOCINDEX is just "a security interest was recorded". That
covers two very different facts:

  * A bank or owner-trust recording a loan or lease. Every financed aircraft in
    the fleet has one. It says nothing adverse about the operator.
  * A maintenance shop, fuel supplier or tax authority recording a claim. An
    MRO or FBO files a conveyance with the FAA Registry for essentially one
    reason — an unpaid bill escalated to a mechanic's or artisan's lien. That
    is a liquidity signal.

Scoring them identically means a well-financed operator with three aircraft
loans looks worse than one quietly not paying its fuel bills.

WHY THIS IS A CONFIDENCE SIGNAL, NOT A VERDICT
----------------------------------------------
Measured against the real January-2025 archive, restricted to the Part 135
tails we score (345 lien filings, 170 distinct parties):

    matched as financier    32%
    matched as distress      7%
    matched NEITHER         61%

Party names are free text with no registry behind them. `AERIS HOLDINGS LLC`
and `WANZOR CHRISTOPHER DEVIN` are unclassifiable from the string alone, and
they are the majority. Keyword matching also misfires in both directions —
`AFC FINANCIAL SERVICES LLC` is plainly a lender but contains "SERVICES".

So this returns `UNKNOWN` by default and callers must treat that as "not
assessed", exactly as `GAP_TAIL_LIENS` does. The FAA's Part 145 repair-station
database would raise the hit rate, but `av-info.faa.gov` refuses our requests
(see docs §9.6), so there is no authoritative list to join against.

A classification here NEVER removes a lien from the score. It annotates one.
"""

from __future__ import annotations

import re
from typing import Optional

#: Routine financing — the filing is expected and not adverse on its own.
FINANCIER = "FINANCIER"
#: A trade creditor or tax authority. Files with the Registry when unpaid.
DISTRESS = "DISTRESS"
#: Unclassifiable from the party name. The honest majority case.
UNKNOWN = "UNKNOWN"

#: Institutions seen filing aircraft security interests. Matched as substrings
#: on the normalized party name, so "PNC" catches "PNC BANK NA" and
#: "PNC EQUIPMENT FINANCE LLC".
#:
#: Deliberately specific rather than generic: a bare "FINANCE" or "SERVICES"
#: keyword produced false positives in both directions on real data.
_FINANCIER_NAMES = (
    "BANK OF UTAH", "WILMINGTON TRUST", "TVPX", "PNC", "BANC OF AMERICA",
    "BANK OF AMERICA", "WELLS FARGO", "JPMORGAN", "CHASE", "CITIBANK",
    "US BANK", "U S BANK", "TRUIST", "FIFTH THIRD", "KEYBANK", "REGIONS BANK",
    "ATLANTIC UNION BANK", "HUNTINGTON NATIONAL", "CONNECTION BANK",
    "COMMERCIAL NATIONAL BANK", "CITIZENS NATIONAL BANK", "BANTERRA BANK",
    "FIRST NATIONAL BANK", "SYNOVUS", "PINNACLE BANK", "CIT ", "DAIMLER",
    "GLOBAL JET CAPITAL", "AERO CAPITAL", "STONEBRIAR", "SMBC",
    "EQUIPMENT FINANCE", "EQUIPMENT LEASING", "CREDIT UNION",
    "CORPORATION TRUST", "AIRCRAFT SOLUTIONS", "OWNER TRUSTEE",
)

#: Generic financier markers, applied only when nothing in _DISTRESS_PATTERN
#: matched. Ordering matters: "AFC FINANCIAL SERVICES LLC" must land here
#: rather than being trapped by the word "SERVICES".
_FINANCIER_PATTERN = re.compile(
    r"\b(BANK|BANKING|BANCORP|TRUSTEE|FINANCIAL|FINANCE|LEASING|LESSOR|"
    r"CAPITAL CORP|CREDIT CORP|N\.?A\.?)\b"
)

#: Trade-creditor and tax markers. A match here is the interesting case.
#:
#: `FUEL` is included on measured grounds: WORLD FUEL SERVICES INC filed 37 of
#: the 345 Part 135 lien filings in the January-2025 archive — the second most
#: prolific party — and a fuel supplier recording a conveyance against an
#: airframe means unpaid fuel.
_DISTRESS_PATTERN = re.compile(
    r"\b(IRS|INTERNAL REVENUE|DEPARTMENT OF REVENUE|STATE OF [A-Z]+ TAX|"
    r"TAX COMMISSION|TAXATION|COMPTROLLER|"
    r"FUEL|JET CENTER|JETCENTER|AVIONICS|MRO|REPAIR STATION|"
    r"AIRCRAFT MAINTENANCE|AERO MAINTENANCE|MAINTENANCE SERVICES|"
    r"AIRCRAFT SERVICE|AVIATION SERVICES|FBO|GROUND SUPPORT|"
    r"OVERHAUL|PROPELLER|TURBINE SERVICE)\b"
)


def normalize_party(raw: Optional[str]) -> str:
    """Uppercase, collapse whitespace, drop punctuation that varies in filings."""
    text = (raw or "").upper()
    text = re.sub(r"[.,'\"]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_party(raw: Optional[str]) -> str:
    """
    FINANCIER, DISTRESS or UNKNOWN for a DOCINDEX party name.

    Distress is tested first. A name matching both — "AVIATION SERVICES
    FINANCIAL LLC" — is more likely a trade creditor that happens to carry a
    financial word than a bank, and a false DISTRESS is the safer error: it
    flags something for a human rather than quietly clearing it.

    Returns UNKNOWN for 61% of real parties. That is the correct answer, not a
    gap to paper over.
    """
    party = normalize_party(raw)
    if not party:
        return UNKNOWN

    if _DISTRESS_PATTERN.search(party):
        return DISTRESS

    for name in _FINANCIER_NAMES:
        if name in party:
            return FINANCIER

    if _FINANCIER_PATTERN.search(party):
        return FINANCIER

    return UNKNOWN
