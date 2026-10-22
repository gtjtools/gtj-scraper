# DOT OACP Enforcement Orders — TrustScore Data Source #8

Documentation for ingesting U.S. Department of Transportation (DOT) Office of
Aviation Consumer Protection (OACP) enforcement orders into TrustJet.

| | |
|---|---|
| **TrustScore 5.0 source** | Item **#8** — *DOT Office of Aviation Consumer Protection (OACP) [NEW]* |
| **Source document** | `TrustScore 5.0 Data Sources.docx` (Appendix: Data Sources) |
| **Section in doc** | *Commercial Integrity & Conduct Pipelines* |
| **Implementation** | `src/scoring/dot_enforcement_service.py` |
| **API** | `POST /scoring/dot-ingest` |
| **Table** | `gtj.dot_enforcement_orders` (migrations P114 + P115) |
| **Score wiring** | **Not yet** — persists data for future `ELI`; does not affect TrustScore today |

---

## 1. Purpose and context

TrustScore 5.0 groups sources into:

1. **Regulatory & Physical Safety Databases** (items 1–6)
2. **Commercial Integrity & Conduct Pipelines** (items 7–9)

Item **#8** sits in the second group. The appendix says these sources measure
**commercial toxicity** via targeted scraping (and later telemetry), rather than
expensive legal APIs.

### Why we ingest DOT orders

The DOT OACP publishes public **enforcement orders** (settlements, consent
orders, dismissals, and other actions) against airlines and aviation companies.
For TrustJet this is evidence of **legal / consumer-protection enforcement**
tied to an operator name.

Per the TrustScore 5.0 appendix:

> **Algorithm Usage:** Parses legal actions and federal fines to populate the
> **ELI** metric. Unfortunately, there is no way to filter for operators here,
> so we will likely also need to feed the case names into an LLM.

So the ingest job exists to:

1. Pull the full public list (no operator filter on the site).
2. Use an LLM to extract operator names and classify each case.
3. Store rows for later use when **ELI** is defined in the formula.
4. Stay idempotent for hourly (or similar) re-runs without duplicate inserts.

Until `ELI` exists in the calculator, this data is **stored only** — it does
not change Operational Score (OS) or any live TrustScore term.

---

## 2. What we scrape

| Item | Detail |
|------|--------|
| **Acquisition URL** | https://www.transportation.gov/airconsumer/enforcement-orders?field_subject_target_id=All&items_per_page=All |
| **Publisher** | U.S. DOT — Office of Aviation Consumer Protection |
| **Page shape** | Drupal “views” HTML table (`views-table`): title (link) + date |
| **Scope** | **All rows** on the list, including dismissals (no title-based drop) |

### Fields taken from the crawl (before LLM)

| Field | Source on page |
|-------|----------------|
| `title` | Link text in the first column |
| `source_url` | Absolute case URL from the link `href` |
| `effective_date` | List date in the second column (treated as listing date, not a proven legal “effective” date) |

There is **no operator filter** on the DOT page. Every case name must be
classified in software (LLM), as the appendix notes.

### Fetch strategy

1. Browser-like `httpx` GET (Akamai often returns 403 to bot-like clients).
2. On 403 / empty table → Playwright (or Browserbase) fallback.
3. Parse only the `views-table` (no regex fallback if the table is empty).

---

## 3. API — `POST /scoring/dot-ingest`

Triggers a full scrape → skip known rows → LLM batch format → batch insert.

### Query parameters

| Param | Type | Default | Meaning |
|-------|------|---------|---------|
| `dry_run` | bool | `false` | `true` → scrape/log only; **no LLM, no DB**. `false` → LLM + insert for new rows. |
| `limit` | int ≥ 1 | omit | Max number of **new** rows to send to the LLM (omit = all new rows). |

### Examples

```bash
# Crawl only (safe without migration / without spending LLM tokens)
curl -X POST "http://localhost:8000/scoring/dot-ingest?dry_run=true"

# Live ingest (LLM + insert)
curl -X POST "http://localhost:8000/scoring/dot-ingest"

# Live ingest, first 10 new rows only
curl -X POST "http://localhost:8000/scoring/dot-ingest?limit=10"
```

### Response summary (typical keys)

| Key | Meaning |
|-----|---------|
| `rows_found` | Rows parsed from the DOT list |
| `rows_logged` | Rows logged during the run |
| `already_ingested` | Skipped because `source_url` or `title` already exists |
| `pending_for_llm` | New rows queued for LLM |
| `llm_batches` | Number of LLM batches (size 125) |
| `records_inserted` | Rows written this run |
| `llm_failures` | Rows that failed LLM mapping / missing `record_id` |
| `dry_run` / `limit` | Echo of request options |

### Idempotency (hourly runs)

- Skip key: **`source_url` or `title`** already in `gtj.dot_enforcement_orders`.
- If **every** list row is already stored → early return; **no LLM client, no OpenRouter calls**.
- Already-ingested rows are **not** updated (`last_verified_at` is not touched).
- DB unique index on `source_url` is a backstop against races.

---

## 4. Ingestion pipeline

```
1. Fetch HTML list (items_per_page=All)
2. Parse title, list date, case URL (all rows)
3. Load existing source_url + title; skip matches
4. If nothing new → stop
5. LLM-format new rows in parallel batches of 125
   (input: record_id + title + list_date)
6. Map LLM results by record_id → attach crawled title + source_url
7. Batch-insert into gtj.dot_enforcement_orders
```

### LLM batching

| Setting | Value |
|---------|--------|
| Batch size | 125 rows per OpenRouter call |
| Concurrency | Up to 4 batches in parallel |
| Model | `google/gemini-2.5-flash` (same pattern as `gtj-backend` LLM helpers; model in code, not env) |
| Env | `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY=...` |

LLM input per row: `{ record_id, title, list_date }`  
LLM output per row: `{ record_id, order_number, effective_date, operator_name, order_type }`  

`title` and `source_url` are **never** taken from the LLM; they are mapped locally
via ephemeral per-batch `record_id`.

Operator matching at ingest time: **by name only** (`operator_name_raw` /
`operator_name_normalized`). There is **no `operator_id` FK** on the table
(removed in migration P115). Score-time lookup will query by normalized name.

---

## 5. `order_type` values and identification criteria

Stored as plain `varchar` (not a Postgres enum). Allowed values:

| `order_type` | Criteria (from title wording) |
|--------------|-------------------------------|
| `dismissal` | Title explicitly indicates a complaint/case/proceeding was dismissed — e.g. “Order of Dismissal”, “Dismissal Order”, “Dismissing Formal Complaint”, or clear equivalents. |
| `settlement` | Title explicitly identifies a settlement or settlement agreement. |
| `consent_order` | Title explicitly identifies a consent order. |
| `enforcement_action` | Title clearly identifies a substantive DOT enforcement order/action that does **not** fit the types above (e.g. typical “Airline - Order YYYY-M-D” style cases). |
| `unknown` | Not enough evidence in the title to assign one of the other categories. |

### Classification rules (important)

- Classify from **document type wording**, not assumed guilt or outcome.
- Do **not** treat every title containing the word “Order” as `enforcement_action`.
- If multiple types appear, use the clearest explicit type; if still ambiguous → `unknown`.
- A **dismissal** or **settlement** alone does **not** mean the operator should take a negative TrustScore hit; that decision belongs to the future `ELI` formula and weighting.

### Other LLM-extracted fields

| Field | Rule (summary) |
|-------|----------------|
| `order_number` | DOT order id from the title when clear (e.g. in “Airline - Order 2025-12-4”). Not list dates, written calendar dates, or docket ids unless clearly the order number. |
| `effective_date` | From the **list date** supplied to the LLM (YYYY-MM-DD), not inferred from the title. |
| `operator_name` | Respondent / subject of the order (after “v.” / “versus” when applicable). Multiple operators joined with `"; "`. Complainants are not operators unless also respondents. |

---

## 6. Persisted schema (`gtj.dot_enforcement_orders`)

| Column | Role |
|--------|------|
| `id` | UUID PK |
| `order_number` | Optional DOT order id (LLM) |
| `source_url` | Case page URL — primary skip / unique key |
| `title` | Exact list headline — secondary skip key |
| `effective_date` | Listing date from the DOT page |
| `operator_name_raw` | Name(s) from LLM |
| `operator_name_normalized` | Normalized for later score-time name match |
| `order_type` | See §5 |
| `last_verified_at` / `created_at` / `updated_at` | Timestamps (set on insert) |

Migrations:

- **P114** — create table  
- **P115** — drop `operator_id` (name-based matching only for now)

---

## 7. Future formula role — `ELI`

### What the TrustScore 5.0 appendix says

Item #8 algorithm usage (paraphrased from the appendix):

- Parse **legal actions and federal fines**.
- Populate the **`ELI`** metric.
- No operator filter on the site → case names go through an **LLM**.

`ELI` is also fed by other appendix sources:

| Source | Contribution to `ELI` (per 5.0 framing) |
|--------|----------------------------------------|
| **3** — FAA Aircraft Registry | Mechanic’s liens, tax claims, rapid ownership transfers |
| **7** — B2B watchdogs | Scraped articles → `{operator_name, violation_type, date}` |
| **8** — DOT OACP *(this source)* | Legal actions and federal fines |

Sources 7 and 8 sit under **Commercial Integrity & Conduct**; source 3 under
**Regulatory & Physical Safety**. So `ELI` is intentionally a blend of
financial encumbrance and commercial / legal misconduct.

### What is *not* defined yet

The appendix names **`ELI`** as the sink for DOT data but does **not** publish a
closed-form equation for `ELI` in the extracted text (symbols are often equation
objects in the `.docx`). Open design work still includes:

- Exact `ELI` formula and how DOT rows are weighted vs liens / watchdog hits.
- Which `order_type` values count (e.g. exclude `dismissal`? weight
  `consent_order` / `enforcement_action` higher?).
- Sign and placement of `ELI` in the Operational Score equation (today’s code
  still uses forms like `OS = 100 - ORF + FSF - CSF` without an `ELI` term).
- Relationship to existing UCC / financial scoring (`FSF`).

Until that lands, ingestion is the correct milestone: **collect and classify**;
**do not** invent score impact.

### Intended future use (engineering view)

1. At score time, look up orders by **normalized operator name**.
2. Filter / weight by `order_type` and recency (`effective_date`).
3. Feed the result into the `ELI` term once the 5.0 formula is specified.
4. Optionally enrich later with fine amounts from case detail pages (not in the
   list scrape today).

---

## 8. Related code and docs

| Path | Role |
|------|------|
| `src/scoring/dot_enforcement_service.py` | Scrape, LLM batch, insert |
| `src/scoring/router.py` | `POST /scoring/dot-ingest` |
| `src/common/models.py` | `DOTEnforcementOrder` |
| `src/trustscore/llm_client.py` | OpenRouter client / model |
| `../gtj-backend/migrations/P114_create_dot_enforcement_orders.py` | Create table |
| `../gtj-backend/migrations/P115_drop_operator_id_from_dot_enforcement_orders.py` | Drop `operator_id` |
| `docs/TRUSTSCORE_DATA_SOURCES.md` | Cross-source TrustScore status |
| `TrustScore 5.0 Data Sources.docx` | Authoritative appendix |

---

## 9. Status summary

| Area | Status |
|------|--------|
| Scrape full OACP list | Implemented |
| LLM extract + `order_type` | Implemented |
| Persist to `dot_enforcement_orders` | Implemented |
| Idempotent re-run / hourly safe | Implemented |
| Wire into TrustScore / `ELI` | **Not implemented** — waiting on formula |

Last updated: 2026-10-16
