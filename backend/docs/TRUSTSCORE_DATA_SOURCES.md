# TrustScore Data Sources — Implementation Status

Reference for the data sources behind the TrustJet TrustScore, tracking what the
**TrustScore 5.0 Data Sources** document requires against what the code does
today, and how the scraping actually works.

- **Source document:** `backend/TrustScore 5.0 Data Sources.docx`, plus the
  **Asset Stability & Churn / Legal & Title Clearness** addendum (assessed in §9)
- **Last updated:** 2026-11-08
- **Algorithm implemented in code:** **v5.0** (`src/trustscore/calculator_v5.py`),
  live at both call sites. v3 (`calculator.py`) is retained but no longer called.
- **Verified end to end** on Maine Instrument Flight (`BFYA`): 3 NTSB accidents
  + 1 FAA enforcement action produced **80.2 Premier**, with `Orfbase` 16.17,
  `Hsafety` 0.730, `ELI` 16.21 and `Hconduct` 0.667 — every term live.

---

## 1. Status at a glance

| # | Source | Populates | Status |
|---|--------|-----------|--------|
| 1 | FAA Part 135 roster | DBA array, `V_F` | **Implemented** — `scripts/ingest_part135.py`; 1,914 names across 1,870 certificates. Does **not** yield `Age_cert` (no issue date in the file). |
| 2 | OpSpecs D085 | `V_F`, `Churn_Fleet` | **Implemented, not yet usable.** `scripts/ingest_d085.py` ingests the FAA's public weekly Part 135 table — 11,188 authorized tails across 1,663 operators — so JETNET is not needed. `Churn_Fleet` is wired but **withheld**: only 31 days of history exists and `fetch_churn` refuses a window under 180 days (§9.1). |
| 3 | FAA Aircraft Registry | `MR_T`, `OS_T`, `ELI` | **Mostly implemented.** `MR_T`/`OS_T` from `gtj.aircraft`. `Lientail` now live — `src/common/faa_registry.py` parses MASTER/DOCINDEX/DEREG; 99 active encumbrances across 240 tails. Title-transfer velocity is **not** obtainable this way (§9.2). |
| 4a | NTSB CAROL | `ORF_True`, `IH_T` | **Implemented** — returns real accidents; searches every DBA name. |
| 4b | FAA AIDS | `ORF_True`, `IH_T` | **Not implemented** |
| 5 | ASN Wikibase | `L_Risk` | **Not implemented** — `Lrisk` is 0 for every operator |
| 6 | FAA SDRS | `SDR_Penalty` | **Implemented** — severities aligned to §6.2; pooled into `ORF_True` rather than its own term (see §6.6) |
| 7 | B2B Watchdogs | `ELI` | **Skipped** — ToS/licensing decision pending (§5) |
| 8 | DOT OACP | `ELI` | **Implemented end-to-end** — 675 orders; searches every DBA name |
| 9 | First-party telemetry | `Bespenalty`, `FFR` | **Out of scope** (the specification defers it) |

### Also implemented, beyond the source list

| Capability | Where | Notes |
|---|---|---|
| **Entity resolution (§8)** | `src/common/entity_resolution.py` | Resolves an operator to every name its certificate has used, in both directions. NTSB, FAA and DOT lookups all search the full array. 40 certificates currently carry more than one name. |
| **Coverage-aware flags** | `narrative_v5._apply_coverage` | A fourth state, `GREY`, for "not assessed". Only ever downgrades `GREEN`; `RED` and `YELLOW` stand on their own evidence. |
| **Risk Audit narrative (§9)** | `src/trustscore/narrative_v5.py` | Executive summary, six-category audit, broker guidance. Read-only with respect to scoring. |
| **Fleet snapshots** | `scripts/snapshot_fleet.py` | 22,327 rows, 2 months, from `gtj.aircraft` (JETNET's view of what an operator holds). |
| **D085 fleet ingest** | `scripts/ingest_d085.py` | 11,188 tails from the FAA's weekly Part 135 table — the *legally authorized* fleet. Written to the same table under `source='opspecs_d085'`, so the two are comparable. **2,097 tails are in JETNET but absent from D085** — held, but not authorized for charter. |
| **Tail liens** | `scripts/ingest_tail_liens.py` | 303 DOCINDEX filings → **99 active encumbrances** across 240 tails. Feeds `Lientail`. |
| **Registry parsers** | `src/common/faa_registry.py` | MASTER (184 MB), DOCINDEX, DEREG (275 MB). Header-name based, not fixed-offset. |

### Metric symbols

Confirmed from the source document's rendered appendix (the symbols are
equation objects and do not survive plain-text extraction of the `.docx`).

| Symbol | Meaning | In code today? |
|--------|---------|----------------|
| `Age_cert` | Operator age from **original certificate issuance date** | Partially — `operator_age_years` exists, but is read from `operators.business_started_date`, which is business registration, **not** certificate issuance |
| `V_F` | Current fleet size, used as the **square root denominator** | **Yes** — counted from `gtj.aircraft`; denominator is `MAX(1, SQRT(Vf))` |
| `Churn_Fleet` | Fleet size month-over-month differential | **Implemented, deliberately withheld** — `adapter_v5.fetch_churn` diffs D085 snapshots and is live, but returns `None` below a 180-day window. Has 31 days. See §9.1 for why this cannot be backfilled. |
| `MR_T` | Tail maintenance risk (from tail age) | **Yes** — `MRT`, `_calculate_tail_maintenance_risk` |
| `OS_T` | Tail ownership status, verified against the Part 135 certificate holder | **Yes** — `OST`, `_calculate_tail_ownership_status` |
| `ELI` | **Implemented.** Fed by **three** sources: source 3 (mechanic's liens, tax claims, rapid ownership transfers), source 7 (watchdog violations), source 8 (DOT legal actions and federal fines) | **No** — new metric, no field and no term in the OS equation |
| `ORF_True` | Fleet operational risk, from fleet severities | **Yes** — `ORF`, `_calculate_fleet_operational_risk`. The `_True` suffix suggests 5.0 distinguishes it from a raw/unnormalized variant; confirm whether the definition changed or only the name. |
| `IH_T` | Tail incident history, from tail severities | **Yes** — `IHT`, `_calculate_tail_incident_history`. **But see §6.6 — the wiring is wrong today.** |
| `L_Risk` | Latent risk from ASN wikibase, via LLM text-to-JSON | **Field exists, no pipeline** — `latent_risk_events` is accepted and scored; ASN is not ingested |
| `SDR_Penalty` | Mechanical deterioration and emergency procedures from SDRS | **Partial** — SDRs score, but pooled into `ORF_True` rather than a separate term; see §6.6 |
| `Lientail` | Active mechanic's/tax liens against a specific airframe | **Implemented** — `adapter_v5.fetch_tail_liens` from `gtj.tail_liens`. One charge per *financing*, not per document (§9.3). `GAP_TAIL_LIENS` still fires regardless, because DOCINDEX cannot clear title. |

Also live but **not in the source document:**

| Source | Status |
|--------|--------|
| FAA AGC quarterly enforcement reports | Implemented — `faa_enforcement_service.py` |
| UCC state filing registries (~50 states) | Implemented — `ucc_service.py` |

---

---

## 1a. What is still missing

Ordered by how much each would change a score. Everything here is a *data*
gap — the v5.0 formulas themselves are implemented and verified.

### Blocking, and time-sensitive

**`Churn_Fleet` — pipeline done, 31 of 180 days of history.**
The ingest and the differential are both implemented (`scripts/ingest_d085.py`,
`adapter_v5.fetch_churn`) against the FAA's own weekly D085 table. What is
missing is time: `fetch_churn` returns `None` below a 180-day window, so
`Churneffective` stays 0 and `asset_stability` stays GREY.

**This remains the only gap that gets worse with delay**, and the archive cannot
rescue it — web.archive.org holds exactly one capture of the Part 135
spreadsheet, not the "dozens" the addendum assumes (§9.1). A week not captured
is a week that cannot be reconstructed. Usable signal around **May 2027**, the
specification's full window November 2027, *provided the weekly cron runs*.

**`Age_cert` — wrong source, and absent for 47% of operators.**
§3 defines it as years since *original certificate issuance*. The code reads
`operators.business_started_date`, which is business registration — a different
date, usually earlier. Only 972 of 1,839 operators have one at all; the rest
fall back to a hardcoded 10.0 years. `Age_cert` feeds both `Cs` and the `V_F`
denominator, so this moves every score twice over. The Part 135 roster does not
carry an issue date, so this needs a source not yet identified.

One lead, now that the registry is parsed: `MASTER.txt` carries
`CERT ISSUE DATE` per **aircraft**. That is the airframe's registration date,
not the operator's certificate date, so it is not a substitute — but the
earliest such date across an operator's D085 fleet is a defensible *lower
bound* and strictly better than an invented 10.0. `certificate_age_is_estimated`
already exists to mark the result as inferred. Unvalidated; worth an hour before
committing to it.

### Significant

**`Lientail` / DOCINDEX — implemented; title still cannot be cleared.**
`scripts/ingest_tail_liens.py` ingests DOCINDEX weekly: **99 active encumbrances
across 240 tails**, charged one per financing rather than per document (§9.3).

Legal & Title Clearness nonetheless stays `GREY` on every report, by design.
DOCINDEX is a ~180-day rolling suspense index, so an unreleased lien from three
years ago is absent from it — finding nothing is not clear title. Only FAA CARES
(§9.4) can retire that flag, and it is not implemented.

**`L_Risk` / ASN Wikibase — not ingested.**
§4.1's latent-risk term — runway excursions, gear malfunctions, bird strikes —
capped at 15 points. Zero for everyone, so sub-regulatory occurrences are
invisible. Needs scraping plus LLM extraction; `llm_client.py` already exists.

**`SDR_Penalty` is not its own term.**
§6 names it as a distinct metric. SDRs are currently pooled into `ORF_True`
alongside accidents, so they do affect scores but are not separable and are
weighted by the shared severity scale rather than whatever 5.0 intends.
`sdrs_service.py` needs no change; only the aggregation point moves.

**FAA AIDS (Pipeline 4b) — not implemented.**
NTSB CAROL is live, but its companion incident database is not, so incidents
that never reach NTSB are missed.

### Known-wrong rather than missing

**`IH_T` is structurally sound but unexercised.**
`TailData.tail_accident_events` is a separate field from the fleet list, so v3's
bug cannot recur. But no deployed endpoint scores a specific tail — both call
sites pass `build_tail_data(tail_number="")`, which yields a neutral airframe.
TrustScore therefore collapses into FleetScore. `scripts/score_tail.py` exists
for single-tail scoring but is not wired to an endpoint.

**Entity resolution only looks forward.**
The DBA array is built from the current Part 135 roster plus `gtj.operators`.
A rename that happened *before* ingestion began is invisible unless
`--backfill` is run against web.archive.org, which reaches roughly March 2023.
Anything earlier — plausibly including the specification's own Red Wing example
— cannot be recovered.

**California UCC is blocked.**
`bizfileonline.sos.ca.gov` sits behind Imperva Incapsula; the search form never
renders and the underlying API returns HTTP 429. Fails fast (12s) rather than
waiting out a 100s timeout. Note UCC data does not feed v5.0 at all — liens are
specified to come from DOCINDEX — so this costs nothing but time.

**Alaska UCC returns junk.**
Reports `success: true` with filings like `×` and `Sort by` — page furniture
matched by the wrong selectors. A false positive, which is worse than an honest
failure. Harmless today for the same reason as California.

### What the gaps do to a score

Every missing input defaults to **neutral, which means no penalty**. A high score
with several `GREY` flags therefore reads "nothing adverse found in the sources
we could consult" — not "verified clean". `adapter_v5.missing_inputs()` reports
the gaps per operator, and the narrative is instructed to name them rather than
describe an unexamined category as satisfactory.

## 2. How a data source plugs in

Every source reaches the calculator the same way, which is what makes new ones
safe to add.

### The seam

`batch_verify_workflow.py` builds a flat list of event dicts and appends to it
once per source:

```python
fleet_events = [incident.dict() for incident in incidents]   # NTSB

faa_events = FAAEnforcementService.query_actions_as_fleet_events(operator.company)
if faa_events:
    fleet_events = fleet_events + faa_events                 # FAA enforcement

sdr_events = await SDRSService.query_as_fleet_events(operator.company)
if sdr_events:
    fleet_events = fleet_events + sdr_events                 # SDRS
```

The list then flows into `FleetScoreData.fleet_events`, and
`_calculate_fleet_operational_risk` reduces it to the ORF term.

### The event contract

A source must emit dicts shaped like this. The calculator reads every field
with `.get()`, so missing keys degrade rather than raise.

| Field | Required | Purpose |
|-------|----------|---------|
| `event_type` | **yes** | Dispatches severity. Must be registered — see below. |
| `event_date` | strongly preferred | Drives time decay `e^(-k·Δt)`. Missing dates are **skipped entirely** by ORF. |
| `event_id` | no | Traceability. |
| `injury_level`, `severity` | no | Used by the NTSB severity path. |
| `<prefix>_*` | no | Source-specific extras. Ignored by anything that does not know them. |

### Registering a new `event_type`

`_get_event_severity` ends in `else: return 5`. **An unregistered event type
silently scores 5** — no error, just a quietly wrong number. Adding a source
means adding its branch:

```python
if event_type == "faa_sdr":
    return self._get_sdr_severity(event)
```

Current severity scale:

| Event | Severity |
|-------|----------|
| NTSB fatal accident | 50 |
| NTSB non-fatal accident | 25 |
| Serious incident | 15 |
| FAA certificate revocation | 20 |
| FAA civil penalty ≥ $50k / $10–50k / < $10k | 15 / 10 / 5 |
| **SDR emergency** | **15** |
| **SDR fire, engine failure, loss of control** | **10** |
| **SDR crack, corrosion, fatigue** | **5** |
| **SDR routine** | **3** |
| Anything unregistered | 5 (default) |

SDR values sit deliberately below NTSB accident severities. Service
difficulties are maintenance signals, not accidents, and they are far more
numerous — scoring them like accidents would let routine findings dominate ORF.

### Failure isolation

Two layers, both required for a source to be genuinely additive:

1. The service catches its own exceptions and returns `[]`.
2. The workflow's append sits inside the existing `try/except`
   (`batch_verify_workflow.py` lines 347–458) whose handler falls back to an
   NTSB-only score.

A source that is down must leave the TrustScore **exactly** as it would have
been without it. Never let a scraper failure fail a scoring run.

---

## 3. Implemented sources

### 3.1 NTSB CAROL — `src/scoring/service.py`

- **Endpoint:** `POST https://data.ntsb.gov/carol-main-public/api/Query/Main`
- **Method:** JSON query API, not scraping. PDFs fetched per accident number.
- **Produces:** accident/incident events with injury level.

### 3.2 FAA AGC enforcement — `src/scoring/faa_enforcement_service.py`

- **Page:** `https://www.faa.gov/about/office_org/headquarters_offices/agc/practice_areas/enforcement/reports`
- **Method:** scrape the landing page for quarterly `.xlsx` links, parse with
  `openpyxl`, filter to entity type `A/C OR COMM OPER`, persist to
  `faa_enforcement_actions`.
- **Produces:** `event_type="faa_enforcement"` with `faa_*` extras.
- **Note:** not one of the document's sources, but it overlaps source 8's intent.

### 3.3 FAA SDRS — `src/scoring/sdrs_service.py` *(Phase 1, new)*

- **URL:** `https://www.faa.gov/av-info/download_SDR`
- **Method:** bulk download. Handles both a bare CSV and a ZIP containing one
  (the FAA has served both). No browser, no credentials, no pagination.
- **Produces:** `event_type="faa_sdr"` with `sdr_*` extras.

**Field quirks**, exactly as the source document warns:

- `SubmitterTypeCode == "E"` means Part 135. Everything else is filtered out.
- `RegistryNNumber` **omits the leading N** — tail `N427QS` appears as `427QS`.
  `normalize_tail_number()` restores it and is idempotent, so it is safe to
  apply to values from any source.

**Resilience built in:**

- Column names vary between extracts, so `_FIELD_ALIASES` maps several accepted
  spellings per field against a normalized key.
- If `SubmitterTypeCode` is **missing entirely**, the filter keeps all rows and
  logs a warning rather than discarding the extract. Operator matching
  downstream is the real filter.
- Five date formats are accepted. An unparseable date yields `None`, so the
  event still counts but without time decay.
- Matching prefers tail numbers when a fleet list is supplied, falling back to
  normalized operator name. Tail matching is more reliable — SDRS operator
  names are free text.

---

## 4. Not yet implemented

### 4.1 Resolved — the hardcoded inputs are gone

This section previously described three values pinned in the workflow
(`fleet_size = 1`, `aircraft_age_years = 5.0`, `operator_age_years = 10.0`) and
a linear ORF denominator. v5.0 replaced all of it:

| Was | Now |
|---|---|
| `fleet_size = 1` | `adapter_v5.fetch_fleet_size()` counts `gtj.aircraft` |
| `vf = fleet_size * ln(age+1)` | `/ MAX(1, SQRT(Vf))` per §4.1 |
| `aircraft_age_years = 5.0` | neutral tail for operator-level scoring; real age for tail scoring |
| `operator_age_years = 10.0` | read from `business_started_date` **when present** — still a fallback for 47% of operators, and still the wrong date (see §1a) |

Verified on Maine Instrument Flight: `d_scale` 0.777 from a real fleet of 5,
`Cs` 0.99999 from a real 33.9-year certificate.

### 4.2 Straightforward, just not done

| Source | Approach |
|--------|----------|
| **1 — Part 135 DB** | Bulk download, parse, match certificate holder. Gives `Age_cert` from original certificate issuance — which is **not** the `business_started_date` the code reads today. `Age_cert` feeds both `CS` (confidence) and the `V_F` denominator, so switching to it moves every score. |
| **3 — Aircraft Registry** | Bulk download. Gives `MR_T` (tail age) and `OS_T` (ownership verified against the Part 135 holder) — both of which **already exist** in the calculator, so these are drop-in replacements for the hardcoded `aircraft_age_years = 5.0`. The `[NEW]` lien / tax-claim / rapid-transfer parsing feeds `ELI`, which does not. |
| **4b — FAA AIDS** | Search form at `asip.faa.gov` — likely needs Playwright. Same event shape as NTSB; reuse that severity path. |
| **5 — ASN Wikibase** | Scrape `aviation-safety.net/wikibase/`, then LLM text-to-JSON. `llm_client.py` already exists. Check ToS and rate limits. |

---

## 5. Skipped and why

### Source 7 — B2B watchdogs — **skipped, needs a business decision**

The document proposes scraping `privatejetcardcomparisons.com` and
`ch-aviation.com` to "bypass expensive legal APIs."

**This is a legal question, not a technical one.** Both are private commercial
publishers and **ch-aviation is a paid subscription product** with most content
behind a login. Automated scraping likely violates their terms of service, and
the stated motivation — avoiding paid licensing — is the framing most likely to
attract a cease-and-desist.

Not implemented pending sign-off. If it proceeds, confirm ToS, licensing, and
whether an official data agreement is available.

The extraction target is specified, so the work is well defined once cleared —
headless scrape of each site's news feed, then a low-cost LLM prompted to emit:

```json
[{"operator_name": "...", "violation_type": "...", "date": "..."}]
```

Output feeds `ELI`, so it is blocked on that metric regardless of the legal
question.

### Source 8 — DOT OACP — **implemented end-to-end**

Full documentation: **[`DOT_OACP_ENFORCEMENT_ORDERS.md`](../DOT_OACP_ENFORCEMENT_ORDERS.md)**
(API, scrape, `order_type` criteria, ELI purpose).

Ingest: `POST /scoring/dot-ingest` → `gtj.dot_enforcement_orders`.

Scoring: `adapter_v5.dot_orders_to_legal_events` maps each order onto the §6.3
taxonomy as `DOT_OACP_CONSENT_ORDER` (25 points), feeding `ELI` and therefore
`Hconduct`. `adapter_v5.fetch_dot_orders_for_operator` performs the score-time
lookup by `operator_name_normalized`.

Only adverse outcomes score. `dismissal` and `unknown` are skipped — a
dismissed complaint means the operator was cleared, and an unclassified row is
not evidence of wrongdoing.

Known limitation: matching is by normalized operator name, not certificate
designator, so §8's DBA-rebranding defence does not yet apply to this source.

### Source 9 — telemetry — **out of scope**

The document marks it "NOT YET IMPLEMENTING IN CURRENT BUILD."

---

## 6. Open questions blocking TrustScore 5.0

> **RESOLVED — `TrustScore Algorithm v5.0.docx` is now the source of truth.**
>
> The full specification arrived and answers every question in this section.
> The algorithm is implemented in `src/trustscore/calculator_v5.py`, with 76
> tests in `tests/trustscore/test_calculator_v5.py`. v3 (`calculator.py`) is
> untouched and still in service.
>
> | Was open | v5.0 answer |
> |---|---|
> | `ELI` formula and weights | §4.2 + §6.3 — decayed sum over an 8-value taxonomy (35/25/20/15) |
> | `ELI` vs `FSF` overlap | `FSF` is gone. v5.0 has no additive financial term; liens feed `ELI`, and a tail-specific lien additionally feeds `Lientail` |
> | `SDR_Penalty` | §5.3 — `MIN(30, decayed sum)`, inside `Htailhistory` |
> | Square-root denominator | §4.1 — confirmed: `/ MAX(1, SQRT(Vf))` |
> | `Age_cert` | §3 — years since **original certificate issuance**, not business registration |
> | `ORF_True` | §4.1 — named `Orfbase`; the fleet accident term |
> | `Churn_Fleet` | §3 — `Churneffective`, asymmetric, from 12-month D085 snapshot diffs |
> | Commercial conduct metric | §4.2 — `Hconduct`, a non-compensatory multiplicative gate |
>
> **The `IH_T` bug flagged in §6.6 is fixed by construction.** `Iht` (§5.3) is
> defined over tail-specific accidents only, and `calculator_v5.py` reads them
> from `TailData.tail_accident_events` — a distinct field from the fleet list,
> so v3's `tail_events=fleet_events` mistake cannot recur.
>
> One structural note: v3's additive model permitted negative sub-scores;
> v5.0's cannot. Every health factor lies in (0, 1], so the composite
> approaches the 50-point floor asymptotically rather than being clamped from
> below.
>
> The historical analysis below is retained for context.

Phase 1 sources land independently of these, but the **5.0 algorithm cannot be
implemented** until they are answered.

**Resolved** — the metric symbols are now known (see §1). `MR_T` and `OS_T` map
onto the existing `MRT` and `OST`, so sources 1 and 3 largely feed metrics that
already exist rather than requiring new ones.

Still open:

1. **The ORF denominator changed.** The document specifies `V_F` as the
   *"Square Root Denominator"*. The code uses linear `fleet_size`:

   ```python
   vf = fleet_size * math.log(operator_age_years + 1)        # today
   vf = math.sqrt(fleet_size) * math.log(operator_age_years + 1)  # 5.0?
   ```

   This is not a small change. Square root stops large operators from diluting
   incidents through fleet size alone:

   | Fleet | Linear `V_F` | Sqrt `V_F` | Effect |
   |-------|-------------|-----------|--------|
   | 1 | 2.56 | 2.56 | unchanged |
   | 10 | 25.65 | 8.11 | **3.2× harsher** |
   | 50 | 128.25 | 18.14 | **7.1× harsher** |
   | 100 | 256.49 | 25.65 | **10× harsher** |

   Confirm the intended form before implementing — it materially re-ranks large
   operators.

2. **`Age_cert` is not what the code reads.** The document defines it as years
   since **original certificate issuance** (source 1). The code uses
   `operators.business_started_date`, i.e. business registration. These differ,
   often by years. `Age_cert` feeds both `CS` (confidence) and the `V_F`
   denominator, so the distinction changes every score.

3. **`Churn_Fleet` has no implementation or storage.** A month-over-month fleet
   differential requires fleet size *history*; nothing is currently snapshotted,
   so this cannot be computed retroactively. Capturing monthly fleet size should
   start early, even before the metric is used, or there will be no baseline.

4. **`ELI` is the single largest open item — three sources converge on it.**
   It has no `FleetScoreData` field and no term in
   `OS = 100 - ORF + FSF - CSF`, yet it is fed by:

   | Source | Contributes |
   |--------|-------------|
   | 3 — Aircraft Registry | mechanic's liens, tax claims, rapid ownership transfers |
   | 7 — B2B watchdogs | `{operator_name, violation_type, date}` from article text |
   | 8 — DOT OACP | legal actions and federal fines |

   Note the document's own framing places sources 7 and 8 under *"Commercial
   Integrity & Conduct"* while source 3 is under *"Regulatory & Physical
   Safety"* — so `ELI` deliberately blends financial encumbrance with commercial
   misconduct. That is a wide remit for one metric, and these inputs are not
   naturally commensurable: a mechanic's lien and a trade-press violation report
   are different kinds of evidence with different reliability.

   Needed before implementation:

   - The formula, and how the three input types are weighted against each other.
   - Its term and sign in the OS equation.
   - **Its relationship to `FSF`**, which already scores UCC liens via
     `_calculate_fleet_financial_score`. Does `ELI` replace `FSF`, supplement
     it, or cover only the encumbrances UCC filings miss? Without this, lien
     data risks being counted twice.

5. **`SDR_Penalty` is a dedicated metric; Phase 1 built it as a shared-pool
   severity.** See §6.6.

---

### 6.6 Two findings from the source-4/5/6 symbols

#### SDRS is meant to be its own term

The document assigns source 6 to `SDR_Penalty` — a **named metric**, implying a
distinct term in the score equation. Phase 1 instead routes SDRs into the shared
`fleet_events` pool, where they are scored by `_get_event_severity` and summed
into `ORF_True` alongside accidents and enforcement actions.

Why it was built that way: the symbol was not known at implementation time, and
the shared pool was the only additive integration point that could not disturb
existing scores.

What this means in practice:

- SDRs **do** influence the score today, through `ORF_True`.
- They are **not** separable — no `SDR_Penalty` value is reported, and the
  weighting is whatever the shared severity scale implies rather than whatever
  5.0 intends.
- Migrating is contained: `sdrs_service.py` needs no change at all. It already
  emits `sdr_severity` per event. Only the aggregation point moves — sum the
  events into their own `SDR_Penalty` term instead of appending them to
  `fleet_events`.

**Open question:** what is `SDR_Penalty`'s formula and weight in the 5.0
equation? Until that is known, the shared-pool treatment is the safer default,
because it is additive and reversible.

#### `IH_T` is fed the wrong data — existing bug

`IH_T` is defined as **tail** severities. The code passes the entire fleet's
events to it:

```python
# batch_verify_workflow.py:428  and  scoring/router.py:577
tail_events=fleet_events,          # every event for the whole operator
```

`IHT` is multiplied by 5 in `TS = 100 - MRT + OST - 5*IHT`, so every fleet-wide
incident is charged against **each individual tail**, five times over.

Measured on a 3-event fleet where only 1 event involved the tail in question:

| | `IHT` | TS penalty |
|---|---|---|
| All fleet events (current) | 63.74 | **318.67** |
| Only this tail's events (correct) | 34.08 | 170.39 |
| | | **148-point over-penalty** |

On a 100-point scale, that is severe — and it grows with fleet size, so the
largest operators are penalized hardest. This is independent of TrustScore 5.0
and of Phase 1; it is wrong under v3 as written.

Fixing it requires per-tail event attribution, which needs the FAA Aircraft
Registry (source 3) to map tails to operators — so it is naturally Phase 2 work.
`sdrs_service.py` already returns a `tail_number` on every event, and
`rows_to_fleet_events` accepts a `tail_numbers` filter, so SDRs are ready for
per-tail attribution as soon as a fleet list is available.

---

## 7. Adding a source — checklist

1. New module in `src/scoring/<source>_service.py`.
2. Expose `query_as_fleet_events(operator_name, ...) -> List[Dict]`, matching
   the existing services' signature.
3. **Catch everything; return `[]` on failure.** Never raise into the workflow.
4. Emit a distinct `event_type`.
5. **Register it in `_get_event_severity`** — otherwise it silently scores 5.
6. Append in `batch_verify_workflow.py` behind `if events:`, inside the
   existing `try`.
7. Keep the module free of `openpyxl` / database imports if it does not need
   them, so it stays testable in isolation. (`sdrs_service.py` duplicates
   `normalize_operator_name` for exactly this reason.)
8. Test the pure functions against sample rows before touching the network.

---

## 8. Environment

Scraping-relevant variables (full list in `.env.example`):

| Variable | Used by |
|----------|---------|
| `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID` | UCC scrapers. **Currently unset** — those scrapers will fail until filled. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `LLM_PROVIDER` | LLM extraction (sources 5, 7, 8). |
| `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET` | Database and auth. |
| `JETNET_USER`, `JETNET_PWD` | Source 2. Present but **not yet read** by this repo. |

No new credentials are required for SDRS, Part 135, Aircraft Registry, or AIDS —
all are public FAA downloads.

> **Known issue:** `src/common/config.py` ignores `SUPABASE_URL` for the actual
> database connection and uses a hardcoded production password. That credential
> is in git history; rotating it is the real fix.

---

## 9. Asset Stability & Churn / Legal & Title Clearness — addendum assessed

The addendum proposes replacing a JETNET subscription with free FAA sources. It
is largely right, and most of it is now implemented. Four of its specific
claims do not survive contact with the real files, which is recorded here so
nobody re-derives them.

Everything below was measured against the live FAA download (73,154,051 bytes,
ingested 2026-11-08) and the FAA's own `ardata.pdf` inside that archive.

### 9.1 Fleet churn via the weekly Part 135 table — **implemented, output withheld**

`scripts/ingest_d085.py`, weekly. Downloads the public `.xlsx`, groups by the
4-character designator, and writes one row per authorized tail into
`gtj.fleet_snapshots` under `source='opspecs_d085'`.

Verified: **11,482 authorized aircraft parsed → 11,188 matched to our
operators across 1,663 certificates.** 92 certificates in the roster are not in
`gtj.operators`.

`adapter_v5.fetch_churn` computes `TailsAdded` / `TailsRemoved` /
`BaselineVf` as a set difference of N-numbers between snapshots. Confirmed
working against a simulated 365-day baseline: `added=1, removed=0, baseline=2,
window_days=365`.

**The addendum's backfill claim is wrong, and this is the binding constraint.**
It states the Wayback Machine holds "dozens of timestamped snapshots" of the
Part 135 spreadsheet. The CDX API returns **exactly one**:

```
20261018  526,783 bytes
```

So a trailing 12-month baseline cannot be assembled from the archive. `--backfill`
runs, finds that single capture, and writes it — which is why the database holds
two snapshot months whose contents are 31 days apart and nearly identical.

`fetch_churn` therefore refuses any window under **180 days** and returns
`None`, so `GAP_CHURN` keeps firing and `asset_stability` stays GREY. This is
deliberate: `Churneffective = 0` is a *full confidence* score under §3, so
reporting a 31-day diff as churn would read as verified stability. Before the
guard, Flexjet reported `3 added / 3 removed` from a three-week
self-comparison.

**Consequence:** churn has to accrue month by month. At the 180-day threshold
that is roughly **May 2027**; for the full 12-month window, November 2027. Every
missed weekly run pushes it out, which makes the cron load-bearing:

```
0 3 * * 1 cd /home/gtjadmin/gtj-scraper/backend && \
          venv/bin/python3 scripts/ingest_d085.py >> ~/d085.log 2>&1
```

**Also unavailable:** the addendum's backup portal, `av-info.faa.gov/OpSpec.asp`,
returns HTTP 503. It shares an IP (`23.198.132.191`) with `registry.faa.gov` and
`cares.faa.gov`; all three refuse some networks while `www.faa.gov` serves
normally. The production server reaches `registry.faa.gov`; this developer
machine does not, which is why `ingest_tail_liens.py` accepts `--archive`.

### 9.2 Tail ownership velocity via MASTER/DEREG — **not deliverable this way**

The addendum says to match a tail's airframe serial across `MASTER.txt` and
`DEREG.txt` to expose "every previous N-number and registered owner". Measured,
it does not work, and the failure is quiet rather than loud.

**Serial number alone is not a key.** In `DEREG.txt`, serial `'1'` appears
**3,936 times** and `'001'` **1,967 times**, across unrelated manufacturers.
Matching on serial reported **3,707 of 10,092** Part 135 tails as having prior
owners. Adding `MFR MDL CODE` to the key reduced that to **0** — so the original
figure was almost entirely collisions: one Cessna inheriting every prior owner
of every other airframe numbered 1. Plausible-looking and entirely fabricated.

**And 0 is the correct answer.** `DEREG.txt` holds *terminated* registrations —
97% of sampled rows carry a `CANCEL-DATE` — while an airframe still flying is in
`MASTER.txt` precisely because it has not been deregistered. The two files
overlap on **46 keys out of 300,081 (MASTER) and 379,796 (DEREG)**.

`src/common/faa_registry.py` documents this inline rather than exposing an API
that returns empty lists a caller would read as "one owner since new".

Two routes remain, neither implemented:

- **`MASTER.txt` snapshot diffs.** `CERT ISSUE DATE` moves when a new
  registration certificate is issued, so differencing two snapshots does detect
  a transfer. This is the addendum's other suggestion and it is sound — but like
  churn it needs accrued history, and Wayback coverage of the registry zip is
  sparse and gapped (captures in 2016, 2017, 2020, 2021, 2024, 2025, 2026 — no
  2018, 2019, 2022, 2023).
- **FAA CARES** (§9.4).

**The addendum's yearly-archive claim is also wrong.** It states the FAA hosts
`ReleasableAircraft.year.zip` files under a "Yearly Aircraft Registration
Database" heading "directly underneath the daily zip link". No such section
exists on the live page: the only `.zip` link is the current
`ReleasableAircraft.zip`, and `ReleasableAircraft.2025.zip` returns HTTP 403.

### 9.3 Legal & Title via DOCINDEX — **implemented**

`scripts/ingest_tail_liens.py`, weekly, into `gtj.tail_liens` (migrations 081
and 082). Current state: **303 filings, 240 tails, 99 active encumbrances**,
observation reaching back to 2026-05-12.

**The addendum's DOC-TYPE codes are wrong.** It describes single letters — `'M'`
mechanic's, `'T'` tax. The real codes are three characters, per `ardata.pdf`
(positions 165–167):

| Code | Meaning | Treated as |
|---|---|---|
| `S/A` | Security Conveyance/Lien | **lien** |
| `CSC` | Evidence of Ownership w/Lien | **lien** |
| `REL` | Lien Release | discharge |
| `REP` | Repossession | discharge |
| `BOS` | Evidence of Ownership | conveyance |
| `DIS` / `CRT` | Disclaimer / Court Documents | neither |

The index does **not** distinguish mechanic's from tax liens — both are `S/A` —
so §4.2's separate charges cannot be told apart from this source. Both score as
"active encumbrance", which is the distinction that matters.

Three further corrections, each of which silently produced wrong output first:

1. **The date field is `DRDATE`**, not `DOC-DATE`. There is no `DOC-DATE` column.
2. **`COLLATERAL` holds an N-number, not a serial**, and only when
   `TYPE-COLLATERAL = 1`. Codes 2 and 3 carry engine and propeller
   make/model/serial; parsing those as tails attributes an engine lien to
   whichever airframe the string collides with.
3. **Every file opens with a UTF-8 BOM.** Decoded as Latin-1 it becomes `Ï»¿`
   welded onto the first header name, making that column unfindable. The parser
   returned **0 rows with no error** — a pipeline that looks healthy and
   ingests nothing.

**One charge per financing, not per document.** Aircraft lending records one
document per collateral item — airframe, each engine, avionics — so a single
secured loan arrives as a run of sequential DOC-IDs. `N402XT` carried 16 from
`GUNTRACK AVIATION LLC` on one day (`ARE016566074`–`6108`, stepping by 2).
Charged per document that was 18 §4.2 penalties, scoring **67.45** against
95.92 unencumbered — a routine loan read as catastrophic distress.
`fetch_tail_liens` groups by `(doc_type, doc_date, party)`, giving 3
encumbrances and **74.09**.

Note the deliberate asymmetry: `gtj.tail_liens` stores **one row per document**
(the factual record of what was filed), while the scoring query returns **one
event per financing**. Both are correct. The `reference` string carries the
volume — `GUNTRACK AVIATION LLC (16 documents)` — so an audit can still
disclose it.

**`GAP_TAIL_LIENS` fires unconditionally, even when liens are found.** DOCINDEX
is a ~180-day rolling suspense index: a lien recorded years ago and never
released is simply absent. Finding filings proves encumbrance; finding none
proves nothing about title. Without this, ingesting liens would have flipped
`legal_title` from GREY to GREEN for ~11,000 tails on the strength of a 180-day
lookback.

### 9.4 FAA CARES — **not implemented**

`cares.faa.gov` holds the permanent life-of-airframe packets: every Bill of
Sale, Security Agreement, mechanic's lien and release since manufacture. It is
the only source that can actually clear title, and therefore the only thing
that can retire `GAP_TAIL_LIENS` or deliver §9.2's ownership velocity.

Not started. Two obstacles:

- The host returns **HTTP 403** from this network (same IP as `registry.faa.gov`).
  Whether the production server reaches it is untested.
- It serves scanned PDF packets per airframe, so ~2,000 Part 135 tails means
  ~2,000 Playwright sessions plus OCR — a different order of effort from parsing
  a flat file, and the only item here that needs a real build rather than a
  parser.

### 9.5 Summary

| Addendum item | Status |
|---|---|
| Weekly Part 135 D085 ingest | **Implemented** — 11,188 tails |
| Group by designator for `V_F` / `S_current` | **Implemented** |
| Rolling churn diff | **Implemented**, output withheld until ≥180 days of history |
| Wayback backfill for churn | **Not possible** — 1 capture exists, not "dozens" |
| AVInfo backup portal | **Unreachable** — HTTP 503 |
| DOCINDEX lien parsing | **Implemented** — 99 active encumbrances |
| FAA yearly registry archives | **Do not exist** on the live page; HTTP 403 |
| MASTER/DEREG serial match for prior owners | **Does not work** — serial is not a key; DEREG holds dead registrations |
| MASTER snapshot diffs for title velocity | **Not implemented** — needs accrued history |
| `DEREG.txt` for prior N-numbers | **Not usable** for currently-flying tails |
| FAA CARES packets | **Not implemented** — 403 here, and a large build |
