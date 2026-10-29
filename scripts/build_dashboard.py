"""Build the static dashboard: dashboard/index.html with the warehouse aggregates inlined.

    PYTHONPATH=src python scripts/build_dashboard.py [--out site]
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
TOP_LABELERS = 150
TOP_PRODUCTS = 300
TOP_DISPUTES = 100


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [
        {k: (round(v, 2) if isinstance(v, float) else v) for k, v in zip(names, r, strict=True)}
        for r in cur.fetchall()
    ]


def collect(con: duckdb.DuckDBPyConnection) -> dict:
    return {
        "generated": date.today().isoformat(),
        "coverage": rows(con, """
            select strftime(min(quarter_start), '%Y-%m-%d') as first_quarter,
                   strftime(max(quarter_start), '%Y-%m-%d') as last_quarter
            from rpt_liability_summary
        """)[0],
        "quarterly": rows(con, """
            select year, quarter, rebate_category as cat,
                   sum(liability_point) as point, sum(liability_high) as high,
                   sum(medicaid_reimbursed) as paid
            from rpt_liability_summary group by all order by year, quarter, cat
        """),
        "labeler_quarterly": rows(con, f"""
            with top as (
                select labeler_name from rpt_liability_summary
                where labeler_name <> '(not in MDRP file)'
                group by 1 order by sum(liability_point) desc nulls last limit {TOP_LABELERS}
            )
            select labeler_name as labeler, year, quarter, rebate_category as cat,
                   sum(liability_point) as point, sum(liability_high) as high,
                   sum(medicaid_reimbursed) as paid
            from rpt_liability_summary join top using (labeler_name)
            group by all order by labeler, year, quarter, cat
        """),
        "states": rows(con, """
            select year, state, sum(liability_point) as point, sum(medicaid_reimbursed) as paid
            from rpt_liability_summary group by all order by year, point desc
        """),
        "products": rows(con, f"""
            select year, product_name as product, labeler_name as labeler,
                   rebate_category as cat, ndcs, liability_point as point,
                   medicaid_reimbursed as paid, rebate_to_reimbursed as ratio
            from rpt_product_liability
            qualify row_number() over (partition by year order by liability_point desc nulls last)
                <= {TOP_PRODUCTS}
            order by year, point desc
        """),
        "sensitivity": rows(con, """
            select year, quarters, amp_nadac_factor as factor, bp_discount as bp,
                   pre_nadac_excess_growth as growth, liability_point as point,
                   liability_high as high, is_base
            from rpt_sensitivity order by year, growth, factor, bp
        """),
        "validation": rows(con, "select * from rpt_validation_cms64"),
        "disputes": rows(con, """
            select year, reason_code as reason, count(*) as lines,
                   sum(dollars_at_stake) as dollars
            from fct_dispute_candidates group by all order by year, dollars desc nulls last
        """),
        "dispute_lines": rows(con, f"""
            select year, quarter, state, ndc, product_name as product, labeler_name as labeler,
                   reason_code as reason, reason_detail as detail, dollars_at_stake as dollars
            from fct_dispute_candidates
            qualify row_number() over (partition by year order by dollars_at_stake desc nulls last)
                <= {TOP_DISPUTES}
            order by year, dollars desc
        """),
    }


def build(warehouse: Path, out: Path) -> Path:
    con = duckdb.connect(str(warehouse), read_only=True)
    data = collect(con)
    con.close()
    template = (ROOT / "dashboard" / "index.html").read_text()
    payload = json.dumps(data, separators=(",", ":"), default=str).replace("</", "<\\/")
    out.mkdir(parents=True, exist_ok=True)
    page = out / "index.html"
    page.write_text(template.replace("/*__DATA__*/null", payload))
    print(f"{page}: {page.stat().st_size / 1e6:.1f} MB")
    return page


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    data_dir = Path(os.environ.get("GTN_DATA_DIR", ROOT / "data"))
    build(data_dir / "warehouse.duckdb", args.out)
