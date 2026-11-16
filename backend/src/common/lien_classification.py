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
#: LEAS(E|ING) is matched without a leading word boundary so compounds land
#: here too: "DYNAMIC AVLEASE INC" is plainly a lessor, but `\bLEASING\b` misses
#: it because the word is welded to "AV". Trailing \b still anchors the end, so
#: this does not swallow unrelated words.
_FINANCIER_PATTERN = re.compile(
    r"(\b(BANK|BANKING|BANCORP|TRUSTEE|FINANCIAL|FINANCE|LESSOR|"
    r"CAPITAL CORP|CREDIT CORP|N\.?A\.?)\b|LEASE\b|LEASING\b)"
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


# ── Severity tiers (§2) ──────────────────────────────────────────────────────
#
# Scoring liens by row count inverts real risk: a large operator accumulating
# routine bank financings and small vendor filings outranks a distressed one
# carrying a single six-figure engine-overhaul claim, because the first has more
# rows. Tiering fixes the ranking; log-dampening stops volume alone driving it.
#
# WHAT THE SPEC ASKS FOR vs WHAT DOCINDEX CARRIES
# The tier definitions are written in dollars (<$10k / $10-75k / >$75k). FAA
# DOCINDEX publishes NO claim amounts — `gtj.tail_liens` has doc_type, doc_date,
# party and doc_id, because the source has nothing else. So amount cannot be the
# discriminator here.
#
# What DOCINDEX does carry is WHO filed, and that proxies severity well: a bank
# recording a loan is routine regardless of size, while a tax authority or fuel
# supplier recording a claim means an unpaid bill escalated to a lien. Tiering
# therefore runs off `classify_party` plus doc_type.
#
# `claim_amount` is accepted and takes precedence wherever a caller can supply
# it, so the dollar thresholds activate unchanged if a source with amounts
# (CARES, UCC, court records) is ever ingested. Until then it is always None.

#: Nuisance/administrative, or routine financing. Never RED on its own.
TIER_NUISANCE = 1
#: Material mechanics'/MRO/fuel claim. YELLOW territory.
TIER_MATERIAL = 2
#: Crippling encumbrance — tax levy, judgment, program default. Single-event RED.
TIER_CRIPPLING = 3

#: §2A dollar bands, used only when a claim amount is actually available.
_TIER_2_FLOOR = 10_000.0
_TIER_3_FLOOR = 75_000.0

#: Parties whose filings are grounding-grade regardless of amount: tax
#: authorities, courts, and the hourly engine programmes whose default lets the
#: provider pull coverage mid-trip.
_CRIPPLING_PATTERN = re.compile(
    r"\b(IRS|INTERNAL REVENUE|DEPARTMENT OF REVENUE|STATE OF [A-Z]+ TAX|"
    r"TAX COMMISSION|TAXATION|COMPTROLLER|LEVY|WARRANT|"
    r"JUDGMENT|JUDGEMENT|WRIT|ATTACHMENT|SHERIFF|COURT|MARSHAL|"
    r"JSSI|JET SUPPORT|MSP|CORPORATECARE|CORPORATE CARE|POWER ADVANTAGE|"
    r"ESP GOLD|TAP BLUE|ENGINE PROGRAM)\b"
)

#: Release of a previously recorded interest. The opposite of an encumbrance.
_RELEASE_DOC_TYPES = frozenset({"REL", "RELEASE"})


def lien_tier(
    party: Optional[str] = None,
    doc_type: Optional[str] = None,
    claim_amount: Optional[float] = None,
) -> int:
    """
    Severity tier 1-3 for one lien filing (§2A).

    Amount wins when known, because it is the discriminator the specification
    actually names. DOCINDEX never supplies one, so in practice the party name
    and doc_type decide:

        tax / court / engine-programme party  -> 3  (crippling)
        trade creditor: MRO, fuel, FBO        -> 2  (material)
        bank, lessor, owner trust             -> 1  (routine financing)
        unclassifiable                        -> 2  (cautious middle)

    A MISSING party and an UNCLASSIFIABLE one are treated differently, because
    they are different facts:

      * No party recorded at all (67% of rows in gtj.tail_liens — DOCINDEX
        often omits it) is missing data. It resolves to Tier 1 so it cannot
        manufacture a finding. Defaulting these to Tier 2 put 445 of 906
        tails (49%) into YELLOW on no evidence whatsoever, which is the same
        class of error as the GREY-everything bug: a verdict with nothing
        behind it.
      * A party that IS named but matches no pattern ("AERIS HOLDINGS LLC")
        resolves to Tier 2. Someone recorded a conveyance and we cannot rule
        out a trade claim, so it is worth a look without forcing RED.

    Args:
        party: DOCINDEX party name, free text.
        doc_type: DOCINDEX document type (S/A, REL, REP, CSC...).
        claim_amount: Claim in USD if a source ever provides one.

    Returns:
        TIER_NUISANCE, TIER_MATERIAL or TIER_CRIPPLING.
    """
    if (doc_type or "").strip().upper() in _RELEASE_DOC_TYPES:
        return TIER_NUISANCE

    if claim_amount is not None:
        if claim_amount >= _TIER_3_FLOOR:
            return TIER_CRIPPLING
        if claim_amount >= _TIER_2_FLOOR:
            return TIER_MATERIAL
        return TIER_NUISANCE

    normalized = normalize_party(party)
    # No party on the filing: missing data, not a middling claim.
    if not normalized:
        return TIER_NUISANCE

    if _CRIPPLING_PATTERN.search(normalized):
        return TIER_CRIPPLING

    party_class = classify_party(party)
    if party_class == FINANCIER:
        return TIER_NUISANCE
    if party_class == DISTRESS:
        return TIER_MATERIAL
    # Named but unclassifiable.
    return TIER_MATERIAL
