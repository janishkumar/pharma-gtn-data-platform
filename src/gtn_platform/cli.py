"""`gtn` command line: ingest public data, build the dbt warehouse, write the report."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import httpx

from . import __version__, cpi
from .download import fetch, load_manifest, save_manifest
from .sources import DEFAULT_YEARS, SOURCES, resolve

CATALOG_URL = "https://data.medicaid.gov/api/1/metastore/schemas/dataset/items"
USER_AGENT = (
    f"pharma-gtn-data-platform/{__version__} "
    "(+https://github.com/janishkumar/pharma-gtn-data-platform)"
)
REPO_ROOT = Path(__file__).resolve().parents[2]
CPI_START_YEAR = 1990  # inflation baselines go back to 1990 Q3


def data_dir() -> Path:
    return Path(os.environ.get("GTN_DATA_DIR", REPO_ROOT / "data")).resolve()


def parse_years(text: str | None) -> set[int] | None:
    """'2016,2021-2023' -> {2016, 2021, 2022, 2023}."""
    if not text:
        return None
    years: set[int] = set()
    for part in text.split(","):
        first, _, last = part.strip().partition("-")
        years.update(range(int(first), int(last or first) + 1))
    return years


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(60, read=600),
        follow_redirects=True,
    )


def ingest(sources: list[str], years: set[int] | None) -> None:
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(root)
    with client() as http:
        if "cpi_u" in sources:
            rows = cpi.fetch_cpi_u(http, CPI_START_YEAR, date.today().year)
            cpi.write(rows, root)
            print(f"cpi_u: {len(rows)} months", flush=True)
        catalog = http.get(CATALOG_URL).raise_for_status().json()
        for name in sources:
            if name == "cpi_u":
                continue
            spec = SOURCES[name]
            wanted = years if years is not None else DEFAULT_YEARS.get(name)
            resources = resolve(catalog, spec, wanted)
            if not resources:
                raise SystemExit(f"{name}: no catalog entry matched {spec.title_regex!r}")
            for resource in resources:
                changed = fetch(http, resource, root, manifest)
                save_manifest(root, manifest)
                label = f"{name} {resource.year or ''}".strip()
                print(f"{label}: {'loaded' if changed else 'unchanged'}", flush=True)


def dbt(*args: str) -> None:
    env = {**os.environ, "GTN_DATA_DIR": str(data_dir())}
    project = REPO_ROOT / "dbt"
    cmd = ["dbt", *args, "--project-dir", str(project), "--profiles-dir", str(project)]
    subprocess.run(cmd, check=True, env=env)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gtn", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_ingest = sub.add_parser("ingest", help="download changed source files to data/raw")
    p_ingest.add_argument("--sources", default=",".join([*SOURCES, "cpi_u"]))
    p_ingest.add_argument("--years", help="e.g. 2016,2021-2026 (yearly sources only)")
    sub.add_parser("build", help="dbt seed + build (models and tests)")
    p_report = sub.add_parser("report", help="write reports/summary.md from the warehouse")
    p_report.add_argument("--out", default=str(REPO_ROOT / "reports"))
    args = parser.parse_args(argv)

    if args.command == "ingest":
        names = [s.strip() for s in args.sources.split(",") if s.strip()]
        unknown = set(names) - {*SOURCES, "cpi_u"}
        if unknown:
            parser.error(f"unknown sources: {sorted(unknown)}")
        ingest(names, parse_years(args.years))
    elif args.command == "build":
        dbt("build")
    elif args.command == "report":
        from .report import write_report

        write_report(data_dir() / "warehouse.duckdb", Path(args.out))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
