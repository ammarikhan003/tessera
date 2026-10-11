import geopandas as gpd
import pandas as pd
import pytest
import shapely
from shapely.geometry import box

from tessera import config, maps


def _grid(n: int = 3, size: float = 100.0) -> gpd.GeoDataFrame:
    """n x n square OAs in two 'boroughs' (left column vs the rest), EPSG:27700."""
    cells = [box(x * size, y * size, (x + 1) * size, (y + 1) * size) for x in range(n) for y in range(n)]
    lad = ["A" if i < n else "B" for i in range(n * n)]
    return gpd.GeoDataFrame(
        {"OA21CD": [f"E{i:03d}" for i in range(n * n)], "LAD22CD": lad, "LAD22NM": lad},
        geometry=cells,
        crs=config.ANALYSIS_CRS,
    )


def test_dissolve_gives_one_polygon_per_borough_without_holes() -> None:
    boroughs = maps.dissolve_boroughs(_grid())
    assert sorted(boroughs["LAD22CD"]) == ["A", "B"]
    assert maps.interior_rings(boroughs).empty
    assert boroughs.area.sum() == pytest.approx(9 * 100.0**2)


def test_interior_rings_reports_and_fill_removes_small_hole() -> None:
    oas = _grid()
    centre = oas["OA21CD"] == "E004"  # middle cell, in borough B
    oas.loc[centre, "geometry"] = oas.loc[centre, "geometry"].apply(lambda g: g.difference(box(140, 140, 142, 142)))
    holes = maps.interior_rings(maps.dissolve_boroughs(oas))
    assert len(holes) == 1
    assert holes["area_m2"].iloc[0] == pytest.approx(4.0)
    assert maps.interior_rings(maps.dissolve_boroughs(oas, fill_below_m2=10.0)).empty


def test_repair_overlaps_restores_valid_coverage() -> None:
    oas = _grid()
    first = oas["OA21CD"] == "E000"
    # Extra vertex on the shared edge bulges 3 mm into the right-hand neighbour (the source defect).
    oas.loc[first, "geometry"] = [shapely.Polygon([(0, 0), (100, 0), (100.003, 50), (100, 100), (0, 100)])]
    assert not maps.coverage_check(oas.geometry)[0]
    repaired, log = maps.repair_overlaps(oas.set_index("OA21CD").geometry)
    assert shapely.coverage_is_valid(repaired.to_numpy())
    assert len(log) == 1
    assert log["overlap_m2"].iloc[0] == pytest.approx(0.15)


def test_simplify_coverage_keeps_shared_edges_consistent() -> None:
    oas = _grid()
    # Add collinear vertices every 10 m so there is something to simplify away.
    oas["geometry"] = shapely.segmentize(oas.geometry.to_numpy(), 10)
    simple = maps.simplify_coverage(oas.geometry, 5.0)
    assert simple.count_coordinates().sum() < oas.count_coordinates().sum()
    assert shapely.coverage_is_valid(simple.to_numpy())
    assert simple.is_valid.all()
    assert simple.area.sum() == pytest.approx(oas.area.sum())


def test_choose_tolerance_prefers_largest_within_area_cap() -> None:
    sweep = pd.DataFrame(
        {
            "tolerance_m": [0.0, 5.0, 10.0],
            "invalid": [0, 0, 0],
            "empty": [0, 0, 0],
            "coverage_valid": [True, True, True],
            "max_area_change_pct": [0.0, 0.8, 30.0],
        }
    )
    assert maps.choose_tolerance(sweep, max_area_change_pct=1.0) == 5.0
    assert maps.choose_tolerance(sweep, max_area_change_pct=0.5) == 0.0


def test_write_geojson_is_wgs84(tmp_path) -> None:
    path = tmp_path / "out.geojson"
    maps.write_geojson(_grid().set_geometry(_grid().geometry.translate(530000, 180000)), path)
    back = gpd.read_file(path)
    assert back.crs.to_epsg() == config.EXPORT_CRS
    lon, lat = back.geometry.iloc[0].centroid.coords[0]
    assert -1 < lon < 1 and 51 < lat < 52  # central London
