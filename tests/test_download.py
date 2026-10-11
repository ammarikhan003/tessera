"""Offline tests for download.py: no network, tiny synthetic files in tmp_path."""

import hashlib
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from tessera import download


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for i in range(0, len(self.payload), chunk_size):
            yield self.payload[i : i + chunk_size]


class FakeSession:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    def get(self, url: str, stream: bool, timeout: int) -> FakeResponse:
        self.calls += 1
        return FakeResponse(self.payload)


def test_download_file_writes_then_skips(tmp_path: Path) -> None:
    dest = tmp_path / "f.bin"
    session = FakeSession(b"abc" * 1000)
    assert download.download_file("http://x", dest, session=session) is True
    assert dest.read_bytes() == b"abc" * 1000
    assert not dest.with_name("f.bin.part").exists()
    assert download.download_file("http://x", dest, session=session) is False
    assert session.calls == 1


def test_manifest_entry_hash_and_kept_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"hello")
    entry = download.manifest_entry(path, "http://x", downloaded=False, previous={"downloaded_utc": "T0"})
    assert entry["sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert entry["bytes"] == 5
    assert entry["downloaded_utc"] == "T0"


def test_extract_oa_csv_picks_oa_member(tmp_path: Path) -> None:
    zip_path = tmp_path / "census2021-ts999.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("census2021-ts999-lsoa.csv", "lsoa")
        zf.writestr("census2021-ts999-oa.csv", "oa")
    out = download.extract_oa_csv(zip_path, "ts999", tmp_path / "out.csv")
    assert out.read_text() == "oa"


def test_extract_oa_csv_missing_member_raises(tmp_path: Path) -> None:
    zip_path = tmp_path / "z.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("census2021-ts999-lsoa.csv", "lsoa")
    with pytest.raises(FileNotFoundError):
        download.extract_oa_csv(zip_path, "ts999", tmp_path / "out.csv")


def _lookup_csv(tmp_path: Path) -> Path:
    rows = pd.DataFrame(
        {
            "OA21CD": ["E00000002", "E00000001", "E00099999", "W00000001"],
            "LSOA21CD": ["L1", "L1", "L2", "L3"],
            "LSOA21NM": ["a", "a", "b", "c"],
            "MSOA21CD": ["M1", "M1", "M2", "M3"],
            "MSOA21NM": ["a", "a", "b", "c"],
            "LAD22CD": ["E09000001", "E09000001", "E06000001", "W06000001"],
            "LAD22NM": ["City of London", "City of London", "Hartlepool", "Isle of Anglesey"],
            "ObjectId": ["1", "2", "3", "4"],
        }
    )
    path = tmp_path / "lookup.csv"
    rows.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def test_london_lookup_filters_and_sorts(tmp_path: Path) -> None:
    london = download.london_lookup(_lookup_csv(tmp_path))
    assert london["OA21CD"].tolist() == ["E00000001", "E00000002"]
    assert list(london.columns) == download.LOOKUP_COLUMNS


def test_filter_boundaries_keeps_london_and_adds_lad(tmp_path: Path) -> None:
    gdf = gpd.GeoDataFrame(
        {"OA21CD": ["E00000001", "E00000002", "E00099999"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(5, 5, 6, 6)],
        crs="EPSG:27700",
    )
    path = tmp_path / "b.gpkg"
    gdf.to_file(path, driver="GPKG")
    out = download.filter_boundaries(path, download.london_lookup(_lookup_csv(tmp_path)))
    assert sorted(out["OA21CD"]) == ["E00000001", "E00000002"]
    assert (out["LAD22CD"] == "E09000001").all()


def test_filter_boundaries_rejects_wrong_crs(tmp_path: Path) -> None:
    gdf = gpd.GeoDataFrame({"OA21CD": ["E00000001"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    path = tmp_path / "b.gpkg"
    gdf.to_file(path, driver="GPKG")
    with pytest.raises(ValueError, match="EPSG:27700"):
        download.filter_boundaries(path, download.london_lookup(_lookup_csv(tmp_path)))
