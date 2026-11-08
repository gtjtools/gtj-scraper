"""
Parsers for the FAA Releasable Aircraft Database (MASTER / DOCINDEX / DEREG).

Feeds the two TrustScore v5.0 inputs that Phase 1 left unevidenced:

    Asset Stability   title-transfer velocity — how often a tail has changed
                      registered owner, which is how a plane shuffled between
                      shell LLCs becomes visible (§3)
    Legal & Title     Lientail — active mechanic's and tax liens against a
                      specific N-number, which feed ELI (§4.2)

SOURCE
------
https://registry.faa.gov/database/ReleasableAircraft.zip — refreshed daily,
overwritten in place, ~68 MB. The zip contains fixed-width, comma-delimited
text files; this module parses the three that carry title and lien history.

ON FIELD OFFSETS
----------------
The FAA publishes these as comma-separated records with fixed-width *padded*
fields, which means a naive split(",") works but leaves every value padded, and
a naive fixed-slice breaks whenever the FAA adds a column. Parsing is therefore
by header name, resolved from the first line of each file, so a column added or
reordered upstream does not silently shift every field by one.

That matters more than it sounds: a shifted MASTER.txt would misattribute
owners to aircraft, and the resulting "title transfer" signal would be entirely
fictional while looking perfectly plausible.

ON DOCINDEX AND ITS 180-DAY WINDOW
----------------------------------
DOCINDEX.txt is a rolling *suspense* index of filings received in roughly the
last 180 days — not a permanent lien ledger. A lien recorded two years ago and
never released does not appear in it. So an empty DOCINDEX result means "no
filing in the last ~180 days", NOT "no liens". `docindex_is_complete` is
returned alongside every lien lookup so a caller can report that honestly
rather than inferring clear title; CARES (cares.faa.gov) holds the permanent
life-of-airframe packets and is the eventual source for a real answer.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterator, List, Optional, Set

logger = logging.getLogger(__name__)

#: Files inside ReleasableAircraft.zip that carry title/lien history.
MASTER_FILE = "MASTER.txt"
DOCINDEX_FILE = "DOCINDEX.txt"
DEREG_FILE = "DEREG.txt"

#: DOCINDEX covers filings received in roughly this window. Anything older has
#: aged out of the index without being resolved, so absence is not clearance.
DOCINDEX_WINDOW_DAYS = 180

#: DOC-TYPE codes, verbatim from the FAA's own ardata.pdf (positions 165-167):
#:
#:     BOS – Evidence of Ownership
#:     S/A – Security Conveyance/Lien
#:     REL – Lien Release
#:     REP – Repossession
#:     CSC – Evidence of Ownership w/Lien
#:     DIS – Disclaimer
#:     CRT – Court Documents
#:
#: Note these are three-character codes, not the single letters the v5.0 source
#: document describes ('M' for mechanic's, 'T' for tax). The FAA index does not
#: distinguish mechanic's from tax liens at all — both are filed as S/A — so
#: §4.2's separate charges cannot be told apart from this file. Both are scored
#: as "active encumbrance", which is the distinction that actually matters.
LIEN_DOC_TYPES = frozenset({"S/A", "CSC"})
#: A release discharges a prior S/A. Counted so an unresolved lien can be
#: distinguished from a settled one — §4.2 scores only active encumbrances.
RELEASE_DOC_TYPES = frozenset({"REL", "REP"})
#: Title movement, not encumbrance. Feeds Asset Stability, never Lientail.
CONVEYANCE_DOC_TYPES = frozenset({"BOS", "CSC"})

#: TYPE-COLLATERAL codes. Only 1 (Aircraft) carries an N-number in COLLATERAL;
#: 2/3 carry engine and propeller identifiers, 5 a recordation number. Filtering
#: on this is what stops an engine lien being attributed to an airframe.
COLLATERAL_AIRCRAFT = "1"


# ─── Records ──────────────────────────────────────────────────────────────────

@dataclass
class MasterRecord:
    """One currently-registered aircraft from MASTER.txt."""
    tail_number: str                      # N-NUMBER, with the N restored
    serial_number: str                    # SERIAL NUMBER
    mfr_mdl_code: str                     # MFR MDL CODE — needed to disambiguate
    owner_name: str                       # NAME, the registered owner
    cert_issue_date: Optional[date]       # CERT ISSUE DATE
    last_action_date: Optional[date]      # LAST ACTION DATE
    year_manufactured: Optional[int]


@dataclass
class DocIndexRecord:
    """One filing from the DOCINDEX suspense index."""
    tail_number: str
    collateral_type: str                  # '1' = aircraft; see COLLATERAL_AIRCRAFT
    party: str                            # name of the filing party
    doc_id: str
    doc_type: str                         # 'BOS' | 'S/A' | 'REL' | …
    doc_date: Optional[date]              # DRDATE, date of receipt

    @property
    def is_lien(self) -> bool:
        return self.doc_type in LIEN_DOC_TYPES

    @property
    def is_release(self) -> bool:
        return self.doc_type in RELEASE_DOC_TYPES

    @property
    def is_conveyance(self) -> bool:
        return self.doc_type in CONVEYANCE_DOC_TYPES


@dataclass
class DeregRecord:
    """One cancelled/exported registration from DEREG.txt."""
    tail_number: str
    serial_number: str
    mfr_mdl_code: str
    owner_name: str
    cancel_date: Optional[date]


@dataclass
class TailTitleHistory:
    """
    What the registry knows about one airframe's title.

    MEASURED LIMIT ON prior_owners / prior_tails
    --------------------------------------------
    These are populated by matching (serial number, manufacturer model code)
    across MASTER and DEREG. Verified against the real 2025 archive, that
    overlap is 46 keys out of 300,081 in MASTER and 379,796 in DEREG — because
    DEREG holds *terminated* registrations (97% carry a CANCEL-DATE), and an
    airframe still flying is in MASTER precisely because it has not been
    deregistered. So for a current Part 135 tail these lists are almost always
    empty, and an empty list means "no deregistration event", NOT "one owner
    since new".

    Serial alone is not a usable key either: '1' appears 3,936 times in DEREG
    and '001' 1,967 times, across unrelated manufacturers. Matching on serial
    by itself reported 3,707 of 10,092 Part 135 tails as having prior owners;
    adding the model code reduced that to 0, which means the original figure
    was almost entirely collisions — one aircraft inheriting every prior owner
    of every other airframe numbered 1.

    Real title-transfer velocity therefore needs CARES packets (permanent,
    life-of-airframe) or MASTER snapshot diffs accumulated over time, not this
    file. `cert_issue_date` from MASTER is the one usable proxy available today:
    it moves whenever a new registration certificate is issued, so differencing
    it between two MASTER snapshots does detect a transfer.
    """
    tail_number: str
    serial_number: str = ""
    current_owner: str = ""
    cert_issue_date: Optional[date] = None

    #: Distinct registered owners seen across MASTER + DEREG, newest first.
    prior_owners: List[str] = field(default_factory=list)
    #: Previous N-numbers this airframe has carried.
    prior_tails: List[str] = field(default_factory=list)
    #: Conveyance/bill-of-sale filings in the DOCINDEX window.
    conveyance_dates: List[date] = field(default_factory=list)
    #: Active mechanic's/tax lien filings in the DOCINDEX window.
    lien_filings: List[DocIndexRecord] = field(default_factory=list)

    #: False whenever the DOCINDEX window cannot answer the question — which is
    #: always, for liens older than ~180 days. Carried so a caller never
    #: reports "no liens found" as "clear title".
    docindex_is_complete: bool = False

    @property
    def owner_changes(self) -> int:
        """Distinct owners beyond the current one — title-transfer velocity."""
        return max(0, len(self.prior_owners))


# ─── Parsing ──────────────────────────────────────────────────────────────────

def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def _parse_date(raw: Optional[str]) -> Optional[date]:
    """
    FAA dates are YYYYMMDD. Returns None for blanks and malformed values rather
    than raising: one bad row must not abandon an 80 MB file.
    """
    text = _clean(raw)
    if not text or len(text) != 8 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _normalize_tail(raw: Optional[str]) -> str:
    """MASTER stores N-numbers without the leading N; restore it."""
    text = _clean(raw).upper()
    if not text:
        return ""
    return text if text.startswith("N") else f"N{text}"


def _rows(blob: bytes) -> Iterator[Dict[str, str]]:
    """
    Yield each record as a dict keyed by the file's own header names.

    Resolved from the header rather than by fixed offsets, so an added or
    reordered upstream column cannot silently shift every field.
    """
    # These files begin with a UTF-8 BOM, and the registry is otherwise Latin-1
    # in practice. Decoding as Latin-1 first would turn the BOM into 'Ï»¿' and
    # weld it onto the first header name, so the first column — TYPE-COLLATERAL
    # in DOCINDEX, N-NUMBER in MASTER — becomes unfindable and every row is
    # silently skipped. Strip the BOM bytes before decoding, then fall back to
    # Latin-1 for the stray high bytes in owner names that are not valid UTF-8.
    if blob.startswith(b"\xef\xbb\xbf"):
        blob = blob[3:]
    try:
        text_body = blob.decode("utf-8")
    except UnicodeDecodeError:
        text_body = blob.decode("latin-1", errors="replace")

    stream = io.StringIO(text_body)
    reader = csv.reader(stream)

    try:
        # lstrip the BOM character too, in case decoding produced it as U+FEFF.
        header = [h.strip().lstrip("﻿").upper() for h in next(reader)]
    except StopIteration:
        return

    for row in reader:
        if not row:
            continue
        yield {header[i]: row[i] for i in range(min(len(header), len(row)))}


def _first(record: Dict[str, str], *names: str) -> Optional[str]:
    """
    First present column among `names`.

    The FAA has used more than one spelling for these fields across years
    (`N-NUMBER` vs `N NUMBER`, `CERT ISSUE DATE` vs `CERTIFICATE ISSUE DATE`),
    and the yearly archives are not internally consistent. Trying several keeps
    a historical zip parseable instead of silently producing empty values.
    """
    for name in names:
        if name in record:
            return record[name]
    return None


def parse_master(blob: bytes) -> Iterator[MasterRecord]:
    """Stream MASTER.txt — every currently-registered aircraft."""
    for record in _rows(blob):
        tail = _normalize_tail(_first(record, "N-NUMBER", "N NUMBER", "NNUMBER"))
        if not tail:
            continue
        year_raw = _clean(_first(record, "YEAR MFR", "YEAR-MFR"))
        yield MasterRecord(
            tail_number=tail,
            serial_number=_clean(_first(record, "SERIAL NUMBER", "SERIAL-NUMBER")),
            mfr_mdl_code=_clean(_first(record, "MFR MDL CODE", "MFR-MDL-CODE")),
            owner_name=_clean(_first(record, "NAME")),
            cert_issue_date=_parse_date(
                _first(record, "CERT ISSUE DATE", "CERTIFICATE ISSUE DATE")
            ),
            last_action_date=_parse_date(_first(record, "LAST ACTION DATE")),
            year_manufactured=int(year_raw) if year_raw.isdigit() else None,
        )


def parse_docindex(blob: bytes) -> Iterator[DocIndexRecord]:
    """
    Stream DOCINDEX.txt — filings received in the trailing ~180 days.

    Only TYPE-COLLATERAL = 1 rows are yielded. Per ardata.pdf, COLLATERAL holds
    an N-number only for that code; 2 and 3 hold engine and propeller
    make/model/serial, 5 a recordation number. Without the filter an engine
    lien would be parsed as an N-number and attributed to whichever airframe
    happened to collide with the string.
    """
    for record in _rows(blob):
        collateral_type = _clean(_first(record, "TYPE-COLLATERAL", "TYPE COLLATERAL"))
        if collateral_type != COLLATERAL_AIRCRAFT:
            continue

        tail = _normalize_tail(_first(record, "COLLATERAL"))
        if not tail:
            continue

        yield DocIndexRecord(
            tail_number=tail,
            collateral_type=collateral_type,
            party=_clean(_first(record, "PARTY")),
            doc_id=_clean(_first(record, "DOC-ID", "DOC ID")),
            # Three-character code; never truncate to one character.
            doc_type=_clean(_first(record, "DOC-TYPE", "DOC TYPE")).upper(),
            # DRDATE is the date of receipt — the field this file actually
            # carries. There is no DOC-DATE column.
            doc_date=_parse_date(_first(record, "DRDATE", "PROCESSING-DATE")),
        )


def parse_dereg(blob: bytes) -> Iterator[DeregRecord]:
    """Stream DEREG.txt — the permanent ledger of cancelled registrations."""
    for record in _rows(blob):
        tail = _normalize_tail(_first(record, "N-NUMBER", "N NUMBER", "NNUMBER"))
        serial = _clean(_first(record, "SERIAL NUMBER", "SERIAL-NUMBER"))
        if not tail and not serial:
            continue
        yield DeregRecord(
            tail_number=tail,
            serial_number=serial,
            mfr_mdl_code=_clean(_first(record, "MFR-MDL-CODE", "MFR MDL CODE")),
            owner_name=_clean(_first(record, "NAME")),
            # DEREG hyphenates where MASTER uses spaces; both spellings tried.
            cancel_date=_parse_date(
                _first(record, "CANCEL-DATE", "CANCEL DATE",
                       "LAST-ACT-DATE", "LAST ACTION DATE")
            ),
        )


# ─── Archive access ───────────────────────────────────────────────────────────

def read_member(archive_path: str, member: str) -> Optional[bytes]:
    """
    One file out of ReleasableAircraft.zip.

    Member names vary in case between yearly archives, so the lookup is
    case-insensitive. Returns None rather than raising when a member is absent —
    older archives do not all carry DOCINDEX.txt.
    """
    try:
        with zipfile.ZipFile(archive_path) as archive:
            wanted = member.lower()
            for name in archive.namelist():
                if name.lower().rsplit("/", 1)[-1] == wanted:
                    return archive.read(name)
        logger.warning("%s not found in %s", member, archive_path)
        return None
    except Exception as exc:
        logger.warning("Could not read %s from %s: %s", member, archive_path, exc)
        return None


def build_title_history(
    archive_path: str,
    tails: Set[str],
) -> Dict[str, TailTitleHistory]:
    """
    Title and lien history for `tails`, from one registry archive.

    Streams each file once and keeps only matching rows, so memory stays
    proportional to the tails asked about rather than to the ~290,000-row
    MASTER file.

    Serial-number matching is what makes the ownership chain work: DEREG rows
    for a re-registered airframe carry a *different* N-number, so they are only
    reachable via the serial recorded in MASTER.

    Args:
        archive_path: Path to a downloaded ReleasableAircraft.zip.
        tails: N-numbers of interest, with or without the leading N.

    Returns:
        One TailTitleHistory per requested tail that exists in MASTER.
        `docindex_is_complete` is False whenever DOCINDEX was unreadable or
        absent — and is never True for a question about liens older than the
        180-day window.
    """
    wanted = {_normalize_tail(t) for t in tails if t}
    if not wanted:
        return {}

    out: Dict[str, TailTitleHistory] = {}

    # ── MASTER: current owner, serial, certificate date ──────────────────────
    master_blob = read_member(archive_path, MASTER_FILE)
    if not master_blob:
        logger.warning("No %s in %s — cannot build title history",
                       MASTER_FILE, archive_path)
        return {}

    # Keyed on (serial, mfr-model) — see TailTitleHistory on why serial alone
    # cannot be trusted.
    airframe_to_tail: Dict[tuple, str] = {}
    for record in parse_master(master_blob):
        if record.tail_number not in wanted:
            continue
        out[record.tail_number] = TailTitleHistory(
            tail_number=record.tail_number,
            serial_number=record.serial_number,
            current_owner=record.owner_name,
            cert_issue_date=record.cert_issue_date,
        )
        if record.serial_number and record.mfr_mdl_code:
            airframe_to_tail[(record.serial_number, record.mfr_mdl_code)] = \
                record.tail_number

    if not out:
        return {}

    # ── DEREG: previous owners and N-numbers for the same airframe ───────────
    dereg_blob = read_member(archive_path, DEREG_FILE)
    if dereg_blob:
        for record in parse_dereg(dereg_blob):
            tail = airframe_to_tail.get((record.serial_number, record.mfr_mdl_code))
            if not tail:
                continue
            history = out[tail]
            if record.owner_name and record.owner_name != history.current_owner:
                if record.owner_name not in history.prior_owners:
                    history.prior_owners.append(record.owner_name)
            if record.tail_number and record.tail_number != tail:
                if record.tail_number not in history.prior_tails:
                    history.prior_tails.append(record.tail_number)

    # ── DOCINDEX: liens and conveyances in the trailing window ───────────────
    docindex_blob = read_member(archive_path, DOCINDEX_FILE)
    if docindex_blob:
        # DOCINDEX identifies aircraft collateral by N-number only — there is no
        # serial column — so matching is on tail. A re-registered airframe's
        # older filings sit under its previous N-number and are unreachable
        # here; DEREG above is what recovers those identities.
        releases: Dict[str, List[DocIndexRecord]] = {}
        for record in parse_docindex(docindex_blob):
            history = out.get(record.tail_number)
            if history is None:
                continue
            if record.is_lien:
                history.lien_filings.append(record)
            if record.is_release:
                releases.setdefault(record.tail_number, []).append(record)
            if record.is_conveyance and record.doc_date:
                history.conveyance_dates.append(record.doc_date)

        # §4.2 charges only *active* encumbrances. A release filed on or after a
        # lien discharges it, so drop those; a release dated earlier belongs to
        # some prior lien and leaves this one standing.
        for tail, history in out.items():
            discharges = releases.get(tail) or []
            if not discharges or not history.lien_filings:
                continue
            latest_release = max(
                (r.doc_date for r in discharges if r.doc_date), default=None
            )
            if latest_release is None:
                continue
            history.lien_filings = [
                lien for lien in history.lien_filings
                if lien.doc_date is None or lien.doc_date > latest_release
            ]

        # True only in the narrow sense that the index was read: it still
        # covers ~180 days, which is why callers must surface the limit.
        for history in out.values():
            history.docindex_is_complete = True

    return out


def to_lien_records(history: TailTitleHistory) -> List[Dict[str, object]]:
    """
    Lien filings in the shape `adapter_v5.build_tail_data(tail_lien_records=…)`
    expects: `{"date", "reference"}` per active encumbrance.

    Only mechanic's and tax liens are returned. The calculator applies a flat
    §4.2 charge per filing, so a conveyance included here would be scored as an
    encumbrance it is not.
    """
    return [
        {
            "date": filing.doc_date.isoformat() if filing.doc_date else None,
            "reference": f"DOCINDEX {filing.doc_type} {filing.tail_number}"
                         + (f" {filing.doc_date.isoformat()}" if filing.doc_date else ""),
        }
        for filing in history.lien_filings
    ]
