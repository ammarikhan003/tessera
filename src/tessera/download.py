"""Download Census 2021 tables (Nomis), OA boundaries and lookup (ONS), LOAC (+ descriptions) and IMD 2025.

National raw files go to data/raw/ untouched; London subsets go to data/interim/.
Every download is recorded in data/raw/manifest.json (URL, bytes, SHA-256, UTC time).

Run with:  python -m tessera.download [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests

from tessera import config

log = logging.getLogger(__name__)

CHUNK_BYTES = 1 << 20
TIMEOUT_SECONDS = 120
LOOKUP_COLUMNS = ["OA21CD", "LSOA21CD", "LSOA21NM", "MSOA21CD", "MSOA21NM", "LAD22CD", "LAD22NM"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str, dest: Path, force: bool = False, session: requests.Session | None = None
) -> bool:
    """Stream url to dest. Returns True if downloaded, False if dest already existed."""
    if dest.exists() and not force:
        log.info("exists, skipping: %s", dest.name)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    http = session or requests.Session()
    log.info("downloading %s", url)
    with http.get(url, stream=True, timeout=TIMEOUT_SECONDS) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in resp.iter_content(CHUNK_BYTES):
                f.write(chunk)
    tmp.replace(dest)  # only a complete download ever gets the final name
    return True


def manifest_entry(path: Path, url: str, downloaded: bool, previous: dict[str, Any] | None) -> dict[str, Any]:
    """Describe a raw file. Keeps the original download time when the file was skipped."""
    if downloaded or previous is None:
        when = datetime.now(timezone.utc) if downloaded else datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        )
        downloaded_utc = when.isoformat(timespec="seconds")
    else:
        downloaded_utc = previous["downloaded_utc"]
    return {
        "url": url,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "downloaded_utc": downloaded_utc,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def oa_member_name(table: str) -> str:
    return f"census2021-{table}-oa.csv"


def extract_oa_csv(zip_path: Path, table: str, dest: Path) -> Path:
    """Extract only the output-area CSV from a Nomis bulk zip."""
    member = oa_member_name(table)
    with zipfile.ZipFile(zip_path) as zf:
        if member not in zf.namelist():
            raise FileNotFoundError(f"{member} not in {zip_path.name}: {zf.namelist()}")
        dest.write_bytes(zf.read(member))
    return dest


def london_lookup(lookup_path: Path, prefix: str = config.LONDON_LAD_PREFIX) -> pd.DataFrame:
    """OA -> LSOA -> MSOA -> LAD rows for London (LAD22CD starting with prefix)."""
    lookup = pd.read_csv(lookup_path, dtype=str, encoding="utf-8-sig")
    missing = set(LOOKUP_COLUMNS) - set(lookup.columns)
    if missing:
        raise ValueError(f"lookup is missing columns {sorted(missing)}")
    london = lookup.loc[lookup["LAD22CD"].str.startswith(prefix), LOOKUP_COLUMNS]
    return london.sort_values("OA21CD").reset_index(drop=True)


def filter_boundaries(boundaries_path: Path, london: pd.DataFrame) -> gpd.GeoDataFrame:
    """Keep London OAs from the national boundary file and attach borough codes."""
    gdf = gpd.read_file(boundaries_path)
    if gdf.crs is None or gdf.crs.to_epsg() != config.BNG_EPSG:
        raise ValueError(f"expected EPSG:{config.BNG_EPSG}, got {gdf.crs}")
    keep = gdf[gdf["OA21CD"].isin(london["OA21CD"])]
    return keep.merge(london[["OA21CD", "LAD22CD", "LAD22NM"]], on="OA21CD", how="left")


def fetch(url: str, dest: Path, manifest: dict[str, Any], force: bool) -> None:
    key = dest.relative_to(config.PROJECT_ROOT).as_posix()
    downloaded = download_file(url, dest, force=force)
    manifest[key] = manifest_entry(dest, url, downloaded, manifest.get(key))


def report(london: pd.DataFrame, boundaries: gpd.GeoDataFrame, loac: pd.DataFrame) -> None:
    """Print the counts later steps rely on, straight from the downloaded files."""
    print(f"London OAs in ONS lookup:        {london['OA21CD'].nunique():,}")
    print(f"London local authorities:        {london['LAD22CD'].nunique()}")
    print(f"London OA boundaries kept:       {len(boundaries):,}")
    print(f"LOAC rows / unique OAs:          {len(loac):,} / {loac['OA'].nunique():,}")
    print(f"LOAC distinct supergroups (SG):  {loac['SG'].nunique()}  {sorted(loac['SG'].unique())}")
    print(f"LOAC distinct groups (G):        {loac['G'].nunique()}  {sorted(loac['G'].unique())}")
    print(f"LOAC OAs not in London lookup:   {(~loac['OA'].isin(london['OA21CD'])).sum()}")


def main(force: bool = False) -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    config.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(config.MANIFEST_PATH)

    for table in config.CENSUS_TABLES:
        zip_path = config.census_zip_path(table)
        fetch(config.NOMIS_BULK_URL.format(table=table), zip_path, manifest, force)
        extract_oa_csv(zip_path, table, config.census_oa_csv_path(table))

    fetch(config.OA_LOOKUP_URL, config.OA_LOOKUP_RAW, manifest, force)
    fetch(config.OA_BOUNDARIES_URL, config.OA_BOUNDARIES_RAW, manifest, force)
    fetch(config.LOAC_LOOKUP_URL, config.LOAC_LOOKUP_RAW, manifest, force)
    fetch(config.LOAC_DESCRIPTIONS_URL, config.LOAC_DESCRIPTIONS_RAW, manifest, force)
    fetch(config.IMD_URL, config.IMD_RAW, manifest, force)
    save_manifest(manifest, config.MANIFEST_PATH)

    london = london_lookup(config.OA_LOOKUP_RAW)
    london.to_csv(config.OA_LOOKUP_LONDON, index=False)
    boundaries = filter_boundaries(config.OA_BOUNDARIES_RAW, london)
    boundaries.to_file(config.OA_BOUNDARIES_LONDON, driver="GPKG")

    loac = pd.read_csv(config.LOAC_LOOKUP_RAW, dtype=str, encoding="utf-8-sig")
    report(london, boundaries, loac)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main(force=parser.parse_args().force)
