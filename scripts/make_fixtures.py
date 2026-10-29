"""Cut a small, real-row fixture set from a full `gtn ingest` for CI.

Keeps every source's rows for a handful of NDCs, a few states and the quarters the tests
need, so `dbt build` and `gtn report` run end to end in seconds without network access.

    PYTHONPATH=src python scripts/make_fixtures.py [--data data] [--out tests/fixtures/raw]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import duckdb

# Chosen to exercise every branch of the rebate model and every dispute rule; see
# tests/test_pipeline.py for what each one is expected to show.
NDCS = {
    "00002143380": "Trulicity: single source, NADAC priced, inflation penalty",
    "00074433902": "Humira pen: single source with a pre-NADAC launch (baseline before 2013)",
    "59148000713": "Abilify: innovator multiple source",
    "00054327099": "fluticasone nasal spray: generic with a FUL weighted AMP",
    "47335047583": "imatinib: generic with a FUL weighted AMP",
    "00944304610": "Advate: clotting factor (17.1% minimum)",
    "00006302602": "Keytruda: single source NADAC doesn't survey (priced from Medicaid paid)",
}
STATES = ("AK", "CA", "NY", "TX", "OH")
SDUD_YEARS = (2016, 2023, 2024)


def cut(data: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    con = duckdb.connect()
    ndcs = list(NDCS)

    def write(source: str, where: str, params: list) -> None:
        target = out / source / "fixture.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        src = f"read_parquet('{data / 'raw' / source}/*.parquet', union_by_name=true)"
        con.execute(
            f"copy (select * from {src} where {where}) to '{target}' (format parquet)", params
        )
        n = con.execute(f"select count(*) from '{target}'").fetchone()[0]
        print(f"{source}: {n} rows")

    write(
        "sdud",
        "lpad(ndc, 11, '0') in (select unnest(?)) and state in (select unnest(?)) "
        "and cast(year as int) in (select unnest(?))",
        [ndcs, list(STATES), list(SDUD_YEARS)],
    )
    write("nadac", "lpad(ndc, 11, '0') in (select unnest(?))", [ndcs])
    write("ful", "replace(ndc, '-', '') in (select unnest(?))", [ndcs])
    write("drug_products", "lpad(ndc, 11, '0') in (select unnest(?))", [ndcs])
    write("cms64", "true", [])
    write("cpi_u", "true", [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/raw"))
    args = parser.parse_args()
    cut(args.data, args.out)
