#!/usr/bin/env python3
"""Quick smoke test for DOT title helpers (no network / DB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring.dot_enforcement_service import (
    parse_orders_html,
    _parse_llm_json_array,
    _build_record,
    _assign_record_ids,
    _batch_inputs_for_prompt,
    _LLM_BATCH_SIZE,
)


def main() -> None:
    assert _LLM_BATCH_SIZE == 125

    html = """
    <table class="views-table cols-2">
    <tbody>
    <tr><td><a href="/airconsumer/eo-2026-3-9">Southwest Airlines - Order 2026-3-9</a></td><td>03/18/2026</td></tr>
    <tr><td><a href="/airconsumer/eo-2026-7-2">Complaint of X v. American Order of Dismissal 2026-7-2</a></td><td>07/02/2026</td></tr>
    </tbody>
    </table>
    """
    rows = parse_orders_html(html)
    assert len(rows) == 2, rows
    assert rows[0]["title"].startswith("Southwest")
    assert str(rows[0]["effective_date"]) == "2026-03-18"
    assert rows[0]["source_url"].endswith("/airconsumer/eo-2026-3-9")
    assert "Dismissal" in rows[1]["title"]

    by_id = _assign_record_ids(rows)
    assert set(by_id.keys()) == {"1", "2"}
    inputs = _batch_inputs_for_prompt(by_id)
    assert inputs[0]["record_id"] == "1"
    assert "source_url" not in inputs[0]
    assert inputs[0]["list_date"] == "2026-03-18"

    parsed_rows = _parse_llm_json_array(
        '```json\n['
        '{"record_id": "1", "operator_name": "Southwest Airlines", '
        '"order_type": "enforcement_action", "order_number": "2026-3-9", '
        '"effective_date": "2026-03-18"},'
        '{"record_id": "2", "operator_name": "American", '
        '"order_type": "dismissal", "order_number": "2026-7-2", '
        '"effective_date": "2026-07-02"}'
        ']\n```'
    )
    assert len(parsed_rows) == 2
    assert "source_url" not in parsed_rows[0]
    assert "title" not in parsed_rows[0]

    crawled = by_id[parsed_rows[0]["record_id"]]
    record = _build_record(
        title=crawled["title"],
        source_url=crawled["source_url"],
        list_date=crawled["effective_date"],
        parsed=parsed_rows[0],
    )
    assert "operator_id" not in record
    assert record["order_type"] == "enforcement_action"
    assert record["order_number"] == "2026-3-9"
    assert record["source_url"].endswith("/airconsumer/eo-2026-3-9")
    assert record["title"].startswith("Southwest")

    print("ok")


if __name__ == "__main__":
    main()
