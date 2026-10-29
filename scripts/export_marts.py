"""Export the marts the dashboard and data release use to Parquet."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb

MARTS = (
    "fct_rebate_liability",
    "fct_dispute_candidates",
    "rpt_sensitivity",
    "rpt_validation_cms64",
    "rpt_liability_summary",
    "rpt_product_liability",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("dist/marts"))
    parser.add_argument("--only", nargs="*", default=MARTS)
    args = parser.parse_args()
    data = Path(os.environ.get("GTN_DATA_DIR", "data"))
    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(data / "warehouse.duckdb"), read_only=True)
    for mart in args.only:
        target = args.out / f"{mart}.parquet"
        con.execute(f"copy {mart} to '{target}' (format parquet, compression zstd)")
        print(f"{target}: {target.stat().st_size / 1e6:.1f} MB")
