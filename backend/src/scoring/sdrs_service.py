# src/scoring/sdrs_service.py
"""
FAA Service Difficulty Reporting System (SDRS) Service

Downloads SDR bulk extracts from the FAA, filters them to Part 135 operations,
and converts matching reports into fleet events for the TrustScore calculator.
SDRs capture active mechanical deterioration — cracks, corrosion, component
failures, emergency procedures — which is risk that never reaches NTSB because
nothing was damaged and nobody was hurt.

TrustScore 5.0 Data Sources, item 6 [NEW].
Data source: https://www.faa.gov/av-info/download_SDR

Field naming quirks, per the source document:
  - SubmitterTypeCode is "E" for Part 135 operations; everything else is
    filtered out (air carriers, manufacturers, general aviation).
  - RegistryNNumber omits the leading "N". Tail N427QS appears as "427QS".

This module is additive: it contributes new events and never modifies events
produced by other sources. A failure here returns an empty list, leaving the
TrustScore exactly as it would have been without SDRS.
"""

import csv
import io
import logging
import re
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

SDRS_DOWNLOAD_URL = "https://www.faa.gov/av-info/download_SDR"

# Per the source document: Part 135 operations only.
PART_135_SUBMITTER_CODE = "E"

# HTTP timeout for FAA requests (seconds). The bulk extract is large, so this
# is deliberately more generous than the enforcement scraper's 60s.
_HTTP_TIMEOUT = 300.0

# Column names vary in case and spacing between extracts, so lookups are made
# against a normalized key (lowercase, non-alphanumerics stripped).
_FIELD_ALIASES = {
    "submitter_type": ("submittertypecode",),
    "tail_number": ("registrynnumber", "nnumber", "aircraftregistrynnumber"),
    "operator": ("operatorname", "submittername", "operator"),
    "report_date": ("difficultydate", "reportdate", "receiptdate", "date"),
    "control_number": ("controlnumber", "recordid", "sdrnumber"),
    "part_name": ("partname", "componentname"),
    "discrepancy": ("discrepancynarrative", "remarks", "narrative", "discrepancy"),
    "stage": ("stageofoperation", "stage"),
    # Serial is a SECONDARY key, used only when the N-number is absent or
    # unmatched — see `_serial_index` for why it can never be primary.
    "serial_number": ("aircraftserialnumber", "serialnumber", "acserialno",
                      "aircraftserialno"),
    "make": ("aircraftmake", "make", "manufacturername"),
    "model": ("aircraftmodel", "model", "aircraftmodelname"),
}


def normalize_serial(raw: Optional[str]) -> str:
    """
    Reduce a serial number to the form two sources can be compared on.

    The same airframe is written `60-271` (type-prefixed, as SDRS and
    manufacturers do), `60271`, `271` (as `gtj.aircraft` holds it) and `0271`.
    A prefix-preserving normalization makes those *fail* to match, which is
    the opposite of what is wanted — so the type prefix is dropped and only
    the trailing serial portion is kept.

    Dropping the prefix costs nothing in precision, because `_serial_match_key`
    re-qualifies the result with the make and model. That is a stronger
    discriminator than a prefix the sources do not agree on anyway.

        60-271  -> 271
        60271   -> 271      (hyphen-free form of the same)
        271     -> 271
        0271    -> 271

    Note `60271` is deliberately treated as prefix + serial. A genuine
    six-digit serial would collide, but combined with make/model that is far
    rarer than the formatting disagreement this resolves.
    """
    text = re.sub(r"[^A-Z0-9]", "", (raw or "").upper())
    if not text:
        return ""
    # Hyphenated form: keep the part after the last separator.
    raw_upper = (raw or "").upper()
    if "-" in raw_upper:
        tail_part = re.sub(r"[^A-Z0-9]", "", raw_upper.rsplit("-", 1)[-1])
        if tail_part:
            text = tail_part
    return text.lstrip("0") or text


def _model_digits(make: str, model: str) -> str:
    """
    The numeric part of a model designation, as a cross-source type qualifier.

    SDRS and `gtj.aircraft` encode aircraft type in incompatible ways:

        SDRS            make="LEARJET"   model="LR-60"
        gtj.aircraft    make_model="LR-60-60"
        SDRS            make="CESSNA"    model="560XL"
        gtj.aircraft    make_model="CE-560-560XL"

    One uses manufacturer names, the other ICAO-style codes (`CE-`, `BHT-`,
    `EMB-`), so neither the make string nor the full model string can be
    compared directly. Building a manufacturer-name-to-ICAO-code mapping is a
    data project in its own right and would be wrong in the tails.

    The digits survive both encodings: `60` for a Learjet 60, `560` for a
    Citation Excel, `407` for a Bell 407. They are a weaker discriminator than
    a full type match, which is acceptable here because the digits only ever
    QUALIFY a serial that already matched — the pair has to agree, not the
    digits alone.
    """
    blob = f"{make or ''} {model or ''}".upper()
    digits = re.findall(r"\d+", blob)
    if not digits:
        return ""
    # Longest run, which is the model number rather than a variant suffix:
    # "LR-60-60" -> 60, "CE-560-560XL" -> 560, "BD-100-1A10" -> 100.
    return max(digits, key=len)


def _serial_match_key(serial: str, make: str, model: str) -> str:
    """
    A serial-based match key qualified by aircraft type.

    SERIAL ALONE IS NOT A KEY. Measured on `gtj.aircraft`: 11,166 aircraft
    carry a serial but only 10,395 are distinct — serial `226` is shared by six
    different airframes, `236` by six more. Matching on the bare number would
    attach one operator's maintenance reports to another's aircraft, which is
    the same mistake that fabricated 3,707 false ownership chains during the
    FAA registry work.

    Qualifying with the model digits collapses that: two aircraft sharing
    serial `271` are rarely both -60s. See `_model_digits` for why digits
    rather than the type string.

    Returns "" when either part is missing — an unqualified serial is not
    matchable and must not fall through to a bare-number comparison.
    """
    normalized_serial = normalize_serial(serial)
    if not normalized_serial:
        return ""
    type_token = _model_digits(make, model)
    if not type_token:
        return ""
    return f"{normalized_serial}|{type_token}"


def _serial_index(fleet_serials: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    """
    Map a qualified serial key to the tail number it belongs to.

    Args:
        fleet_serials: Dicts with `tail_number`, `serial_number` and either
            `make_model` or separate `make`/`model`, from `gtj.aircraft`.

    Returns:
        {serial_key: tail_number}. Ambiguous keys — the same qualified serial
        on two different tails — are DROPPED rather than guessed, because a
        wrong attribution is worse than a missed one.
    """
    index: Dict[str, str] = {}
    ambiguous = set()
    for entry in fleet_serials or []:
        make = entry.get("make") or ""
        model = entry.get("model") or ""
        if not (make or model):
            # gtj.aircraft stores a combined "LR-60-60" style string.
            combined = str(entry.get("make_model") or "")
            make, model = combined, combined
        key = _serial_match_key(str(entry.get("serial_number") or ""), make, model)
        tail = normalize_tail_number(str(entry.get("tail_number") or ""))
        if not key or not tail:
            continue
        if key in index and index[key] != tail:
            ambiguous.add(key)
            continue
        index[key] = tail
    for key in ambiguous:
        index.pop(key, None)
    return index

# Narrative keywords mapped to the TrustScore v5.0 §6.2 maintenance severity
# schedule. Ordered most severe first; the first match wins.
#
#   20  In-flight shutdown (IFSD), uncontained engine failure
#   15  Precautionary aborted takeoff, flight control malfunction, emergency descent
#   10  In-flight cabin smoke or toxic fume event
#    5  Unscheduled landing or divert on secondary subsystem failure
#
# SDRS carries no severity field, so severity is inferred from the discrepancy
# narrative. These buckets are fixed by the specification — do not retune them
# without a corresponding change to the document.
_SEVERITY_KEYWORDS = (
    (("in-flight shutdown", "inflight shutdown", "ifsd", "uncontained",
      "engine failure", "engine shutdown"), 20.0),
    (("aborted takeoff", "rejected takeoff", "emergency descent",
      "flight control", "declared an emergency", "forced landing",
      "emergency landing", "loss of control", "uncommanded"), 15.0),
    (("cabin smoke", "smoke", "toxic fume", "fumes", "fire",
      "depressurization"), 10.0),
    (("unscheduled landing", "divert", "diversion", "precautionary",
      "crack", "corrosion", "fracture", "separation", "leak", "worn",
      "fatigue", "delamination"), 5.0),
)

# Severity applied when nothing in the narrative matches a §6.2 bucket. Below
# the lowest schedule value, so an unclassifiable report cannot outweigh a
# categorized one.
_DEFAULT_SEVERITY = 3.0

# Business suffixes stripped when matching operator names. Kept local rather
# than imported from faa_enforcement_service: that module pulls in openpyxl and
# the database layer at import time, which this one has no need for.
_STRIP_SUFFIXES = re.compile(
    r"\b(LLC\.?|INC\.?|CORP\.?|CO\.?|LTD\.?|L\.?L\.?C\.?|"
    r"INCORPORATED|CORPORATION|COMPANY|LIMITED|DBA)\b",
    re.IGNORECASE,
)


def normalize_operator_name(raw_name: str) -> str:
    """
    Normalize an operator name for matching.

    Mirrors faa_enforcement_service.normalize_operator_name so that operator
    matching behaves identically across sources. Duplicated rather than
    imported to keep this module free of the Excel and database dependencies
    that module carries.

    Args:
        raw_name: The original operator name string.

    Returns:
        Cleaned, uppercase operator name suitable for comparison.
    """
    if not raw_name:
        return ""
    name = _STRIP_SUFFIXES.sub("", raw_name)
    name = re.sub(r"[.,]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.upper()


def _normalize_key(key: str) -> str:
    """Reduce a CSV header to a comparable form: lowercase, alphanumeric only."""
    return "".join(ch for ch in (key or "").lower() if ch.isalnum())


def _build_field_map(headers: List[str]) -> Dict[str, str]:
    """
    Map this extract's actual header names onto our canonical field names.

    The FAA changes column naming between extracts, so each canonical field
    lists several accepted aliases.

    Args:
        headers: Raw header row from the CSV.

    Returns:
        Canonical field name -> actual header name, for fields that were found.
    """
    normalized = {_normalize_key(h): h for h in headers}
    field_map: Dict[str, str] = {}
    for canonical, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                field_map[canonical] = normalized[alias]
                break
    return field_map


def normalize_tail_number(registry_number: Optional[str]) -> str:
    """
    Restore the leading "N" that SDRS strips from registration numbers.

    Per the source document, tail N427QS is listed as 427QS. Values that
    already carry the N prefix are returned unchanged, so this is safe to
    apply to data from any source.

    Args:
        registry_number: Value of the RegistryNNumber column.

    Returns:
        Uppercase tail number including the leading N, or "" if empty.
    """
    value = (registry_number or "").strip().upper()
    if not value:
        return ""
    return value if value.startswith("N") else f"N{value}"


def _parse_sdr_date(raw: Optional[str]) -> Optional[str]:
    """
    Normalize an SDRS date to ISO format for the calculator.

    The calculator parses event_date itself, but it expects a recognizable
    format; SDRS extracts use several. Unparseable values yield None so the
    event is still counted, just without time decay.

    Args:
        raw: Date string from the extract.

    Returns:
        ISO-8601 date string, or None if it could not be parsed.
    """
    value = (raw or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y%m%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    logger.debug("Unrecognized SDRS date format: %r", value)
    return None


def classify_sdr_severity(discrepancy: Optional[str]) -> float:
    """
    Score an SDR by what its narrative describes.

    SDRS has no severity field, so severity is inferred from the discrepancy
    text. Values are deliberately below NTSB accident severities (25-50): a
    service difficulty is a maintenance signal, not an accident, and should
    not dominate a score built mainly from accidents and enforcement.

    Args:
        discrepancy: Free-text discrepancy narrative.

    Returns:
        Severity score: 15 (emergency), 10 (serious), 5 (deterioration),
        or 3 (routine).
    """
    text = (discrepancy or "").lower()
    if not text:
        return _DEFAULT_SEVERITY
    for keywords, severity in _SEVERITY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return severity
    return _DEFAULT_SEVERITY


# ─── Service ─────────────────────────────────────────────────────────────────


class SDRSService:
    """
    Fetches and parses FAA Service Difficulty Reports.

    Every public method is failure-tolerant: network, format, and parsing
    errors are logged and yield an empty result rather than raising, so that
    an SDRS outage can never fail a TrustScore run.
    """

    @staticmethod
    async def download_extract(url: str = SDRS_DOWNLOAD_URL) -> List[Dict[str, str]]:
        """
        Download the SDRS bulk extract and return its rows.

        Handles both a bare CSV response and a ZIP archive containing one,
        since the FAA has served both.

        Args:
            url: Override for the download URL, for testing.

        Returns:
            List of raw row dicts. Empty if the download or parse failed.
        """
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
        except Exception as e:
            logger.warning("SDRS download failed (%s): %s", url, e)
            return []

        try:
            if content[:2] == b"PK":
                return SDRSService._rows_from_zip(content)
            return SDRSService._rows_from_csv(content.decode("utf-8", errors="replace"))
        except Exception as e:
            logger.warning("Could not parse SDRS extract: %s", e)
            return []

    @staticmethod
    def _rows_from_zip(content: bytes) -> List[Dict[str, str]]:
        """Extract rows from the first CSV/TXT member of a ZIP archive."""
        rows: List[Dict[str, str]] = []
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for name in archive.namelist():
                if name.lower().endswith((".csv", ".txt")):
                    with archive.open(name) as handle:
                        text = handle.read().decode("utf-8", errors="replace")
                    rows.extend(SDRSService._rows_from_csv(text))
                    break
        return rows

    @staticmethod
    def _rows_from_csv(text: str) -> List[Dict[str, str]]:
        """Parse CSV text into row dicts."""
        return list(csv.DictReader(io.StringIO(text)))

    @staticmethod
    def filter_part_135(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Keep only rows submitted under Part 135 operations.

        Per the source document, SubmitterTypeCode "E" denotes Part 135. If
        the column is absent — the FAA has renamed it before — all rows are
        kept rather than silently discarding the whole extract. Operator
        matching downstream is the real filter.

        Args:
            rows: Raw extract rows.

        Returns:
            Rows belonging to Part 135 operations.
        """
        if not rows:
            return []

        field_map = _build_field_map(list(rows[0].keys()))
        submitter_col = field_map.get("submitter_type")
        if not submitter_col:
            logger.warning(
                "SDRS extract has no SubmitterTypeCode column; skipping Part 135 "
                "filter and relying on operator matching instead."
            )
            return rows

        return [
            row for row in rows
            if (row.get(submitter_col) or "").strip().upper() == PART_135_SUBMITTER_CODE
        ]

    @staticmethod
    def rows_to_fleet_events(
        rows: List[Dict[str, str]],
        operator_name: str,
        tail_numbers: Optional[List[str]] = None,
        fleet_serials: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convert SDRS rows into fleet events for the TrustScore calculator.

        Rows are matched by tail number, then by qualified serial number, then
        by operator name — in that order of reliability. SDRS operator names
        are free text, so name matching is the last resort.

        `fleet_serials` enables the serial fallback: an SDR filed with a blank
        or mistyped N-number was previously dropped whenever `tail_numbers`
        was supplied, even though it named our aircraft by serial. Pass dicts
        carrying `tail_number`, `serial_number` and `make_model`.

        The serial path is qualified by aircraft type and refuses ambiguous
        keys — see `_serial_index`. A bare serial is not unique enough to
        match on.

        The returned dicts follow the same contract as NTSB and FAA
        enforcement events: event_type drives severity in the calculator, and
        any extra sdr_* keys are ignored by code that does not know them.

        Args:
            rows: Part 135 filtered extract rows.
            operator_name: Operator to match against.
            tail_numbers: Optional fleet tail numbers (with or without "N").

        Returns:
            Fleet event dicts. Empty if nothing matched.
        """
        if not rows:
            return []

        field_map = _build_field_map(list(rows[0].keys()))
        target_operator = normalize_operator_name(operator_name)
        target_tails = {normalize_tail_number(t) for t in (tail_numbers or []) if t}
        serial_index = _serial_index(fleet_serials)

        events: List[Dict[str, Any]] = []
        for row in rows:
            tail = normalize_tail_number(row.get(field_map.get("tail_number", ""), ""))
            row_operator = normalize_operator_name(
                row.get(field_map.get("operator", ""), "")
            )

            # Match by tail; fall back to serial; then to operator name.
            #
            # The serial fallback exists because an SDR filed with a blank,
            # malformed or mistyped N-number was previously dropped entirely
            # whenever tail_numbers was supplied — the report existed, named
            # our aircraft by serial, and scored nothing.
            matched_by = ""
            if target_tails and tail in target_tails:
                matched_by = "tail"
            elif serial_index:
                key = _serial_match_key(
                    row.get(field_map.get("serial_number", ""), ""),
                    row.get(field_map.get("make", ""), ""),
                    row.get(field_map.get("model", ""), ""),
                )
                if key and key in serial_index:
                    matched_by = "serial"
                    tail = tail or serial_index[key]
            if not matched_by:
                if target_tails or serial_index:
                    continue
                if not target_operator or target_operator not in row_operator:
                    continue
                matched_by = "operator_name"

            discrepancy = row.get(field_map.get("discrepancy", ""), "")
            events.append({
                "event_id": row.get(field_map.get("control_number", ""), "") or None,
                "event_date": _parse_sdr_date(row.get(field_map.get("report_date", ""), "")),
                "event_type": "faa_sdr",
                "injury_level": "",
                "severity": "",
                "location": "",
                "aircraft_damage": "",
                "investigation_type": "FAA Service Difficulty Report",
                "tail_number": tail,
                # Extra fields consumed by the calculator's severity mapping.
                "sdr_part_name": row.get(field_map.get("part_name", ""), ""),
                "sdr_discrepancy": discrepancy,
                "sdr_stage_of_operation": row.get(field_map.get("stage", ""), ""),
                "sdr_severity": classify_sdr_severity(discrepancy),
                # How this row was attributed to the operator. Recorded so a
                # serial-matched report can be audited — serial matching is
                # the less certain path and should be reviewable.
                "sdr_matched_by": matched_by,
            })

        return events

    @staticmethod
    async def query_as_fleet_events(
        operator_name: str,
        tail_numbers: Optional[List[str]] = None,
        fleet_serials: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch SDRs for an operator as fleet events.

        This is the entry point used by the batch verification workflow. It
        mirrors FAAEnforcementService.query_actions_as_fleet_events so the two
        can be appended to fleet_events the same way.

        Any failure returns an empty list: SDRS is additive, and its absence
        must leave the TrustScore unchanged rather than failing the run.

        Args:
            operator_name: Operator to query.
            tail_numbers: Optional fleet tail numbers for precise matching.
            fleet_serials: Optional serial/make-model records enabling the
                serial fallback for SDRs filed without a usable N-number.

        Returns:
            Fleet event dicts, possibly empty.
        """
        try:
            rows = await SDRSService.download_extract()
            part_135 = SDRSService.filter_part_135(rows)
            events = SDRSService.rows_to_fleet_events(
                part_135, operator_name, tail_numbers, fleet_serials
            )
            logger.info(
                "SDRS: %d row(s) downloaded, %d Part 135, %d matched %s",
                len(rows), len(part_135), len(events), operator_name,
            )
            return events
        except Exception as e:
            logger.warning("SDRS lookup failed for %s: %s", operator_name, e)
            return []
