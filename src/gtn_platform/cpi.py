"""CPI-U (all items, US city average, not seasonally adjusted) from the BLS public API."""

from __future__ import annotations

from pathlib import Path

import duckdb
import httpx

SERIES = "CUUR0000SA0"
API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
MAX_YEARS_PER_CALL = 10  # BLS v1 limit for unregistered use


def year_windows(start: int, end: int) -> list[tuple[int, int]]:
    return [
        (y, min(y + MAX_YEARS_PER_CALL - 1, end)) for y in range(start, end + 1, MAX_YEARS_PER_CALL)
    ]


def parse(payload: dict) -> list[tuple[int, int, float]]:
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS request failed: {payload.get('message')}")
    rows = []
    for series in payload["Results"]["series"]:
        for point in series["data"]:
            period = point["period"]
            if not period.startswith("M") or period == "M13":  # M13 is the annual average
                continue
            if point["value"] == "-":  # month never published (October 2025 shutdown)
                continue
            rows.append((int(point["year"]), int(period[1:]), float(point["value"])))
    return rows


def fetch_cpi_u(client: httpx.Client, start: int, end: int) -> list[tuple[int, int, float]]:
    rows: list[tuple[int, int, float]] = []
    for first, last in year_windows(start, end):
        # GET ignores the year range and returns the last three years; POST honours it.
        response = client.post(
            API, json={"seriesid": [SERIES], "startyear": str(first), "endyear": str(last)}
        )
        response.raise_for_status()
        rows.extend(parse(response.json()))
    return sorted(set(rows))


def write(rows: list[tuple[int, int, float]], data_dir: Path) -> Path:
    out = data_dir / "raw" / "cpi_u" / "all.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("create table cpi (year integer, month integer, cpi_u double)")
    con.executemany("insert into cpi values (?, ?, ?)", rows)
    con.execute(f"copy cpi to '{out}' (format parquet)")
    con.close()
    return out
