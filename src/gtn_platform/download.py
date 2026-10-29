"""Conditional download of one catalog resource to all-varchar Parquet."""

from __future__ import annotations

import csv
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx

from .contracts import check_header
from .sources import SOURCES, Resource

MANIFEST = "manifest.json"


def load_manifest(data_dir: Path) -> dict:
    path = data_dir / MANIFEST
    return json.loads(path.read_text()) if path.exists() else {}


def save_manifest(data_dir: Path, manifest: dict) -> None:
    (data_dir / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def parquet_path(data_dir: Path, resource: Resource) -> Path:
    return data_dir / "raw" / resource.source / f"{resource.year or 'all'}.parquet"


def _key(resource: Resource) -> str:
    return f"{resource.source}/{resource.year or 'all'}"


def fetch(client: httpx.Client, resource: Resource, data_dir: Path, manifest: dict) -> bool:
    """Download `resource` unless the manifest shows the same file. Returns True if reloaded.

    The server's ETag and Last-Modified decide whether a file changed: CMS re-issues whole
    prior-year SDUD files, so a year already loaded can still need reloading.
    """
    out = parquet_path(data_dir, resource)
    head = client.head(resource.url)
    head.raise_for_status()
    stamp = {
        "url": resource.url,
        "etag": head.headers.get("etag", ""),
        "last_modified": head.headers.get("last-modified", ""),
    }
    previous = manifest.get(_key(resource), {})
    if out.exists() and all(previous.get(k) == v for k, v in stamp.items()):
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        csv_path = Path(tmp) / "download.csv"
        with client.stream("GET", resource.url) as response, csv_path.open("wb") as fh:
            response.raise_for_status()
            for chunk in response.iter_bytes(1 << 20):
                fh.write(chunk)
        rows = to_parquet(csv_path, out, resource.source)

    manifest[_key(resource)] = {
        **stamp,
        "rows": rows,
        "loaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return True


def to_parquet(csv_path: Path, out: Path, source: str) -> int:
    """Check the header contract, then write every column as text with normalised names.

    Keeping raw values as text preserves NDC leading zeros and CMS's zero-padded numbers;
    typing happens in dbt staging where it is tested.
    """
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        header = next(csv.reader(fh))
    names = check_header(header, SOURCES[source].columns, source)
    con = duckdb.connect()
    sql = (
        "create or replace table raw as select * from read_csv(?, header=true, all_varchar=true, "
        "names=?, quote='\"', escape='\"', strict_mode=false, parallel={})"
    )
    try:
        con.execute(sql.format("true"), [str(csv_path), names])
    except duckdb.NotImplementedException:
        # Some older NADAC files defeat the parallel reader; single-threaded reads them fine.
        con.execute(sql.format("false"), [str(csv_path), names])
    con.execute(f"copy raw to '{out}' (format parquet, compression zstd)")
    rows = con.execute("select count(*) from raw").fetchone()[0]
    con.close()
    return rows
