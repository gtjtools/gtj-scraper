# TrustScore Data Sources — Implementation Status

Reference for the data sources behind the TrustJet TrustScore, tracking what the
**TrustScore 5.0 Data Sources** document requires against what the code does
today, and how the scraping actually works.

- **Source document:** `backend/TrustScore 5.0 Data Sources.docx`, plus the
  **Asset Stability & Churn / Legal & Title Clearness** addendum (assessed in §9)
  and the **Flag Resolution, Lien Severity & Narrative Elaboration** spec
  (implemented in §10), plus the **catastrophic-event** fixes (§11)
- **Last updated:** 2026-11-16
- **Algorithm implemented in code:** **v5.0** (`src/trustscore/calculator_v5.py`),
  live at both call sites. v3 (`calculator.py`) is retained but no longer called.
- **Verified end to end** on Maine Instrument Flight (`BFYA`): 3 NTSB accidents
  + 1 FAA enforcement action produced **80.2 Premier**, with `Orfbase` 16.17,
  `Hsafety` 0.730, `ELI` 16.21 and `Hconduct` 0.667 — every term live.

---

## 1. Status at a glance

How to read the **Access** column:

- **Public scrape** — a free, unauthenticated download or page. No contract.
- **Public, blocked** — public by policy, but the host refuses our requests.
  Needs FAA registered access, not an engineering fix.
- **Commercial** — a paid subscription or licence is required.
- **Untested** — not probed from the production server; status unknown.

No source in this table is behind a paid API *that we need*. JETNET was the one
commercial dependency the specification assumed, and the D085 ingest replaced it
(source 2). The two genuinely blocked items are free-but-gated FAA systems, and
the one commercial item (source 7) is optional.

| # | Source | Populates | Access | Status |
|---|--------|-----------|--------|--------|
| 1 | FAA Part 135 roster | DBA array, `V_F` | Public scrape | **Implemented** — `scripts/ingest_part135.py`; 1,914 names across 1,870 certificates. Does **not** yield `Age_cert` (no issue date in the file). |
| 2 | OpSpecs D085 | `V_F`, `Churn_Fleet` | Public scrape — **replaces JETNET** | **Implemented, not yet usable.** `scripts/ingest_d085.py` ingests the FAA's public weekly Part 135 table — 11,188 authorized tails across 1,663 operators — so JETNET is not needed. `Churn_Fleet` is wired but **withheld**: only 31 days of history exists and `fetch_churn` refuses a window under 180 days (§9.1). |
| 3 | FAA Aircraft Registry | `MR_T`, `OS_T`, `ELI` | Public scrape | **Mostly implemented.** `MR_T`/`OS_T` from `gtj.aircraft`. `Lientail` live and backfilled — **524 active encumbrances across 482 tails**, 2.2 years of history (§9.3, §9.7). Title-transfer velocity is **not** obtainable this way (§9.2). Reachable from the production server only. |
| 4a | NTSB CAROL | `ORF_True`, `IH_T` | Public scrape | **Implemented** — searches every DBA name, and since 2026-11-16 **also queries by registration number** (§11.2). The cached `gtj.ntsb_incidents` table is **15 months stale** and must be re-ingested (§11.1). |
| 4b | FAA AIDS | `ORF_True`, `IH_T` | Public, **untested** | **Not implemented.** No subscription known to be required — AIDS is a public FAA incident database. Returns 403 from the developer machine, but so does `registry.faa.gov`, which the server reaches; **probe from the server before assuming it is blocked**. |
| 5 | ASN Wikibase | `L_Risk` | Public, **untested** | **Not implemented** — `Lrisk` is 0 for every operator. Free to read; no subscription. Returns 403 here (Cloudflare), untested from the server. Needs scraping plus LLM extraction, not a contract. |
| 6 | FAA SDRS | `SDR_Penalty` | Public scrape | **Implemented** — severities aligned to §6.2; pooled into `ORF_True` rather than its own term (see §6.6) |
| 7 | B2B Watchdogs | `ELI` | **Commercial** | **Skipped** — the only source here needing a paid licence. A cost and terms-of-service decision, not an engineering one (§5). |
| 8 | DOT OACP | `ELI` | Public scrape | **Implemented end-to-end** — 675 orders; searches every DBA name |
| 9 | First-party telemetry | `Bespenalty`, `FFR` | Internal | **Out of scope** (the specification defers it) |
| — | FAA CARES | permanent lien/title record | **Public, blocked** | **Not implemented.** Free by policy; HTTP 403 from the production server *and* the developer machine. Needs FAA registered access — procurement, not engineering. Largely worked around (§9.7). |
| — | FAA AVInfo | `Age_cert` | **Public, blocked** | **Not implemented.** Free by policy; HTTP 503 from the production server too. The only source holding certificate issuance dates, so `Age_cert` stays an acknowledged estimate (§1a). |

### Also implemented, beyond the source list

| Capability | Where | Notes |
|---|---|---|
| **Entity resolution (§8)** | `src/common/entity_resolution.py` | Resolves an operator to every name its certificate has used, in both directions. NTSB, FAA and DOT lookups all search the full array. 40 certificates currently carry more than one name. |
| **Coverage-aware flags** | `narrative_v5._apply_coverage` | A fourth state, `GREY`, for "not assessed". Only ever downgrades `GREEN`; `RED` and `YELLOW` stand on their own evidence. **Reworked 2026-11-16 to an anchor OR-gate — `GREY` now requires total category blindness, not merely one gap (§10.1).** |
| **Lien severity tiers** | `src/common/lien_classification.py` | §10.2. Tiers a filing 1–3 from who filed and the document type, since DOCINDEX publishes no claim amounts. Breaks the count-vs-severity inversion: one tax levy now outweighs twenty bank financings. |
| **Clean-search evidence** | `narrative_v5._clean_searches` | §10.1. Nil returns from sources that *were* queried, phrased as affirmative findings, so the narrative can cite them as positives instead of seeing only an absence. |
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
| `Churn_Fleet` | Fleet size month-over-month differential | **Implemented, deliberately withheld** — `adapter_v5.fetch_churn` diffs D085 snapshots and is live, but returns `None` below a 180-day window. Has 31 days. See §9.1 for why this cannot be backfilled. As of §10.1 the *unmeasured* state is tracked explicitly (`churn_measured`) rather than inferred from a zero, so a stable fleet is no longer indistinguishable from an unseen one. |
| `MR_T` | Tail maintenance risk (from tail age) | **Yes** — `MRT`, `_calculate_tail_maintenance_risk` |
| `OS_T` | Tail ownership status, verified against the Part 135 certificate holder | **Yes** — `OST`, `_calculate_tail_ownership_status` |
| `ELI` | **Implemented.** Fed by **three** sources: source 3 (mechanic's liens, tax claims, rapid ownership transfers), source 7 (watchdog violations), source 8 (DOT legal actions and federal fines) | **No** — new metric, no field and no term in the OS equation |
| `ORF_True` | Fleet operational risk, from fleet severities | **Yes** — `ORF`, `_calculate_fleet_operational_risk`. The `_True` suffix suggests 5.0 distinguishes it from a raw/unnormalized variant; confirm whether the definition changed or only the name. |
| `IH_T` | Tail incident history, from tail severities | **Yes** — `IHT`, `_calculate_tail_incident_history`. **But see §6.6 — the wiring is wrong today.** |
| `L_Risk` | Latent risk from ASN wikibase, via LLM text-to-JSON | **Field exists, no pipeline** — `latent_risk_events` is accepted and scored; ASN is not ingested |
| `SDR_Penalty` | Mechanical deterioration and emergency procedures from SDRS | **Partial** — SDRs score, but pooled into `ORF_True` rather than a separate term; see §6.6 |
| `Lientail` | Active mechanic's/tax liens against a specific airframe | **Implemented, now severity-tiered** — `adapter_v5.fetch_tail_liens` from `gtj.tail_liens`. One charge per *financing*, not per document (§9.3), and since §10.2 charged at a per-tier rate with Tier 1 log-dampened and capped. `GAP_TAIL_LIENS` no longer fires unconditionally: it tracks whether the lookup *ran* (§10.1). |

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

**The `MASTER.txt` lead was tested and does not work.** `CERT ISSUE DATE` has
98% coverage (294,592 of 300,082 rows), so it looked promising. Taking the
earliest such date across each operator's D085 fleet yields a date for 1,616 of
1,659 operators — but measured against the 870 operators that also have a
`business_started_date`, it agrees exactly only **16%** of the time, and the
disagreements split evenly in both directions (363 later, 340 earlier, median
delta 0.0 years). That is noise, not signal.

The reason is structural: `CERT ISSUE DATE` is the *current registration* date
and resets on every re-registration or sale — 39,435 of the dates fall in 2023
alone, for a fleet that includes 1940s airframes. So "earliest across the
fleet" measures when the operator last acquired an aircraft nobody has since
re-registered, which is unrelated to when the FAA issued their Part 135
certificate. A long-established operator that refreshed its fleet looks new; a
new operator that bought an old aeroplane looks established. It would substitute
one wrong number for another.

**Remaining options, in order of preference:**

1. ~~**FAA AVInfo Air Operator Search** (`av-info.faa.gov`)~~ — **unreachable,
   tested 2026-11-08.** This was the one source that actually holds certificate
   issue dates per operator, and it returns **HTTP 503 from the production
   server** as well as from the developer machine. Not buildable. See §9.6 for
   why this is the same obstacle as CARES rather than a coincidence.
2. **A data request to AFS-900**, who publish the Part 135 roster. Authoritative
   and slow; now the *only* remaining route to a number that is not inferred,
   and a procurement path rather than an engineering one.
3. **Accept the estimate and keep marking it — the current state, and the
   recommended one.** `certificate_age_is_estimated`
   and `GAP_CERTIFICATE_AGE` already fire for every operator on the fallback, so
   the score is explicitly "computed on an estimated certificate age" — which is
   accurate. The hardcoded 10.0 also happens to sit near the real median (10.7
   years, derived above), so it is not wildly wrong on average, merely
   unevidenced per operator.

### Significant

**`Lientail` / DOCINDEX — implemented and backfilled; title still cannot be
cleared.** Weekly ingest plus a 7-capture archive backfill: **524 active
encumbrances across 482 tails**, 2.2 years of history, charged one per financing
rather than per document (§9.3, §9.7). **235 of 1,841 operators** own a liened
charter tail.

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

Every missing input defaults to **neutral, which means no penalty**.

What a `GREY` flag means changed on 2026-11-16 (§10.1). It now means *this
category could not be assessed at all* — every anchor source for it was
missing. It no longer means "one of several inputs was absent", which is what
made `GREY` so common that it stopped carrying information.

The corollary matters as much: a queried source that returns nothing is now
treated as **affirmative evidence of a clean record**, not as a gap. Finding no
DOT enforcement order against an operator whose names were all searched is a
favourable finding, and the narrative is instructed to present it as one.
`verified_clean_searches` in the audit payload lists those nil returns
explicitly so the model has something positive to cite.

`adapter_v5.missing_inputs()` still reports the residual limits per operator —
for example that DOCINDEX covers a rolling window — but as **scope notes on a
finding**, no longer as grounds to call a category unevidenced.

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
and 082), plus `scripts/backfill_tail_liens.py` for history (§9.7).

**Current state, 10 November 2026:**

| | |
|---|---|
| Rows stored | **1,358** |
| ├ lien filings (`S/A`, `CSC`) | 813 |
| ├ release filings (`REL`, `REP`) | 545 |
| └ liens discharged by a release | 210 |
| **Active encumbrances** (what §4.2 charges) | **524** |
| Tails with an active encumbrance | **482** |
| Lien history span | **2024-09-03 … 2026-11-05** |
| Operators owning a liened charter tail | **235** of 1,841 |

Encumbrances are counted **per tail and summed**, never `DISTINCT` across the
table. A global distinct collapses across tails — a fleet financier lending on
40 aircraft on one day shares the `(doc_type, doc_date, party)` tuple, so 40
encumbrances counted as 1, and the reports said 209 where §4.2 charges 524.
`adapter_v5.fetch_tail_liens` filters by tail first and was always right; only
the reporting undercounted, by 2.5x, understating exactly the multi-aircraft
financings that matter most.

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

**`GAP_TAIL_LIENS` used to fire unconditionally, even when liens were found.
Superseded on 2026-11-16 — see §10.1.** The original reasoning was that
DOCINDEX is a rolling suspense index, so a lien recorded years ago and never
released is simply absent; finding filings proves encumbrance while finding
none proves nothing about title.

The premise is true but the conclusion did not follow. Raising the gap for
tails that *were* searched meant `legal_title` could never read GREEN for any
operator, however clear the title — so the flag carried no information and a
spotless airframe was indistinguishable from an unexamined one. DOCINDEX
writes a row only when an encumbrance is filed, so for an indexed tail zero
rows is the finding "nothing on file".

The gap now tracks whether the lookup *ran*. The rolling-window limit is still
disclosed, as a scope note attached to a real finding rather than as a refusal
to report one. Only FAA CARES can prove absence outright (§9.4), and that
remains blocked.

### 9.4 FAA CARES — **blocked; largely worked around (see §9.7)**

`cares.faa.gov` holds the permanent life-of-airframe packets: every Bill of
Sale, Security Agreement, mechanic's lien and release since manufacture. It is
the only source that can actually clear title, and therefore the only thing
that can retire `GAP_TAIL_LIENS` or deliver §9.2's ownership velocity.

**Blocked, not merely unbuilt.** `cares.faa.gov` returns **HTTP 403** from the
developer machine *and from the production server* (tested 2026-11-08). The body
is an Akamai edge denial (`errors.edgesuite.net`), the same refusal
`registry.faa.gov` gives this developer machine — but the server reaches
`registry.faa.gov` fine and still cannot reach CARES. So this is not a
network-location problem that a different host would solve, and no amount of
scraping engineering changes it. Access would need whatever FAA
registration/credentialing CARES expects, which is a procurement question rather
than an engineering one.

Were it reachable, it would still be a materially larger build than anything
else in this document — the only item needing a real pipeline rather than a
parser:

| | DOCINDEX | CARES |
|---|---|---|
| Format | one 3.5 MB CSV | scanned PDF packets |
| Access | bulk download | per-airframe request |
| Volume | 1 file | **~11,000 tails** |
| Extraction | `csv.reader` | OCR + LLM |
| Runtime | ~10 seconds | days |

(The addendum says "~2,000 active Part 135 charter tails"; the real D085 count
is 11,066–11,188.)

The failure mode would also be quiet: a mis-OCR'd lien *release* turns a cleared
title into an active encumbrance, or an active lien into a clean one, with
nothing downstream to catch it. That argues for treating OCR output as
provisional even once access exists.

**Most of what CARES was wanted for is now obtained without it** — see §9.7.
Archived DOCINDEX snapshots give 2.2 years of lien history rather than a
180-day window, and party classification distinguishes a routine bank loan
from a maintenance shop's unpaid-bill claim. What CARES alone can still do is
prove the *absence* of an encumbrance, because it is the permanent record.

**The current state is honest.** `GAP_TAIL_LIENS` fires on every tail, so
`legal_title` reads "not assessed" — which remains true even with 2.2 years of
history, because a lien filed before our earliest capture and never released is
still invisible. Nothing is overclaimed.

### 9.5 Summary of the addendum items

| Addendum item | Status |
|---|---|
| Weekly Part 135 D085 ingest | **Implemented** — 11,188 tails |
| Group by designator for `V_F` / `S_current` | **Implemented** |
| Rolling churn diff | **Implemented**, output withheld until ≥180 days of history |
| Wayback backfill for churn | **Not possible** — 1 capture of the Part 135 `.xlsx` exists, not "dozens" |
| Wayback backfill for *liens* | **Implemented** (§9.7.1) — 67 captures of the registry zip; 7 ingested, history 206 days → 2.2 years |
| Party classification (CARES workaround) | **Implemented** (§9.7.2) — 25% financier / 11% distress / 64% unknown. **No longer annotation-only:** since §10.2 it drives the severity tier, and therefore the penalty and the flag. |
| Release inference from repeated parties | **Not needed** (§9.7.3) — the FAA files an explicit REL/REP doc_type |
| AVInfo backup portal | **Unreachable** — HTTP 503 |
| DOCINDEX lien parsing | **Implemented** — 524 active encumbrances across 482 tails |
| FAA yearly registry archives | **Do not exist** on the live page; HTTP 403 |
| MASTER/DEREG serial match for prior owners | **Does not work** — serial is not a key; DEREG holds dead registrations |
| MASTER snapshot diffs for title velocity | **Not implemented** — needs accrued history |
| `DEREG.txt` for prior N-numbers | **Not usable** for currently-flying tails |
| FAA CARES packets | **Blocked**, but largely worked around (§9.4, §9.7). Still the only way to prove absence of a lien. |
| AVInfo for `Age_cert` (not in the addendum, but the same obstacle) | **Blocked** — HTTP 503 from the server too (§9.6) |

### 9.6 FAA host reachability — the shared obstacle behind two dead ends

Both remaining FAA gaps — permanent lien history (`GAP_TAIL_LIENS`) and
`Age_cert` — are blocked by the same thing, and it is worth stating once rather
than rediscovering per source.

Measured 2026-11-08. The dev-machine column and the IPs were tested directly;
the server column is from runs on the production host.

| Host | Resolves to | Dev machine | Production server | Holds |
|---|---|---|---|---|
| `www.faa.gov` | `23.198.135.73` | **200** | **200** (implied — the D085 ingest downloads from it successfully) | Part 135 D085 `.xlsx` |
| `registry.faa.gov` | `23.198.132.191` | 403 | **200** | `ReleasableAircraft.zip` |
| `cares.faa.gov` | `23.198.132.191` | 403 | **403** | permanent title packets |
| `av-info.faa.gov` | `23.198.132.191` | 503 | **503** | certificate issue dates |

The informative part is that the **production server reaches `registry.faa.gov`
but not `cares` or `av-info`**. Those two refuse it while a third FAA host on
the same CDN serves it normally, which rules out a simple egress or geographic
block — that would fail uniformly.

A caveat on an earlier version of this note: it argued the three hostnames
"share one IP" and inferred per-hostname edge rules from that. The IPs are
Akamai-assigned and **rotate** — re-checked 2026-11-10, `registry.faa.gov`
resolved to a different address than when first measured, and the four hosts no
longer share one. The shared-IP observation was a coincidence of timing and
should not be relied on. What stands is the reproducible behaviour: two hosts
refuse the server, one serves it.

**Consequence: neither gap is an engineering problem.**

- Everything implemented in §9 comes from the two open hosts, which is why the
  D085 and DOCINDEX pipelines work.
- `cares.faa.gov` is the only source that can clear title, so `legal_title`
  stays GREY indefinitely. That is honest — the flag says "not assessed".
- `av-info.faa.gov` was the only source of certificate issue dates, so
  `Age_cert` stays an acknowledged estimate. Both inference routes are now
  tested and dead: `MASTER.txt` `CERT ISSUE DATE` agrees with
  `business_started_date` 16% of the time (§1a), and this host is unreachable.

The remaining path for both is an FAA data request or registered access — a
procurement decision. **No further scraping work should be attempted against
these two hosts**; a 403 and a 503 that reproduce from two independent networks
are not transient, and retrying them is the kind of thing that gets rediscovered
every few months.

Worth re-testing only if the FAA announces a change, or if someone obtains
credentials — in which case §9.4's effort estimate (OCR over ~11,000 scanned
packets, with mis-read lien releases failing silently) still applies.

### 9.7 The CARES workaround — **implemented**

CARES is unreachable (§9.4, §9.6). A proposed workaround argued that in most
cases the scanned PDF is unnecessary: the nature and resolution of a filing can
be inferred from the unauthenticated daily bulk download. Two of its three
parts were built; the third was already handled better. Each claim was measured
against real archives before any code was written.

#### 9.7.1 Lien history backfill — `scripts/backfill_tail_liens.py`

**Outcome: 7 captures, 0 failures. Lien history from 206 days to 2.2 years.**

| | Before | After |
|---|---|---|
| Rows in `gtj.tail_liens` | 303 | **1,358** |
| Lien filings | 303 | **813** |
| Release filings | 0 | **545** |
| Liens discharged | 81 | **210** |
| Active encumbrances | 128 | **524** |
| Tails with an active encumbrance | 91 | **482** |
| Tails appearing at all | 240 | **939** |

Captures ingested, each ~72 MB, newest window last:

```
2024-09-26   window 2022-02-15 .. 2024-09-25   198 filings ->  169 stored
2025-02-02   window 2024-07-09 .. 2025-01-31   345 filings ->  273 stored
2025-07-15   window 2025-01-16 .. 2025-07-14   134 filings ->   92 stored
2025-10-21   window 2025-04-17 .. 2025-10-20   187 filings ->  129 stored
2026-02-27   window 2025-09-09 .. 2026-02-25   162 filings ->  136 stored
2026-05-28   window 2024-12-23 .. 2026-05-27   405 filings ->  270 stored
2026-09-14   window 2026-03-26 .. 2026-09-11   148 filings ->   91 stored
```

**I had previously documented Wayback coverage as "sparse and gapped". That was
wrong, and the error was mine:** the CDX query used
`collapse=timestamp:4`, which compresses to one capture per *year*. Real
coverage is **67 captures since 2023**, dense through 2026. The earlier
conclusion that churn and lien history could not be backfilled was therefore
half wrong — churn genuinely cannot (one capture of the Part 135 `.xlsx`
exists), but the registry zip can.

Measured window length is **206 days**, so the addendum's 90-day sampling does
guarantee overlapping coverage. `--every-days 90` selects 7 captures (~0.5 GB)
rather than all 67 (~4.4 GB).

Proven additive rather than redundant: the January-2025 and May-2026 captures
share **zero** filings — 5,803 rows exist only in the first, 2,279 only in the
second. Each archived window is a disjoint slice of history.

**Releases must be stored, not merely counted.** The first run reported
`0 lien(s) marked released` across 537 rows, which did not add up. Both ingests
were filtering to lien types before writing, so `REL`/`REP` rows were read,
used for in-memory netting, then discarded — one archive alone carried 335
Part 135 release filings. That left cross-window reconciliation with nothing to
join against: a release landing in a different capture from its lien would
leave a discharged encumbrance marked active forever. After the fix, **129
liens were discharged by cross-window reconciliation** — precisely the case
in-memory netting cannot reach. `N102JE` and `N141SH` now correctly report zero
encumbrances.

Three read paths had to exclude release rows so a release is never charged as
an encumbrance: `fetch_tail_liens` and both report queries.

#### 9.7.2 Party classification — `src/common/lien_classification.py`

The insight is sound: a bank recording a loan is routine, while a maintenance
shop, FBO or tax authority files with the Registry essentially only when
unpaid. `WORLD FUEL SERVICES INC` filed **37 of 345** Part 135 lien filings in
the January-2025 archive — the second most prolific party — which is a
liquidity signal a bank lien is not.

**But it is a confidence signal, not a verdict.** Measured on that population
(170 distinct parties):

| | |
|---|---|
| matched as financier | **25%** |
| matched as distress | **11%** |
| **matched neither** | **64%** |

Party names are free text with no registry behind them; `AERIS HOLDINGS LLC`
and `WANZOR CHRISTOPHER DEVIN` cannot be classified from the string. A 40-party
whitelist covers only 62% of filings. The function therefore returns `UNKNOWN`
by default, and callers treat that as not-assessed.

The addendum's keyword list also misfires: a bare `SERVICES` trigger traps
`AFC FINANCIAL SERVICES LLC`, plainly a lender, as a trade creditor. Distress
patterns are tested first and financier names are specific rather than generic,
with a regression test pinning that case.

Its proposed Part 145 cross-reference is unavailable —
`av-info.faa.gov/RepairStation.asp` is the host already known to refuse us.

Classification **annotates and never scores**. `N402XT` reads 74.1 before and
after, with its encumbrances labelled `[distress]` for World Fuel and
`[financier]` for the banks.

#### 9.7.3 Release inference — **deliberately not implemented**

The addendum infers release from "two entries, same party, different dates".
The FAA already files release as its own `doc_type` (`REL`/`REP`), which is read
directly: **62** tails where a `REL` shares its lien's party, against only
**27** showing the inferred pattern. Reading an explicit field beats inferring
from repetition.

#### 9.7.4 Yearly registry zips — **do not exist**

`ReleasableAircraft.2022.zip` through `.2025.zip` all return **HTTP 403**. The
live FAA page has no "Yearly Aircraft Registration Database" section and links
only the current zip. Wayback covers the same ground.

#### 9.7.5 What the workaround does *not* close

2.2 years of DOCINDEX is a longer window, not the permanent record: a lien
filed before 2024-09-03 and never released remains invisible. Only CARES can
prove absence outright, and §9.4 stands.

What changed on 2026-11-16 (§10.1) is how that limit is *reported*. It is now a
scope note on a finding rather than a refusal to make one:

```
DOCINDEX scope note: the search returned no active filings for this airframe,
which is the expected result for clear title. The index covers a rolling recent
window, so a filing predating our earliest capture and never released would not
appear
```

The earlier wording — `no DOCINDEX lien in the captured window — this is NOT
clear title` — contradicted the flag it accompanied and is what kept
`legal_title` permanently GREY.

---

## 10. Flag Resolution, Lien Severity & Narrative Elaboration — implemented 2026-11-16

A spec addendum in three parts. §10.1 and §10.3 are implemented as written;
§10.2 is implemented on a different discriminator than specified, because the
one it names does not exist in the source data. Each subsection records what
was done and what was not.

**Verification:** 215 tests pass. Four test classes encoded the behaviour being
removed and were rewritten to the new contract. Checked end to end on the live
scoring path against `N257BW` (Triton Air, `70TA`), `N722BD` (Aurora Aviation,
`GLRA`) and `N717XJ` (Red Wing Aeroplane, `R3WA`).

### 10.1 Partial coverage ≠ GREY — **implemented as specified**

**The bug.** `GREY` was inferred from *emptiness*, and emptiness is not the same
fact as absence of coverage. Three gaps fired on the **good** outcome:

| Gap | Fired when | Why that is wrong |
|---|---|---|
| `GAP_CHURN` | `tails_added == tails_removed == 0` | That is a perfectly stable fleet — the outcome worth commending |
| `GAP_DOT_ORDERS` | no enforcement order was **found** | Finding none is a clean regulatory record |
| `GAP_TAIL_LIENS` | **always** | `legal_title` could never be GREEN for anyone |

`GAP_SAME_TYPE_FLEET` was also miscategorised: a genuinely single-aircraft fleet
is an observed fact, not missing data.

Compounding it, `_CATEGORY_DEPENDENCIES` was an **AND**-gate read as an OR — any
one gap in a long list forced `GREY`. So the categories with the most inputs
were the hardest to ever assess.

**The fix.** Observability now travels separately from results. `OperatorData`
gains `churn_measured`, `conduct_sources_queried` and `safety_sources_queried`;
`TailData` gains `liens_queried` and `ownership_observed`. All default `False`,
so a caller that sets nothing still gets the cautious reading.

`_CATEGORY_ANCHORS` replaces the dependency list with a true OR-gate — a
category is assessable while **any one** anchor answered, and goes `GREY` only
under total blindness:

| Category | Anchors (any one suffices) |
|---|---|
| Asset Stability | certificate age **OR** measured churn |
| Legal & Title | FAA ownership classification **OR** an executed lien lookup |
| Commercial Integrity | DOT OACP / watchdog corpus queried |
| Primary Flight Safety | NTSB/AIDS queried — un-ingested ASN is explicitly ignored |
| Flight Fulfilment | fleet counted |
| Maintenance Discipline | no gating source |

The §8 name-resolution concern was also over-applied. It now covers only the
four **entity-keyed** categories: NTSB, AIDS and SDRS records attach to the
N-number, which is immutable and was searched directly, so a clean airframe
history stands regardless of what the operator currently calls itself.

**Two further bugs found while verifying this:**

- The §8 trade-name caveat was appended to the human-readable gap list
  *unconditionally*, so an operator whose lookups **were** expanded across every
  name on its certificate was still reported as searched by trade name.
- `conduct_sources_queried` was derived from `include_dot_orders` alone, which
  reported a caller-supplied DOT docket as unqueried and greyed out
  `commercial_integrity` on evidence sitting in the argument list.

**Pre-prompt rule.** The old guardrail told the model to describe any category
with a listed gap as "unevidenced", which would have silently overridden every
`GREEN` this change makes reachable. Gaps are now scope notes; only `GREY` means
not assessed. `verified_clean_searches` was added to the payload so the model
has affirmative nil-return findings to cite rather than seeing only an absence.

**Measured effect.** All three reference tails moved from mostly-`GREY` to six
`GREEN` with four affirmative clean searches and four honest gaps.

**One caveat, deliberate.** §10.1's Asset Stability rule says to commend "0%
fleet churn", but churn is unmeasurable for **every operator** today: D085 holds
Oct and Nov 2026 only — a 31-day span against `fetch_churn`'s 180-day minimum,
so **0 of the 1,664 operators in D085** (of 1,845 in `gtj.operators`) have a
usable window. The category therefore anchors on certificate longevity, and the churn
sentence is emitted only once the window supports it. Asserting a 12-month
retention finding that no snapshot can back would be the same class of error as
the bug being fixed.

### 10.2 Lien severity tiers — **implemented on a different discriminator**

**What could not be done as written.** Every tier in the spec is defined by
claim amount (`< $10,000`, `$10k–$75k`, `> $75,000`). **FAA DOCINDEX publishes
no claim amounts.** `gtj.tail_liens` carries `doc_type`, `doc_date`, `party` and
`doc_id`, because that is what the source provides — there is no amount column
to tier on, and inventing one would mean fabricating the figure that drives the
result.

**What was done instead.** Tiering runs off **who filed**, which proxies
severity well: a bank recording a loan is routine at any size, while a tax
authority or fuel supplier recording a claim means an unpaid bill escalated to a
lien. Built on the existing `classify_party`:

| Tier | Criteria | Points | Flag effect |
|---|---|---|---|
| 1 — nuisance | bank, lessor, owner trust, or a release | 3.0, log-damped, capped at 8 total | does not move the flag |
| 2 — material | MRO, fuel, FBO, or a party named but unmatched | 25.0 each | `YELLOW` |
| 3 — crippling | tax authority, court, judgment, hourly engine programme default | 60.0 each | `RED` on a single filing |

`claim_amount` is accepted and **takes precedence** whenever a caller can supply
one, so the dollar bands activate unchanged if a source with amounts (CARES,
UCC, court records) is ever ingested. Until then it is always `None`.

**The inversion, before and after.** Tier 1 is log-dampened in count and capped,
so volume alone cannot accumulate into a verdict:

| Lien shape | Old penalty | New penalty |
|---|---|---|
| 20 routine bank financings | 500 pts (25 × 20) | **7.5 pts** |
| 1 material MRO claim | 25 pts | 23.5 pts |
| 1 tax levy | 25 pts | **56.3 pts** |

Previously all three were 25 points per row and volume won — the exact
false-inversion the spec describes, with financing rather than count as the
cause.

**A judgement call worth recording.** `party` is `NULL` on 67% of rows. Treating
those as the spec's cautious middle (Tier 2) put **445 of 906 tails (49%) into
`YELLOW` on no evidence** — the same class of error as greying out everything,
pointed the other way. So a *missing* party means Tier 1, while a party that is
*named but unmatched* means Tier 2. Measured on all 1,148 active filings: **92%
of tails routine, 8% flagged, 0 forced RED**, which matches data that is
overwhelmingly bank and lessor financing.

Tier 3 currently matches **zero** real filings. That is the correct answer, not
a defect — no tax authority, court or engine programme appears in the present
data. The classifier is unit-tested against synthetic IRS, state-tax, sheriff,
JSSI and CorporateCare parties so it fires when one does appear.

### 10.3 "So-What" elaboration standard — **implemented as specified**

Added to `SYSTEM_PROMPT` as section 4. Every datapoint cited in the Executive
Summary and all six category blocks must now carry **Fact → Operational
Mechanism → Live-Trip Impact**, with worked examples for sister-ship redundancy,
airframe age vs SDRs, ownership structure, certificate longevity, liens and
commercial integrity.

The payload also carries per-tier lien counts plus explicit framing guidance,
because §2B's two failure modes are symmetrical and both easy to fall into:
narrating many trivial filings as distress, and under-reporting one catastrophic
filing because the count is low.

The breakdown is published as `lien_profile`, **not** `lien_severity` — the §9
Black Box test forbids the word "severity" anywhere in the payload, and it
caught the first attempt.

### 10.4 Not done, and why

| Item | Status |
|---|---|
| Amount-based lien tiers (`$10k` / `$75k` bands) | **Not possible from DOCINDEX** — the source publishes no claim amounts. Logic is written and dormant behind `claim_amount`; activates if a source with figures is ingested. |
| "0% fleet churn" in the Asset Stability narrative | **Withheld** until D085 reaches a ≥180-day window (currently 31 days). Flag resolution already anchors on certificate age, so the category is assessed; only the churn *claim* waits. |
| Tier 3 escalation on `party IS NULL` rows | **Not attempted** — 67% of rows have no party, and inferring severity from absence is the error this whole addendum corrects. |
| `ownership_observed` wired into `score_tail.py` | **Not done.** `legal_title` currently anchors on the lien lookup alone, which works. Passing `gtj.aircraft.registered_owner` through would make the category robust to a lien-lookup failure. Small follow-up. |
| Re-score of the 1,841-operator population | **Not run.** The stored scores from the 10 Nov rescore still carry the over-greyed flags. Numeric scores change only where liens are present; flags change widely. |
| ASN latent risk (`L_Risk`) | **Still not ingested** (source 5). §10.1 explicitly stops it holding `flight_safety` at `GREY`, which was its only practical effect on a flag. |

---

## 11. Catastrophic events — investigated and fixed 2026-11-16

Prompted by a report that an operator scored **81** weeks after a fatal crash
of one of its aircraft (N722BD / Aurora Aviation, certificate `GLRA`, NTSB
`ERA27MA026`).

The investigation found **three independent defects**, any one of which was
sufficient to produce the reported score. Two of the three were the hypotheses
in the report; the third was worse than either and is the one that actually
mattered.

### 11.1 The cached NTSB table is 15 months stale — **the dominant cause**

`gtj.ntsb_incidents` could not have flagged this crash under any query shape:

| Measurement | Value |
|---|---|
| Most recent `event_date` held | **2025-08-16** |
| Events dated 2026 at all | **0** |
| Events with `total_fatalities > 0` | **0** |
| Events with `aircraft_damage` indicating a hull loss | **0** |
| Rows with `tail_number` populated | **2 of 247 (1%)** |
| Most recent `last_verified` | 2026-01-12 |

So the table holds **no fatal accident at all**, and a 1% tail-number fill rate
means even a correct tail-keyed query against it would miss nearly everything.
This is an ingestion freshness problem, not a scoring problem.

Note the live scoring path (`src/scoring/service.py`) queries CAROL directly
rather than reading this table, so the staleness affects anything that reports
from the cache rather than re-scoring. **Both need attention** — see §11.5.

> **ACTION REQUIRED (not code):** re-run the NTSB ingestion and put it on a
> schedule. `scripts/download_ntsb_incidents.py` exists. Until then the cached
> table must not be treated as an accident record.

### 11.2 NTSB was queried by operator name only — **confirmed**

`query_ntsb_incidents` sent only the operator name, against
`AviationOperation.OperatorName`. Tail numbers were never sent. That fails
three ways:

- NTSB records the operator name **as filed at the time**, so a rebranded or
  dba-trading operator reads clean — the §8 problem, in the one source where
  entity resolution cannot fully solve it;
- the name is free text and the query used `"Operator": "is"` (**exact
  match**). Probed live: `"Aurora Aviation"` with `contains` returns **7**
  cases where `"Aurora Aviation, Inc."` with `is` returns **1**;
- an aircraft on a management agreement may be filed against another entity.

**Fixed.** `query_ntsb_by_tail_numbers` queries `Aircraft.RegistrationNumber`
for every tail on the D085 certificate. The name query is retained as a
supplement, since it can still catch an event filed against the certificate for
a tail we do not hold.

Four CAROL facts were established by probing the live API rather than assumed,
and they constrain what is possible:

| Finding | Consequence |
|---|---|
| `Aircraft.RegistrationNumber` is the only valid registration column (the three plausible alternatives all return **HTTP 400**) | the query works; verified returning a real hit for `N474NA` |
| The case-list response carries **no `AircraftDamage` field at all** | hull loss cannot come from this response; the pre-existing `aircraft_damage=None` was accurate, not lazy |
| `HighestInjuryLevel` is frequently **empty — observed empty even on a `Final` report** | it cannot be the only route to "was this fatal"; `InjuryOnboardCount` and `MostRecentReportType` are now carried too |
| `N#` is **multi-valued** (observed `['N474NA', 'N296EA']` on one event) | `_extract_field_value` returned only the first, so an event where our tail was second looked like another operator's |

### 11.3 Open dockets scored as zero severity — **the mechanism, restated**

The report asked whether open/preliminary rows were *filtered out or multiplied
by zero*. Neither, exactly. Nothing filters them. What happens is subtler and
worse:

An NTSB investigation stays open 12–24 months, and for the first weeks carries
no injury or damage codes. `classify_accident_severity` infers severity from
those free-text fields, so a destroyed aircraft with an open docket graded as
**`SUBSTANTIAL_DAMAGE` (25)** — or, with nothing populated at all, produced
`Hsafety = 1.0000`. Measured on the reported shape: the arithmetic saw **no
risk whatsoever** in a hull loss.

Then three mechanisms diluted even that, compounding:

| Mechanism | Effect on a fatal accident |
|---|---|
| Exposure normalization, `MAX(1, SQRT(Vf))` | a 36-aircraft operator carries it at **1/6th weight** |
| `Dscale` operator damping | further discount for a large, mature certificate |
| Five-year exponential decay | erodes it from the day it happens |

**Fixed — §4.1a circuit breaker.** A fatal accident or hull loss within
**36 months** bypasses the arithmetic entirely:

- `Hsafety` forced to `0.0`;
- the composite forced to the `SCORE_FLOOR` of **50**;
- Primary Flight Safety forced **RED**;
- the narrative gets a `catastrophic_events` block and is instructed to lead
  with it, never to offset it against clean findings, and never to present an
  open docket as though the crash itself were unconfirmed.

Measured on the reported shape: **73.67 Benchmark → 50.0 Standard**.

Two design points worth preserving:

**Zeroing `Hsafety` alone is insufficient.** It carries only the 0.35 weight,
so the 0.65 tail term would still carry a clean airframe to roughly **74** — a
Benchmark score for an operator that has just destroyed an aircraft. The
override therefore also applies at the composite level.

**The breaker reads raw facts, never graded severity.** `RiskEvent` gains
`fatalities`, `aircraft_damage` and `investigation_status`, carried as facts
rather than folded into `severity`, so a hull loss stays recognisable whatever
the arithmetic did to it. Severity is read **undecayed**, because decay must not
be able to answer "did a catastrophe happen" in the negative; recency is handled
by the lookback window instead.

`fatalities = None` is deliberately distinct from `0`. An open docket reports no
tally, and `HighestInjuryLevel` is empty often enough that a missing value cannot
mean "nobody died". Only an explicit `0` means that.

**36 months, not the five-year decay half-life:** long enough to cover an
investigation from preliminary to final report, short enough that an operator is
not defined forever by one event. Outside the window the ordinary decayed
arithmetic resumes.

### 11.4 SDRS matched on N-number only — **fixed**

`rows_to_fleet_events` dropped a row outright whenever `tail_numbers` was
supplied and the row's N-number did not match, so an SDR filed with a blank or
mistyped registration was discarded even when it named our aircraft by serial.
Serial is now a secondary key, tried after tail and before operator name.

**Serial alone is not a key, and this is the trap.** Measured on
`gtj.aircraft`: 11,166 aircraft carry a serial but only **10,395 are distinct** —
serial `226` is shared by six airframes, `236` by six more. Matching on the bare
number would attach one operator's maintenance reports to another's aircraft,
which is the same mistake that fabricated 3,707 false ownership chains during
the FAA registry work (§9.2). So the key is qualified by aircraft type, and
`_serial_index` **drops** any qualified serial resolving to two different tails
rather than guessing.

Two format problems had to be solved for the qualifier to work, both found by
testing real values rather than reading code:

| Problem | Example | Resolution |
|---|---|---|
| Serial formats disagree | `60-271` (SDRS) vs `271` (`gtj.aircraft`) | `normalize_serial` keeps only the trailing portion; a prefix-preserving form makes these *fail* to match |
| Make/model encodings disagree entirely | SDRS `make="LEARJET" model="LR-60"` vs `make_model="LR-60-60"`; also `CE-560-560XL`, `BHT-407-407` | `_model_digits` uses the model **number** (`60`, `560`, `407`), which survives both encodings |

Building a manufacturer-name-to-ICAO-code mapping would be a data project in its
own right and wrong in the tails. Digits are a weaker discriminator than a full
type match, which is acceptable because they only ever *qualify* a serial that
already matched — the pair must agree, not the digits alone. Verified that
`LR-60/271` and `CE-560/271` still produce different keys.

### 11.5 Not done, and why

| Item | Status |
|---|---|
| **Re-ingest `gtj.ntsb_incidents`** | **NOT DONE — the most important remaining item.** The table is 15 months stale and holds zero fatal events. This is an ingestion run plus a schedule, not a code change, and it needs to happen before the cache is trusted again. |
| Confirm the N722BD crash itself | **Could not verify.** `ERA27MA026` and `N722BD` both return **zero rows from live CAROL** as queried on 2026-11-16, and the event postdates what this analysis could independently confirm. The aircraft is real in our data (`N722BD`, serial `271`, LR-60, Aurora Aviation Inc, `GLRA`) and the serial matches the report. The circuit breaker is correct regardless of this one case. |
| ASN latent risk (`Lrisk`) ingestion | **Still not implemented, and newly measured as blocked from here:** `asn.flightsafety.org` returns **HTTP 403** on both `/wikibase/` and `/database/`. A CAROL control request from the same machine returned 405, so this is the host refusing us, not a connectivity fault. Untested from the production server — §9.6 showed `registry.faa.gov` behaves differently there, so **probe from the server before concluding it is unavailable**. |
| FAA AIDS (source 4b) | **Still not implemented.** `asias.faa.gov` also returns **HTTP 403** from this machine. Same caveat: probe from the server. |
| Preliminary-incident feed separate from CAROL | **Not built.** CAROL already exposes open dockets, and the circuit breaker now acts on them, which closes the urgent part of the gap. A dedicated preliminary feed would improve latency, not correctness. |
| Per-case CAROL detail fetch for `AircraftDamage` | **Not built.** The case-list response has no damage field, so hull loss is currently detected via fatalities, a graded fatal severity, or a damage string supplied by another source. A per-case fetch would add a request per event. |
| Re-score of the operator population | **Not run.** Stored scores predate both §10 and §11. Any operator with a catastrophe in the last 36 months is currently scored too high in the stored data. |
