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
}

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
    ) -> List[Dict[str, Any]]:
        """
        Convert SDRS rows into fleet events for the TrustScore calculator.

        Rows are matched to the operator by name, or by tail number when a
        fleet list is supplied — tail matching is the more reliable of the
        two, since SDRS operator names are free text.

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

        events: List[Dict[str, Any]] = []
        for row in rows:
            tail = normalize_tail_number(row.get(field_map.get("tail_number", ""), ""))
            row_operator = normalize_operator_name(
                row.get(field_map.get("operator", ""), "")
            )

            # Prefer tail matching; fall back to operator-name matching.
            if target_tails:
                if tail not in target_tails:
                    continue
            elif not target_operator or target_operator not in row_operator:
                continue

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
            })

        return events

    @staticmethod
    async def query_as_fleet_events(
        operator_name: str,
        tail_numbers: Optional[List[str]] = None,
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

        Returns:
            Fleet event dicts, possibly empty.
        """
        try:
            rows = await SDRSService.download_extract()
            part_135 = SDRSService.filter_part_135(rows)
            events = SDRSService.rows_to_fleet_events(
                part_135, operator_name, tail_numbers
            )
            logger.info(
                "SDRS: %d row(s) downloaded, %d Part 135, %d matched %s",
                len(rows), len(part_135), len(events), operator_name,
            )
            return events
        except Exception as e:
            logger.warning("SDRS lookup failed for %s: %s", operator_name, e)
            return []
