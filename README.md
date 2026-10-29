# Pharma gross-to-net data platform

Medicaid rebates are usually the largest deduction between a drug manufacturer's gross and net sales, and the hardest to accrue. States invoice months after the drug is dispensed, the unit counts on those invoices are often wrong, and the rebate per unit depends on confidential prices plus an inflation penalty that has had no cap since January 2024.

This repo rebuilds that workflow on public CMS data as a tested, automatically refreshed data platform. It answers two questions a GTN or Medicaid operations team faces every quarter:

1. **How much Medicaid rebate liability should we accrue?** Estimated by NDC, state and quarter, with every confidential input exposed as a scenario parameter.
2. **Which invoice lines should we dispute?** Six rules a Medicaid team applies before paying a state, each with the rebate dollars at stake.

**[Open the dashboard](https://janishkumar.github.io/pharma-gtn-data-platform/)** to filter by year and manufacturer. The marts behind it are published as Parquet on each [data release](https://github.com/janishkumar/pharma-gtn-data-platform/releases).

> Every figure below is a public-data estimate produced by `gtn report` (full output in [`reports/summary.md`](reports/summary.md)). It is not any manufacturer's actual liability.

## Results

Coverage: 30,259,849 state utilization lines for 85,916 NDCs, 2016 and 2021 Q1 to 2026 Q1, with $551.21B of Medicaid reimbursement.

### Liability, 2025

The base case puts 2025 statutory rebate liability at **$31.41B** (up to $35.60B including rows CMS suppresses for privacy), or 30.2% of the $104.10B states paid for drugs. That headline depends on inputs nobody outside a manufacturer can see, so here is how far it moves:

| Pre-2014 price growth over CPI | AMP / NADAC | Best Price gap 0% | Best Price gap 30% | Best Price gap 50% |
|---|---|---|---|---|
| 0% | 0.90 | $28.30B | $34.38B | $51.60B |
| **0%** | **1.00** | **$31.41B** | $38.16B | $57.30B |
| 5% | 0.90 | $33.26B | $39.33B | $56.56B |
| 5% | 1.00 | $36.92B | $43.67B | $62.81B |

- **Best Price gap** is the discount off AMP given to the best commercial customer. Below 23.1% it changes nothing (the statutory minimum applies), so 0% is the floor.
- **AMP / NADAC** scales the pharmacy acquisition cost used as the AMP proxy for brands.
- **Pre-2014 price growth over CPI** sets the inflation-penalty baseline for drugs launched before NADAC began. At 0% the penalty for older drugs is a lower bound: in the base case no 2023 units hit the 100% AMP cap (0.0%), which real older brands do.

The range runs from $28.30B to $62.81B. The base case is deliberately the conservative corner.

### Dispute candidates, 2025

45,954 distinct invoice lines, **$237.6M** of estimated rebate at stake:

| Rule | Lines | At stake |
|---|---|---|
| `UOM_OUTLIER`: units per prescription above 10x the national median | 4,964 | $118.5M |
| `PRICE_OUTLIER`: Medicaid paid per unit under 10% of NADAC, so units look overstated | 5,078 | $110.6M |
| `TERMINATED_NDC`: utilization after the NDC's termination date | 36,363 | $61.0M |
| `PRE_MARKET`: utilization before the market date | 2 | $2,473 |
| `NOT_COD`: DESI 5/6 products, not rebate-eligible | 87 | $0 |

A sixth rule, `INVALID_NDC` (utilization reported against a code that isn't an 11-digit NDC), flagged no non-suppressed lines in 2025.

The largest flags are classic unit-of-measure errors. NY reported Spiriva Respimat at 3,708.1 units per prescription against a national median of 4.1 ($12.1M at stake in 2025 Q2). OR reported a Skyrizi pen at 30.2 units per prescription against 1.0 ($27.7M).

### Check against CMS-64

data.medicaid.gov carries states' CMS-64 expenditure reports for 2016:

| 2016 check | CMS-64 | This repo | Ratio |
|---|---|---|---|
| Fee-for-service drug spend | $22.81B | $22.70B | 99.5% |
| Rebate offset vs fee-for-service estimate | $12.89B | $7.71B | 59.8% |
| Rebate offset vs total estimate | $12.89B | $19.42B | 150.7% |

Gross spend ties out within half a percent, so the utilization load is complete. The rebate check only brackets the reported offset, because the CMS-64 file doesn't say whether that line includes rebates on managed-care utilization. It is also cash in the federal fiscal year, including prior-period adjustments.

## How it works

```
data.medicaid.gov (SDUD, NADAC, FUL, MDRP products, CMS-64) + BLS CPI-U
  │  gtn ingest: catalog lookup, header contracts, ETag-based change detection
  ▼
data/raw/*.parquet (all text, NDC leading zeros intact)
  │  dbt-duckdb: staging → intermediate (AMP proxy, inflation penalty, URA) → marts
  │  models with enforced contracts, data tests, dbt unit tests on the rebate rules
  ▼
warehouse.duckdb → gtn report (every README number) → static dashboard → GitHub Pages
```

**Rebate per unit (URA).** Basic rebate is 13% of AMP for generics. For brands it is the greater of 23.1% (17.1% for clotting factors and pediatric drugs) and AMP minus Best Price. On top sits an inflation penalty: the amount AMP has risen faster than CPI-U since the drug's baseline quarter. URA is capped at AMP before 2024 Q1 and uncapped after.

**Prices.** AMP is confidential. The model uses, in order:
1. The FUL weighted average of AMPs for generics, when it is within 10x of NADAC.
2. NADAC for everything else.
3. National Medicaid paid per unit for drugs NADAC doesn't survey, mostly clinic-administered ones.

In 2025, 99.6% of units got a price.

**Inflation penalty without baseline AMP.** The penalty is computed as a share of AMP from NADAC growth against CPI-U since the first NADAC observation. Because it's a ratio, it works whichever source supplies the current AMP. The design doc ([`docs/design.md`](docs/design.md)) has the formula and every assumption.

**Data contracts.** Ingest fails if CMS renames or drops a column. dbt contracts pin the mart schemas. Tests guard the grain, NDC formatting, and any single invoice line over $1B. The last of these caught a real CMS data error (see below).

**Refresh.** A monthly GitHub Actions run checks the catalog and downloads only changed files. CMS reissues whole prior-year SDUD files, so a changed ETag reloads a year. The run then rebuilds and tests, publishes the marts as a data release, and redeploys the dashboard. No manual step: every source answers scripted requests.

## What didn't work (and what replaced it)

- **FUL as the generic AMP.** FUL's weighted average covers every equivalent product, brand included, so for some generics it lands far above what the generic sells for (for generic imatinib, more than 10x NADAC; a pipeline test pins this). One February 2023 row also carried an AMP millions of times too high, which on its own made 2023 several times larger than any other year. The $1B-per-line test caught it. FUL is now taken as the median month per quarter and dropped when more than 10x from NADAC: 10,206 of 434,574 NDC-quarters with a FUL price.
- **Two-sided price outliers.** Flagging Medicaid paid per unit far above NADAC mostly caught dispensing fees on penny generics, not disputes. Only the low side remains: units that look overstated, which is what a manufacturer actually disputes.
- **CMS-64 as a rebate benchmark.** It validates gross spend but can't settle the rebate number (see above). A cleaner benchmark would need the yearly CMS-64 files on medicaid.gov, which aren't in the scripted catalog.
- **Evidence for the dashboard.** Its open-source template now points to a hosted CLI. It was replaced by one static HTML page with the aggregates inlined: no Node build, nothing to host but Pages.
- **BLS by GET.** The CPI-U API silently ignores the year range on GET and returns three years. POST honours it. BLS also never published October 2025, so the model falls back to the latest earlier month.

## Limitations

- Statutory rebates only. State supplemental rebates are confidential and not modelled. 340B duplicate-discount exclusions and the line-extension alternative rebate aren't modelled either.
- AMP, Best Price and baseline AMP are proxies. Treat the base case as a floor and read the sensitivity table.
- Rows priced from Medicaid paid amounts include dispensing fees and get no inflation penalty.
- SDUD suppresses lines under 11 prescriptions. The high estimate fills them at the national median units per prescription.

## Run it

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/). A full ingest downloads several GB of CSVs, and the build is set to use up to 8 GB of memory (`GTN_DUCKDB_MEMORY`).

```bash
uv sync
uv run gtn ingest     # all sources into data/raw; re-runs skip unchanged files
uv run gtn build      # dbt seed, models and tests
uv run gtn report     # reports/summary.md
uv run python scripts/build_dashboard.py --out site   # open site/index.html
```

Tests run offline on real-row fixtures cut by `scripts/make_fixtures.py`: `uv run pytest`.

## Data

All sources are US government works in the public domain:

- [State Drug Utilization Data](https://data.medicaid.gov/) (2016, 2021 onward)
- NADAC (2013 onward)
- ACA Federal Upper Limits
- Drug Products in the Medicaid Drug Rebate Program
- Medicaid Financial Management Data (CMS-64)
- [BLS CPI-U](https://www.bls.gov/cpi/) series CUUR0000SA0

## License

MIT
