import json

import duckdb
import httpx
import pytest

from gtn_platform import cpi
from gtn_platform.cli import parse_years
from gtn_platform.contracts import ContractError, check_header
from gtn_platform.download import fetch, load_manifest, parquet_path, save_manifest
from gtn_platform.sources import SDUD_COLUMNS, SOURCES, Resource, normalise_column, resolve

CATALOG = [
    {"title": "State Drug Utilization Data 2016", "modified": "a",
     "distribution": [{"downloadURL": "https://x/sdud2016.csv"}]},
    {"title": "State Drug Utilization Data 2025", "modified": "b",
     "distribution": [{"downloadURL": "https://x/sdud2025.csv"}]},
    {"title": "State Drug Utilization Data 1999", "modified": "c",
     "distribution": [{"downloadURL": "https://x/sdud1999.csv"}]},
    {"title": "ACA Federal Upper Limits", "modified": "d",
     "distribution": [{"downloadURL": "https://x/ful.csv"}]},
    {"title": "Something else 2025", "distribution": [{"downloadURL": "https://x/no.csv"}]},
]

SDUD_CSV = (
    "Utilization Type,State,NDC,Labeler Code,Product Code,Package Size,Year,Quarter,"
    "Suppression Used,Product Name,Units Reimbursed,Number of Prescriptions,"
    "Total Amount Reimbursed,Medicaid Amount Reimbursed,Non Medicaid Amount Reimbursed\n"
    "FFSU,AK,00002143380,00002,1433,80,2025,4,false,TRULICITY ,00000000226.000,000000113,"
    "000000106729.18,0000104889.56,0000001839.62\n"
    "MCOU,AK,00002143380,00002,1433,80,2025,4,true,TRULICITY ,,,,,\n"
)


def test_resolve_filters_years_newest_first():
    found = resolve(CATALOG, SOURCES["sdud"], {2016, 2025})
    assert [r.year for r in found] == [2025, 2016]
    assert found[0].url == "https://x/sdud2025.csv"


def test_resolve_single_file_source():
    (ful,) = resolve(CATALOG, SOURCES["ful"], None)
    assert ful.year is None and ful.url == "https://x/ful.csv"


def test_resolve_rejects_duplicate_single_file_source():
    with pytest.raises(ValueError):
        resolve(CATALOG + [CATALOG[3]], SOURCES["ful"], None)


def test_normalise_column_handles_old_and_new_nadac_headers():
    assert normalise_column("NADAC_Per_Unit") == normalise_column("NADAC Per Unit")
    assert normalise_column(" As of Date ") == "as_of_date"


def test_contract_names_missing_and_unexpected_columns():
    header = [c for c in SDUD_COLUMNS if c != "ndc"] + ["ndc_11"]
    with pytest.raises(ContractError, match=r"missing=\['ndc'\] unexpected=\['ndc_11'\]"):
        check_header(header, SDUD_COLUMNS, "sdud")


def test_contract_tolerates_added_columns():
    assert check_header([*SDUD_COLUMNS, "new_field"], SDUD_COLUMNS, "sdud")[-1] == "new_field"


def test_parse_years():
    assert parse_years("2016,2021-2023") == {2016, 2021, 2022, 2023}
    assert parse_years(None) is None


def _server(etag: str, calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        headers = {"etag": etag, "last-modified": "Mon, 13 Jul 2026 15:24:16 GMT"}
        body = SDUD_CSV.encode() if request.method == "GET" else b""
        return httpx.Response(200, headers=headers, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_skips_unchanged_and_reloads_reissued_file(tmp_path):
    resource = Resource("sdud", 2025, "https://x/sdud2025.csv", "")
    manifest: dict = {}
    calls: list[str] = []

    assert fetch(_server('"v1"', calls), resource, tmp_path, manifest) is True
    assert fetch(_server('"v1"', calls), resource, tmp_path, manifest) is False
    assert fetch(_server('"v2"', calls), resource, tmp_path, manifest) is True
    assert calls == ["HEAD", "GET", "HEAD", "HEAD", "GET"]

    save_manifest(tmp_path, manifest)
    saved = load_manifest(tmp_path)["sdud/2025"]
    assert saved["etag"] == '"v2"' and saved["rows"] == 2


def test_fetch_keeps_ndc_leading_zeros_and_empty_suppressed_values(tmp_path):
    resource = Resource("sdud", 2025, "https://x/sdud2025.csv", "")
    fetch(_server('"v1"', []), resource, tmp_path, {})
    rows = duckdb.sql(
        f"select ndc, units_reimbursed from '{parquet_path(tmp_path, resource)}' order by 2"
    ).fetchall()
    assert rows == [("00002143380", "00000000226.000"), ("00002143380", None)]


def test_fetch_rejects_changed_layout(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"etag": "x"}, content=b"NDC,Units\n1,2\n")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ContractError):
        fetch(http, Resource("sdud", 2025, "https://x/a.csv", ""), tmp_path, {})
    assert not parquet_path(tmp_path, Resource("sdud", 2025, "", "")).exists()


def test_cpi_windows_and_parse(tmp_path):
    assert cpi.year_windows(2013, 2026) == [(2013, 2022), (2023, 2026)]
    payload = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{"data": [
            {"year": "2026", "period": "M09", "value": "336.940"},
            {"year": "2025", "period": "M13", "value": "320.0"},
            {"year": "2025", "period": "M10", "value": "-"},
        ]}]},
    }
    assert cpi.parse(payload) == [(2026, 9, 336.94)]
    with pytest.raises(RuntimeError):
        cpi.parse({"status": "REQUEST_NOT_PROCESSED", "message": ["limit"]})


def test_fetch_cpi_u_calls_each_window(tmp_path):
    seen = []

    def handler(request):
        assert request.method == "POST"
        body = json.loads(request.content)
        seen.append(body)
        year = body["startyear"]
        return httpx.Response(200, content=json.dumps({
            "status": "REQUEST_SUCCEEDED",
            "Results": {"series": [{"data": [{"year": year, "period": "M01", "value": "1"}]}]},
        }))

    rows = cpi.fetch_cpi_u(httpx.Client(transport=httpx.MockTransport(handler)), 2013, 2026)
    assert [p["startyear"] for p in seen] == ["2013", "2023"]
    assert rows == [(2013, 1, 1.0), (2023, 1, 1.0)]
    out = cpi.write(rows, tmp_path)
    assert duckdb.sql(f"select count(*) from '{out}'").fetchone()[0] == 2


def test_cli_ingest_end_to_end_with_mocked_http(tmp_path, monkeypatch, capsys):
    from gtn_platform import cli

    catalog = [{"title": "State Drug Utilization Data 2025",
                "distribution": [{"downloadURL": "https://x/sdud2025.csv"}]}]

    def handler(request):
        if request.url.path.endswith("/items"):
            return httpx.Response(200, json=catalog)
        if "bls.gov" in request.url.host:
            return httpx.Response(200, json={"status": "REQUEST_SUCCEEDED", "Results": {
                "series": [{"data": [{"year": "2025", "period": "M01", "value": "320.0"}]}]}})
        body = SDUD_CSV.encode() if request.method == "GET" else b""
        return httpx.Response(200, headers={"etag": '"v1"'}, content=body)

    monkeypatch.setenv("GTN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    cli.main(["ingest", "--sources", "sdud,cpi_u", "--years", "2025"])
    cli.main(["ingest", "--sources", "sdud", "--years", "2025"])
    out = capsys.readouterr().out
    assert "sdud 2025: loaded" in out and "sdud 2025: unchanged" in out and "cpi_u: 1" in out
    assert load_manifest(tmp_path)["sdud/2025"]["rows"] == 2

    with pytest.raises(SystemExit):
        cli.main(["ingest", "--sources", "bogus"])
    with pytest.raises(SystemExit, match="no catalog entry"):
        cli.main(["ingest", "--sources", "ful"])
