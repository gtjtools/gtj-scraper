# src/scoring/faa_enforcement_service.py
"""
FAA Enforcement Actions Service

Scrapes quarterly enforcement report Excel files from the FAA website,
parses operator-relevant enforcement actions, and stores them in the
database for use in TrustScore calculations.

Data source: https://www.faa.gov/about/office_org/headquarters_offices/agc/practice_areas/enforcement/reports
"""

import re
import io
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import httpx
import openpyxl

from src.common.config import SessionLocal
from src.common.models import FAAEnforcementAction

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

FAA_REPORTS_URL = (
    "https://www.faa.gov/about/office_org/headquarters_offices/agc/"
    "practice_areas/enforcement/reports"
)

# Only ingest enforcement actions against aircraft/commercial operators.
# Uppercased to match against normalized cell values consistently.
RELEVANT_ENTITY_TYPE = "A/C OR COMM OPER"

# Suffixes stripped during operator name normalization
_STRIP_SUFFIXES = re.compile(
    r"\b(LLC\.?|INC\.?|CORP\.?|CO\.?|LTD\.?|L\.?L\.?C\.?|"
    r"INCORPORATED|CORPORATION|COMPANY|LIMITED|DBA)\b",
    re.IGNORECASE,
)

# HTTP timeout for FAA requests (seconds)
_HTTP_TIMEOUT = 60.0


# ─── Name normalization ─────────────────────────────────────────────────────

def normalize_operator_name(raw_name: str) -> str:
    """
    Normalize an operator name for matching.

    Strips common business suffixes (LLC, INC, CORP, etc.),
    converts to uppercase, and collapses whitespace.

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


# ─── Service ─────────────────────────────────────────────────────────────────

class FAAEnforcementService:
    """
    Service for downloading, parsing, and querying FAA enforcement actions.

    The FAA publishes quarterly enforcement reports as .xlsx files on their
    reports page.  This service scrapes the index page for download links,
    downloads each file, filters to aircraft/commercial operator actions,
    and upserts them into the `gtj.faa_enforcement_actions` table.
    """

    # ── Scraping ─────────────────────────────────────────────────────────

    @staticmethod
    async def discover_report_urls() -> List[str]:
        """
        Scrape the FAA enforcement reports index page and return all
        downloadable .xlsx report URLs.

        The FAA page uses three link patterns across different eras:
          1. /media/{id} links (2023+) -- serve xlsx directly with no file extension
          2. /sites/faa.gov/files/.../*.xlsx links -- direct xlsx file downloads
          3. Landing page links (2021-2022) -- HTML pages that contain an xlsx
             download link inside them

        Returns:
            List of absolute URLs pointing to quarterly .xlsx files.
        """
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(FAA_REPORTS_URL)
            response.raise_for_status()
            html = response.text

            xlsx_urls: List[str] = []
            landing_page_urls: List[str] = []

            # --- Pattern 1: /media/{id} links (2023+ reports) ---
            # These serve xlsx content directly but have no file extension in the URL.
            media_pattern = re.compile(r'href="(/media/\d+)"', re.IGNORECASE)
            for path in media_pattern.findall(html):
                xlsx_urls.append(f"https://www.faa.gov{path}")

            # --- Pattern 2: Direct .xlsx file links ---
            xlsx_pattern = re.compile(r'href="([^"]*\.xlsx[^"]*)"', re.IGNORECASE)
            for link in xlsx_pattern.findall(html):
                xlsx_urls.append(_to_absolute_url(link))

            # --- Pattern 3: Landing page links (2021-2022 era) ---
            # These are HTML pages containing an xlsx download link inside them.
            # Patterns: /headquartersoffices/agc/..., /about/.../reports/...-report
            landing_patterns = [
                re.compile(r'href="(/headquartersoffices/agc/[^"]*report[^"]*)"', re.IGNORECASE),
                re.compile(r'href="(/about/[^"]*quarter-\d+-report[^"]*)"', re.IGNORECASE),
                re.compile(r'href="(https://www\.faa\.gov/headquartersoffices/agc/[^"]*)"', re.IGNORECASE),
            ]
            for pattern in landing_patterns:
                for link in pattern.findall(html):
                    landing_page_urls.append(_to_absolute_url(link))

            # Follow landing pages to extract the actual xlsx download links
            for page_url in _deduplicate(landing_page_urls):
                try:
                    inner_xlsx = await _extract_xlsx_from_landing_page(client, page_url)
                    if inner_xlsx:
                        xlsx_urls.append(inner_xlsx)
                    else:
                        logger.debug("No xlsx link found on landing page: %s", page_url)
                except Exception as e:
                    logger.warning("Failed to scrape landing page %s: %s", page_url, e)

        unique_urls = _deduplicate(xlsx_urls)
        logger.info("Discovered %d FAA enforcement report URLs", len(unique_urls))
        return unique_urls

    # ── Downloading & Parsing ────────────────────────────────────────────

    @staticmethod
    async def download_and_parse_report(url: str) -> List[Dict[str, Any]]:
        """
        Download a single quarterly .xlsx report and parse it into a list
        of enforcement action dictionaries.

        Only rows where ENTITY TYPE matches RELEVANT_ENTITY_TYPE are returned.

        Handles two FAA xlsx layouts:
          - Newer files (2025+): Row 1 is a title row, row 2 has column headers.
          - Older files (2023-2024): Row 1 has column headers directly.

        Args:
            url: Direct URL to the .xlsx file.

        Returns:
            List of dicts, each representing one enforcement action row.
        """
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        # NOTE: Some /media/ URLs serve PDFs instead of xlsx. The ZIP magic
        # bytes (PK\x03\x04) reliably distinguish xlsx from other formats.
        if response.content[:4] != b'PK\x03\x04':
            logger.info(
                "Skipping non-xlsx content from %s (content-type: %s)",
                url, response.headers.get("content-type", "unknown"),
            )
            return []

        workbook = openpyxl.load_workbook(
            filename=io.BytesIO(response.content),
            read_only=True,
            data_only=True,
        )
        sheet = workbook.active

        # Collect all rows up front so we can scan for the header row.
        # FAA files are small (~30-50 rows) so this is fine for memory.
        all_rows = list(sheet.iter_rows(values_only=True))
        workbook.close()

        if not all_rows:
            logger.warning("Empty spreadsheet from %s", url)
            return []

        # Find the header row by scanning for a row containing "CASE NUMBER".
        # Newer FAA files (2025+) have a title/banner row before the headers.
        header_row_idx = _find_header_row(all_rows)
        if header_row_idx is None:
            logger.warning(
                "Could not locate header row in %s. First row: %s",
                url, all_rows[0] if all_rows else "empty",
            )
            return []

        raw_headers = all_rows[header_row_idx]
        data_rows = all_rows[header_row_idx + 1:]

        # Normalize headers: strip whitespace, uppercase
        headers = [
            (str(h).strip().upper() if h else "") for h in raw_headers
        ]

        # Build column name -> index map
        col_map: Dict[str, int] = {}
        for idx, header in enumerate(headers):
            col_map[header] = idx

        # Expected column names (as they appear in the FAA .xlsx files)
        COL_INITIAL_ACTION = _find_column(col_map, "INITIAL ACTION")
        COL_CASE_NUMBER = _find_column(col_map, "CASE NUMBER")
        COL_NAME = _find_column(col_map, "NAME")
        COL_ENTITY_TYPE = _find_column(col_map, "ENTITY TYPE")
        COL_DATE_KNOWN = _find_column(col_map, "DATE KNOWN")
        COL_ACTION = _find_column(col_map, "ACTION")
        COL_SANCTION_AMOUNT = _find_column(col_map, "SANCTION AMOUNT")
        COL_SANCTION = _find_column(col_map, "SANCTION")
        COL_CASE_TYPE = _find_column(col_map, "CASE TYPE")
        COL_CLOSED_DATE = _find_column(col_map, "CLOSED DATE")

        records: List[Dict[str, Any]] = []
        for row in data_rows:
            # Skip empty rows
            if not row or all(cell is None for cell in row):
                continue

            entity_type = _cell_str(row, COL_ENTITY_TYPE)

            # Filter: only aircraft/commercial operators
            if not entity_type or RELEVANT_ENTITY_TYPE not in entity_type.upper():
                continue

            operator_name = _cell_str(row, COL_NAME)
            case_number = _cell_str(row, COL_CASE_NUMBER)

            # Skip rows without essential data
            if not case_number or not operator_name:
                continue

            records.append({
                "case_number": case_number.strip(),
                "operator_name": operator_name.strip(),
                "operator_name_normalized": normalize_operator_name(operator_name),
                "entity_type": entity_type.strip(),
                "date_known": _parse_cell_date(row, COL_DATE_KNOWN),
                "action_type": _cell_str(row, COL_ACTION),
                "sanction_amount": _parse_cell_decimal(row, COL_SANCTION_AMOUNT),
                "sanction_type": _cell_str(row, COL_SANCTION),
                "case_type": _cell_str(row, COL_CASE_TYPE),
                "closed_date": _parse_cell_date(row, COL_CLOSED_DATE),
                "initial_action_narrative": _cell_str(row, COL_INITIAL_ACTION),
                "source_url": url,
            })

        logger.info(
            "Parsed %d operator enforcement actions from %s", len(records), url
        )
        return records

    # ── Batch Ingestion ──────────────────────────────────────────────────

    @staticmethod
    async def run_full_ingestion() -> Dict[str, Any]:
        """
        Discover all quarterly reports and ingest any that haven't been
        processed yet.  Skips records whose case_number already exists
        in the database.

        Returns:
            Summary dict with counts of discovered, new, and skipped records.
        """
        urls = await FAAEnforcementService.discover_report_urls()
        if not urls:
            logger.warning("No FAA enforcement report URLs discovered")
            return {"reports_found": 0, "records_inserted": 0, "records_skipped": 0}

        total_inserted = 0
        total_skipped = 0

        for url in urls:
            try:
                records = await FAAEnforcementService.download_and_parse_report(url)
                inserted, skipped = _upsert_records(records)
                total_inserted += inserted
                total_skipped += skipped
                logger.info(
                    "Ingested report %s: %d inserted, %d skipped",
                    url, inserted, skipped,
                )
            except Exception as e:
                logger.error("Failed to ingest report %s: %s", url, e)

        summary = {
            "reports_found": len(urls),
            "records_inserted": total_inserted,
            "records_skipped": total_skipped,
        }
        logger.info("FAA enforcement ingestion complete: %s", summary)
        return summary

    # ── Querying ─────────────────────────────────────────────────────────

    @staticmethod
    def query_by_operator_name(operator_name: str) -> List[Dict[str, Any]]:
        """
        Look up all enforcement actions matching an operator name
        using normalized name comparison.

        Args:
            operator_name: Raw operator name (will be normalized internally).

        Returns:
            List of enforcement action dicts ready for TrustScore integration.
        """
        normalized = normalize_operator_name(operator_name)
        if not normalized:
            return []

        db = SessionLocal()
        try:
            actions = (
                db.query(FAAEnforcementAction)
                .filter(FAAEnforcementAction.operator_name_normalized == normalized)
                .order_by(FAAEnforcementAction.date_known.desc())
                .all()
            )

            return [_action_to_dict(action) for action in actions]
        finally:
            db.close()

    @staticmethod
    def query_actions_as_fleet_events(operator_name: str) -> List[Dict[str, Any]]:
        """
        Query enforcement actions and convert them to the fleet_events format
        expected by the TrustScore calculator.

        Each enforcement action becomes a fleet event with:
          - event_type: "faa_enforcement"
          - event_date: the date_known field
          - injury_level: not applicable (empty)
          - severity: mapped from action_type and sanction_amount

        Args:
            operator_name: Raw operator name.

        Returns:
            List of fleet event dicts compatible with TrustScoreCalculator.
        """
        actions = FAAEnforcementService.query_by_operator_name(operator_name)

        fleet_events: List[Dict[str, Any]] = []
        for action in actions:
            fleet_events.append({
                "event_id": action["case_number"],
                "event_date": action["date_known"],
                "event_type": "faa_enforcement",
                "injury_level": "",
                "severity": "",
                "location": "",
                "aircraft_damage": "",
                "investigation_type": "FAA Enforcement",
                # Extra fields for severity mapping in calculator
                "faa_action_type": action["action_type"],
                "faa_sanction_amount": action["sanction_amount"],
                "faa_sanction_type": action["sanction_type"],
                "faa_case_number": action["case_number"],
                "faa_narrative": action["initial_action_narrative"],
            })

        return fleet_events


# ─── URL discovery helpers ────────────────────────────────────────────────────

def _to_absolute_url(link: str) -> str:
    """Convert a relative or absolute FAA URL to a fully qualified URL."""
    if link.startswith("http"):
        return link
    if link.startswith("/"):
        return f"https://www.faa.gov{link}"
    return f"https://www.faa.gov/{link}"


def _deduplicate(urls: List[str]) -> List[str]:
    """Remove duplicate URLs while preserving insertion order."""
    seen: set[str] = set()
    unique: List[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


async def _extract_xlsx_from_landing_page(
    client: httpx.AsyncClient,
    page_url: str,
) -> Optional[str]:
    """
    Fetch an FAA report landing page and extract the .xlsx download link.

    Some quarterly reports (2021-2022 era) are linked from the index page
    as HTML landing pages rather than direct file downloads. The actual
    xlsx file is linked within the landing page content.
    """
    response = await client.get(page_url)
    response.raise_for_status()

    html = response.text
    xlsx_pattern = re.compile(r'href="([^"]*\.xlsx[^"]*)"', re.IGNORECASE)
    matches = xlsx_pattern.findall(html)

    if matches:
        return _to_absolute_url(matches[0])
    return None


# ─── Private helpers ─────────────────────────────────────────────────────────

def _find_header_row(rows: List[tuple]) -> Optional[int]:
    """
    Scan rows to find the one containing column headers.

    FAA xlsx files have two layouts:
      - Headers in row 0 (older files): first cell is "CASE NUMBER"
      - Headers in row 1+ (newer files): row 0 is a title banner like
        "QUARTERLY ENFORCEMENT REPORT - 01/01/2025 - 03/31/2025"

    We identify the header row by looking for "CASE NUMBER" in any cell.
    Scans up to 10 rows to be safe.
    """
    for idx, row in enumerate(rows[:10]):
        if not row:
            continue
        for cell in row:
            if cell is not None and "CASE NUMBER" in str(cell).upper():
                return idx
    return None


def _find_column(col_map: Dict[str, int], name: str) -> Optional[int]:
    """Find a column index by name, trying exact then partial match."""
    if name in col_map:
        return col_map[name]
    # Try partial match for headers that may have extra whitespace or text
    for header, idx in col_map.items():
        if name in header:
            return idx
    return None


def _cell_str(row: tuple, col_idx: Optional[int]) -> Optional[str]:
    """Safely extract a string value from a row tuple."""
    if col_idx is None or col_idx >= len(row):
        return None
    val = row[col_idx]
    if val is None:
        return None
    return str(val).strip()


def _parse_cell_date(row: tuple, col_idx: Optional[int]) -> Optional[str]:
    """
    Extract a date from a cell and return as ISO date string.
    Handles both datetime objects (from Excel) and date strings.
    """
    if col_idx is None or col_idx >= len(row):
        return None
    val = row[col_idx]
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    # Try parsing common date formats
    val_str = str(val).strip()
    if not val_str:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d-%b-%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(val_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Return raw string as fallback
    return val_str


def _parse_cell_decimal(row: tuple, col_idx: Optional[int]) -> Optional[float]:
    """Extract a numeric value from a cell, stripping currency symbols."""
    if col_idx is None or col_idx >= len(row):
        return None
    val = row[col_idx]
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    # Strip $, commas, whitespace
    val_str = str(val).replace("$", "").replace(",", "").strip()
    if not val_str:
        return None
    try:
        return float(val_str)
    except ValueError:
        return None


def _action_to_dict(action: FAAEnforcementAction) -> Dict[str, Any]:
    """Convert an ORM FAAEnforcementAction to a plain dict."""
    return {
        "id": str(action.id) if action.id else None,
        "case_number": action.case_number,
        "operator_name": action.operator_name,
        "operator_name_normalized": action.operator_name_normalized,
        "entity_type": action.entity_type,
        "date_known": action.date_known.isoformat() if action.date_known else None,
        "action_type": action.action_type,
        "sanction_amount": float(action.sanction_amount) if action.sanction_amount else None,
        "sanction_type": action.sanction_type,
        "case_type": action.case_type,
        "closed_date": action.closed_date.isoformat() if action.closed_date else None,
        "initial_action_narrative": action.initial_action_narrative,
        "created_at": action.created_at.isoformat() if action.created_at else None,
    }


def _upsert_records(records: List[Dict[str, Any]]) -> tuple[int, int]:
    """
    Insert enforcement action records, skipping any whose case_number
    already exists.

    Returns:
        Tuple of (inserted_count, skipped_count).
    """
    if not records:
        return 0, 0

    db = SessionLocal()
    inserted = 0
    skipped = 0

    try:
        # Batch-fetch existing case numbers for efficiency
        case_numbers = [r["case_number"] for r in records]
        existing = set(
            row[0]
            for row in db.query(FAAEnforcementAction.case_number)
            .filter(FAAEnforcementAction.case_number.in_(case_numbers))
            .all()
        )

        for record in records:
            if record["case_number"] in existing:
                skipped += 1
                continue

            db.add(FAAEnforcementAction(
                case_number=record["case_number"],
                operator_name=record["operator_name"],
                operator_name_normalized=record["operator_name_normalized"],
                entity_type=record["entity_type"],
                date_known=record.get("date_known"),
                action_type=record.get("action_type"),
                sanction_amount=record.get("sanction_amount"),
                sanction_type=record.get("sanction_type"),
                case_type=record.get("case_type"),
                closed_date=record.get("closed_date"),
                initial_action_narrative=record.get("initial_action_narrative"),
            ))
            inserted += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return inserted, skipped
