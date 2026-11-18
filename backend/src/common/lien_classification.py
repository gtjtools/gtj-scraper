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
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

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
#: `CAPITAL`/`CREDIT` are matched as bare words rather than only as
#: "CAPITAL CORP": "BOMBARDIER CAPITAL INC" is plainly a finance arm but was
#: falling through to the cautious Tier 2 default, which promoted an ordinary
#: aircraft loan. The OEM-marque rule above still routes a genuine support
#: default to Tier 3, so loosening this does not hide programme claims.
_FINANCIER_PATTERN = re.compile(
    r"(\b(BANK|BANKING|BANCORP|TRUSTEE|FINANCIAL|FINANCE|LESSOR|"
    r"CAPITAL|CREDIT|N\.?A\.?)\b|LEASE\b|LEASING\b)"
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
#:
#: GOVERNMENT / COURT. A revenue authority or court does not file against an
#: airframe over a routine invoice — by the time it reaches the Registry the
#: debt is enforced, and a levy or writ can detain the aircraft.
#:
#: OEM AND HOURLY ENGINE PROGRAMMES. Default on an engine or airframe programme
#: withdraws coverage, which grounds the aircraft on the spot regardless of the
#: sum owed.
#:
#: Note `TEXTRON`/`BOMBARDIER`/`GULFSTREAM`/`DASSAULT` are deliberately NOT
#: here. Those manufacturers also operate finance arms — Textron Financial,
#: Bombardier Capital — that record ordinary aircraft loans, so matching the
#: bare marque would promote routine financing to the most severe tier. They
#: are matched below only when a support/programme/service word accompanies
#: them, which is what distinguishes a programme default from a loan.
_CRIPPLING_PATTERN = re.compile(
    # Tax and government warrants
    r"\b(IRS|INTERNAL REVENUE|DEPARTMENT OF REVENUE|DEPT OF REVENUE|"
    r"STATE OF [A-Z]+ TAX|TAX COMMISSION|TAXATION|FRANCHISE TAX|"
    r"COMPTROLLER|TREASURY|COUNTY TAX|TAX COLLECTOR|REVENUE SERVICE|"
    r"LEVY|WARRANT|"
    # Courts and enforcement
    r"JUDGMENT|JUDGEMENT|WRIT|ATTACHMENT|SHERIFF|COURT|MARSHAL|"
    # Hourly engine / airframe programmes
    r"JSSI|JET SUPPORT|MSP|CORPORATECARE|CORPORATE CARE|POWER ADVANTAGE|"
    r"ESP GOLD|TAP BLUE|ENGINE PROGRAM|ENGINE PROGRAMME|"
    # Engine OEMs. These build and maintain engines; they do not finance
    # airframes, so the bare name is safe to match.
    r"ROLLS-ROYCE|ROLLS ROYCE|PRATT & WHITNEY|PRATT AND WHITNEY|"
    r"WILLIAMS INTERNATIONAL|HONEYWELL|GE AVIATION|CFM INTERNATIONAL|"
    r"SAFRAN|WESTINGHOUSE)\b"
)

#: Airframe OEMs that ALSO run captive finance arms.
#:
#: Matched as crippling only alongside a support/programme/parts word. A bare
#: "Textron Financial Corporation" filing is an aircraft loan and belongs in
#: Tier 1; "Textron Aviation Parts & Programs" is an unpaid support account and
#: belongs in Tier 3. Matching the marque alone would conflate the two and
#: promote every financed Cessna to the most severe tier.
_OEM_MARQUE_PATTERN = re.compile(
    r"\b(TEXTRON|BOMBARDIER|GULFSTREAM|DASSAULT|CESSNA|BEECHCRAFT|"
    r"EMBRAER|AIRBUS|BOEING|PILATUS|CIRRUS)\b"
)
_OEM_SUPPORT_PATTERN = re.compile(
    r"\b(SUPPORT|PROGRAM|PROGRAMME|PARTS|SERVICE CENTER|SERVICE CENTRE|"
    r"MAINTENANCE|SPARES|AOG|COMPLETIONS|MRO)\b"
)
#: Finance-arm markers that keep an OEM filing in routine territory.
_OEM_FINANCE_PATTERN = re.compile(
    r"\b(FINANCIAL|FINANCE|CAPITAL|CREDIT|LEASING|LEASE|TRUST)\b"
)

#: Major MRO and contract-fuel networks. Material on one filing; see
#: `promote_for_contagion` for the escalation when several appear on a fleet.
#:
#: These file against an airframe when a maintenance or fuel account goes
#: unpaid, which is a working-capital signal rather than a routine financing
#: event — but a single disputed invoice is not grounds for the top tier.
_MRO_FUEL_PATTERN = re.compile(
    r"\b(WEST STAR|DUNCAN AVIATION|STANDARD AERO|STANDARDAERO|"
    r"CONSTANT AVIATION|JET AVIATION|SIGNATURE FLIGHT|ATLANTIC AVIATION|"
    r"AVFUEL|WORLD FUEL|TITAN AVIATION|EPIC FUEL|PHILLIPS 66 AVIATION|"
    r"CLAY LACY|ELLIOTT AVIATION|STEVENS AEROSPACE|GARMIN SERVICE)\b"
)

#: Release of a previously recorded interest. The opposite of an encumbrance.
_RELEASE_DOC_TYPES = frozenset({"REL", "RELEASE"})

#: §2A Proxy 2 — days an unreleased filing may sit before it stops reading as
#: routine.
#:
#: A genuine nuisance or administrative DISPUTE is paid off or bonded over
#: within roughly 90-180 days, because the owner needs clean title to
#: refinance, sell or charter the hull. One still unreleased past that window
#: signals illiquidity or active litigation rather than paperwork.
#:
#: Deliberately does NOT promote beyond Tier 2: age alone evidences that
#: something is unresolved, not that it is grounding-grade.
LIEN_STALE_DAYS = 180

#: Proxy 2 applies ONLY where the claimant is NOT an identified financier.
#:
#: This exclusion is the whole reason the proxy is usable. An aircraft loan
#: legitimately sits unreleased for the TERM OF THE LOAN — five to ten years —
#: so age says nothing adverse about it. Measured on live data: 401 of 680
#: active filings (59%) are older than 180 days, and the old ones include PNC
#: BANK NA, BANC OF AMERICA LEASING and FIRST HORIZON BANK behaving exactly as
#: intended. Promoting on age alone moved 290 filings to Tier 2 and would have
#: marked most financed aircraft as distressed — reintroducing the inversion
#: the tiering exists to prevent, from the opposite direction.
#:
#: So persistence is evidence only where prompt release was the expectation:
#: an unnamed or unclassifiable claimant, or a small measured claim. A bank's
#: filing is dated, but its age is not a finding.
_PERSISTENCE_EXEMPT = frozenset({FINANCIER})


def _is_oem_support_claim(normalized: str) -> bool:
    """
    True for an airframe-OEM filing that is a support account, not a loan.

    Textron, Bombardier, Gulfstream and Dassault all run captive finance arms
    alongside their parts and programme businesses, so the marque alone cannot
    tell a grounding-grade support default from an ordinary aircraft loan.
    Requiring a support word — and excluding an explicit finance word — keeps
    "Textron Financial Corporation" in Tier 1 while catching "Textron Aviation
    Parts & Programs".
    """
    if not _OEM_MARQUE_PATTERN.search(normalized):
        return False
    if _OEM_FINANCE_PATTERN.search(normalized):
        return False
    return bool(_OEM_SUPPORT_PATTERN.search(normalized))


def lien_tier(
    party: Optional[str] = None,
    doc_type: Optional[str] = None,
    claim_amount: Optional[float] = None,
    doc_date: Optional[Any] = None,
    now: Optional[Any] = None,
) -> int:
    """
    Severity tier 1-3 for one lien filing (§2A).

    Amount wins when known, because it is the discriminator the specification
    actually names. DOCINDEX never supplies one, so in practice the party name
    and doc_type decide:

        tax / court / engine OEM / programme  -> 3  (crippling)
        OEM support account (not its finance
          arm — see _is_oem_support_claim)    -> 3
        major MRO or contract-fuel network    -> 2  (material)
        trade creditor: MRO, fuel, FBO        -> 2
        bank, lessor, owner trust             -> 1  (routine financing)
        unclassifiable                        -> 2  (cautious middle)

    PROXY 2 — PERSISTENCE. A Tier 1 filing still unreleased after
    LIEN_STALE_DAYS is promoted to Tier 2. Nuisance disputes get paid or bonded
    over within ~180 days so the owner can refinance or charter the hull
    cleanly; one that has not signals illiquidity or litigation. Requires
    `doc_date`; without it the promotion simply does not apply, because age
    cannot be inferred from absence.

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
        doc_date: Filing date, for the persistence promotion. A date or an
            ISO string; ignored when absent.
        now: Reference date, for testing.

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
        # An amount below the Tier 2 floor is a measured small claim, so the
        # persistence proxy still applies — a $2k filing left unreleased for a
        # year is the signal Proxy 2 exists to catch.
        return _apply_persistence(TIER_NUISANCE, doc_date, now)

    normalized = normalize_party(party)
    # No party on the filing: missing data, not a middling claim.
    #
    # Persistence does NOT apply here either. 521 of 680 active filings (77%)
    # carry no party, 242 of them older than 180 days — so promoting on age
    # alone would move a third of all filings to Tier 2 on the strength of a
    # blank field. Without knowing WHO filed, we cannot say whether prompt
    # release was ever the expectation: a bank's loan is meant to outlive the
    # window, a vendor's dispute is not. Age is only evidence once that is
    # known.
    if not normalized:
        return TIER_NUISANCE

    if _CRIPPLING_PATTERN.search(normalized):
        return TIER_CRIPPLING

    if _is_oem_support_claim(normalized):
        return TIER_CRIPPLING

    if _MRO_FUEL_PATTERN.search(normalized):
        return TIER_MATERIAL

    party_class = classify_party(party)
    if party_class == FINANCIER:
        # Routine financing. NOT subject to the persistence promotion: a loan
        # legitimately outlives the 180-day window by years.
        return TIER_NUISANCE
    if party_class == DISTRESS:
        return TIER_MATERIAL
    # Named but unclassifiable.
    return TIER_MATERIAL


def _apply_persistence(
    tier: int,
    doc_date: Optional[Any],
    now: Optional[Any] = None,
    party_class: Optional[str] = None,
) -> int:
    """
    §2A Proxy 2 — promote a stale Tier 1 filing to Tier 2.

    Only ever promotes Tier 1, and only by one step. Two things are left alone:

      * an UNDATED filing — age that cannot be measured must not be inferred,
        the same rule applied to churn and to coverage flags elsewhere;
      * a filing by an identified FINANCIER — see _PERSISTENCE_EXEMPT. A loan
        is meant to sit unreleased for its term, so its age is not a finding.
    """
    if tier != TIER_NUISANCE or doc_date is None:
        return tier
    if party_class in _PERSISTENCE_EXEMPT:
        return tier

    filed = _coerce_date(doc_date)
    if filed is None:
        return tier

    reference = _coerce_date(now) or datetime.now(timezone.utc).date()
    if (reference - filed).days > LIEN_STALE_DAYS:
        return TIER_MATERIAL
    return tier


def _coerce_date(value: Any):
    """A `date` from a date, datetime or ISO string; None if unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except (TypeError, ValueError):
        return None


# ── Proxy 3: multi-tail contagion ────────────────────────────────────────────

#: Distinct tails a single claimant must hit before it reads as systemic.
CONTAGION_TAIL_THRESHOLD = 2


def promote_for_contagion(
    filings: List[Dict[str, Any]],
    now: Optional[Any] = None,
) -> Dict[str, int]:
    """
    §2A Proxy 3 — certificate-wide vendor distress.

    One unpaid vendor on one aircraft is a dispute. The SAME claimant filing
    against two or more separate tails on one certificate, or two or more
    different MRO/fuel claimants across the fleet, is an operator that is not
    paying its vendors — and the exposure is to the certificate, not to the
    airframe that happens to carry the filing. Those cases promote to Tier 3.

    Operates on the whole fleet at once, because contagion is invisible from a
    single filing. Call it with every active filing on the certificate.

    Args:
        filings: Dicts with `tail_number`, `party`, `doc_type` and optionally
            `doc_date` / `claim_amount`.
        now: Reference date, for testing.

    Returns:
        {tail_number: tier} carrying the promoted tier for each tail that has
        one. Tails with no filing are absent. A tail already at Tier 3 stays
        there.
    """
    by_claimant: Dict[str, set] = {}
    mro_tails: set = set()
    base: Dict[str, int] = {}

    for filing in filings or []:
        tail = str(filing.get("tail_number") or "").strip().upper()
        if not tail:
            continue
        if str(filing.get("doc_type") or "").strip().upper() in _RELEASE_DOC_TYPES:
            continue

        tier = lien_tier(
            party=filing.get("party"),
            doc_type=filing.get("doc_type"),
            claim_amount=filing.get("claim_amount"),
            doc_date=filing.get("doc_date") or filing.get("date"),
            now=now,
        )
        base[tail] = max(base.get(tail, 0), tier)

        normalized = normalize_party(filing.get("party"))
        if not normalized:
            # An unnamed claimant cannot be shown to be the SAME claimant as
            # any other, so it cannot evidence contagion. Counting blanks
            # together would make every fleet with two unnamed filings look
            # systemically distressed — 67% of rows have no party.
            continue

        # ONLY TRADE CREDITORS CAN BE CONTAGIOUS.
        #
        # A single lender financing several tails on one certificate is the
        # most ordinary arrangement in aviation — a fleet bought on one credit
        # facility. Counting that as contagion flagged every well-financed
        # operator RED, which is precisely the count-over-severity inversion
        # the tiering exists to prevent. Measured during development: one bank
        # across three tails escalated all three to Tier 3.
        #
        # An unpaid MRO or fuel account across multiple tails is the opposite
        # signal: the operator is not paying vendors fleet-wide.
        is_trade = (
            bool(_MRO_FUEL_PATTERN.search(normalized))
            or classify_party(filing.get("party")) == DISTRESS
        )
        if not is_trade:
            continue

        by_claimant.setdefault(normalized, set()).add(tail)
        mro_tails.add(tail)

    # One trade creditor across several tails.
    contagious: set = set()
    for claimant, tails in by_claimant.items():
        if len(tails) >= CONTAGION_TAIL_THRESHOLD:
            contagious |= tails

    # Several DISTINCT trade creditors across the fleet, even if each hit only
    # one tail. Two different vendors filing on one certificate is the same
    # finding as one vendor filing twice.
    if len(by_claimant) >= CONTAGION_TAIL_THRESHOLD:
        contagious |= mro_tails

    return {
        tail: (TIER_CRIPPLING if tail in contagious else tier)
        for tail, tier in base.items()
    }
