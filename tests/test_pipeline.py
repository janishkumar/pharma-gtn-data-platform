"""End to end on the committed real-row fixtures: dbt build (models, data tests, unit tests),
then the report and the dashboard. No network."""

import importlib.util
import json
import shutil
from pathlib import Path

import duckdb
import pytest

from gtn_platform import cli
from gtn_platform.report import money, pct, write_report

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "raw"


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory, monkeypatch_module):
    data = tmp_path_factory.mktemp("data")
    shutil.copytree(FIXTURES, data / "raw")
    monkeypatch_module.setenv("GTN_DATA_DIR", str(data))
    monkeypatch_module.setenv("GTN_DUCKDB_MEMORY", "1GB")
    cli.main(["build"])  # raises CalledProcessError if any model or test fails
    return data / "warehouse.duckdb"


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


def query(warehouse, sql):
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_every_line_has_a_liability_row(warehouse):
    raw = query(warehouse, "select count(*) from stg_sdud")[0][0]
    fact = query(warehouse, "select count(*) from fct_rebate_liability")[0][0]
    assert raw == fact > 0


def test_generics_priced_from_ful_and_brands_from_nadac(warehouse):
    sources = dict(query(warehouse, """
        select rebate_category, mode(amp_source) from fct_rebate_liability
        where rebate_category in ('N', 'S') and year >= 2023 group by 1
    """))
    assert sources == {"N": "FUL", "S": "NADAC"}


def test_brand_inflation_penalty_present(warehouse):
    (penalised,) = query(warehouse, """
        select count(*) from int_ura
        where is_base and rebate_category = 'S' and penalty_pct > 0
    """)[0]
    assert penalised > 0


def test_ura_never_exceeds_amp_before_2024(warehouse):
    (over,) = query(warehouse, """
        select count(*) from int_ura
        where quarter_start < date '2024-01-01' and ura > amp * (1 + 1e-9)
    """)[0]
    assert over == 0


def test_point_never_exceeds_high(warehouse):
    (bad,) = query(warehouse, """
        select count(*) from fct_rebate_liability where liability_point > liability_high + 1e-6
    """)[0]
    assert bad == 0


def test_sensitivity_has_every_scenario_and_base_is_lowest_bp(warehouse):
    rows = query(warehouse, """
        select year, count(*), min(liability_point) filter (where bp_discount = 0
            and amp_nadac_factor = 1 and pre_nadac_excess_growth = 0),
            max(liability_point) filter (where is_base)
        from rpt_sensitivity group by 1 order by 1
    """)
    assert rows and all(n == 12 for _, n, _, _ in rows)
    assert all(a == b for _, _, a, b in rows)


def test_validation_row_for_2016(warehouse):
    ((year, gross, offset, ffs, total),) = query(warehouse, """
        select year, cms64_prescribed_drugs, cms64_national_rebate_offset,
               estimate_ffs_point, estimate_point
        from rpt_validation_cms64
    """)
    assert year == 2016 and gross > 1e10 and offset > 1e9 and 0 < ffs <= total


def test_report_and_dashboard(warehouse, tmp_path):
    path = write_report(warehouse, tmp_path)
    text = path.read_text()
    assert "## Sensitivity" in text and "## Validation against CMS-64" in text
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["latest_full_year"] in (2016, 2023, 2024)

    spec = importlib.util.spec_from_file_location("build_dashboard", ROOT / "scripts" /
                                                  "build_dashboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = module.build(warehouse, tmp_path / "site").read_text()
    assert "/*__DATA__*/" not in page and '"sensitivity":[' in page


def test_formatting():
    assert money(None) == "n/a" and money(1.5e9) == "$1.50B" and money(2.5e6) == "$2.5M"
    assert money(999) == "$999" and pct(0.1234) == "12.3%" and pct(None) == "n/a"
