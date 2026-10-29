# Pharma gross-to-net data platform: design

Author: Janish Kumar
Status: approved 2026-10-28; section 12 records changes made during the build

## 1. Why this exists

Medicaid rebates are usually the largest single deduction in a US manufacturer's gross-to-net (GTN) waterfall, and the hardest to accrue. State invoices arrive months after the drug is dispensed, unit data on those invoices is often wrong, and the rebate per unit (URA) depends on confidential prices (AMP, Best Price) plus an inflation penalty that has been uncapped since 1 January 2024. GTN and finance teams end up estimating liability in spreadsheets, then fighting state invoices line by line.

This project rebuilds that workflow on public CMS data as a reproducible data platform:

1. **Estimate Medicaid rebate liability** by NDC, state and quarter from published utilization and public price proxies, with every assumption exposed as a parameter and shown as a sensitivity table, never as one number.
2. **Flag invoice lines a manufacturer would dispute** (unit-of-measure errors, terminated or pre-launch NDCs, implausible units per prescription) with the rebate dollars at stake.
3. **Check the estimate against what states actually reported collecting** (CMS-64), and say how far off it is.

The decision it supports: how much to accrue for Medicaid this quarter, and which invoice lines are worth disputing.

## 2. Users

Primary (assumed, not confirmed with a client): a GTN, revenue-management or Medicaid-operations analyst at a manufacturer, or the consultants serving that team. They know what URA, AMP, Best Price, FFSU/MCOU and CMS-R-144 invoices are. They want numbers they can trace back to a rule and a source row.

Secondary: anyone reviewing the repo as a portfolio piece. The README must make sense to a data engineer who has never heard of GTN, in its first screen.

## 3. Goals, non-goals, anti-goals

**Goals**

- Fully automated quarterly refresh from public sources, running in GitHub Actions with no manual download step.
- A modelled warehouse (staging, intermediate, marts) with enforced contracts on the marts and tests that fail loudly when CMS changes a file layout.
- Rebate liability by NDC x state x quarter x utilization type, with a low/high range that accounts for suppressed rows.
- Dispute-candidate flags with a reason code and dollars at stake.
- A public, clickable dashboard that needs no login.
- A validation number: bottom-up estimate vs CMS-64 reported national rebate offset for the same year, with the gap explained.

**Non-goals (v1)**

- Other GTN buckets: chargebacks, 340B, Medicare Part D coverage-gap or IRA inflation rebates, commercial/PBM rebates, copay. The schema should leave room for them, but none is modelled.
- State supplemental rebates (confidential).
- Forecasting the quarters SDUD has not published yet. Listed as v2 in section 10.
- A Power BI file. The marts are plain Parquet, so a `.pbip` can be added later on a Windows machine.

**Anti-goals (would count as failure even if the code works)**

- Presenting a proxy estimate as a specific company's real liability. The dashboard can filter by labeler because the data is public, but every view carries the "public-data estimate" label, and the README never ranks labelers by what they "owe".
- One headline dollar figure without its sensitivity table.
- Any client name, client data or client-specific rule in the repo.
- A number in the README that no code in the repo produces.

## 4. Data

All sources are on `data.medicaid.gov` (DKAN metastore at `/api/1/metastore/schemas/dataset/items`) and download from `download.medicaid.gov` with plain scripted HTTP requests (checked 2026-10-28: HTTP 200, no auth, no browser checks). Licence on every dataset below is US public domain (`usa.gov/publicdomain/label/1.0` or `usa.gov/government-works`), so commercial demo use is fine.

| Source | What it gives | Grain | Refresh | Size |
|---|---|---|---|---|
| State Drug Utilization Data (SDUD), one dataset per year | Units reimbursed, prescriptions, amount reimbursed; `Suppression Used` flag when a row has under 11 prescriptions | state x NDC-11 x year x quarter x FFSU/MCOU | Quarterly; CMS also re-publishes prior years (all 2020+ files were reissued "updated July 2026") | ~500 MB CSV per year |
| NADAC, one dataset per year | Pharmacy acquisition cost per unit, pricing unit, brand/generic classification | NDC-11 x effective date (weekly survey) | Weekly | tens of MB per year |
| ACA Federal Upper Limits (FUL) | **Weighted average of AMPs** per unit for multiple-source drugs: the only public AMP figure | product group x NDC x month | Monthly | small |
| Drug Products in the Medicaid Drug Rebate Program | Drug category (S/I/N), unit type, units per package, market and termination dates, clotting-factor, pediatric and line-extension indicators, COD status | NDC-11 x quarter | Quarterly | small |
| Medicaid Financial Management Data (CMS-64) | States' reported "Drug Rebate Offset - National" and "State Sidebar Agreement" (supplemental) lines | state x year | The data.medicaid.gov copy only covers 2016 | small |
| CPI-U (BLS, series CUUR0000SA0) | Inflation index for the additional rebate | month | Monthly | tiny |

Years in scope: SDUD/NADAC 2016 (validation year, matches the CMS-64 copy) and 2021 onward (current view).

Data facts that shape the build:

- SDUD numbers are zero-padded text (`00000000226.000`), suppressed rows have empty measures, and NDCs are 11-digit text with leading zeros. Never cast NDC to an integer.
- FUL writes NDCs as `50268-0050-11`; SDUD and NADAC as `50268005011`. Normalise to 11-digit text at staging.
- CMS re-issues whole prior-year SDUD files. The refresh must detect a changed file (`Last-Modified`/size) and reload it, not only append the new quarter.
- Requests use a project User-Agent (`pharma-gtn-data-platform/<version> (+repo URL)`). No email or personal contact goes in any header.

## 5. The rebate model

Liability for a row = units reimbursed x estimated URA. SDUD units are already in MDRP unit type (EA, ML, GM), the same unit a URA is quoted in.

**AMP proxy (per NDC per quarter)**

- Non-innovator multiple-source (category N) with a FUL row: FUL weighted average of AMPs.
- Everything else: quarterly mean NADAC per unit x an AMP/NADAC factor (scenario parameter; default 1.00, sensitivity 0.90). NADAC measures what pharmacies pay, AMP what manufacturers receive from them, so they are close for brands and the factor captures the gap. NADAC is used only when its pricing unit matches the MDRP unit type.
- No NADAC at all (mostly clinic-administered drugs NADAC doesn't survey): national Medicaid paid per unit for that NDC-quarter x the same factor. It includes dispensing fees, so it overstates AMP for cheap drugs; it is reported as its own source.
- No proxy available (or NADAC in the wrong unit): the row is kept, liability left empty, and the priced share of units is reported.

**Basic rebate**

- N: 13% of AMP.
- S and I: max(23.1% x AMP, AMP - Best Price). Best Price is confidential, so `AMP - BP` is a scenario parameter expressed as a discount off AMP (default 0%, sensitivity 0% to 50%).
- Clotting factor and exclusively pediatric drugs (S/I): 17.1% minimum instead of 23.1%.
- Line-extension alternative rebate: not modelled; flagged in the output.

**Additional (CPI-U) rebate**

- Additional = max(0, AMP_q - baseline AMP x CPI-U_q / CPI-U_baseline), with CPI-U taken from the month before each quarter starts.
- Baseline quarter: first full quarter after launch, floored at 1990 Q3 (innovators) or 2014 Q3 (non-innovators, which pay the penalty from 2017 Q1).
- Baseline AMP is confidential. The penalty is computed as a share of AMP from NADAC growth, `1 - (NADAC_anchor / NADAC_q) x (CPI_q / CPI_anchor) / (1 + g)^years(baseline -> anchor)`, where the anchor is the first NADAC observation on or after the baseline quarter and g is a scenario parameter (excess price growth over CPI before NADAC began). Being a ratio, it works whichever source supplies the current AMP. With g = 0 the penalty for drugs launched before late 2013 is a lower bound; the sensitivity table shows g = 5%.
- Rows priced from Medicaid paid amounts have no NADAC history, so they get no penalty (also a lower bound).

**Cap**

- URA capped at 100% of AMP for quarters before 2024 Q1; uncapped from 2024 Q1 (American Rescue Plan Act).

**Suppressed rows**

- Low estimate: 0 units. High: 10 prescriptions x the NDC's median units per prescription in that quarter. Liability is always reported as point, low and high.

**Parameters** live in one versioned seed file (`rebate_scenarios.csv`), so a scenario is a row, and the sensitivity table is a dbt model that runs every scenario.

## 6. Dispute candidates

Rules a Medicaid operations team actually applies before paying a state invoice, run against SDUD rows:

| Code | Rule |
|---|---|
| `UOM_OUTLIER` | Units per prescription above a threshold multiple of the NDC's national median, or a whole multiple of units per package (state billed packages, not units) |
| `TERMINATED_NDC` | Utilization in a quarter after the NDC's termination date |
| `PRE_MARKET` | Utilization before the market date |
| `NOT_COD` | COD status 05 or 06 (DESI 5/6, not rebate-eligible) |
| `PRICE_OUTLIER` | Medicaid amount reimbursed per unit far from NADAC per unit |

Each flagged row carries the rebate dollars at stake (its estimated liability). Thresholds are parameters, and the README reports how many rows and dollars each rule flags, from code.

## 7. Architecture

```
data.medicaid.gov / BLS
   |  Python ingest (httpx): catalog lookup via DKAN, conditional download,
   |  header contract check, raw CSV -> typed Parquet, manifest of what was loaded
   v
data/raw/*.parquet
   |  dbt-duckdb
   |   staging   : one model per source, types, NDC normalisation
   |   intermediate: AMP proxy, quarterly NADAC, product attributes by quarter
   |   marts     : fct_rebate_liability, fct_dispute_candidates,
   |               rpt_sensitivity, rpt_validation_cms64   (contracts enforced)
   v
warehouse.duckdb + marts/*.parquet  -> GitHub Release asset (data release)
   |
   v
static dashboard on GitHub Pages
```

Stack (my calls, all local and free, no Docker and no cloud account):

- Python 3.12+, `uv`, `httpx`, `duckdb`, `pyarrow`.
- dbt-core with dbt-duckdb: model contracts on marts, generic and singular tests, source freshness, `dbt docs` for lineage.
- Data contracts at two layers: raw header/column checks in Python (fail the refresh if CMS changes a layout), and dbt contracts plus tests on marts.
- Orchestration: GitHub Actions. A scheduled monthly workflow checks the catalog, downloads changed files, rebuilds, runs tests, and publishes a new data release only if tests pass. No Airflow or Dagster: a monthly batch with five sources doesn't need a scheduler service, and the README says so.
- Dashboard: one static HTML page (`dashboard/index.html`) with the mart aggregates inlined by `scripts/build_dashboard.py`, deployed to GitHub Pages by the refresh workflow. See section 12 for why not Evidence.
- CI (shared portfolio bar): ruff, pytest with a coverage gate, pip-audit, gitleaks, dbt build on a small fixture dataset, package build check.

Full refresh downloads about 3.5 GB of SDUD. CI tests run on committed fixtures (a few hundred rows per source), not the real files.

## 8. Repo layout

```
src/gtn_platform/        ingest, contracts, CLI
dbt/                     models/{staging,intermediate,marts}, seeds/, tests/
dashboard/               static dashboard template
scripts/                 fixture cutting, mart export, dashboard build
tests/                   pytest, fixtures/
docs/design.md
.github/workflows/       ci.yml, refresh.yml, pages.yml
```

## 9. README requirements

- Opens with the business problem and the decision it supports.
- Headline liability shown as a sensitivity table (AMP factor x Best Price gap x CPI baseline), not one number.
- Validation: estimate vs CMS-64 2016, with the gap and its likely causes (cash vs accrual timing, prior-period adjustments, supplemental rebates on a separate line, proxy error).
- Dispute-candidate counts and dollars by rule.
- "What didn't work (and what replaced it)".
- Every number generated by a script in the repo and checked before writing.

## 10. Later (v2)

- **Restatement tracking.** CMS re-issues prior-year SDUD files; snapshot each release and diff quarter totals to show prior-period adjustments, the thing that makes Medicaid accruals move after close. History only accumulates from the first scheduled run, unless older file versions can be recovered (Internet Archive was offline when checked).
- **Nowcast** of the quarters SDUD has not published yet, so the platform produces an accrual for the current quarter.
- Other GTN buckets (340B via HRSA data, Medicare Part D).

## 11. Open items

- CMS-64 drug-rebate lines for FY2017 onward: data.medicaid.gov only carries 2016. Check whether medicaid.gov's yearly FMR spreadsheets can be fetched by script; if so, extend validation.

## 12. Changes made during the build

- **FUL history** is in the single FUL file (monthly from April 2016), so generics get a FUL AMP in every quarter in scope, not only recent ones.
- **CPI-U** comes from the BLS public API by POST (GET ignores the year range). BLS never published October 2025; the model falls back to the latest earlier month.
- **Third price source.** About a fifth of Medicaid spend in a sample quarter had no NADAC price, so national Medicaid paid per unit was added as a labelled last-resort proxy (section 5).
- **Dashboard.** Evidence's open-source template now points to a hosted CLI, so the design's fallback was used: a single static page with inlined aggregates and hand-built SVG charts. No Node build step.
- **NADAC headers** changed from underscores to spaces in 2023; raw columns are normalised before the contract check.
- **Some older NADAC files** defeat DuckDB's parallel CSV reader; ingest retries single-threaded.
