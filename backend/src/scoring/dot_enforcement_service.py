# src/scoring/dot_enforcement_service.py
"""
DOT Office of Aviation Consumer Protection (OACP) Enforcement Orders

Scrapes the public enforcement-orders list (every row, including dismissals),
sends new rows to an LLM for structured JSON in batches, and inserts into
gtj.dot_enforcement_orders. Operator matching is by name at score time.

TrustScore 5.0 Data Sources, item 8.
Data source:
  https://www.transportation.gov/airconsumer/enforcement-orders

Pipeline:
  1. Fetch HTML list (items_per_page=All)
  2. Parse title, date, case URL per row (no title filtering)
  3. Skip rows already in DB (by source_url or title)
  4. LLM-format new rows in parallel batches of 125 (record_id + title + list_date)
  5. Map LLM results back via record_id → insert (title/source_url from crawl)

Not wired into TrustScore until ELI is defined.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx

from src.common.config import SessionLocal
from src.common.models import DOTEnforcementOrder
from src.scoring.faa_enforcement_service import normalize_operator_name
from src.trustscore.llm_client import LLMClient, LLMProvider

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

DOT_ORDERS_URL = (
    "https://www.transportation.gov/airconsumer/enforcement-orders"
    "?field_subject_target_id=All&items_per_page=All"
)
DOT_BASE_URL = "https://www.transportation.gov"

_HTTP_TIMEOUT = 120.0
# transportation.gov (Akamai) blocks bot-like User-Agents with 403.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_BROWSER_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Allowed values for gtj.dot_enforcement_orders.order_type
_ALLOWED_ORDER_TYPES = frozenset(
    {
        "dismissal",
        "settlement",
        "consent_order",
        "enforcement_action",
        "unknown",
    }
)

# Batched LLM formatting. title/source_url are mapped locally via record_id after response.
_LLM_BATCH_SIZE = 125
# Max concurrent OpenRouter batch calls (keeps rate limits in check).
_LLM_BATCH_CONCURRENCY = 4

# Literal braces doubled for str.format(); {records_json} is filled in.
_LLM_BATCH_PROMPT = """You extract structured data from U.S. DOT aviation enforcement-order listings
so each row can be inserted into gtj.dot_enforcement_orders.

Input is a JSON array of records. Each input record has exactly:
  record_id, title, list_date

Return ONLY one valid JSON array with exactly one object per input record.
Each object must have exactly these keys:
{{
  "record_id": "",
  "order_number": null,
  "effective_date": null,
  "operator_name": null,
  "order_type": "unknown"
}}

Do NOT return title or source_url. Those are mapped locally using record_id.

Field rules:

1. record_id
- Echo the exact record_id from the matching input record. Do not invent or renumber ids.

2. order_number
- Extract the DOT order identifier from the title when it can be identified with reasonable confidence.
- Date-like identifiers such as YYYY-M-D may be valid order identifiers when used in a recognizable DOT order-title pattern, for example:
  "Southwest Airlines - Order 2025-12-4".
- Do not assume every YYYY-M-D sequence is an order number.
- Do not use the list date as the order number.
- Do not treat written calendar dates such as "December 23, 2010" as order numbers.
- Do not treat docket identifiers such as "Docket OST 2003-15046" as order numbers unless the title clearly identifies the identifier as the order number.
- Do not extract arbitrary hyphenated numbers from company names, docket references, or other unrelated text.
- If the title contains no clearly identifiable DOT order identifier, return null.
- Do not invent or reconstruct missing identifiers.

3. effective_date
- Use the supplied list date, not a date inferred from the title.
- Convert a valid list date to YYYY-MM-DD.
- If the list date is missing or invalid, return null.
- Do not assume the listing date is the order's actual effective date. This field represents the date supplied by the listing because no separate effective date is provided.

4. operator_name
- Identify the airline, aviation company, or other regulated entity that is the respondent or subject of the order.
- Use the full company name as written in the title whenever possible.
- Use the entire title to determine the operator. Do not rely only on the first or last words.
- For titles containing "v.", "v", or "versus", identify the respondent or respondents on the opposing side. The complainant may be a person, company, organization, or another entity.
- Do not assume there is only one respondent. If multiple operators are named, return all identifiable operator names in a single string, separated by "; ".
- For titles such as "Airline - Order YYYY-M-D", use the airline or company named in the title.
- For settlement agreements, consent orders, and other orders, identify the company or companies subject to the order, not merely the first company mentioned.
- Distinguish complainants from respondents. Do not include a complainant as an operator unless the title also identifies that party as a respondent or subject of the order.
- Titles may contain multiple complaints, multiple respondents, or several company names. Consider the complete title before deciding.
- Do not assume every named airline is an operator subject to the order if the title does not support that interpretation.
- If the operator cannot be identified reliably, return null.
- Do not invent company names or infer an operator solely from outside knowledge.

5. order_type
- Return exactly one of:
  "dismissal", "settlement", "consent_order", "enforcement_action", "unknown".
- "dismissal": the title explicitly indicates that a complaint, case, or proceeding was dismissed. This includes "Order of Dismissal", "Dismissal Order", "Dismissing Formal Complaint", and clearly equivalent wording.
- "settlement": the title explicitly identifies a settlement or settlement agreement.
- "consent_order": the title explicitly identifies a consent order.
- "enforcement_action": the title clearly identifies a substantive DOT enforcement order or action that does not fit the preceding categories.
- "unknown": the title does not provide enough evidence to assign one of the other categories.
- Classify based on the wording and apparent document type, not on assumptions about the outcome.
- Do not classify a title as enforcement_action merely because it contains the word "Order".
- If multiple order types appear, use the clearest explicitly stated document type. If the title remains ambiguous, use "unknown".
- A dismissal or settlement does not by itself establish that the operator committed a violation or should receive a negative TrustScore impact.

General rules:
- Use only the supplied title and list_date for each record.
- Preserve every input record_id in the output (one response object per input).
- Do not invent facts, violations, penalties, outcomes, dates, or identifiers.
- Use JSON null for missing scalar values.
- Return a valid JSON array with exactly the specified keys per object. Do not add keys.
- Do not include Markdown, explanations, comments, or text outside the JSON array.

Records:
{records_json}
"""


# ─── HTML table parser ───────────────────────────────────────────────────────

class _OrdersTableParser(HTMLParser):
    """
    Pull title / href / date cells from the Drupal views table on the
    enforcement-orders page. Ignores nav and footer links.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[Dict[str, Optional[str]]] = []
        self._in_table = False
        self._in_tbody = False
        self._in_row = False
        self._in_cell = False
        self._in_link = False
        self._cell_index = 0
        self._current: Dict[str, Optional[str]] = {}
        self._cell_text: List[str] = []
        self._link_href: Optional[str] = None
        self._table_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table":
            classes = attrs_dict.get("class") or ""
            # Prefer the views/results table; fall back to first table if unmarked.
            if "views-table" in classes or "cols-" in classes or not self._in_table:
                self._in_table = True
                self._table_depth += 1
            return

        if not self._in_table:
            return

        if tag == "tbody":
            self._in_tbody = True
        elif tag == "tr" and (self._in_tbody or self._in_table):
            self._in_row = True
            self._cell_index = 0
            self._current = {"title": None, "href": None, "date": None}
        elif tag in ("td", "th") and self._in_row:
            self._in_cell = True
            self._cell_text = []
            self._link_href = None
        elif tag == "a" and self._in_cell:
            self._in_link = True
            href = attrs_dict.get("href")
            if href:
                self._link_href = href

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._in_table:
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._in_table = False
                self._in_tbody = False
            return

        if not self._in_table:
            return

        if tag == "tbody":
            self._in_tbody = False
        elif tag in ("td", "th") and self._in_cell:
            text = " ".join("".join(self._cell_text).split()).strip()
            if self._cell_index == 0:
                self._current["title"] = text or None
                self._current["href"] = self._link_href
            elif self._cell_index == 1:
                self._current["date"] = text or None
            self._cell_index += 1
            self._in_cell = False
            self._in_link = False
        elif tag == "a":
            self._in_link = False
        elif tag == "tr" and self._in_row:
            if self._current.get("title") and self._current.get("href"):
                # Skip header rows that look like "Title" / "Date"
                title_lower = (self._current["title"] or "").lower()
                if title_lower not in ("title", "date"):
                    self.rows.append(self._current)
            self._in_row = False
            self._current = {}

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)


# ─── Service ─────────────────────────────────────────────────────────────────

class DOTEnforcementService:
    """Scrape all list rows, LLM-format, and persist DOT enforcement orders."""

    @staticmethod
    async def run_full_ingestion(
        limit: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Full ingest pipeline.

        Args:
            limit: Max number of NEW rows to LLM-process (None = all).
            dry_run: If True, scrape/log only — no LLM, no DB reads/writes.
                     If False, LLM-format new rows and insert.

        Returns:
            Summary counts for the run.
        """
        rows = await DOTEnforcementService.fetch_order_list()
        logger.info("DOT list: %d row(s) parsed", len(rows))

        # dry_run: crawl/log only (no DB). Live run: load skip keys.
        existing = (
            {"source_urls": set(), "titles": set()}
            if dry_run
            else _load_existing_keys()
        )
        summary = {
            "rows_found": len(rows),
            "already_ingested": 0,
            "rows_logged": 0,
            "pending_for_llm": 0,
            "records_inserted": 0,
            "llm_failures": 0,
            "llm_batches": 0,
            "dry_run": dry_run,
            "limit": limit,
        }

        pending: List[Dict[str, Any]] = []

        for row in rows:
            title = row["title"]
            source_url = row["source_url"]
            list_date = row.get("effective_date")

            logger.info(
                "DOT row: date=%s title=%r url=%s",
                list_date,
                title,
                source_url,
            )
            print(f"  [DOT row] date={list_date} title={title!r}")
            summary["rows_logged"] += 1

            if _is_already_ingested(existing, source_url=source_url, title=title):
                summary["already_ingested"] += 1
                continue

            if limit is not None and len(pending) >= limit:
                continue

            pending.append(row)

        summary["pending_for_llm"] = len(pending)

        # dry_run gates LLM + insert: scrape/log only when True.
        if dry_run:
            logger.info("DOT ingestion complete (dry_run): %s", summary)
            return summary

        # Nothing new → no LLM client, no OpenRouter calls.
        if not pending:
            logger.info("DOT ingestion complete (nothing new): %s", summary)
            return summary

        llm_client = _create_llm_client()
        batches = [
            pending[i : i + _LLM_BATCH_SIZE]
            for i in range(0, len(pending), _LLM_BATCH_SIZE)
        ]
        summary["llm_batches"] = len(batches)
        sem = asyncio.Semaphore(_LLM_BATCH_CONCURRENCY)

        # Parallel LLM calls (capped); inserts stay sequential afterward.
        batch_results = await asyncio.gather(*[
            DOTEnforcementService._llm_format_batch(
                llm_client,
                batch=batch,
                batch_index=idx,
                sem=sem,
            )
            for idx, batch in enumerate(batches)
        ])

        for batch_result in batch_results:
            summary["llm_failures"] += batch_result["llm_failures"]
            to_insert = batch_result["to_insert"]
            if to_insert:
                inserted = _insert_records(to_insert)
                summary["records_inserted"] += inserted
                for rec in to_insert:
                    existing["source_urls"].add(rec["source_url"])
                    existing["titles"].add(rec["title"])

        logger.info("DOT ingestion complete: %s", summary)
        return summary

    @staticmethod
    async def fetch_order_list(url: str = DOT_ORDERS_URL) -> List[Dict[str, Any]]:
        """
        Download the DOT list page and return parsed rows.

        Tries a browser-like httpx request first. transportation.gov sits
        behind Akamai and often returns 403 to plain HTTP clients — on 403
        (or empty parse) fall back to local Playwright Chromium.
        """
        html: Optional[str] = None
        try:
            html = await DOTEnforcementService._fetch_html_httpx(url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
            logger.warning(
                "DOT list returned 403 via httpx; falling back to Playwright"
            )
        except httpx.HTTPError as e:
            logger.warning("DOT httpx fetch failed (%s); falling back to Playwright", e)

        rows: List[Dict[str, Any]] = []
        if html:
            rows = parse_orders_html(html)
            if rows:
                return rows
            logger.warning(
                "DOT httpx returned HTML but views-table had 0 rows; trying Playwright"
            )

        html = await DOTEnforcementService._fetch_html_playwright(url)
        rows = parse_orders_html(html)
        if not rows:
            raise RuntimeError(
                "DOT enforcement-orders views-table returned 0 rows "
                "(httpx and Playwright). No regex fallback — check page markup or bot block."
            )
        return rows

    @staticmethod
    async def _fetch_html_httpx(url: str) -> str:
        """GET the list page with browser-like headers."""
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
        ) as client:
            # Warm up on the site root so Akamai can set cookies.
            await client.get(DOT_BASE_URL, headers={
                **_BROWSER_HEADERS,
                "Sec-Fetch-Site": "none",
            })
            response = await client.get(
                url,
                headers={
                    **_BROWSER_HEADERS,
                    "Referer": f"{DOT_BASE_URL}/airconsumer",
                    "Sec-Fetch-Site": "same-origin",
                },
            )
            response.raise_for_status()
            return response.text

    @staticmethod
    async def _fetch_html_playwright(url: str) -> str:
        """
        Load the list page in a real browser (Akamai blocks plain HTTP).

        Order:
          1. Local Playwright Chromium / system Chrome
          2. Browserbase hosted browser (same credentials as UCC)
        """
        try:
            return await DOTEnforcementService._fetch_html_local_playwright(url)
        except Exception as e:
            logger.warning("Local Playwright failed (%s); trying Browserbase", e)

        return await DOTEnforcementService._fetch_html_browserbase(url)

    @staticmethod
    async def _fetch_html_local_playwright(url: str) -> str:
        """Headless Chromium or installed Chrome via Playwright."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = None
            last_error: Optional[Exception] = None
            for launch_kwargs in (
                {"headless": True},
                {"headless": True, "channel": "chrome"},
                {"headless": True, "channel": "msedge"},
            ):
                try:
                    browser = await p.chromium.launch(**launch_kwargs)
                    break
                except Exception as e:
                    last_error = e
                    browser = None
            if browser is None:
                raise RuntimeError(
                    f"Could not launch local browser for DOT scrape: {last_error}"
                )

            try:
                context = await browser.new_context(
                    user_agent=_USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                try:
                    await page.wait_for_selector(
                        "table.views-table a, .view-content a",
                        timeout=30_000,
                    )
                except Exception:
                    logger.warning(
                        "DOT Playwright: table selector timed out; using page content anyway"
                    )
                return await page.content()
            finally:
                await browser.close()

    @staticmethod
    async def _fetch_html_browserbase(url: str) -> str:
        """Load the list page through Browserbase (requires env credentials)."""
        import os

        from browserbase import Browserbase
        from playwright.async_api import async_playwright

        api_key = os.getenv("BROWSERBASE_API_KEY")
        project_id = os.getenv("BROWSERBASE_PROJECT_ID")
        if not api_key or not project_id:
            raise RuntimeError(
                "DOT page returned 403 and no local browser is available. "
                "Set BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID, or run "
                "`playwright install chromium`."
            )

        bb = Browserbase(api_key=api_key)
        session = bb.sessions.create(project_id=project_id)
        session_id = session.id
        connect_url = session.connect_url
        logger.info("DOT scrape using Browserbase session %s", session_id)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(connect_url)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                try:
                    await page.wait_for_selector(
                        "table.views-table a, .view-content a",
                        timeout=30_000,
                    )
                except Exception:
                    logger.warning(
                        "DOT Browserbase: table selector timed out; using page content anyway"
                    )
                return await page.content()
        finally:
            try:
                bb.sessions.update(session_id, status="REQUEST_RELEASE")
            except Exception as e:
                logger.warning("Failed to release Browserbase session %s: %s", session_id, e)

    @staticmethod
    async def _llm_format_batch(
        llm_client: LLMClient,
        batch: List[Dict[str, Any]],
        batch_index: int,
        sem: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """
        Run one LLM batch under the concurrency semaphore.

        Returns {to_insert, llm_failures}. Does not write to the DB.
        """
        by_id = _assign_record_ids(batch)
        async with sem:
            try:
                parsed_rows = await DOTEnforcementService.parse_batch_with_llm(
                    llm_client,
                    batch_inputs=_batch_inputs_for_prompt(by_id),
                )
            except Exception as e:
                logger.warning(
                    "LLM batch %d failed (%d rows): %s",
                    batch_index,
                    len(batch),
                    e,
                )
                return {"to_insert": [], "llm_failures": len(batch)}

        seen_ids: set[str] = set()
        to_insert: List[Dict[str, Any]] = []
        llm_failures = 0

        for parsed in parsed_rows:
            record_id = str(parsed.get("record_id") or "").strip()
            crawled = by_id.get(record_id)
            if crawled is None:
                logger.warning(
                    "LLM batch %d returned unknown record_id=%r",
                    batch_index,
                    record_id,
                )
                llm_failures += 1
                continue
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            to_insert.append(
                _build_record(
                    title=crawled["title"],
                    source_url=crawled["source_url"],
                    list_date=crawled.get("effective_date"),
                    parsed=parsed,
                )
            )

        missing = len(by_id) - len(seen_ids)
        if missing > 0:
            llm_failures += missing
            logger.warning(
                "LLM batch %d missing %d record_id(s) of %d",
                batch_index,
                missing,
                len(by_id),
            )

        return {"to_insert": to_insert, "llm_failures": llm_failures}

    @staticmethod
    async def parse_batch_with_llm(
        llm_client: LLMClient,
        batch_inputs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Ask the LLM to format a batch of rows into structured JSON objects.

        Each input: {record_id, title, list_date}.
        Each output: {record_id, order_number, effective_date, operator_name, order_type}.
        title/source_url are mapped by the caller via record_id.
        """
        prompt = _LLM_BATCH_PROMPT.format(
            records_json=json.dumps(batch_inputs, ensure_ascii=False, indent=2),
        )
        raw = await llm_client.get_completion(prompt)
        return _parse_llm_json_array(raw)


# ─── Pure helpers (testable without network/DB) ──────────────────────────────

def parse_orders_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse the enforcement-orders HTML views-table into row dicts.

    Returns list of {title, source_url, effective_date}.
    Returns [] if the table is missing or empty (no regex fallback).
    """
    parser = _OrdersTableParser()
    parser.feed(html)

    results: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()

    for row in parser.rows:
        title = (row.get("title") or "").strip()
        href = (row.get("href") or "").strip()
        if not title or not href:
            continue

        source_url = urljoin(DOT_BASE_URL, href)
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        results.append({
            "title": title,
            "source_url": source_url,
            "effective_date": _parse_list_date(row.get("date")),
        })

    return results


def _parse_list_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _strip_llm_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """Strip optional markdown fences and load a JSON object."""
    data = json.loads(_strip_llm_fences(raw))
    if not isinstance(data, dict):
        raise ValueError("LLM response is not a JSON object")
    return data


def _parse_llm_json_array(raw: str) -> List[Dict[str, Any]]:
    """Strip optional markdown fences and load a JSON array of objects."""
    data = json.loads(_strip_llm_fences(raw))
    if not isinstance(data, list):
        raise ValueError("LLM response is not a JSON array")
    out: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def _assign_record_ids(batch: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Ephemeral per-batch ids used to map LLM results back to crawled rows."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for i, row in enumerate(batch, start=1):
        by_id[str(i)] = row
    return by_id


def _batch_inputs_for_prompt(
    by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build LLM input rows: record_id + title + list_date (no source_url)."""
    inputs: List[Dict[str, Any]] = []
    for record_id, row in by_id.items():
        list_date = row.get("effective_date")
        inputs.append({
            "record_id": record_id,
            "title": row["title"],
            "list_date": list_date.isoformat() if list_date else None,
        })
    return inputs


def _create_llm_client() -> LLMClient:
    import os

    env_provider = (os.getenv("LLM_PROVIDER") or "openrouter").lower()
    try:
        provider = LLMProvider(env_provider)
    except ValueError:
        provider = LLMProvider.OPENROUTER
    client = LLMClient(provider=provider)
    if not client.client:
        raise RuntimeError(
            "LLM client not initialized. Set OPENROUTER_API_KEY (or the "
            "provider key matching LLM_PROVIDER)."
        )
    return client


def _load_existing_keys() -> Dict[str, set]:
    db = SessionLocal()
    try:
        rows = db.query(
            DOTEnforcementOrder.source_url,
            DOTEnforcementOrder.title,
        ).all()
        source_urls = {r.source_url for r in rows if r.source_url}
        titles = {r.title for r in rows if r.title}
        return {"source_urls": source_urls, "titles": titles}
    finally:
        db.close()


def _is_already_ingested(
    existing: Dict[str, set],
    source_url: str,
    title: str,
) -> bool:
    """True when source_url or title already exists in DB (not order_number)."""
    if source_url and source_url in existing["source_urls"]:
        return True
    if title and title in existing["titles"]:
        return True
    return False


def _build_record(
    title: str,
    source_url: str,
    list_date: Optional[date],
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge crawled title/source_url with LLM fields (title/url never from LLM)."""
    operator_raw = parsed.get("operator_name") or None
    if isinstance(operator_raw, str):
        operator_raw = operator_raw.strip() or None

    order_type = (parsed.get("order_type") or "unknown").strip().lower()
    if order_type not in _ALLOWED_ORDER_TYPES:
        order_type = "unknown"

    # order_number is LLM-owned (no regex pre-parse of the title).
    llm_order_number = parsed.get("order_number") or None
    if isinstance(llm_order_number, str):
        llm_order_number = llm_order_number.strip() or None

    llm_date = _parse_list_date(parsed.get("effective_date"))
    effective_date = list_date or llm_date

    # Keep normalized name for later score-time lookup by name (no operator_id FK).
    normalized = normalize_operator_name(operator_raw) if operator_raw else None

    return {
        "order_number": llm_order_number,
        "source_url": source_url,
        "title": title,
        "effective_date": effective_date,
        "operator_name_raw": operator_raw,
        "operator_name_normalized": normalized,
        "order_type": order_type,
    }


def _insert_records(records: List[Dict[str, Any]]) -> int:
    """
    Batch-insert finished records in one commit.

    No per-row duplicate checks — callers already skip via source_url/title
    before LLM. Relies on DB unique indexes if a race slips through.
    """
    if not records:
        return 0

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        db.add_all([
            DOTEnforcementOrder(
                order_number=record.get("order_number"),
                source_url=record["source_url"],
                title=record["title"],
                effective_date=record.get("effective_date"),
                operator_name_raw=record.get("operator_name_raw"),
                operator_name_normalized=record.get("operator_name_normalized"),
                order_type=record.get("order_type"),
                last_verified_at=now,
                created_at=now,
                updated_at=now,
            )
            for record in records
        ])
        db.commit()
        return len(records)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
